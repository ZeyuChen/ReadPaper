"""
Phase 4: PDF Compiler — single-shot pdfLaTeX compilation.

compile_pdf() attempts one latexmk -pdf run and returns (success, log).
Errors are propagated upstream and displayed to the user in the frontend.
The AI fix loop has been removed to avoid token waste; post_process.py
handles the most common LaTeX issues via targeted regex transformations.
"""

import subprocess
import os
import re
import shutil
from typing import Optional, Tuple
from .logging_utils import logger


# ── Error Log Parser ─────────────────────────────────────────────────────────

def parse_latex_error(log: str) -> Optional[dict]:
    """
    Parse a LaTeX error log to extract the key error message, file and line.

    Returns dict with:
      'file'       : relative filename (or None)
      'line'       : line number (int or None)
      'error_type' : short description (e.g. 'Undefined control sequence')
      'snippet'    : the most relevant 40-line window of the log
    """
    if not log:
        return None

    error_line_pat = re.compile(r'^! (.+)$', re.MULTILINE)
    file_line_pat  = re.compile(r'^(\.?/?[\w./\-]+\.tex):(\d+):', re.MULTILINE)
    line_num_pat   = re.compile(r'^l\.(\d+)\s', re.MULTILINE)

    error_match    = error_line_pat.search(log)
    error_type     = error_match.group(1).strip() if error_match else 'Unknown error'

    file_match     = file_line_pat.search(log)
    error_file     = file_match.group(1) if file_match else None
    error_line_num = int(file_match.group(2)) if file_match else None

    if not error_line_num:
        line_match = line_num_pat.search(log)
        if line_match:
            error_line_num = int(line_match.group(1))

    # Extract a readable 40-line window around the first error
    lines = log.splitlines()
    if error_match:
        err_idx = next((i for i, l in enumerate(lines) if l.startswith('!')), 0)
        start = max(0, err_idx - 5)
        end   = min(len(lines), err_idx + 35)
        snippet_lines = lines[start:end]
    else:
        snippet_lines = lines[-40:]

    return {
        'file':       error_file,
        'line':       error_line_num,
        'error_type': error_type,
        'snippet':    '\n'.join(snippet_lines),
    }


# ── Core Compilation ─────────────────────────────────────────────────────────

def compile_pdf(
    source_dir: str,
    main_tex_file: str,
    timeout: int = 180,
) -> Tuple[bool, str]:
    """
    Compile a LaTeX project to PDF using latexmk -pdf (pdfLaTeX engine).

    Args:
        source_dir:    Directory containing the source files.
        main_tex_file: Absolute path to the main .tex file.
        timeout:       Max compilation seconds (default 180).

    Returns:
        (success: bool, error_summary: str)
        On failure, error_summary is a human-readable extract of the LaTeX
        log suitable for display in the frontend error panel.
    """
    cwd = os.getcwd()
    os.chdir(source_dir)
    rel_tex_file = os.path.basename(main_tex_file)
    logger.info(f"Compiling {rel_tex_file} in {source_dir} (timeout={timeout}s, engine=pdfLaTeX)...")

    try:
        latexmk_path = shutil.which("latexmk")

        # macOS local fallback paths (for non-PATH TeX installations)
        if not latexmk_path:
            try:
                sysname = os.uname().sysname
            except AttributeError:
                sysname = ''
            if sysname == 'Darwin':
                for p in [
                    "/Library/TeX/texbin/latexmk",
                    "/usr/local/bin/latexmk",
                    "/opt/homebrew/bin/latexmk",
                ]:
                    if os.path.isfile(p) and os.access(p, os.X_OK):
                        latexmk_path = p
                        break

        if latexmk_path:
            cmd = [
                latexmk_path, "-pdf", "-bibtex",
                "-interaction=nonstopmode", "-f",
                "-file-line-error", "-outdir=.",
                rel_tex_file,
            ]
        else:
            logger.info("latexmk not found; using Docker TeX Live fallback")
            uid = os.getuid() if hasattr(os, 'getuid') else 0
            gid = os.getgid() if hasattr(os, 'getgid') else 0
            cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "-v", f"{os.path.abspath(source_dir)}:/workdir",
                "-w", "/workdir",
                "--user", f"{uid}:{gid}",
                "ghcr.io/xu-cheng/texlive-full:latest",
                "latexmk", "-pdf", "-bibtex",
                "-interaction=nonstopmode", "-f",
                "-file-line-error", "-outdir=.",
                rel_tex_file,
            ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )

        combined_log = result.stdout + "\n" + result.stderr
        pdf_name = rel_tex_file.replace(".tex", ".pdf")

        if os.path.exists(pdf_name):
            if result.returncode != 0:
                logger.warning(f"Compilation succeeded with warnings (rc={result.returncode})")
            else:
                logger.info("Compilation successful.")
            return True, ""
        else:
            logger.error(f"PDF not generated (rc={result.returncode})")
            # Build a user-readable error summary
            error_info = parse_latex_error(combined_log)
            if error_info:
                location = (
                    f" in {error_info['file']} line {error_info['line']}"
                    if error_info['file'] else ""
                )
                summary = (
                    f"LaTeX Error: {error_info['error_type']}{location}\n\n"
                    f"{error_info['snippet']}"
                )
            else:
                summary = combined_log[-3000:]
            return False, summary

    except subprocess.TimeoutExpired:
        logger.error(f"Compilation timed out after {timeout}s")
        return False, f"Compilation timed out after {timeout}s"
    except Exception as e:
        logger.error(f"Compiler error: {e}")
        return False, str(e)
    finally:
        os.chdir(cwd)
