import subprocess
import os
import shutil
from .logging_utils import logger

def compile_pdf(source_dir: str, main_tex_file: str):
    """
    Compiles the LaTeX project to PDF using latexmk.
    Supports both native execution (if latexmk is installed) and Docker fallback.
    
    Args:
        source_dir (str): The directory containing the source files.
        main_tex_file (str): The path to the main .tex file.
    """
    # Ensure we are in the source dir
    cwd = os.getcwd()
    os.chdir(source_dir)
    
    # main_tex_file might be absolute, we need relative for latexmk usually
    rel_tex_file = os.path.basename(main_tex_file)
    
    logger.info(f"Compiling {rel_tex_file} in {source_dir}...")
    
    try:
        # Check if latexmk is installed natively
        latexmk_path = shutil.which("latexmk")

        # Explicit check for common MacOS TeX paths if not found in PATH
        if not latexmk_path and os.uname().sysname == 'Darwin':
             possible_paths = [
                 "/Library/TeX/texbin/latexmk",
                 "/usr/local/bin/latexmk",
                 "/opt/homebrew/bin/latexmk"
             ]
             for p in possible_paths:
                 if os.path.exists(p) and os.access(p, os.X_OK):
                     latexmk_path = p
                     logger.info(f"Found latexmk content at {p} via explicit check.")
                     break
        
        if latexmk_path:
            logger.info(f"Found native latexmk at {latexmk_path}. Using native compilation.")
            # Native execution (Cloud Run or Local with TeX Live)
            cmd = [
                "latexmk", "-xelatex", "-bibtex", "-interaction=nonstopmode", "-f", "-file-line-error", "-outdir=.", rel_tex_file
            ]
        else:
            logger.info("Native latexmk not found. Falling back to Dockerized TeX Live.")
            # Docker fallback (Local Dev without TeX Live)
            uid = os.getuid()
            gid = os.getgid()
            docker_image = "ghcr.io/xu-cheng/texlive-full:latest" # Use specific image for consistency
            
            cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "-v", f"{os.path.abspath(source_dir)}:/workdir",
                "-w", "/workdir",
                "--user", f"{uid}:{gid}",
                docker_image,
                "latexmk", "-xelatex", "-bibtex", "-interaction=nonstopmode", "-f", "-file-line-error", "-outdir=.", rel_tex_file
            ]
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.warning(f"Compilation finished with return code {result.returncode}")
            logger.warning("Compilation had warnings/errors.")
            logger.warning(f"STDOUT: {result.stdout[-2000:]}") # Last 2000 chars
            logger.warning(f"STDERR: {result.stderr[-2000:]}")
            # return False # We tolerate warnings if PDF is generated
        else:
            logger.info("Compilation successful.")
            
        # Verify PDF generation
        pdf_name = rel_tex_file.replace(".tex", ".pdf")
        if os.path.exists(pdf_name):
            return True, ""
        else:
            logger.error("PDF was not generated despite return code.")
            # Capture relevant error from log
            combined_log = result.stdout + "\n" + result.stderr
            return False, combined_log[-3000:] # Return last 3000 chars of log

    except Exception as e:
        logger.error(f"Compiler error: {e}")
        return False, str(e)
    finally:
        os.chdir(cwd)
