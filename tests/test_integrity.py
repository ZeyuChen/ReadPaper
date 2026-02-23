"""
Tests for translation integrity validation.
"""

import pytest
from app.backend.arxiv_translator.integrity import validate_translation


# ── Layer 1: Basic non-empty checks ──────────────────────────────────────────

def test_empty_translation_rejected():
    is_valid, reason = validate_translation("Hello world", "", "test.tex")
    assert not is_valid
    assert "too short" in reason.lower()


def test_very_short_translation_rejected():
    is_valid, reason = validate_translation("Hello world" * 10, "Hi", "test.tex")
    assert not is_valid
    assert "too short" in reason.lower()


# ── Layer 2: LaTeX structural completeness ────────────────────────────────────

def test_missing_end_document_rejected():
    original = r"""
\documentclass{article}
\begin{document}
Hello world.
\end{document}
"""
    translated = r"""
\documentclass{article}
\begin{document}
你好世界。
"""  # Missing \end{document}!
    is_valid, reason = validate_translation(original, translated, "main.tex", is_main_file=True)
    assert not is_valid
    assert "end{document}" in reason.lower()


def test_missing_begin_document_rejected():
    original = r"""
\documentclass{article}
\begin{document}
Hello world.
\end{document}
"""
    translated = r"""
\documentclass{article}
你好世界。
\end{document}
"""  # Missing \begin{document}!
    is_valid, reason = validate_translation(original, translated, "main.tex")
    assert not is_valid
    assert "begin{document}" in reason.lower()


def test_valid_translation_accepted():
    original = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
Hello world. This paper presents our approach to the problem.
We use Transformer models.
\cite{brown2020}
\ref{tab:results}
\label{sec:intro}
\end{document}
"""
    translated = r"""
\documentclass{article}
\usepackage[UTF8]{ctex}
\begin{document}
\section{引言}
你好世界。本文介绍了我们解决问题的方法。
我们使用 Transformer 模型。
\cite{brown2020}
\ref{tab:results}
\label{sec:intro}
\end{document}
"""
    is_valid, reason = validate_translation(original, translated, "main.tex", is_main_file=True)
    assert is_valid, f"Expected valid but got: {reason}"


# ── Layer 3: Key structure preservation ───────────────────────────────────────

def test_section_count_mismatch_rejected():
    original = r"""
\begin{document}
\section{Intro}
Text.
\section{Method}
More text.
\section{Results}
Results text.
\section{Conclusion}
Done.
\end{document}
"""
    translated = r"""
\begin{document}
\section{引言}
文本。
\section{方法}
Done. 只翻译了两个 section。
\end{document}
"""  # Missing 2 sections
    is_valid, reason = validate_translation(original, translated, "main.tex")
    assert not is_valid
    assert "section" in reason.lower()


def test_cite_count_drop_rejected():
    original = r"""
\begin{document}
Text \cite{a} and \cite{b} and \cite{c} and \cite{d} and \cite{e} and \cite{f}.
\end{document}
"""
    translated = r"""
\begin{document}
文本 \cite{a}。
\end{document}
"""  # Lost 5 out of 6 citations
    is_valid, reason = validate_translation(original, translated, "main.tex")
    assert not is_valid
    assert "cite" in reason.lower()


# ── Layer 4: Truncation detection ─────────────────────────────────────────────

def test_unclosed_braces_rejected():
    original = r"""
\begin{document}
Hello world.
\end{document}
"""
    translated = r"""
\begin{document}
你好 {世界 {这是 {嵌套的 {未闭合的 {括号 {六个
\end{document}
"""
    is_valid, reason = validate_translation(original, translated, "main.tex")
    assert not is_valid
    assert "unclosed braces" in reason.lower()


# ── Sub-file (non-main) passing ────────────────────────────────────────────┐─

def test_subfile_without_document_accepted():
    """Sub-files don't need \\begin/end{document}."""
    original = r"""
\section{Related Work}
This section discusses related work.
\cite{smith2023}
"""
    translated = r"""
\section{相关工作}
本节讨论相关工作。
\cite{smith2023}
"""
    is_valid, reason = validate_translation(original, translated, "related.tex")
    assert is_valid, f"Expected valid but got: {reason}"


# ── Environment balance check ────────────────────────────────────────────────

def test_unbalanced_environments_rejected():
    original = r"""
\begin{document}
\begin{figure}
\end{figure}
\begin{table}
\end{table}
\end{document}
"""
    translated = r"""
\begin{document}
\begin{figure}
\begin{table}
\end{document}
"""  # Missing both \end{figure} and \end{table}
    is_valid, reason = validate_translation(original, translated, "main.tex")
    assert not is_valid
    assert "unbalanced" in reason.lower() or "environment" in reason.lower()
