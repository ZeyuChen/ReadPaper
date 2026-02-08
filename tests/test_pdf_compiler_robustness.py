import pytest
import subprocess
import os
import sys

# List of papers from tests/e2e
# We exclude the prefix "test_" and suffix ".py" to get IDs
# But some filenames might be slightly different, so let's list them explicitly based on the `ls` output.
# 2310.06825
# 2401.04088
# 2403.05530
# 2403.09611
# 2407.21783
# 2408.00118
# 2412.02612
# 2412.15115
# 2412.19437
# 2501.08313
# 2501.12948
# 2504.07491
# 2506.13585
# 2507.20534
# 2602.04705

PAPERS = [
    "2407.21783",
    "2408.00118",
    "2412.02612",
    "2412.15115",
    "2412.19437",
    "2501.08313",
    "2501.12948",
    "2504.07491",
    "2506.13585",
    "2507.20534",
    "2602.04705"
]

@pytest.mark.parametrize("arxiv_id", PAPERS)
def test_pdf_compilation_robustness(arxiv_id):
    """
    Runs the arxiv-translator on the given paper and asserts that the PDF is generated.
    This serves as a robustness test for the compiler and post-processing logic.
    """
    print(f"\nTesting PDF Compilation for {arxiv_id}...")
    
    # Construct command
    # We use -m app.backend.arxiv_translator.main to avoid relative import issues
    # We assume the CWD is the project root (ReadPaper)
    
    cmd = [
        sys.executable, "-m", "app.backend.arxiv_translator.main",
        f"https://arxiv.org/abs/{arxiv_id}",
        "--model", "flash",
        "--keep" # Keep intermediate files for debugging
    ]
    
    # Ensure PYTHONPATH includes current directory
    env = os.environ.copy()
    if "PYTHONPATH" not in env:
        env["PYTHONPATH"] = os.getcwd()
    else:
        env["PYTHONPATH"] = os.getcwd() + os.pathsep + env["PYTHONPATH"]
        
    # Run the translator
    # We verify success by checking the return code AND the existence of the PDF
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=1200 # 20 minutes timeout per paper (compilation can be slow)
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"Translation/Compilation timed out for {arxiv_id}")

    # Check for success message or return code
    # main.py sys.exits(0) on success usually? No, it doesn't explicitly exit 0 on success logic, just falls through.
    # But it might exit 1 on error.
    
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        pytest.fail(f"Translator failed with return code {result.returncode}")
        
    # Verify PDF existence
    # Logic from main.py:
    # final_pdf = f"{arxiv_id}{suffix}.pdf"
    # suffix = "_zh_flash" for flash model
    expected_pdf = f"{arxiv_id}_zh_flash.pdf"
    
    if not os.path.exists(expected_pdf):
        # Check if it was generated but not copied?
        # main.py says: compiled_pdf = os.path.join(source_zh_dir, pdf_name)
        # then shutil.copy(compiled_pdf, final_pdf)
        
        # Let's inspect stdout to see what happened
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        pytest.fail(f"PDF {expected_pdf} was not generated.")
        
    # Verify PDF size
    if os.path.getsize(expected_pdf) < 1000:
        pytest.fail(f"PDF {expected_pdf} is too small (likely corrupted)")
        
    print(f"SUCCESS: {expected_pdf} created.")
