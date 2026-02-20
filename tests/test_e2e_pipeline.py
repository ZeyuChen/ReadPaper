
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
@patch("app.backend.arxiv_translator.main.clean_latex_directory")
@patch("app.backend.arxiv_translator.main.PaperAnalyzer")
@patch("concurrent.futures.ProcessPoolExecutor")
@patch("concurrent.futures.as_completed")
def test_e2e_pipeline_mocked(
    mock_as_completed, mock_executor, mock_analyzer_cls,
    mock_clean, mock_compile_pdf,
    mock_deepdive, mock_translator,
    mock_extract, mock_download, mock_workspace
):
    """Verifies the main entry point logic without external calls.
    
    NOTE: compile_with_fix_loop has been removed. compile_pdf is now the sole
    compilation function. It serves both the pre-flight check and the final
    compilation, so mock_compile_pdf is configured to:
      - First call (pre-flight): return (True, "")
      - Second call (final compile): create the dummy PDF and return (True, "")
    """

    # ── Executor: run synchronously ──────────────────────────────────────────
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

    # ── compile_pdf: pre-flight (1st call) succeeds; final compile (2nd call)
    #    creates the dummy PDF and succeeds. ──────────────────────────────────
    call_count = [0]

    def side_effect_compile_pdf(source_dir, main_tex, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Pre-flight compile — just return success
            return (True, "")
        # Final compile — create the PDF output so main() can find & copy it
        pdf_path = os.path.join(source_dir, os.path.basename(main_tex).replace(".tex", ".pdf"))
        os.makedirs(source_dir, exist_ok=True)
        with open(pdf_path, "w") as f:
            f.write("%PDF-1.4 dummy")
        return (True, "")

    mock_compile_pdf.side_effect = side_effect_compile_pdf

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
        cwd = os.getcwd()
        os.chdir(mock_workspace)
        try:
            main()
        finally:
            os.chdir(cwd)

    # ── Assertions ───────────────────────────────────────────────────────────
    mock_download.assert_called_once()
    mock_clean.assert_called_once()
    # compile_pdf is now called twice: once for pre-flight, once for final compile
    assert mock_compile_pdf.call_count >= 2, "compile_pdf should be called for pre-flight + final"
