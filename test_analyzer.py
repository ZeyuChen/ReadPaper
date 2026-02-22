import os
import sys
import asyncio

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app', 'backend')))

from arxiv_translator.downloader import download_source
from arxiv_translator.extractor import extract_source
from arxiv_translator.analyzer import PaperAnalyzer

async def test():
    arxiv_id = "2602.05400"
    work_dir = f"/tmp/workspace_{arxiv_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    print(f"Downloading source for {arxiv_id}...")
    tarball = download_source(arxiv_id, work_dir)
    print(f"Downloaded to {tarball}")
    
    print("Extracting...")
    source_dir = os.path.join(work_dir, "source")
    extract_source(tarball, source_dir)
    print(f"Extracted to {source_dir}")
    
    print("Analyzing structure...")
    analyzer = PaperAnalyzer(source_dir)
    struct = analyzer.analyze()
    print(f"Main TeX: {struct.main_tex}")
    
    print("All files:")
    for path, info in struct.files.items():
        rel = os.path.relpath(path, source_dir)
        print(f"  - {rel}: {info.file_type}")

if __name__ == "__main__":
    asyncio.run(test())
