import subprocess
import os
import sys
import time

# Configuration
ARXIV_ID = "1706.03762" # Attention Is All You Need (Classic, but maybe large? Let's use a smaller one if possible, or just this one as it's standard)
# Better: "2312.12456" (Random recent one?) 
# Let's use the one from the user's example in README or prompt if available. 
# The user mentioned 2602.04705. Let's try that one or a known short one. 
# 1706.03762 is fine, everyone uses it.
ARXIV_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
MODEL = "flash"
ENV_NAME = "readpaper"

def run_test():
    print(f"Testing translation for {ARXIV_ID} with model {MODEL}...")
    
    # Ensure raw output directory exists
    working_dir = os.path.abspath(f"test_workspace_{ARXIV_ID}")
    os.makedirs(working_dir, exist_ok=True)
    
    print(f"Working directory: {working_dir}")

    # path to micromamba env python or bin? 
    # We are running this script FROM the active environment or using `micromamba run`
    # The command inside subprocess should also be correct.
    
    cmd = [
        "arxiv-translator",
        ARXIV_URL,
        "--model", MODEL
    ]
    
    print(f"Executing command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        print("--- Process Started ---")
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                line = line.strip()
                print(f"[STDOUT] {line}")
                if line.startswith("PROGRESS:"):
                    print(f"--> DETECTED PROGRESS: {line}")

        return_code = process.poll()
        print(f"--- Process Finished with code {return_code} ---")
        
        if return_code != 0:
            stderr = process.stderr.read()
            print(f"[STDERR]\n{stderr}")
        else:
            print("SUCCESS")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    run_test()
