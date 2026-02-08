import logging
import os
import shutil
import sys
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.backend.arxiv_translator.main import main
from unittest.mock import patch

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_deepdive_suffix():
    paper_id = "2505.09388"
    expected_pdf = f"{paper_id}_zh_deepdive.pdf"
    
    # Clean up previous runs
    if os.path.exists(expected_pdf):
        os.remove(expected_pdf)
        
    logger.info(f"Testing DeepDive suffix for {paper_id}...")
    
    # Simulate command line arguments
    test_args = [
        "arxiv-translator",
        f"https://arxiv.org/abs/{paper_id}",
        "--deepdive",
        "--model", "flash" # Force flash to ensure default or explicit works
    ]
    
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            if e.code != 0:
                logger.error("Main exited with error")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Main failed: {e}")
            sys.exit(1)
            
    # Check if PDF exists and has correct name
    # The script outputs to current dir if no -o is specified? 
    # Let's check main.py logic. 
    # It copies to `f"{arxiv_id}{suffix}.pdf"` in CWD.
    
    if os.path.exists(expected_pdf):
        logger.info(f"SUCCESS: Found {expected_pdf}")
        sys.exit(0)
    else:
        logger.error(f"FAILURE: {expected_pdf} not found.")
        # Check if other PDFs were generated
        for f in os.listdir("."):
            if f.endswith(".pdf") and paper_id in f:
                logger.error(f"Found unexpected PDF: {f}")
        sys.exit(1)

if __name__ == "__main__":
    test_deepdive_suffix()
