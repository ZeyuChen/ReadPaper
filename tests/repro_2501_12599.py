
import sys
import os
import logging
# Add project root to sys.path
sys.path.append(os.getcwd())

from app.backend.arxiv_translator.compiler import compile_pdf
from app.backend.arxiv_translator.post_process import apply_post_processing

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def repro():
    # Use absolute path to the existing workspace
    source_dir = "/home/zeyuc/ReadPaper/paper_storage/2501.12599/workspace_2501.12599/source_zh"
    main_tex = "template.tex" 
    
    print(f"Repro: processing {main_tex} in {source_dir}")
    
    # 1. Post-processing
    print("Running post-processing...")
    try:
        main_tex_path = os.path.join(source_dir, main_tex)
        apply_post_processing(source_dir, main_tex_path)
    except Exception as e:
        print(f"Post-processing failed: {e}")
    
    # 2. Compilation
    print("Running compilation...")
    success = compile_pdf(source_dir, main_tex)
    
    if success:
        print("Compilation SUCCESS")
    else:
        print("Compilation FAILED")

if __name__ == "__main__":
    repro()
