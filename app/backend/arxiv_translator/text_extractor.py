"""
Phase 1: LaTeX Text Extractor

Extracts only the human-readable prose text nodes from a LaTeX document,
leaving all LaTeX commands, math, and special environments untouched.

The round-trip is:
  1. extract(content) → [TextNode, ...]   # find all translatable text spans
  2. (translate the .text of each TextNode via GeminiTranslator)
  3. reintegrate(content, nodes) → str    # stitch translations back at original offsets

Key design invariant — the following are ALWAYS preserved verbatim:
  • Preamble (everything before \\begin{document})
  • Math environments: equation, align, tikzpicture, algorithm, verbatim, ...
  • Bibliography: \\begin{thebibliography}...\\end{thebibliography}  ← citation fix
  • All \\cite{}, \\ref{}, \\label{}, \\usepackage{} commands
  • Inline math: $...$ and $$...$$, \\(...\\), \\[...\\]
  • LaTeX control tokens: \\textbf, \\emph, \\section, etc.
  • Special chars: { } [ ] \\ ^ _ ~ & (structural)

Only pure English prose in the gaps between the above is sent to the LLM,
so structural corruption and citation loss are impossible by design.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple
from .logging_utils import logger


@dataclass
class TextNode:
    """A span of translatable prose text in a LaTeX document."""
    start: int    # character offset in original content
    end: int      # character offset (exclusive)
    text: str     # original English text
    translated: str = ""  # filled in after translation; empty = skip (keep original)

    def __repr__(self):
        preview = self.text[:40].replace('\n', '↵')
        return f"TextNode({self.start}:{self.end} '{preview}...')"


# ── Skip Region Patterns ──────────────────────────────────────────────────────
# These are regions that must NEVER be translated.
# Order matters: longer/more specific patterns first.

# Named math environments (multi-line, DOTALL)
_MATH_ENVS = [
    'equation', 'equation*', 'align', 'align*', 'aligned',
    'gather', 'gather*', 'multline', 'multline*',
    'eqnarray', 'eqnarray*', 'flalign', 'flalign*',
    'split', 'cases', 'subequations', 'math',
    'tikzpicture', 'tikzcd', 'pgfpicture',
    'algorithm', 'algorithm2e', 'algorithmic',
    'verbatim', 'verbatim*', 'lstlisting', 'minted',
    'Verbatim',  # from fancyvrb
    # ── References / Bibliography — NEVER translate ───────────────────────────
    'thebibliography',       # \begin{thebibliography}{99}...\end{thebibliography}
    'filecontents', 'filecontents*',  # sometimes used to embed .bib inline
]


def _detect_newtheorem_envs(content: str) -> list[str]:
    """Scan the preamble for \\newtheorem{name} declarations (ported from MathTranslate).
    Returns a list of user-defined theorem environment names."""
    pattern = re.compile(r'\\newtheorem\s*\{(.+?)\}')
    return [m.group(1) for m in pattern.finditer(content)]


def _build_env_pattern(extra_envs: list[str] | None = None) -> re.Pattern:
    """Build the environment skip pattern, optionally including extra environments."""
    envs = list(_MATH_ENVS)
    if extra_envs:
        envs.extend(extra_envs)
    return re.compile(
        r'\\begin\{(' + '|'.join(re.escape(e) for e in envs) + r')\}.*?\\end\{\1\}',
        re.DOTALL
    )


# Default pattern (without dynamic theorem envs)
_ENV_PATTERN = _build_env_pattern()

# Inline math: $...$ and $$...$$
# Be careful not to match escaped \$ — covered by the negative lookbehind
_INLINE_MATH = re.compile(r'(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$.*?(?<!\\)\$', re.DOTALL)

# \( ... \) and \[ ... \]
_PAREN_MATH = re.compile(r'\\\(.*?\\\)|\\\[.*?\\\]', re.DOTALL)

# LaTeX commands with arguments that must not be translated:
# \usepackage, \documentclass, \bibliographystyle, \bibliography, 
# \includegraphics, \input, \include, \cite, \ref, \label, \eqref,
# \newcommand, \renewcommand, \def, \let, \providecommand,
# \DeclareMathOperator, \setcounter, \hypersetup, \geometry, etc.
_COMMAND_WITH_ARG = re.compile(
    r'\\(?:'
    r'usepackage|documentclass|bibliographystyle|bibliography|'
    r'includegraphics|input|include|import|'
    r'cite[tp]?|(?:auto)?ref|label|eqref|pageref|'
    r'newcommand|renewcommand|providecommand|def|let|'
    r'DeclareMathOperator\*?|DeclareRobustCommand|'
    r'setcounter|setlength|addtolength|settowidth|settoheight|'
    r'hypersetup|geometry|PassOptionsToPackage|RequirePackage|'
    r'newtheorem\*?|theoremstyle|'
    r'begin|end|'
    r'hspace\*?|vspace\*?|rule|raisebox|'
    r'bibitem|newblock'
    r')\s*(?:\[[^\]]*\])?\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}',
    re.DOTALL
)

# Preamble: everything before \begin{document} — skip entirely
_BEGIN_DOCUMENT = re.compile(r'\\begin\s*\{document\}')

# Single-line LaTeX comments (% to end of line) — already removed by cleaner, but just in case
_COMMENT = re.compile(r'(?<!\\)%.*')

# URLs and file paths inside \url{} \href{}
_URL = re.compile(r'\\(?:url|href)\s*\{[^}]*\}(?:\s*\{[^}]*\})?')

# Figure/table captions we DO want to translate — these are handled naturally
# by the text extractor (text inside \caption{} is prose)


def is_complete_latex(content: str) -> bool:
    """Check if content is a complete LaTeX document (ported from MathTranslate).
    Returns True if it has \\documentclass, \\begin{document}, and \\end{document}
    in the correct order."""
    dc_pat = re.compile(r'\\document(?:class|style)(?:\[.*?\])?\{.*?\}', re.DOTALL)
    begin_pat = re.compile(r'\\begin\{document\}')
    end_pat = re.compile(r'\\end\{document\}')

    dc_match = dc_pat.search(content)
    if not dc_match:
        return False
    begin_match = begin_pat.search(content)
    if not begin_match:
        return False
    end_match = end_pat.search(content)
    if not end_match:
        return False
    return dc_match.end() <= begin_match.start() < end_match.start()


class LatexTextExtractor:
    """
    Walks a LaTeX document and extracts TextNode spans of pure prose.

    Algorithm:
    1. Mark all "skip" regions (math, commands with args, preamble, etc.)
    2. Everything NOT in a skip region and not a LaTeX command is a text node
    3. Text nodes shorter than 5 chars or containing no letters are ignored

    Enhanced with MathTranslate techniques:
    - Auto-detects \\newtheorem environments and adds them to skip patterns
    - Validates LaTeX document completeness
    """

    MIN_TEXT_LEN = 10  # Minimum characters to bother translating

    def extract(self, content: str) -> Tuple[List[TextNode], List[Tuple[int, int]]]:
        """
        Returns:
          - nodes: list of TextNode to translate
          - skip_spans: list of (start, end) that must be preserved verbatim
        """
        # Detect user-defined theorem environments from preamble
        self._extra_envs = _detect_newtheorem_envs(content)
        if self._extra_envs:
            logger.info(f"Detected {len(self._extra_envs)} custom theorem envs: {self._extra_envs}")

        skip_spans = self._compute_skip_spans(content)
        nodes = self._extract_text_nodes(content, skip_spans)
        logger.debug(f"Text extractor: {len(nodes)} text nodes, {len(skip_spans)} skip spans")
        return nodes, skip_spans

    def reintegrate(self, original: str, nodes: List[TextNode]) -> str:
        """
        Stitch translations back into the original document at exact character offsets.

        Algorithm:
          For each TextNode (sorted by start offset):
            1. Append original[prev_end : node.start]  — skip-span content, unchanged
            2. Append node.translated (or node.text if translation failed/empty)
            3. advance prev_end = node.end
          After loop: append original[prev_end:]       — document tail

        This guarantees:
          - ALL LaTeX structure (math, bibliography, commands) is preserved exactly
          - Translated prose replaces original prose at precisely the right position
          - No content is ever dropped, even on partial translation failure
        """
        if not nodes:
            return original

        # Sort nodes by start position (should already be sorted from extract())
        nodes = sorted(nodes, key=lambda n: n.start)

        result_parts = []
        prev_end = 0

        for node in nodes:
            # Append unchanged content between previous node end and this node start
            # (includes all skip-span material: math, commands, bibliography, etc.)
            result_parts.append(original[prev_end:node.start])
            # Use translation if non-empty, else fall back to original English
            replacement = node.translated if node.translated.strip() else node.text
            result_parts.append(replacement)
            prev_end = node.end

        # Append document tail after last text node
        result_parts.append(original[prev_end:])
        return ''.join(result_parts)

    # ── Internal ────────────────────────────────────────────────────────────

    def _compute_skip_spans(self, content: str) -> List[Tuple[int, int]]:
        """Compute all spans that must be preserved verbatim, sorted and merged."""
        spans = []

        # 0. Preamble (everything before \begin{document})
        m = _BEGIN_DOCUMENT.search(content)
        if m:
            # Include \begin{document} itself in the skip
            spans.append((0, m.end()))

        # 1. Named math/verbatim/algorithm environments (includes auto-detected theorems)
        env_pattern = _build_env_pattern(getattr(self, '_extra_envs', None)) if getattr(self, '_extra_envs', None) else _ENV_PATTERN
        for m in env_pattern.finditer(content):
            spans.append((m.start(), m.end()))

        # 2. Inline math $...$ $$...$$
        for m in _INLINE_MATH.finditer(content):
            spans.append((m.start(), m.end()))

        # 3. \(...\) and \[...\]
        for m in _PAREN_MATH.finditer(content):
            spans.append((m.start(), m.end()))

        # 4. Commands with non-text arguments
        for m in _COMMAND_WITH_ARG.finditer(content):
            spans.append((m.start(), m.end()))

        # 5. URLs
        for m in _URL.finditer(content):
            spans.append((m.start(), m.end()))

        # 6. LaTeX comments
        for m in _COMMENT.finditer(content):
            spans.append((m.start(), m.end()))

        # 7. Any remaining backslash-command token (e.g. \textbf, \emph, \par, etc.)
        #    We skip just the command token itself (not its argument — that may be prose)
        cmd_token = re.compile(r'\\[a-zA-Z@]+\*?')
        for m in cmd_token.finditer(content):
            spans.append((m.start(), m.end()))

        # 8. LaTeX special characters that are not prose: {, }, [, ], \, ^, _
        special = re.compile(r'[{}\[\]\\^_~&]')
        for m in special.finditer(content):
            spans.append((m.start(), m.end()))

        return self._merge_spans(sorted(spans, key=lambda s: s[0]))

    def _merge_spans(self, spans: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Merge overlapping or adjacent skip spans."""
        if not spans:
            return []
        merged = [spans[0]]
        for start, end in spans[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def _extract_text_nodes(
        self, content: str, skip_spans: List[Tuple[int, int]]
    ) -> List[TextNode]:
        """Find all gaps between skip spans as candidate text nodes."""
        nodes = []
        prev_end = 0

        for span_start, span_end in skip_spans:
            if span_start > prev_end:
                gap = content[prev_end:span_start]
                node = self._make_node(prev_end, span_start, gap)
                if node:
                    nodes.append(node)
            prev_end = span_end

        # Tail after last skip span
        if prev_end < len(content):
            gap = content[prev_end:]
            node = self._make_node(prev_end, len(content), gap)
            if node:
                nodes.append(node)

        return nodes

    def _make_node(self, start: int, end: int, text: str) -> TextNode | None:
        """Create a TextNode if the text is worth translating."""
        stripped = text.strip()
        # Must be long enough and contain actual letters (not just numbers/punctuation)
        if len(stripped) < self.MIN_TEXT_LEN:
            return None
        if not re.search(r'[a-zA-Z]', stripped):
            return None
        # Skip lines that are purely numbers, punctuation, or LaTeX artifacts
        if re.fullmatch(r'[\d\s.,;:()\[\]{}|/\\*+\-=<>?!@#$%^&~`\'"]+', stripped):
            return None
        return TextNode(start=start, end=end, text=text)


def split_into_paragraphs(nodes: List[TextNode], max_chars: int = 3000) -> List[List[TextNode]]:
    """
    Group TextNodes into chunks for batch translation.
    
    Groups contiguous nodes that together are under max_chars.
    This is a simple greedy packer — nodes from different logical regions
    will not be mixed (they're naturally ordered by document position).
    """
    if not nodes:
        return []

    chunks = []
    current = []
    current_len = 0

    for node in nodes:
        node_len = len(node.text)
        if current and current_len + node_len > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(node)
        current_len += node_len

    if current:
        chunks.append(current)

    return chunks
