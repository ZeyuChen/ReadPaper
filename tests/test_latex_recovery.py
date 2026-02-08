
import os
import shutil
import pytest
from app.backend.arxiv_translator.compiler import compile_pdf
from app.backend.arxiv_translator.latex_fixer import LatexFixer
from dotenv import load_dotenv

# Load env for API key
load_dotenv()

@pytest.fixture
def workspace_setup(tmp_path):
    """Creates a temporary workspace with a broken LaTeX file."""
    work_dir = tmp_path / "workspace_recovery_test"
    work_dir.mkdir()
    
    source_dir = work_dir / "source"
    source_dir.mkdir()
    
    # Broken LaTeX: Missing \end{document} and has syntax error
    # Also has DeepDive-like content
    broken_tex = r"""
\documentclass{article}
\usepackage{amsmath}
\begin{document}
Hello World.
\section{Broken Section}
Here is a broken command: \undefinedcommand{foo}

\begin{quote}
\textbf{[AI DeepDive]} \textbf{Analysis} \\
Explanation goes here.
\end{quote}

% Missing end document
"""
    
    main_tex = source_dir / "main.tex"
    main_tex.write_text(broken_tex, encoding="utf-8")
    
    return source_dir, main_tex

def test_latex_compiler_failure(workspace_setup):
    """Verifies that compile_pdf fails for broken latex."""
    source_dir, main_tex = workspace_setup
    
    success, _ = compile_pdf(str(source_dir), str(main_tex))
    assert success is False, "Compiler should fail on broken LaTeX"

@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="Needs Gemini API Key")
def test_latex_fixer_recovery(workspace_setup):
    """
    End-to-End test:
    1. Compile (Fail)
    2. Fix using LatexFixer
    3. Compile (Success)
    """
    source_dir, main_tex = workspace_setup
    api_key = os.getenv("GEMINI_API_KEY")
    
    # 1. Compile (Expected Failure)
    success, error_log = compile_pdf(str(source_dir), str(main_tex))
    assert success is False

    
    # 2. Simulate capturing error log (In real app, we'd get this from compiler return)
    # For test, we can just say "Undefined control sequence" to guide the LLM
    error_log = r"Undefined control sequence \undefinedcommand ... Runaway argument? ... File ended while scanning use of ..."
    
    # 3. Running Fixer
    print("\n[TEST] Running LatexFixer...")
    fixer = LatexFixer(api_key)
    
    with open(main_tex, 'r', encoding='utf-8') as f:
        content = f.read()
        
    fixed_content = fixer.fix_latex(content, error_log)
    
    assert fixed_content != content, "Fixer should modify the content"
    assert "\\undefinedcommand" not in fixed_content, "Fixer should remove undefined command"
    assert "\\end{document}" in fixed_content, "Fixer should add missing end document"
    
    # 4. Overwrite and Retry Compile
    print("\n[TEST] Overwriting file with fixed content...")
    with open(main_tex, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
        
    print("\n[TEST] Retrying Compilation...")
    cwd = os.getcwd()
    try:
        success_retry, _ = compile_pdf(str(source_dir), str(main_tex))
    finally:
        os.chdir(cwd) # Safety reset if compiler changes dir
        
    assert success_retry is True, "Compilation should succeed after fix"
    
    # Verify PDF exists
    pdf_path = source_dir / "main.pdf"
    assert pdf_path.exists(), "PDF should be generated"
    print(f"\n[TEST] SUCCESS: Generated {pdf_path}")

if __name__ == "__main__":
    # Allow running directly
    import sys
    from pytest import ExitCode
    sys.exit(pytest.main(["-v", __file__]))
