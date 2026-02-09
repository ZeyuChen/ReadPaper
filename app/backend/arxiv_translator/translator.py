from google import genai
from google.genai import types
import os
import re
import time
from .logging_utils import logger

class GeminiTranslator:
    """
    Handles the translation of LaTeX content using the Google Gemini API.
    
    This class manages the API client, system prompts, and implements robust
    chunking strategies to handle large LaTeX documents while preserving structure.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"): 
        self.api_key = api_key
        # Default to Gemini 3 Flash Preview as per docs
        self.model_name = model_name
        self.client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1beta', 'timeout': 600000})

        # Load Prompt
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "translation_prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            # Fallback (should not happen if file exists)
            logger.warning(f"Translation prompt not found at {prompt_path}, using fallback.")
            self.system_prompt = "You are a professional academic translator. Translate LaTeX from English to Chinese, preserving all commands."

    @property
    def _system_prompt(self) -> str:
        return self.system_prompt

    def translate_latex(self, latex_content: str) -> str:
        """
        Translates a full LaTeX document or segment from English to Chinese.
        
        Args:
            latex_content: The raw LaTeX string to translate.
            
        Returns:
            The translated LaTeX string with structure preserved.
        """
        # Always use chunking to ensure stability and partial progress
        # This handles both small and large files uniformly using the robust streaming approach
        return self._translate_chunked(latex_content)

    def _translate_chunked(self, content: str, chunk_size=150) -> str:
        """
        Splits content into manageable chunks and translates them sequentially.
        
        Why Chunking?
        1. Context Window: Prevents exceeding the model's output token limit.
        2. Stability: Smaller chunks are less likely to result in generation errors or timeouts.
        3. Recovery: Allows for partial success (though current implementation assumes all pass).
        
        Args:
            content: The text to split.
            chunk_size: Approximate number of lines per chunk.
        """
        # Chunking Strategy 2.0: Paragraph-aware splitting
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in lines:
            current_chunk.append(line)
            current_size += 1
            
            # Check for split condition:
            # 1. Size exceeds threshold
            # 2. current line is empty (paragraph break) OR strict threshold reached (force split to avoid OOM)
            is_empty = (line.strip() == "")
            
            if (current_size >= chunk_size and is_empty) or (current_size >= chunk_size * 2):
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
                
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
            
        translated_chunks = []
        logger.info(f"Split content into {len(chunks)} chunks for translation (Paragraph-aware).")
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Translating chunk {i+1}/{len(chunks)}...")
            try:
                # Use streaming to keep connection alive and reduce timeouts
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self._system_prompt,
                        temperature=0.1, 
                    ),
                    contents=[chunk]
                )
                
                full_text = ""
                for chunk_resp in response_stream:
                    if chunk_resp.text:
                        full_text += chunk_resp.text
                
                if full_text:
                    cleaned = self._clean_output(full_text)
                    translated_chunks.append(cleaned)
                else:
                    # Fallback
                    logger.warning(f"Chunk {i+1} returned empty response. Using fallback.")
                    cleaned_fallback = self._clean_output(chunk)
                    translated_chunks.append(cleaned_fallback)
                    
            except Exception as e:
                logger.error(f"Chunk {i+1} failed: {e}")
                cleaned_fallback = self._clean_output(chunk)
                translated_chunks.append(cleaned_fallback)
            
            if "pro" in self.model_name.lower():
                time.sleep(2)
                
        return '\n'.join(translated_chunks)

    def _clean_output(self, text: str) -> str:
        # Remove ```latex ... ``` or ``` ... ```
        pattern = r"^```(?:latex)?\s*(.*?)\s*```$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            text = match.group(1)
            
        # Remove LaTeX comment lines (lines starting with %)
        # This reduces token usage for subsequent steps (DeepDive) and reduces interference
        lines = text.splitlines()
        # Keep lines that are NOT comments (ignoring leading whitespace)
        # We perform this post-processing to ensure clean input for DeepDive
        cleaned_lines = [line for line in lines if not line.strip().startswith('%')]
        
        return '\n'.join(cleaned_lines)
