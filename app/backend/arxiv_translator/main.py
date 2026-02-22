"""
arXiv LaTeX Translator — Simplified Pipeline

Leverages Gemini 3.0 Flash's 1M context window to translate each .tex file
in its entirety. No text-node extraction, no batching, no delimiter splitting.

Pipeline:
  1. DOWNLOAD   — Fetch arXiv source tarball
  2. EXTRACT    — Unpack and analyse paper structure
  3. TRANSLATE  — Per-file async Gemini API calls (one file = one call)
  4. COMPILE    — pdflatex/xelatex compilation
"""

import argparse
import asyncio
import os
import shutil
import sys

from .analyzer import PaperAnalyzer
from .compiler import compile_with_fix_loop
from .config_manager import ConfigManager
from .downloader import download_source, extract_source
from .logging_utils import logger, log_ipc
from .translator import GeminiTranslator
from .latex_cleaner import clean_latex_directory

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Per-file translation worker ──────────────────────────────────────────────

async def translate_one_file(
    translator: GeminiTranslator,
    filepath: str,
    file_idx: int,
    total_files: int,
) -> tuple[str, int, int, bool]:
    """
    Translate a single .tex file in-place.
    Returns (filename, in_tokens, out_tokens, success).
    """
    filename = os.path.basename(filepath)

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Skip very short files (style files, empty stubs)
        if len(content.strip()) < 50:
            logger.info(f"[{filename}] Too short ({len(content)} chars), skipping")
            log_ipc(f"PROGRESS:FILE_DONE:{filename}:ok")
            return filename, 0, 0, True

        # Translate entire file
        translated, in_tok, out_tok = await translator.translate_file(content, filename)

        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(translated)

        # Report progress
        log_ipc(f"PROGRESS:TRANSLATING:{file_idx}:{total_files}:✅ {filename} | In {in_tok:,}/Out {out_tok:,} tokens")
        log_ipc(f"PROGRESS:TOKENS_TOTAL:{in_tok}:{out_tok}:{filename}")
        log_ipc(f"PROGRESS:FILE_DONE:{filename}:ok")

        return filename, in_tok, out_tok, True

    except Exception as e:
        logger.error(f"[{filename}] Translation failed: {e}", exc_info=True)
        log_ipc(f"PROGRESS:TRANSLATING:{file_idx}:{total_files}:❌ {filename} failed")
        log_ipc(f"PROGRESS:FILE_DONE:{filename}:fail")
        return filename, 0, 0, False


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="arXiv LaTeX Translator (Simplified)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("arxiv_url", nargs="?", help="arXiv URL or ID")
    group.add_argument("--set-key", help="Save Gemini API key to config and exit")

    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model")
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

    logger.info(f"Starting translation for {arxiv_id} using {model_name}")

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

        # ── Structural Analysis ───────────────────────────────────────────
        log_ipc(f"PROGRESS:EXTRACTING:Analyzing paper structure...")
        analyzer = PaperAnalyzer(source_zh_dir)
        structure = analyzer.analyze()
        main_tex = structure.main_tex

        translatable = structure.translatable_files()
        skipped = structure.skip_files()
        logger.info(f"Main tex: {os.path.relpath(main_tex, source_zh_dir)}")
        logger.info(f"Files to translate: {len(translatable)}, to skip: {len(skipped)}")

        # ── Clean LaTeX comments ──────────────────────────────────────────
        log_ipc(f"PROGRESS:EXTRACTING:Cleaning LaTeX comments...")
        cleaned_count = clean_latex_directory(source_zh_dir)
        logger.info(f"Cleaned {cleaned_count} files")

        # ── Translate all files concurrently ──────────────────────────────
        total_files = len(translatable)
        file_list_names = "|".join(os.path.basename(f) for f in translatable)
        log_ipc(f"PROGRESS:FILE_LIST:{file_list_names}")
        log_ipc(f"PROGRESS:TRANSLATING:0:{total_files}:Starting whole-file translation ({model_name})...")

        translator = GeminiTranslator(api_key=api_key, model_name=model_name)

        # Run all file translations concurrently with asyncio
        async def run_all():
            # Use a semaphore to limit concurrent API calls
            max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", "4"))
            semaphore = asyncio.Semaphore(max_concurrent)

            async def guarded_translate(filepath, idx):
                async with semaphore:
                    return await translate_one_file(translator, filepath, idx, total_files)

            tasks = [
                guarded_translate(f, i + 1)
                for i, f in enumerate(translatable)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run_all())

        # Summarize results
        total_in = sum(r[1] for r in results)
        total_out = sum(r[2] for r in results)
        failed_files = [r[0] for r in results if not r[3]]

        if failed_files:
            log_ipc(
                f"PROGRESS:WARN:{len(failed_files)} file(s) failed translation: "
                f"{', '.join(failed_files)}"
            )

        logger.info(f"Translation complete — In: {total_in:,} / Out: {total_out:,} tokens total")
        logger.info(f"Failed files: {len(failed_files)}/{total_files}")

        # ── Compile PDF ───────────────────────────────────────────────────
        log_ipc(f"PROGRESS:COMPILING:Compiling PDF (pdfLaTeX)...")

        suffix = "_zh_deepdive" if args.deepdive else "_zh"
        final_pdf = args.output or f"{arxiv_id}{suffix}.pdf"

        success, compile_error = compile_with_fix_loop(
            source_dir=source_zh_dir,
            main_tex=main_tex,
            api_key=api_key,
            model_name=model_name,
            timeout=200,
        )

        # Locate the compiled PDF
        pdf_name = os.path.basename(main_tex).replace(".tex", ".pdf")
        compiled_pdf = os.path.join(source_zh_dir, pdf_name)

        if success and os.path.exists(compiled_pdf):
            shutil.copy(compiled_pdf, final_pdf)
            logger.info(f"SUCCESS: Generated {final_pdf}")
            if failed_files:
                log_ipc(
                    f"PROGRESS:COMPLETED_WITH_WARNINGS:{len(failed_files)} file(s) "
                    f"could not be translated."
                )
            else:
                log_ipc(f"PROGRESS:COMPLETED:Translation finished successfully.")
        else:
            logger.error("PDF generation failed.")
            error_msg = compile_error[:1500] if compile_error else "PDF compilation failed."
            log_ipc(f"PROGRESS:FAILED:{error_msg}")

    except Exception as e:
        logger.error(f"Translation FAILED: {e}", exc_info=True)
        log_ipc(f"PROGRESS:FAILED:{str(e)[:200]}")
    finally:
        if not args.keep:
            pass  # Keep workspace for debugging


if __name__ == "__main__":
    main()
