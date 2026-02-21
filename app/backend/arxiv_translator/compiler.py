"""
Phase 4 (Part A): PDF Compiler with error-driven AI fix loop.

Changes from the old version:
1. compile_pdf() now accepts a timeout parameter (default 180s)
2. Added parse_latex_error() to extract file+line from error log
3. Added ai_fix_file() to ask Gemini to fix only the broken file
4. Added compile_with_fix_loop() — up to 3 compile→parse→fix iterations
   before falling back to LatexRescuer
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
    Parse a LaTeX error log to find the failing file and line number.
    
    Returns dict with:
      'file'        : relative filename (or None)
      'line'        : line number (int or None)
      'error_type'  : short description (e.g. 'Undefined control sequence')
      'snippet'     : the most relevant 40-line window of the log
    """
    if not log:
        return None

    # Common error patterns
    # ! Undefined control sequence.
    # ! Missing { inserted.
    # ! Environment ... undefined.
    # ! Package ... Error: ...
    error_line_pat = re.compile(r'^! (.+)$', re.MULTILINE)
    # ./filename.tex:123: ...  (file-line-error format)
    file_line_pat = re.compile(r'^(\.?/?[\w./\-]+\.tex):(\d+):', re.MULTILINE)
    # l.123 ...
    line_num_pat = re.compile(r'^l\.(\d+)\s', re.MULTILINE)

    error_match = error_line_pat.search(log)
    error_type = error_match.group(1).strip() if error_match else 'Unknown error'

    file_match = file_line_pat.search(log)
    error_file = file_match.group(1) if file_match else None
    error_line_num = int(file_match.group(2)) if file_match else None

    if not error_line_num:
        line_match = line_num_pat.search(log)
        if line_match:
            error_line_num = int(line_match.group(1))

    # Extract relevant snippet: 20 lines around the error
    lines = log.splitlines()
    snippet_lines = []
    if error_match:
        err_idx = next((i for i, l in enumerate(lines) if l.startswith('!')), 0)
        start = max(0, err_idx - 5)
        end = min(len(lines), err_idx + 35)
        snippet_lines = lines[start:end]
    else:
        # Use last 40 lines as fallback
        snippet_lines = lines[-40:]

    return {
        'file': error_file,
        'line': error_line_num,
        'error_type': error_type,
        'snippet': '\n'.join(snippet_lines),
    }


def ai_fix_file(file_path: str, error_snippet: str, api_key: str, model_name: str) -> bool:
    """
    Ask Gemini to fix a specific LaTeX file based on the error snippet.
    
    Reads the file, sends it + error to Gemini, writes back the fixed version.
    Returns True if the file was modified.
    """
    from google import genai
    from google.genai import types

    if not os.path.exists(file_path):
        logger.warning(f"ai_fix_file: file not found: {file_path}")
        return False

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            original_content = f.read()
    except Exception as e:
        logger.error(f"ai_fix_file: can't read {file_path}: {e}")
        return False

    # Load fix prompt
    prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'latex_fix_prompt.txt')
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            fix_prompt = f.read()
    else:
        fix_prompt = "You are a LaTeX expert. Fix the compilation error in the file. Output ONLY the corrected LaTeX."

    user_content = (
        f"## Error Log\n```\n{error_snippet}\n```\n\n"
        f"## LaTeX File (`{os.path.basename(file_path)}`)\n```latex\n{original_content}\n```\n"
    )

    try:
        client = genai.Client(
            api_key=api_key,
            http_options={'api_version': 'v1beta', 'timeout': 120000}
        )
        response = client.models.generate_content(
            model=model_name,
            config=types.GenerateContentConfig(
                system_instruction=fix_prompt,
                temperature=0.05,
            ),
            contents=[user_content]
        )
        fixed_content = response.text or ""

        # Strip markdown fences if LLM added them
        fence_match = re.search(r'^```(?:latex)?\s*(.*?)\s*```$', fixed_content, re.DOTALL | re.MULTILINE)
        if fence_match:
            fixed_content = fence_match.group(1)

        if not fixed_content.strip():
            logger.warning("ai_fix_file: empty response from Gemini")
            return False

        if fixed_content.strip() == original_content.strip():
            logger.info("ai_fix_file: no changes produced")
            return False

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        logger.info(f"ai_fix_file: applied AI fix to {os.path.basename(file_path)}")
        return True

    except Exception as e:
        logger.error(f"ai_fix_file: Gemini call failed: {e}")
        return False


# ── Core Compilation ─────────────────────────────────────────────────────────

def compile_pdf(
    source_dir: str,
    main_tex_file: str,
    timeout: int = 180,
) -> Tuple[bool, str]:
    """
    Compile a LaTeX project to PDF using latexmk.
    
    Args:
        source_dir: Directory containing the source files.
        main_tex_file: Path to the main .tex file.
        timeout: Maximum seconds to allow compilation (default 180s).
    
    Returns:
        (success: bool, error_log: str)
    """
    cwd = os.getcwd()
    os.chdir(source_dir)
    rel_tex_file = os.path.basename(main_tex_file)
    logger.info(f"Compiling {rel_tex_file} in {source_dir} (timeout={timeout}s)...")

    try:
        latexmk_path = shutil.which("latexmk")

        # macOS fallback paths
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
                rel_tex_file
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
                rel_tex_file
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
            logger.error(f"Log tail: {combined_log[-3000:]}")
            return False, combined_log[-5000:]

    except subprocess.TimeoutExpired:
        logger.error(f"Compilation timed out after {timeout}s")
        return False, f"Compilation timed out after {timeout}s"
    except Exception as e:
        logger.error(f"Compiler error: {e}")
        return False, str(e)
    finally:
        os.chdir(cwd)


# ── Error-Driven Compile+Fix Loop ────────────────────────────────────────────

def compile_with_fix_loop(
    source_dir: str,
    main_tex: str,
    api_key: str,
    model_name: str,
    max_attempts: int = 3,
    timeout: int = 180,
) -> Tuple[bool, str]:
    """
    Compile PDF with an error-driven fix loop.
    
    On each failure:
    1. Parse the error log to find the failing file + error type
    2. Ask Gemini to fix only that file
    3. Retry compilation
    
    After max_attempts, fall back to LatexRescuer.
    
    Returns (success: bool, final_log: str)
    """
    last_log = ""

    for attempt in range(1, max_attempts + 1):
        logger.info(f"Compilation attempt {attempt}/{max_attempts}...")
        success, log = compile_pdf(source_dir, main_tex, timeout=timeout)

        if success:
            logger.info(f"Compilation succeeded on attempt {attempt}")
            return True, ""

        last_log = log
        logger.warning(f"Attempt {attempt} failed.")

        if attempt == max_attempts:
            break

        # Parse error → find file to fix
        error_info = parse_latex_error(log)
        if not error_info:
            logger.warning("Could not parse error log; skipping AI fix.")
            continue

        logger.info(f"Error: {error_info['error_type']}")

        # Resolve the failing file path
        error_file_rel = error_info.get('file')
        if error_file_rel:
            # Try to resolve relative to source_dir
            candidate = os.path.join(source_dir, error_file_rel.lstrip('./'))
            if not os.path.isfile(candidate):
                # Try just the basename
                for root, _, files in os.walk(source_dir):
                    for fn in files:
                        if fn == os.path.basename(error_file_rel):
                            candidate = os.path.join(root, fn)
                            break
            fix_path = candidate if os.path.isfile(candidate) else main_tex
        else:
            # No file identified; fix the main tex
            fix_path = main_tex

        logger.info(f"Asking AI to fix: {os.path.relpath(fix_path, source_dir)}")
        fixed = ai_fix_file(fix_path, error_info['snippet'], api_key, model_name)
        if not fixed:
            logger.warning("AI fix produced no changes; stopping fix loop.")
            break

    # All attempts failed — try LatexRescuer as last resort
    logger.warning("All compile attempts failed. Trying LatexRescuer...")
    from .latex_rescuer import LatexRescuer
    rescuer = LatexRescuer(source_dir, main_tex)
    if rescuer.rescue():
        logger.info("LatexRescuer succeeded.")
        return True, "rescued"
    else:
        logger.error("LatexRescuer also failed.")
        return False, last_log
