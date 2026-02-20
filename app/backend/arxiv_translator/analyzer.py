r"""
Phase 0: Paper Structure Analyzer

Builds a dependency graph of .tex files and classifies each as:
  - 'main'       : Has \documentclass AND \begin{document} — the true entry point
  - 'sub'        : \input-ed or \include-d from main; contains translatable text
  - 'macros'     : Only \newcommand / \def / \let definitions — DO NOT TRANSLATE
  - 'style'      : Contains \ProvidesPackage / \ProvidesClass — DO NOT TRANSLATE
  - 'standalone' : Has \documentclass but NOT reachable from main (e.g. supplement)
  - 'unknown'    : Cannot determine — translate conservatively (treat as sub)
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from .logging_utils import logger


@dataclass
class FileInfo:
    path: str                   # Absolute path
    rel_path: str               # Relative to source_dir
    file_type: str = 'unknown'  # main/sub/macros/style/standalone/unknown
    has_documentclass: bool = False
    has_begin_document: bool = False
    has_only_macros: bool = False
    is_style_file: bool = False
    inputs: List[str] = field(default_factory=list)   # resolved abs paths of \input/\include


@dataclass
class PaperStructure:
    source_dir: str
    main_tex: str                          # abs path to main .tex
    preamble: str = ""                     # content of preamble block
    files: Dict[str, FileInfo] = field(default_factory=dict)  # abs_path -> FileInfo

    def translatable_files(self) -> List[str]:
        """Return abs paths of files that should be translated."""
        return [
            info.path for info in self.files.values()
            if info.file_type in ('main', 'sub', 'unknown')
        ]

    def skip_files(self) -> List[str]:
        """Return abs paths of files that must NOT be translated."""
        return [
            info.path for info in self.files.values()
            if info.file_type in ('macros', 'style', 'standalone')
        ]


# ── Patterns ──────────────────────────────────────────────────────────────────

_RE_DOCUMENTCLASS = re.compile(r'\\documentclass[\[{]')
_RE_BEGIN_DOCUMENT = re.compile(r'\\begin\s*\{document\}')
_RE_INPUT = re.compile(r'\\(?:input|include)\s*\{([^}]+)\}')
_RE_NEWCOMMAND = re.compile(r'\\(?:newcommand|renewcommand|def|let|DeclareMathOperator|providecommand)\b')
_RE_PROVIDES = re.compile(r'\\(?:ProvidesPackage|ProvidesClass|ProvidesFile)\b')

# Heuristic: if >80% of non-blank lines are macro definitions, it's a macro file
_MACRO_LINE = re.compile(r'^\s*(?:\\(?:newcommand|renewcommand|def|let|providecommand|DeclareMathOperator)|%)')


def _read_file(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ''


def _is_macro_file(content: str) -> bool:
    """Return True if file is predominantly macro definitions."""
    lines = [l for l in content.splitlines() if l.strip()]
    if not lines:
        return False
    macro_lines = sum(1 for l in lines if _MACRO_LINE.match(l))
    return macro_lines / len(lines) > 0.6


def _resolve_input(ref: str, from_dir: str, source_dir: str) -> Optional[str]:
    r"""Resolve \input{ref} to an absolute path, trying .tex extension if needed."""
    # Try as-is, relative to the including file's directory, and relative to source_dir
    candidates = [
        os.path.join(from_dir, ref),
        os.path.join(from_dir, ref + '.tex'),
        os.path.join(source_dir, ref),
        os.path.join(source_dir, ref + '.tex'),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def _find_all_tex_files(source_dir: str) -> List[str]:
    """Recursively find all .tex files under source_dir."""
    result = []
    for root, _, files in os.walk(source_dir):
        for f in files:
            if f.lower().endswith('.tex'):
                result.append(os.path.abspath(os.path.join(root, f)))
    return result


def _find_main_tex(source_dir: str, all_tex: List[str]) -> Optional[str]:
    r"""
    Find the true main .tex file:
    Must have BOTH \documentclass AND \begin{document}.
    If multiple match, prefer files named main.tex / ms.tex / paper.tex / article.tex.
    """
    candidates = []
    for path in all_tex:
        content = _read_file(path)
        if _RE_DOCUMENTCLASS.search(content) and _RE_BEGIN_DOCUMENT.search(content):
            candidates.append(path)

    if not candidates:
        logger.warning("No file with both \\documentclass and \\begin{document} found. Falling back to heuristic.")
        # Fallback: file with \documentclass in top-level dir
        top_level = [p for p in all_tex if os.path.dirname(p) == os.path.abspath(source_dir)]
        for p in top_level:
            c = _read_file(p)
            if _RE_DOCUMENTCLASS.search(c):
                return p
        return all_tex[0] if all_tex else None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates — use priority names, prefer shallower paths
    priority_names = ['main.tex', 'ms.tex', 'paper.tex', 'article.tex']
    for name in priority_names:
        for c in candidates:
            if os.path.basename(c).lower() == name:
                return c

    # Prefer files closest to source_dir root (fewest path separators)
    candidates.sort(key=lambda p: p.count(os.sep))
    return candidates[0]


def _build_dependency_graph(
    main_tex: str,
    source_dir: str,
    all_tex_set: Set[str],
) -> Dict[str, Set[str]]:
    r"""
    BFS/DFS from main_tex, following \input and \include.
    Returns: dict of abs_path -> set of abs_paths (direct inputs)
    """
    graph: Dict[str, Set[str]] = {}
    visited: Set[str] = set()
    queue = [main_tex]

    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        content = _read_file(current)
        from_dir = os.path.dirname(current)
        deps: Set[str] = set()
        for m in _RE_INPUT.finditer(content):
            ref = m.group(1).strip()
            resolved = _resolve_input(ref, from_dir, source_dir)
            if resolved and resolved in all_tex_set:
                deps.add(resolved)
                if resolved not in visited:
                    queue.append(resolved)
        graph[current] = deps

    return graph


def _extract_preamble(main_tex_path: str) -> str:
    r"""Extract everything before \begin{document} from the main tex file."""
    content = _read_file(main_tex_path)
    m = _RE_BEGIN_DOCUMENT.search(content)
    if m:
        return content[:m.start()]
    return ''


class PaperAnalyzer:
    """Analyzes an arXiv LaTeX source directory and returns a PaperStructure."""

    def __init__(self, source_dir: str):
        self.source_dir = os.path.abspath(source_dir)

    def analyze(self) -> PaperStructure:
        logger.info(f"Analyzing paper structure in: {self.source_dir}")

        # 1. Collect all .tex files
        all_tex = _find_all_tex_files(self.source_dir)
        all_tex_set = set(all_tex)
        logger.info(f"Found {len(all_tex)} .tex files total")

        # 2. Find main .tex
        main_tex = _find_main_tex(self.source_dir, all_tex)
        if not main_tex:
            raise FileNotFoundError("No .tex files found in source directory.")
        logger.info(f"Main tex identified: {os.path.relpath(main_tex, self.source_dir)}")

        # 3. Build dependency graph from main
        graph = _build_dependency_graph(main_tex, self.source_dir, all_tex_set)
        reachable_from_main = set(graph.keys())

        # 4. Classify each file
        files: Dict[str, FileInfo] = {}
        for path in all_tex:
            content = _read_file(path)
            rel = os.path.relpath(path, self.source_dir)
            inputs_resolved = [
                r for ref in (_RE_INPUT.findall(content))
                for r in [_resolve_input(ref, os.path.dirname(path), self.source_dir)]
                if r is not None
            ]

            info = FileInfo(
                path=path,
                rel_path=rel,
                has_documentclass=bool(_RE_DOCUMENTCLASS.search(content)),
                has_begin_document=bool(_RE_BEGIN_DOCUMENT.search(content)),
                has_only_macros=_is_macro_file(content),
                is_style_file=bool(_RE_PROVIDES.search(content)),
                inputs=inputs_resolved,
            )

            # Classify
            if path == main_tex:
                info.file_type = 'main'
            elif info.is_style_file:
                info.file_type = 'style'
            elif info.has_only_macros:
                info.file_type = 'macros'
            elif path in reachable_from_main:
                if info.has_documentclass and info.has_begin_document:
                    # Odd: reachable AND has its own document structure
                    info.file_type = 'sub'  # treat as sub (might be an appendix pattern)
                else:
                    info.file_type = 'sub'
            elif info.has_documentclass and info.has_begin_document:
                info.file_type = 'standalone'
            else:
                info.file_type = 'unknown'

            files[path] = info
            logger.debug(f"  {rel} → {info.file_type}")

        # 5. Extract preamble
        preamble = _extract_preamble(main_tex)

        structure = PaperStructure(
            source_dir=self.source_dir,
            main_tex=main_tex,
            preamble=preamble,
            files=files,
        )

        logger.info(
            f"Classification: "
            f"{sum(1 for f in files.values() if f.file_type=='main')} main, "
            f"{sum(1 for f in files.values() if f.file_type=='sub')} sub, "
            f"{sum(1 for f in files.values() if f.file_type=='macros')} macros, "
            f"{sum(1 for f in files.values() if f.file_type=='style')} style, "
            f"{sum(1 for f in files.values() if f.file_type=='standalone')} standalone, "
            f"{sum(1 for f in files.values() if f.file_type=='unknown')} unknown"
        )
        logger.info(
            f"Will translate: {len(structure.translatable_files())} files | "
            f"Will skip: {len(structure.skip_files())} files"
        )

        return structure
