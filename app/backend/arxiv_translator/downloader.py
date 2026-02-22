import requests
import os
import shutil
import tarfile
import gzip
from .logging_utils import logger

def download_source(arxiv_id: str, output_dir: str) -> str:
    """
    Downloads the source files for a given arXiv ID.
    
    Args:
        arxiv_id (str): The arXiv ID (e.g., '2602.04705').
        output_dir (str): The directory to save the downloaded file.
        
    Returns:
        str: The path to the downloaded file.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    filename = f"{arxiv_id}.tar.gz" # arXiv source is usually a tarball
    output_path = os.path.join(output_dir, filename)
    
    logger.info(f"Downloading source based on {arxiv_id} from {url}...")
    
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    logger.info(f"Downloaded to {output_path}")
    return output_path


def extract_source(archive_path: str, output_dir: str) -> str:
    """
    Extracts an arXiv source archive (tar.gz or single .tex file) to output_dir.
    
    Args:
        archive_path: Path to the downloaded archive.
        output_dir: Directory to extract files into.
        
    Returns:
        The output directory path.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Try as tarball first (most common)
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(path=output_dir, filter='data')
            logger.info(f"Extracted tarball to {output_dir}")
    except tarfile.TarError:
        try:
            # Try as gzipped single file
            tex_path = os.path.join(output_dir, "main.tex")
            with gzip.open(archive_path, 'rb') as gz:
                content = gz.read()
            with open(tex_path, 'wb') as f:
                f.write(content)
            logger.info(f"Extracted single gzipped file to {tex_path}")
        except Exception:
            # Last resort: copy as-is (might be a plain .tex)
            tex_path = os.path.join(output_dir, "main.tex")
            shutil.copy2(archive_path, tex_path)
            logger.info(f"Copied file as plain tex: {tex_path}")
    
    return output_dir
