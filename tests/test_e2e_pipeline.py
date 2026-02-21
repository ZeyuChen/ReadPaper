
import os
import shutil
import pytest
from unittest.mock import patch, MagicMock
from app.backend.arxiv_translator.main import main
import sys

@pytest.fixture
def mock_workspace(tmp_path):
    """Creates a fake workspace with a sample .tex file."""
    ws = tmp_path / "workspace_2401.00000"
    ws.mkdir()

    src = ws / "source"
    src.mkdir()

    main_tex = src / "main.tex"
    main_tex.write_text(r"""
\documentclass{article}
\begin{document}
Hello World. This is a test sentence that is long enough to be translatable.
\end{document}
""", encoding="utf-8")

    return str(tmp_path)


class SynchronousExecutor:
    """Dummy executor that runs tasks synchronously (allows mocks to work)."""
    def __init__(self, max_workers=None):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def submit(self, fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            result = e
        return SynchronousFuture(result)


class SynchronousFuture:
    def __init__(self, result):
        self._result = result
    def result(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@patch("app.backend.arxiv_translator.main.download_source")
@patch("app.backend.arxiv_translator.main.extract_source")
@patch("app.backend.arxiv_translator.main.GeminiTranslator")
@patch("app.backend.arxiv_translator.main.DeepDiveAnalyzer")
@patch("app.backend.arxiv_translator.main.compile_pdf")
@patch("app.backend.arxiv_translator.main.compile_with_fix_loop")
@patch("app.backend.arxiv_translator.main.clean_latex_directory")
@patch("app.backend.arxiv_translator.main.PaperAnalyzer")
@patch("concurrent.futures.ProcessPoolExecutor")
@patch("concurrent.futures.as_completed")
def test_e2e_pipeline_mocked(
    mock_as_completed, mock_executor, mock_analyzer_cls,
    mock_clean, mock_compile_with_fix_loop, mock_compile_pdf,
    mock_deepdive, mock_translator,
    mock_extract, mock_download, mock_workspace
):
    """
    Tests the main() pipeline from start to finish with mostly mocked I/O endpoints.
    
    NOTE: compile_pdf is used for pre-flight, and compile_with_fix_loop is used for final compilation.
    """
    # ── Override argv ────────────────────────────────────────────────────────
    sys.argv = [
        "arxiv-translator",
        "https://arxiv.org/abs/2401.00000",
        "--deepdive",
        "--output", "final.pdf",
        "--keep",
    ]

    # ── Mocks Setup ──────────────────────────────────────────────────────────
    mock_executor.side_effect = SynchronousExecutor

    def side_effect_as_completed(fs):
        return list(fs)
    mock_as_completed.side_effect = side_effect_as_completed

    # ── Download / Extract ───────────────────────────────────────────────────
    mock_download.return_value = os.path.join(
        mock_workspace, "workspace_2401.00000", "2401.00000.tar.gz"
    )
    mock_clean.return_value = 1

    # ── PaperAnalyzer: return a mock structure ───────────────────────────────
    source_zh_dir_placeholder = os.path.join(
        mock_workspace, "workspace_2401.00000", "source_zh"
    )
    mock_structure = MagicMock()
    mock_structure.main_tex = os.path.join(source_zh_dir_placeholder, "main.tex")
    mock_structure.translatable_files.return_value = [
        os.path.join(source_zh_dir_placeholder, "main.tex")
    ]
    mock_structure.skip_files.return_value = []
    analyzer_instance = mock_analyzer_cls.return_value
    analyzer_instance.analyze.return_value = mock_structure

    # ── compile_pdf and compile_with_fix_loop ────────────────────────────────
    # Pre-flight compile
    mock_compile_pdf.return_value = (True, "")

    def side_effect_compile_with_fix_loop(source_dir, main_tex, **kwargs):
        # Final compile — create the PDF output so main() can find & copy it
        pdf_path = os.path.join(source_dir, os.path.basename(main_tex).replace(".tex", ".pdf"))
        os.makedirs(source_dir, exist_ok=True)
        with open(pdf_path, "w") as f:
            f.write("%PDF-1.4 dummy")
        return (True, "")

    mock_compile_with_fix_loop.side_effect = side_effect_compile_with_fix_loop

    # ── Translator ───────────────────────────────────────────────────────────
    translator_instance = mock_translator.return_value
    translator_instance.translate_text_nodes.return_value = []

    # ── DeepDive ─────────────────────────────────────────────────────────────
    deepdive_instance = mock_deepdive.return_value
    deepdive_instance.analyze_latex.return_value = (
        r"\documentclass{article}\begin{document}Analyzed\end{document}"
    )

    # ── Run ──────────────────────────────────────────────────────────────────
    test_args = [
        "arxiv-translator",
        "https://arxiv.org/abs/2401.00000",
        "--deepdive",
        "--output", "final.pdf",
        "--keep",
    ]
    
    with patch.object(sys, "argv", test_args):
        main()

    # ── Assertions ───────────────────────────────────────────────────────────
    mock_download.assert_called_once()
    mock_clean.assert_called_once()
    assert mock_compile_pdf.call_count == 1, "pre-flight compile_pdf called"
    assert mock_compile_with_fix_loop.call_count == 1, "final compile_with_fix_loop called"

    assert os.path.exists("final.pdf"), "Final output PDF should have been moved correctly"
    
    # Cleanup dummy output
    if os.path.exists("final.pdf"):
        os.remove("final.pdf")
