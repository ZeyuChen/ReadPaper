import os
import re
from .logging_utils import logger


def apply_post_processing(source_dir: str, main_tex_path: str):
    """
    Phase 3: Apply targeted fixes to all .tex/.bib files after translation.

    Injections (main file only):
      • ctex       [fontset=fandol] — enables CJK typesetting for Chinese text
      • xspace                      — prevents spacing issues after macros
      • xcolor                      — required for DeepDive \\textcolor annotations

    Fixes applied to all .tex files:
      1. Strip LLM conversational preamble (if LLM added text before \\documentclass)
      2. Remove conflicting CJK packages (CJK, xeCJK, CJKutf8 — ctex supersedes them)
      3. Inject ctex + xspace + xcolor before \\begin{document} in main file
      4. Remove legacy \\begin{CJK}...\\end{CJK} environments
      5. Rename \\chinese macro to \\zhtext to avoid conflicts
      6. Deduplicate \\label{} definitions globally across all files
      7. Fix escaped brace artifacts: \\{ → \\lbrace, \\} → \\rbrace in text mode

    .bib files:
      • Fix duplicate 'and' in author lists (bibtex parser bug)
    """
    tex_files = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".tex"):
                tex_files.append(os.path.join(root, file))

    logger.info(f"Post-processing {len(tex_files)} files in {source_dir}...")

    # Global seen_labels set to catch cross-file duplicates
    global_seen_labels: set = set()

    for file_path in tex_files:
        _process_single_file(file_path, main_tex_path, global_seen_labels)

    # Process bib files
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".bib"):
                _process_bib_file(os.path.join(root, file))


def _process_bib_file(file_path: str):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        original = content
        # Fix double 'and' in author list (causes Tectonic/bibtex panic)
        content = re.sub(r'\s+and\s+and\s+', ' and ', content, flags=re.IGNORECASE)
        if content != original:
            logger.debug(f"Fixed .bib: {os.path.basename(file_path)}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception as e:
        logger.error(f"Post-processing failed for .bib {file_path}: {e}")


def _process_single_file(file_path: str, main_tex_path: str, global_seen_labels: set):
    try:
        file_name = os.path.basename(file_path)
        is_main = os.path.abspath(file_path) == os.path.abspath(main_tex_path)

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        original_content = content

        # ── Fix 0: Strip LLM conversational preamble ─────────────────────
        doc_class_match = re.search(r'\\documentclass', content)
        if doc_class_match and doc_class_match.start() > 0:
            preceding = content[:doc_class_match.start()]
            if not all(
                line.strip().startswith('%') or not line.strip()
                for line in preceding.splitlines()
            ):
                logger.warning(f"Stripping LLM preamble from {file_name}")
                content = content[doc_class_match.start():]

        # ── Fix 1: Remove conflicting CJK package variants ───────────────
        content = re.sub(r'\\usepackage\s*(?:\[.*?\])?\s*\{CJK\*?\}', '% [removed CJK package]', content)
        content = re.sub(r'\\usepackage\s*\{xeCJK\}', '% [removed xeCJK - ctex handles this]', content)
        content = re.sub(r'\\usepackage\s*\{CJKutf8\}', '% [removed CJKutf8 - ctex handles this]', content)

        # ── Fix 2: Inject ctex in MAIN file (single correct escape) ──────
        if is_main and '\\documentclass' in content and 'ctex' not in content:
            ctex_line = '\\usepackage[fontset=fandol]{ctex}\n\\usepackage{xspace}\n\\usepackage{xcolor}\n'
            if '\\begin{document}' in content:
                content = content.replace('\\begin{document}', ctex_line + '\\begin{document}', 1)
            else:
                # Inject after first \documentclass line
                content = re.sub(
                    r'(\\documentclass(?:\[.*?\])?\{.*?\})',
                    r'\1\n' + ctex_line.replace('\\', r'\\'),
                    content, count=1
                )

        # ── Fix 3: Remove CJK environments (legacy LaTeX 2e pattern) ─────
        content = re.sub(r'\\begin\{CJK\*?\}\{.*?\}\{.*?\}', '', content)
        content = re.sub(r'\\end\{CJK\*?\}', '', content)
        content = re.sub(r'\\begin\{CJK\}\{.*?\}\{.*?\}', '', content)
        content = re.sub(r'\\end\{CJK\}', '', content)

        # ── Fix 4: \\chinese macro conflict (correct single-escape) ──────
        if r'\chinese' in content:
            # Rename \chinese → \zhtext (short, unlikely to clash)
            # Correct regex: replace \chinese (not followed by a letter) 
            content = re.sub(r'\\chinese(?![a-zA-Z])', r'\\zhtext', content)
            # Also update any \newcommand{\chinese} → \newcommand{\zhtext}
            content = re.sub(
                r'\\newcommand\s*\{\\chinese\}',
                r'\\newcommand{\\zhtext}',
                content
            )
            content = re.sub(r'\\def\\chinese(?![a-zA-Z])', r'\\def\\zhtext', content)

        # ── Fix 5: minted package output dir ─────────────────────────────
        if '{minted}' in content:
            content = re.sub(
                r'\\usepackage\[.*?\]\{minted\}',
                r'\\usepackage[outputdir=.]{minted}',
                content
            )
            if '\\usepackage{minted}' in content:
                content = content.replace('\\usepackage{minted}', '\\usepackage[outputdir=.]{minted}')

        # ── Fix 6: tcolorbox auto-inject if used but not loaded ──────────
        if 'tcolorbox' in content and '{tcolorbox}' not in content:
            inject = '\\usepackage{tcolorbox}\n'
            if '{xcolor}' in content:
                content = content.replace('{xcolor}\n', '{xcolor}\n' + inject, 1)
            elif '\\begin{document}' in content:
                content = content.replace('\\begin{document}', inject + '\\begin{document}', 1)

        # ── Fix 7: Duplicate labels (global cross-file tracking) ─────────
        label_pattern = re.compile(r'\\label\{([^}]+)\}')

        def replace_label(match):
            lbl = match.group(1)
            if lbl in global_seen_labels:
                return f'% [duplicate label removed: {lbl}]'
            global_seen_labels.add(lbl)
            return match.group(0)

        content = label_pattern.sub(replace_label, content)

        # ── Fix 8: Escaped brace typos introduced by LLM ─────────────────
        content = content.replace(r'\ }', r'\}')
        content = content.replace(r'\ {', r'\{')

        # ── Fix 9: Remove stray markdown artifacts ───────────────────────
        # LLM sometimes inserts ```latex or ``` into the middle of a file
        content = re.sub(r'^```(?:latex)?\s*$', '', content, flags=re.MULTILINE)

        # ── Fix 10: Normalize multiple blank lines (max 2) ───────────────
        content = re.sub(r'\n{4,}', '\n\n\n', content)

        if content != original_content:
            logger.debug(f"Post-processing applied fixes to {file_name}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

    except Exception as e:
        logger.error(f"Post-processing failed for {file_path}: {e}")
