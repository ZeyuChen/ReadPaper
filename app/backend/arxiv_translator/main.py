import argparse
import os
import shutil
import sys
from .downloader import download_source
from .extractor import extract_source, find_main_tex
from .translator import GeminiTranslator
from .compiler import compile_pdf
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



def deepdive_analysis_worker(api_key, file_path, model_name="gemini-3-flash-preview"):
    try:
        analyzer = DeepDiveAnalyzer(api_key, model_name=model_name)
        file_name = os.path.basename(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        analyzed = analyzer.analyze_latex(content, file_name)
        
        if analyzed != content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(analyzed)
            return True, file_name
        return False, file_name
    except Exception as e:
        logger.error(f"DeepDive worker failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return False, os.path.basename(file_path)

def translate_file_worker(api_key, model_name, file_path, main_tex_path):
    import re
    try:
        file_name = os.path.basename(file_path)
        # Re-instantiate translator in worker process
        translator = GeminiTranslator(api_key=api_key, model_name=model_name)
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            

            
        translated = translator.translate_latex(content)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(translated)
            
        return True
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(translated)
            
        return True
    except Exception as e:
        # Worker failure logged by executor usually, but good to be explicit
        logger.error(f"Worker failed for {file_path}: {e}")
        raise e

def main():
    # Force line buffering for real-time progress updates
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
        
    parser = argparse.ArgumentParser(description="arXiv LaTeX Translator - Translate arXiv papers to Chinese")
    
    # Exclusive group for mutually exclusive actions (translate vs config)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("arxiv_url", nargs="?", help="URL or ID of the arXiv paper (e.g., https://arxiv.org/abs/2602.04705)")
    group.add_argument("--set-key", help="Save Gemini API key to configuration and exit")
    
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model to use (flash or pro)")
    parser.add_argument("--output", "-o", help="Custom output path for the translated PDF")
    parser.add_argument("--keep", action="store_true", help="Keep intermediate files for debugging")
    parser.add_argument("--deepdive", action="store_true", help="Enable AI DeepDive (Technical Analysis)")
    
    args = parser.parse_args()
    config_manager = ConfigManager()

    # Handle --set-key
    if args.set_key:
        config_manager.set_api_key(args.set_key)
        sys.exit(0)

    # Check for arXiv URL/ID
    if not args.arxiv_url:
        parser.print_help()
        sys.exit(1)

    # Load API Key: CLI (not arg here, but maybe future) > Env > Config
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = config_manager.get_api_key()
    
    if not api_key:
        print("Error: Gemini API Key not found.")
        print("Please set it via environment variable GEMINI_API_KEY")
        print("OR run: arxiv-translator --set-key YOUR_API_KEY")
        sys.exit(1)

    # Handle model aliases
    model_name = args.model
    if model_name.lower() == "flash":
        model_name = "gemini-3-flash-preview"
    elif model_name.lower() == "pro":
        model_name = "gemini-3-pro-preview"
    
    # Extract ID
    # heuristics: 2602.04705 or https://arxiv.org/abs/2602.04705 or https://arxiv.org/pdf/2602.04705
    arxiv_id = args.arxiv_url.split("/")[-1].replace(".pdf", "")

    arxiv_id = args.arxiv_url.split("/")[-1].replace(".pdf", "")

    logger.info(f"Starting translation for {arxiv_id} using model {model_name}")
    logger.info(f"DeepDive Mode: {'ENABLED' if args.deepdive else 'DISABLED'}")
    # print(f"Using model: {model_name}") # Logged above
        
    work_dir = os.path.abspath(f"workspace_{arxiv_id}")
    
    if os.path.exists(work_dir) and not args.keep:
         shutil.rmtree(work_dir)
    
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)
    
    logger.info(f"Work directory: {work_dir}")
    # print(f"Work directory: {work_dir}") # Logged above
    
    try:
        # 1. Download source
        log_ipc(f"PROGRESS:DOWNLOADING:Downloading source for {arxiv_id}...")
        tar_path = os.path.join(work_dir, f"{arxiv_id}.tar.gz")
        if not os.path.exists(tar_path):
             tar_path = download_source(arxiv_id, work_dir)
             logger.info(f"Downloaded source to {tar_path}")
        else:
             logger.info("Using existing source archive.")
        
        # 2. Extract
        # 2. Extract
        log_ipc(f"PROGRESS:EXTRACTING:Extracting source files...")
        source_dir = os.path.join(work_dir, "source")
        if not os.path.exists(source_dir):
            extract_source(tar_path, source_dir)
        
        # 3. Translate
        # Copy source to source_zh
        source_zh_dir = os.path.join(work_dir, "source_zh")
        if os.path.exists(source_zh_dir):
            shutil.rmtree(source_zh_dir) # Always fresh copy for translation
        shutil.copytree(source_dir, source_zh_dir)
        
        # 2.5 Clean LaTeX comments
        log_ipc(f"PROGRESS:EXTRACTING:Cleaning LaTeX comments...")
        cleaned_count = clean_latex_directory(source_zh_dir)
        logger.info(f"Cleaned {cleaned_count} files in {source_zh_dir}")
        
        main_tex = find_main_tex(source_zh_dir)
        logger.info(f"Main TeX file found: {main_tex}")
        # print(f"Main TeX file: {main_tex}", flush=True)
        
        translator = GeminiTranslator(api_key=api_key, model_name=model_name)
        
        # Translate all TeX files
        # Translate all TeX files
        log_ipc(f"PROGRESS:TRANSLATING:0:0:Starting translation with {model_name}...")
        
        # Pre-count and collect files
        tex_files_to_translate = []
        for root, dirs, files in os.walk(source_zh_dir):
            for file in files:
                if file == "math_commands.tex":
                    # print(f"Skipping {file} (definitions)...")
                    continue
                if file.endswith(".tex"):
                     tex_files_to_translate.append(os.path.join(root, file))
        
        total_files = len(tex_files_to_translate)
        total_files = len(tex_files_to_translate)
        logger.info(f"Found {total_files} TeX files to translate.")
        
        max_workers = int(os.getenv("MAX_CONCURRENT_REQUESTS", 8))
        logger.info(f"Using {max_workers} concurrent workers.")
        
        # 3. DeepDive Analysis (Now runs on English source BEFORE translation)
        from concurrent.futures import ProcessPoolExecutor, as_completed

        if args.deepdive:
            log_ipc(f"PROGRESS:ANALYZING:Starting parallel AI DeepDive Analysis ({max_workers} workers)...")
            aux_count = 0
            
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(deepdive_analysis_worker, api_key, f, model_name): f 
                    for f in tex_files_to_translate
                }
                
                for future in as_completed(future_to_file):
                    f_path = future_to_file[future]
                    fname = os.path.basename(f_path)
                    aux_count += 1
                    try:
                        is_changed, _ = future.result()
                        if is_changed:
                            log_ipc(f"PROGRESS:ANALYZING:{aux_count}:{total_files}:Analyzed {fname}")
                        else:
                            log_ipc(f"PROGRESS:ANALYZING:{aux_count}:{total_files}:Skipped {fname}")
                    except Exception as e:
                        logger.error(f"Analysis failed for {fname}: {e}", exc_info=True)

        # 4. Concurrent Translation
        
        # Helper to be pickled
        # define worker inside main or import? needs to be picklable, so top level is best.
        # But we can't move it easily with replace_file_content unless we replace whole file or use a separate file.
        # We can define it at top of main() but better at module level.
        # Impl note: python multiprocessing needs top-level function.
        # I will use a separate small replace to add the worker function at the top, or just put it here if I am replacing a big chunk.
        # Actually, I can't put it here inside main().
        # I HAVE TO MOVE IT OUT.
        # I will replace the whole file or add it before main().
        # Since I am using replace_file_content on a range, I can't easily add to top.
        # Strategy: 
        # 1. Use `replace_file_content` to add imports and the worker function BEFORE `main`.
        # 2. Use `replace_file_content` to rewrite the loop inside `main`.
        
        # Let's do step 2 (loop rewrite) here assuming step 1 (worker def) is done? 
        # No, sequential tools. I should abort this tool call and do the worker def first.
        # But I can't abort myself.
        # I will use this tool call to rewrite the loop, but call the worker `translate_file_worker` which I will define in the NEXT tool call at the top of the file?
        # Python will fail if I run it before defining. But I am editing code.
        # I will define `translate_file_worker` in the NEXT tool call at the top.
        # WAIT, if I edit the loop to call `translate_file_worker`, and then edit top to add it, the file is broken in between. That's fine.
        
        completed_count = 0
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(translate_file_worker, api_key, model_name, f, main_tex): f 
                for f in tex_files_to_translate
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                file_name = os.path.basename(file_path)
                completed_count += 1
                try:
                    res = future.result()
                    # res is boolean or message?
                    log_ipc(f"PROGRESS:TRANSLATING:{completed_count}:{total_files}:Translated {file_name}")
                except Exception as exc:
                    logger.error(f"Generated an exception for {file_name}: {exc}", exc_info=True)
                    log_ipc(f"PROGRESS:TRANSLATING:{completed_count}:{total_files}:Failed {file_name}")



        # 4. Compile
        
        # 3.8 Post-Processing (Robustness Fixes)
        log_ipc(f"PROGRESS:POST_PROCESSING:Applying robustness fixes...")
        apply_post_processing(source_zh_dir, main_tex)
        
        log_ipc(f"PROGRESS:COMPILING:Compiling PDF with Latexmk...")
        success, error_log = compile_pdf(source_zh_dir, main_tex)
        
        if not success:
            logger.warning("Initial compilation failed. Attempting AI Recovery...")
            log_ipc(f"PROGRESS:COMPILING:Initial compilation failed. Attempting AI Recovery...")
            
            # AI Recovery Logic
            try:
                from .latex_fixer import LatexFixer
                fixer = LatexFixer(api_key, model_name="gemini-3-flash-preview")
                
                # Read broken content
                with open(main_tex, 'r', encoding='utf-8') as f:
                    broken_content = f.read()
                    
                # Fix
                fixed_content = fixer.fix_latex(broken_content, error_log)
                
                if fixed_content != broken_content:
                    # Overwrite
                    with open(main_tex, 'w', encoding='utf-8') as f:
                        f.write(fixed_content)
                    
                    logger.info("Applied AI fix to main.tex. Retrying compilation...")
                    log_ipc(f"PROGRESS:COMPILING:Retrying compilation with AI fixes...")
                    
                    success, error_log = compile_pdf(source_zh_dir, main_tex)
                else:
                    logger.warning("AI Fixer returned code without changes. Skipping retry.")
                    
            except Exception as fix_e:
                logger.error(f"AI Recovery failed: {fix_e}", exc_info=True)
        
        # Move PDF to root or custom output
        pdf_name = os.path.basename(main_tex).replace(".tex", ".pdf")
        compiled_pdf = os.path.join(source_zh_dir, pdf_name)
        
        # Suffix handling
        if args.output:
            final_pdf = args.output
        else:
            suffix = "_zh"
            if args.deepdive:
                suffix = "_zh_deepdive"
            
            final_pdf = f"{arxiv_id}{suffix}.pdf"
        
        if success and os.path.exists(compiled_pdf):
            shutil.copy(compiled_pdf, final_pdf)
            logger.info(f"SUCCESS: Generated {final_pdf}")
            log_ipc(f"PROGRESS:COMPLETED:Translation finished successfully.")
        else:
            logger.error("ERROR: PDF was not generated.")
            log_ipc(f"PROGRESS:FAILED:PDF compilation failed.")
            
    except Exception as e:
        logger.error(f"Translation FAILED: {e}", exc_info=True)
        print(f"FAILED: {e}") # Print to stdout for CLI visibility if logger goes to stderr only
        # traceback.print_exc() # Handled by exc_info=True in logger
    finally:
        if not args.keep:
            # shutil.rmtree(work_dir)
            pass # Keep by default for debug
            
if __name__ == "__main__":
    main()
