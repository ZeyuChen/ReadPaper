import os
import re
import logging

logger = logging.getLogger(__name__)

def clean_latex_content(content: str) -> str:
    """
    Removes LaTeX comments to reduce token count.
    Handles:
    1. 'comment' environment blocks: \\begin{comment} ... \\end{comment}
    2. Lines starting with % (ignoring whitespace)
    """
    # Strategy: Split content into chunks: (is_verbatim, text)
    # Then only clean text where is_verbatim is False.
    
    # 1. Regex to find verbatim blocks
    # Supporting standard `verbatim` and `verbatim*`. Also `lstlisting` if common? 
    # Let's start with `verbatim` and `verbatim*`.
    verbatim_pattern = re.compile(r'(\\begin\{verbatim\*?\}.*?\\end\{verbatim\*?\})', flags=re.DOTALL)
    
    parts = verbatim_pattern.split(content)
    # split returns [pre, match, post, match, post...]
    # Even indices are non-verbatim (safe to clean), Odd indices are verbatim blocks (keep as is).
    
    processed_parts = []
    
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # This is a verbatim block, keep as is
            processed_parts.append(part)
        else:
            # This is normal LaTeX, clean it
            
            # A. Remove comment environment blocks (re-applied here on safe chunks)
            # regex for \begin{comment} ... \end{comment}
            part = re.sub(r'\\begin\{comment\}.*?\\end\{comment\}(?:\r?\n)?', '', part, flags=re.DOTALL)
            
            # B. Remove lines starting with %
            lines = part.splitlines(keepends=True) # Keep ends to preserve structure better
            cleaned_lines = []
            for line in lines:
                if not line.strip().startswith('%'):
                    cleaned_lines.append(line)
            
            cleaned_part = ''.join(cleaned_lines)
            processed_parts.append(cleaned_part)
            
    result = ''.join(processed_parts)
    
    # 3. Collapse multiple blank lines (max 2)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result

def clean_latex_file(file_path: str) -> bool:
    """
    Reads a LaTeX file, cleans it, and writes back if changed.
    Returns True if file was modified.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        cleaned = clean_latex_content(content)
        
        if len(cleaned) < len(content):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            return True
    except Exception as e:
        logger.error(f"Error cleaning {file_path}: {e}")
    return False

def clean_latex_directory(directory: str) -> int:
    """
    Recursively cleans all .tex files in a directory.
    Returns number of files modified.
    """
    modified_count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.tex'):
                file_path = os.path.join(root, file)
                if clean_latex_file(file_path):
                    modified_count += 1
    return modified_count
