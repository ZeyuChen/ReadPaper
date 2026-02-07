import subprocess
import sys
import re
import time
import os

# Configuration
ARXIV_ID = "2602.02276"
ARXIV_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
WORK_DIR = os.path.abspath(f"workspace_{ARXIV_ID}")

def run_test():
    print(f"Running E2E test for {ARXIV_ID}...")
    
    # 1. Clean previous workspace if exists
    # if os.path.exists(WORK_DIR):
    #     import shutil
    #     shutil.rmtree(WORK_DIR)

    # 2. Run arxiv-translator
    cmd = [
        "arxiv-translator",
        ARXIV_URL,
        "--model", "flash"
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1 # Line buffered
    )

    # State tracking
    downloaded = False
    extracted = False
    translation_started = False
    files_translated = 0
    compilation_started = False
    pdf_generated = False
    
    start_time = time.time()
    
    try:
        for line in process.stdout:
            print(line, end='') # Echo output
            
            if "PROGRESS:DOWNLOADING" in line:
                downloaded = True
            if "PROGRESS:EXTRACTING" in line:
                extracted = True
            if "PROGRESS:TRANSLATING:0:0" in line:
                translation_started = True
            if "PROGRESS:TRANSLATING:" in line and "Translated" in line:
                files_translated += 1
            if "PROGRESS:COMPILING" in line:
                compilation_started = True
            if "SUCCESS: Generated" in line:
                pdf_generated = True
                
    except Exception as e:
        print(f"Test failed with exception: {e}")
        return False
        
    process.wait()
    
    print("\n--- Test Summary ---")
    print(f"Downloaded: {downloaded}")
    print(f"Extracted: {extracted}")
    print(f"Translation Started: {translation_started}")
    print(f"Files Translated: {files_translated}")
    print(f"Compilation Started: {compilation_started}")
    print(f"PDF Generated: {pdf_generated}")
    
    if process.returncode == 0 and pdf_generated:
        print(f"PASS: E2E test for {ARXIV_ID} completed successfully.")
        return True
    else:
        print(f"FAIL: E2E test for {ARXIV_ID} failed.")
        return False

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
