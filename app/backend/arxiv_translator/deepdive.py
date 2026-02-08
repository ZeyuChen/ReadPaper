from google import genai
from google.genai import types
import os
import re
import time
from .logging_utils import logger

class DeepDiveAnalyzer:
    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        # Use Flash model as requested for stability and speed
        self.model_name = model_name
        self.client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1beta', 'timeout': 600000})
        
        # Load Prompt
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "deepdive_prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            # Fallback simple prompt
            self.system_prompt = "Analyze the technical content and insert explanation boxes in Chinese using tcolorbox for DeepDive."

    def analyze_latex(self, latex_content: str, filename: str) -> str:
        """
        Analyzes the LaTeX content and injects DeepDive reading blocks.
        """
        # Heuristic filtering: Only process files that likely contain technical depth
        # Skip standard boilerplate files
        if filename in ["main.tex", "references.tex", "appendix.tex", "math_commands.tex"]:
            # main.tex might have content, but often just includes. 
            # If it's short, skip.
            if len(latex_content) < 500: 
                return latex_content

        # Simple keyword check to avoid wasting tokens on non-technical files
        # Keywords: method, algorithm, equation, theorem, proof, architecture, layer, loss
        keywords = ["method", "algorithm", "equation", "theorem", "proof", "architecture", "layer", "loss", "model", "training"]
        if not any(k in latex_content.lower() for k in keywords):
            return latex_content

        # Limit file size to avoid timeout/cost issues
        if len(latex_content) > 131072:
            logger.info(f"Skipping {filename} (File too large for single-pass analysis).")
            return latex_content
            
        # Always use chunking for stability and partial progress
        return self._analyze_chunked(latex_content, filename)

    def _analyze_chunked(self, content: str, filename: str, chunk_size=300) -> str:
        """
        Splits content into chunks and analyzes them using streaming.
        Uses a larger chunk size (e.g., 300 lines) to provide sufficient context for DeepDive.
        """
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        
        for line in lines:
            current_chunk.append(line)
            if len(current_chunk) >= chunk_size:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
            
        analyzed_chunks = []
        logger.info(f"Split {filename} into {len(chunks)} chunks for DeepDive analysis.")
        
        for i, chunk in enumerate(chunks):
            logger.info(f"DeepDive analyzing chunk {i+1}/{len(chunks)} of {filename}...")
            try:
                # Use streaming to keep connection alive
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.2, 
                    ),
                    contents=[chunk]
                )
                
                full_text = ""
                for chunk_resp in response_stream:
                    if chunk_resp.text:
                        full_text += chunk_resp.text
                
                if full_text:
                    cleaned = self._clean_output(full_text)
                    analyzed_chunks.append(cleaned)
                else:
                    logger.warning(f"Chunk {i+1} returned empty response. Keeping original.")
                    analyzed_chunks.append(chunk)

            except Exception as e:
                logger.error(f"DeepDive analysis failed for chunk {i+1} of {filename}: {e}")
                analyzed_chunks.append(chunk) # Fallback to original
                
        return '\n'.join(analyzed_chunks)

    def _clean_output(self, text: str) -> str:
        # Remove markdown code fences if present
        pattern = r"^```(?:latex)?\s*(.*?)\s*```$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        return text
