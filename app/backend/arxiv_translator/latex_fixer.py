import os
import logging
from google import genai
from google.genai import types
from .logging_utils import logger

class LatexFixer:
    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        # Use Flash for speed in recovery
        self.model_name = "gemini-3-flash-preview" 
        self.client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1beta', 'timeout': 600000})
        
        # Load prompt
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "latex_fix_prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are a LaTeX expert. Fix the following LaTeX code to make it compile. Delete problematic parts if necessary."

    def fix_latex(self, latex_content: str, error_log: str) -> str:
        """
        Attempts to fix the LaTeX content based on the error log using Gemini.
        Retries up to 3 times on failure.
        """
        logger.info("Attempting AI-based LaTeX repair...")
        
        # Construct input prompt
        # Truncate error log to last 3000 chars to ensure we fit in context context (though 3k is small)
        truncated_log = error_log[-3000:]
        
        input_text = f"""
## ERROR LOG
{truncated_log}

## LATEX CONTENT
{latex_content}
"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"AI Repair Attempt {attempt + 1}/{max_retries}")
                
                # Explicitly disable tools to prevent any function calling overhead/confusion
                # Use streaming to align with other robust components
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.1,
                    ),
                    contents=[input_text]
                )
                
                full_text = ""
                for chunk in response_stream:
                    if chunk.text:
                        full_text += chunk.text
                
                if full_text:
                    return self._clean_output(full_text)
                else:
                    logger.warning(f"LatexFixer returned empty response on attempt {attempt + 1}.")
                    
            except Exception as e:
                logger.error(f"LatexFixer failed attempt {attempt + 1}: {e}")
                import time
                time.sleep(1 * (attempt + 1)) # Backoff
        
        logger.error("LatexFixer failed after all retries.")
        return latex_content # Fallback to original

    def _clean_output(self, text: str) -> str:
        # Remove markdown code fences if present
        import re
        pattern = r"^```(?:latex)?\s*(.*?)\s*```$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        return text
