import os
import subprocess
import sys
import argparse

def test_e2e(arxiv_id="2510.26692"):
    print(f"Running E2E test for {arxiv_id}...")
    
    # Ensure env vars
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not set.")
        sys.exit(1)

    cmd = [
        "arxiv-translator",
        f"https://arxiv.org/abs/{arxiv_id}",
        "--model", "flash"
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    
    # Run and capture output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    found_progress = False
    found_success = False
    
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            print(line.strip())
            if "PROGRESS:TRANSLATING:" in line:
                found_progress = True
            if "SUCCESS: Generated" in line:
                found_success = True
                
    rc = process.poll()
    
    if rc != 0:
        print(f"FAIL: Process exited with code {rc}")
        sys.exit(rc)
        
    if not found_progress:
        print("FAIL: No progress messages detected.")
        sys.exit(1)
        
    if not found_success:
        print("FAIL: PDF generation success message not found.")
        sys.exit(1)
        
    print(f"PASS: E2E test for {arxiv_id} completed successfully.")

if __name__ == "__main__":
    test_e2e()
