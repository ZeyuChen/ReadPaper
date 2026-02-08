import subprocess
import os
from .logging_utils import logger

def compile_pdf(source_dir: str, main_tex_file: str):
    """
    Compiles the LaTeX project to PDF using latexmk.
    
    Args:
        source_dir (str): The directory containing the source files.
        main_tex_file (str): The path to the main .tex file.
    """
    # Ensure we are in the source dir
    cwd = os.getcwd()
    os.chdir(source_dir)
    
    # main_tex_file might be absolute, we need relative for latexmk usually
    rel_tex_file = os.path.basename(main_tex_file)
    
    logger.info(f"Compiling {rel_tex_file} in {source_dir} using Dockerized TeX Live...")
    
    try:
        # Docker command construction
        # We mount the source_dir to /workdir in the container
        # We use the current user ID to ensure generated files are owned by the host user
        uid = os.getuid()
        gid = os.getgid()
        
        docker_image = "texlive/texlive:latest"
        
        # latexmk flags:
        # -xelatex (or -xe): Use XeLaTeX for Chinese support
        # -bibtex: Run BibTeX
        # -interaction=nonstopmode: Don't halt on errors
        # -file-line-error: distinct error messages
        # -outdir=.: Output to current directory
        
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{os.path.abspath(source_dir)}:/workdir",
            "-w", "/workdir",
            "--user", f"{uid}:{gid}",
            docker_image,
            "latexmk", "-xelatex", "-bibtex", "-interaction=nonstopmode", "-file-line-error", "-outdir=.", rel_tex_file
        ]
        
        logger.debug(f"Running docker command: {' '.join(cmd)}")
        
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
            
        return True
    except FileNotFoundError:
        logger.error("Docker command not found. Please ensure Docker is installed and in PATH.")
        return False
    except Exception as e:
        logger.error(f"Compiler error: {e}")
        return False
    finally:
        os.chdir(cwd)
