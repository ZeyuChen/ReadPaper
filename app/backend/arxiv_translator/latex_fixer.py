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
        """
        logger.info("Attempting AI-based LaTeX repair...")
        
        # Construct input prompt
        # We might need to truncate error log if too long
        input_text = f"""
## ERROR LOG
{error_log[-2000:]}

## LATEX CONTENT
{latex_content}
"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.1, 
                ),
                contents=[input_text]
            )
            
            if response.text:
                return self._clean_output(response.text)
            else:
                logger.error("LatexFixer returned empty response.")
                return latex_content # Fallback to original
                
        except Exception as e:
            logger.error(f"LatexFixer failed: {e}")
            return latex_content

    def _clean_output(self, text: str) -> str:
        # Remove markdown code fences if present
        import re
        pattern = r"^```(?:latex)?\s*(.*?)\s*```$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        return text
