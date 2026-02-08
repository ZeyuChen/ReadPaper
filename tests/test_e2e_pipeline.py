
import os
import shutil
import pytest
from unittest.mock import patch, MagicMock
from app.backend.arxiv_translator.main import main
import sys

@pytest.fixture
def mock_workspace(tmp_path):
    """Creates a fake workspace with a sample .tex file."""
    # We need to mock the download/extract headers
    ws = tmp_path / "workspace_2401.00000"
    ws.mkdir()
    
    src = ws / "source"
    src.mkdir()
    
    main_tex = src / "main.tex"
    main_tex.write_text(r"""
\documentclass{article}
\begin{document}
Hello World
\end{document}
""", encoding="utf-8")
    
    return str(tmp_path)

class SynchronousExecutor:
    """
    Dummy executor that runs tasks synchronously in the main thread/process.
    This allows mocks to record calls correctly.
    """
    def __init__(self, max_workers=None):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def submit(self, fn, *args, **kwargs):
        return SynchronousFuture(fn(*args, **kwargs))

class SynchronousFuture:
    def __init__(self, result):
        self._result = result
    def result(self):
        return self._result

@patch("app.backend.arxiv_translator.main.download_source")
@patch("app.backend.arxiv_translator.main.extract_source")
@patch("app.backend.arxiv_translator.main.GeminiTranslator")
@patch("app.backend.arxiv_translator.main.DeepDiveAnalyzer")
@patch("app.backend.arxiv_translator.main.compile_pdf")
@patch("app.backend.arxiv_translator.main.clean_latex_directory")
@patch("concurrent.futures.ProcessPoolExecutor") 
@patch("concurrent.futures.as_completed")
def test_e2e_pipeline_mocked(mock_as_completed, mock_executor, mock_clean, mock_compile, mock_deepdive, mock_translator, mock_extract, mock_download, mock_workspace):
    """
    Verifies the main entry point logic without external calls.
    """
    # Setup Executor Mock to use our SynchronousExecutor
    mock_executor.side_effect = SynchronousExecutor
    
    # Setup as_completed to just return the futures as keys of the dict passed or just the list
    def side_effect_as_completed(fs):
        return list(fs)
    mock_as_completed.side_effect = side_effect_as_completed

    # Setup Mocks
    mock_download.return_value = os.path.join(mock_workspace, "workspace_2401.00000", "2401.00000.tar.gz")
    mock_clean.return_value = 1
    
    def side_effect_compile(source_dir, main_tex):
        # Create a dummy PDF to satisfy os.path.exists check in main
        pdf_path = os.path.join(source_dir, os.path.basename(main_tex).replace(".tex", ".pdf"))
        with open(pdf_path, "w") as f:
            f.write("%PDF-1.4 dummy")
        return (True, "Success Log")
        
    mock_compile.side_effect = side_effect_compile
    
    # Mock Translator Instance
    translator_instance = mock_translator.return_value
    translator_instance.translate_latex.return_value = r"\documentclass{article}\begin{document}Translated\end{document}"
    
    # Mock DeepDive Instance
    deepdive_instance = mock_deepdive.return_value
    deepdive_instance.analyze_latex.return_value = r"\documentclass{article}\begin{document}Analyzed\end{document}"

    # Prepare Args
    test_args = ["arxiv-translator", "https://arxiv.org/abs/2401.00000", "--deepdive", "--output", "final.pdf", "--keep"]
    
    with patch.object(sys, 'argv', test_args):
        # We need to be careful about CWD. main() changes CWD or expects CWD?
        # main() creates workspace_{id} in current dir.
        # We should run this in the temp dir.
        cwd = os.getcwd()
        os.chdir(mock_workspace)
        try:
            main()
        finally:
            os.chdir(cwd)
            
    # Verifications
    mock_download.assert_called_once()
    mock_extract.assert_not_called() # Source exists, so extraction skipped
    mock_clean.assert_called_once()
    
    # Check Translator called
    assert translator_instance.translate_latex.called
    
    # Check DeepDive called
    assert deepdive_instance.analyze_latex.called
    
    # Check Compile called
    mock_compile.assert_called()
    
    # Verify Final PDF exists (copied from dummy)
    final_pdf_path = os.path.join(mock_workspace, "final.pdf")
    assert os.path.exists(final_pdf_path), "Final PDF should be created"

