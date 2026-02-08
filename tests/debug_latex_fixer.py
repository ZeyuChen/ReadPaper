
import os
import sys
import logging
from app.backend.arxiv_translator.latex_fixer import LatexFixer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fixer():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY")
        sys.exit(1)
        
    # Path to file
    tex_path = "workspace_2602.04705/source_zh/colm2024_conference.tex" 
    # Or find it properly
    if not os.path.exists(tex_path):
        print(f"File not found: {tex_path}")
        sys.exit(1)
        
    with open(tex_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    error_log = "Dummy Error Log: File `colm2024_conference.sty' not found."
    
    print(f"Content length: {len(content)}")
    print(f"Error log length: {len(error_log)}")
    
    fixer = LatexFixer(api_key, model_name="gemini-3-flash-preview")
    
    try:
        fixed = fixer.fix_latex(content, error_log)
        print("Fix successful.")
        print("Fixed content preview:", fixed[:100])
    except Exception as e:
        print(f"Fixer failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fixer()
