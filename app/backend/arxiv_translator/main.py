"""
arXiv LaTeX Translator — Main Orchestrator (Robust Pipeline v2)

4-Phase pipeline:
  Phase 0: ANALYZE       — Classify files, build dependency graph
  Phase 1+2: EXTRACT     — Per-file: extract text nodes, translate prose only
  Phase 3: POST-PROCESS  — Targeted regex fixes (no LLM structure corruption)
  Phase 4: COMPILE+FIX   — Error-driven AI fix loop (up to 3 attempts)
"""

import argparse
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

from .analyzer import PaperAnalyzer
from .text_extractor import LatexTextExtractor
from .translator import GeminiTranslator
from .downloader import download_source
from .extractor import extract_source
from .compiler import compile_with_fix_loop, compile_pdf
from .config import ConfigManager
from .deepdive import DeepDiveAnalyzer
from .logging_utils import logger, log_ipc
from .post_process import apply_post_processing
from .latex_cleaner import clean_latex_directory

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Parallel Worker Functions (must be module-level for ProcessPoolExecutor) ──

def translate_file_worker(api_key: str, model_name: str, file_path: str) -> tuple[bool, str, int]:
    """
    Worker: translate a single .tex file using the text-node approach.
    Returns (success, file_path, failed_node_count).
    """
    try:
        translator = GeminiTranslator(api_key=api_key, model_name=model_name)
        extractor = LatexTextExtractor()

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Skip very short files or files with no English text worth translating
        if len(content.strip()) < 50:
            return True, file_path, 0

        # Extract text nodes
        nodes, _ = extractor.extract(content)

        if not nodes:
            logger.info(f"No translatable text nodes in {os.path.basename(file_path)}, skipping.")
            return True, file_path, 0

        # Translate nodes (in-place) — returns (nodes, failed_count)
        nodes, failed_count = translator.translate_text_nodes(nodes)

        # Reintegrate translations into original content
        translated_content = extractor.reintegrate(content, nodes)

        # If some nodes failed, inject a visible warning comment at the top of the file
        if failed_count > 0:
            warning_comment = (
                f"% ============================================================\n"
                f"% \u26a0\ufe0f  TRANSLATION WARNING: {failed_count} text segment(s) could not be\n"
                f"%    translated and remain in the original English.\n"
                f"%    This is usually caused by a temporary API failure.\n"
                f"% ============================================================\n"
            )
            translated_content = warning_comment + translated_content
            logger.warning(f"[{os.path.basename(file_path)}] {failed_count} nodes kept in English (API failure)")

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(translated_content)

        return True, file_path, failed_count

    except Exception as e:
        logger.error(f"Worker failed for {file_path}: {e}", exc_info=True)
        return False, file_path, 0


def deepdive_analysis_worker(api_key: str, file_path: str, model_name: str = "gemini-3-flash-preview") -> tuple[bool, str]:
    try:
        analyzer = DeepDiveAnalyzer(api_key, model_name=model_name)
        file_name = os.path.basename(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        analyzed = analyzer.analyze_latex(content, file_name)
        if analyzed != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(analyzed)
            return True, file_name
        return False, file_name
    except Exception as e:
        logger.error(f"DeepDive worker failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return False, os.path.basename(file_path)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="arXiv LaTeX Translator (Robust Pipeline v2)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("arxiv_url", nargs="?", help="arXiv URL or ID")
    group.add_argument("--set-key", help="Save Gemini API key to config and exit")

    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model to use")
    parser.add_argument("--output", "-o", help="Custom output path for translated PDF")
    parser.add_argument("--keep", action="store_true", help="Keep intermediate files")
    parser.add_argument("--deepdive", action="store_true", help="Enable AI DeepDive analysis")

    args = parser.parse_args()
    config_manager = ConfigManager()

    if args.set_key:
        config_manager.set_api_key(args.set_key)
        sys.exit(0)

    if not args.arxiv_url:
        parser.print_help()
        sys.exit(1)

    # Resolve API key
    api_key = os.getenv("GEMINI_API_KEY") or config_manager.get_api_key()
    if not api_key:
        logger.error("Gemini API key not found. Set GEMINI_API_KEY or run --set-key.")
        sys.exit(1)

    # Model aliases
    model_name = args.model
    model_aliases = {
        'flash': 'gemini-3-flash-preview',
        'pro': 'gemini-3-pro-preview',
        'flash-preview': 'gemini-3-flash-preview',
    }
    model_name = model_aliases.get(model_name.lower(), model_name)

    # Extract arXiv ID
    arxiv_id = args.arxiv_url.rstrip('/').split('/')[-1].replace('.pdf', '')

    logger.info(f"Starting robust translation for {arxiv_id} using {model_name}")
    logger.info(f"DeepDive: {'ENABLED' if args.deepdive else 'DISABLED'}")

    work_dir = os.path.abspath(f"workspace_{arxiv_id}")
    if os.path.exists(work_dir) and not args.keep:
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    try:
        # ── Step 1: Download ──────────────────────────────────────────────
        log_ipc(f"PROGRESS:DOWNLOADING:Downloading source for {arxiv_id}...")

        tar_path = os.path.join(work_dir, f"{arxiv_id}.tar.gz")
        if not os.path.exists(tar_path):
            tar_path = download_source(arxiv_id, work_dir)
        else:
            logger.info("Using cached source archive.")

        # ── Step 2: Extract ───────────────────────────────────────────────
        log_ipc(f"PROGRESS:EXTRACTING:Extracting source files...")
        source_dir = os.path.join(work_dir, "source")
        if not os.path.exists(source_dir):
            extract_source(tar_path, source_dir)

        # Copy to working translation directory
        source_zh_dir = os.path.join(work_dir, "source_zh")
        if os.path.exists(source_zh_dir):
            shutil.rmtree(source_zh_dir)
        shutil.copytree(source_dir, source_zh_dir)

        # ── Phase 0: Structural Analysis ──────────────────────────────────
        log_ipc(f"PROGRESS:EXTRACTING:Analyzing paper structure...")
        analyzer = PaperAnalyzer(source_zh_dir)
        structure = analyzer.analyze()
        main_tex = structure.main_tex

        logger.info(f"Main tex: {os.path.relpath(main_tex, source_zh_dir)}")
        translatable = structure.translatable_files()
        skipped = structure.skip_files()
        logger.info(f"Files to translate: {len(translatable)}, to skip: {len(skipped)}")

        # ── Clean LaTeX comments (reduces token count) ────────────────────
        log_ipc(f"PROGRESS:EXTRACTING:Cleaning LaTeX comments...")
        cleaned_count = clean_latex_directory(source_zh_dir)
        logger.info(f"Cleaned {cleaned_count} files")

        # ── Pre-flight compilation (sanity check) ─────────────────────────
        log_ipc(f"PROGRESS:PRE_FLIGHT:Running pre-flight compilation check...")
        pre_success, _ = compile_pdf(source_zh_dir, main_tex, timeout=120)
        if not pre_success:
            logger.warning("Pre-flight FAILED — source LaTeX may already be broken. Proceeding anyway.")
        else:
            logger.info("Pre-flight SUCCESS.")

        # ── Phase 3 (Optional): DeepDive Analysis ────────────────────────
        # MAX_CONCURRENT_REQUESTS: number of .tex files translated in parallel (ProcessPoolExecutor).
        # MAX_BATCH_CONCURRENCY (in translator.py): within each file, number of
        #   concurrent Gemini API calls fired simultaneously via asyncio.gather.
        # Default: 16 file workers × 8 concurrent batches each = up to 128 in-flight requests.
        # Tune down if you hit 429 rate-limit errors.
        max_workers = int(os.getenv("MAX_CONCURRENT_REQUESTS", "16"))

        if args.deepdive:
            log_ipc(f"PROGRESS:ANALYZING:Starting AI DeepDive ({max_workers} workers)...")
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(deepdive_analysis_worker, api_key, f, model_name): f
                    for f in translatable
                }
                aux_count = 0
                for future in as_completed(futures):
                    aux_count += 1
                    try:
                        changed, fname = future.result()
                        status = "Analyzed" if changed else "Skipped"
                        log_ipc(f"PROGRESS:ANALYZING:{aux_count}:{len(translatable)}:{status} {fname}")
                    except Exception as e:
                        logger.error(f"DeepDive future error: {e}")

        # ── Phase 1+2: Parallel Text-Node Translation ─────────────────────
        total_files = len(translatable)
        log_ipc(f"PROGRESS:TRANSLATING:0:{total_files}:Starting text-node translation ({model_name})...")

        completed_count = 0
        total_failed_nodes = 0
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(translate_file_worker, api_key, model_name, f): f
                for f in translatable
            }
            for future in as_completed(futures):
                file_path = futures[future]
                file_name = os.path.basename(file_path)
                completed_count += 1
                try:
                    success, _, failed_nodes = future.result()
                    total_failed_nodes += failed_nodes
                    if success:
                        log_ipc(f"PROGRESS:TRANSLATING:{completed_count}:{total_files}:Translated {file_name}")
                    else:
                        log_ipc(f"PROGRESS:TRANSLATING:{completed_count}:{total_files}:Failed {file_name}")
                except Exception as exc:
                    logger.error(f"Worker exception for {file_name}: {exc}", exc_info=True)
                    log_ipc(f"PROGRESS:TRANSLATING:{completed_count}:{total_files}:Error {file_name}")

        # Surface translation failures to the user via IPC
        if total_failed_nodes > 0:
            log_ipc(
                f"PROGRESS:WARN:Translation incomplete — {total_failed_nodes} segment(s) "
                f"kept in original English due to API errors. "
                f"PDF may contain mixed-language content."
            )

        # ── Phase 3: Post-Processing ───────────────────────────────────────
        log_ipc(f"PROGRESS:POST_PROCESSING:Applying robustness fixes...")
        apply_post_processing(source_zh_dir, main_tex)

        # ── Phase 4: Compile + Error-Driven Fix Loop ──────────────────────
        log_ipc(f"PROGRESS:COMPILING:Compiling PDF (with AI fix loop)...")

        suffix = "_zh_deepdive" if args.deepdive else "_zh"
        final_pdf = args.output or f"{arxiv_id}{suffix}.pdf"

        success, log = compile_with_fix_loop(
            source_zh_dir,
            main_tex,
            api_key=api_key,
            model_name=model_name,
            max_attempts=3,
            timeout=200,
        )

        # Locate the compiled PDF
        pdf_name = os.path.basename(main_tex).replace(".tex", ".pdf")
        compiled_pdf = os.path.join(source_zh_dir, pdf_name)

        if success and os.path.exists(compiled_pdf):
            shutil.copy(compiled_pdf, final_pdf)
            logger.info(f"SUCCESS: Generated {final_pdf}")
            if total_failed_nodes > 0:
                log_ipc(
                    f"PROGRESS:COMPLETED_WITH_WARNINGS:{total_failed_nodes} segment(s) kept in English "
                    f"due to API errors."
                )
            else:
                log_ipc(f"PROGRESS:COMPLETED:Translation finished successfully.")
        else:
            logger.error("PDF generation failed after all attempts.")
            log_ipc(f"PROGRESS:FAILED:PDF compilation failed after all attempts.")

    except Exception as e:
        logger.error(f"Translation FAILED: {e}", exc_info=True)
        log_ipc(f"PROGRESS:FAILED:{str(e)[:200]}")
    finally:
        if not args.keep:
            pass  # Keep workspace for debugging; uncomment to clean: shutil.rmtree(work_dir)


if __name__ == "__main__":
    main()
