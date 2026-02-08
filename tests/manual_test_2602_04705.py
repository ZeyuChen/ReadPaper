
import sys
import os
import subprocess
import shutil

def test_deepseek_r1_pdf_generation():
    arxiv_id = "2602.04705"
    url = f"https://arxiv.org/abs/{arxiv_id}"
    
    # Setup Paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    work_dir = os.path.join(base_dir, f"workspace_{arxiv_id}")
    
    # Clean previous run
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
        
    print(f"Running translation for {url} in {base_dir}...")
    
    # Run the translator module
    cmd = [
        sys.executable, "-m", "app.backend.arxiv_translator.main",
        url,
        "--model", "flash"
    ]
    
    # Set env vars
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = base_dir + os.pathsep + env.get("PYTHONPATH", "")
    
    # Run
    # Warning: This is a long running process (real translation)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=base_dir)
    
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    
    if result.returncode != 0:
        print(f"Process failed with return code {result.returncode}")
        sys.exit(1)
        
    # Check for PDF
    pdf_found = False
    found_files = []
    
    if os.path.exists(work_dir):
        for root, dirs, files in os.walk(work_dir):
            for f in files:
                found_files.append(f)
                if f.endswith(".pdf"):
                    print(f"Found PDF: {f}")
                    if "_zh" in f:
                        pdf_found = True
    
    print(f"Files in workspace: {found_files}")
    
    if pdf_found:
        print("SUCCESS: PDF was generated.")
    else:
        print("FAILURE: PDF not found.")
        sys.exit(1)

if __name__ == "__main__":
    test_deepseek_r1_pdf_generation()
