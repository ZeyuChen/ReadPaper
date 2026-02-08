import os
import re
from .logging_utils import logger



def apply_post_processing(source_dir: str, main_tex_path: str):
    """
    Applies regex substitutions and fixes to all .tex files in the source directory.
    Targeting common issues in translated LaTeX.
    """
    # 1. Identify all tex files
    tex_files = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".tex"):
                tex_files.append(os.path.join(root, file))

    logger.info(f"Post-processing {len(tex_files)} files in {source_dir}...")

    # 2. Process all tex files
    for file_path in tex_files:
        _process_single_file(file_path, main_tex_path)

    # 3. Process bib files
    bib_files = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".bib"):
                bib_files.append(os.path.join(root, file))

    for file_path in bib_files:
        _process_bib_file(file_path)

def _process_bib_file(file_path: str):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        original_content = content
        
        # 1. Double 'and' in author list (causes Tectonic panic)
        # matches " and and " with any whitespace
        content = re.sub(r'\s+and\s+and\s+', ' and ', content, flags=re.IGNORECASE)
        
        if content != original_content:
            logger.debug(f"Applied fixes to .bib file {os.path.basename(file_path)}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
    except Exception as e:
        logger.error(f"Post-processing failed for .bib file {file_path}: {e}")

def _process_single_file(file_path: str, main_tex_path: str):
    try:
        file_name = os.path.basename(file_path)
        # Determine if this is the MAIN tex file
        # We need absolute paths comparison
        is_main = os.path.abspath(file_path) == os.path.abspath(main_tex_path)
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        original_content = content
        
        # --- fixes ---
        
        # 0. Strip chatty preamble (e.g. "Here is the translation:")
        # 0. Strip chatty preamble (e.g. "Here is the translation:")
        # Find index of \documentclass
        doc_class_match = re.search(r'\\documentclass', content)
        if doc_class_match:
            start_idx = doc_class_match.start()
            if start_idx > 0:
                # Check if preceding content is just comments/whitespace
                preceding = content[:start_idx]
                if not all(line.strip().startswith('%') or not line.strip() for line in preceding.splitlines()):
                     logger.warning(f"Stripping conversational preamble from {file_name}")
                     content = content[start_idx:]

        # 1. Remove CJK packages (ctex handles this)
        # We only remove from preamble, which is usually in main.tex or imported styles.
        # But safer to remove globally if they appear
        # Use simple string replacement for safety where possible, or function
        content = re.sub(r'\\usepackage\s*\{CJK.*\}', '% usepackage{CJK...} removed', content)
        content = re.sub(r'\\usepackage\s*\{xeCJK\}', '% usepackage{xeCJK} removed', content)
        content = re.sub(r'\\usepackage\s*\{CJKutf8\}', '% usepackage{CJKutf8} removed', content)
        
        # 2. Inject ctex if missing in MAIN file
        if is_main:
             if "\\documentclass" in content and "ctex" not in content:
                 # Standard injection before begin document
                 preamble = "\n\\\\usepackage[fontset=fandol]{ctex}\n\\\\usepackage{xspace}\n"
                 if "\\begin{document}" in content:
                     content = content.replace("\\begin{document}", preamble.replace("\\\\", "\\") + "\\begin{document}")
                 else:
                     # Fallback: inject after documentclass
                     # Use function for replacement to avoid escape issues
                     def inject_preamble(match):
                         return match.group(1) + "\n\\usepackage[fontset=fandol]{ctex}\n\\usepackage{xspace}\n"
                     
                     content = re.sub(r'(\\documentclass\[.*?\]\{.*?\})', inject_preamble, content)

        # 3. Remove CJK environments (legacy)
        content = re.sub(r'\\begin\{CJK\*\}\{.*?\}\{.*?\}', '', content)
        content = re.sub(r'\\end\{CJK\*\}', '', content)
        
        # Also handle \begin{CJK}{UTF8}{gbsn} without *
        content = re.sub(r'\\begin\{CJK\}\{.*?\}\{.*?\}', '', content)
        content = re.sub(r'\\end\{CJK\}', '', content)

        # 4. Fix \chinese macro conflict (common in arXiv templates)
        if r"\chinese" in content:
             # Lookahead negative assertion to avoid replacing \chinesefont
             # Replace \chinese with \mychinese. In replacement string, \\\\ becomes \\
             content = re.sub(r'\\chinese(?![a-zA-Z])', r'\\\\mychinese', content)
             
             # Simplify definition if present (e.g. \newcommand{\chinese}[1]{...})
             if r"\newcommand{\mychinese}" in content or r"\def\mychinese" in content:
                 content = re.sub(
                    r'\\newcommand\{\\mychinese\}\[1\]\{.*?\}', 
                    r'\\\\newcommand{\\\\mychinese}[1]{#1}', 
                    content, 
                    flags=re.DOTALL
                 )

        # 5. Minted package options
        if "{minted}" in content:
             content = re.sub(r'\\usepackage\[.*?\]\{minted\}', r'\\usepackage[outputdir=.]{minted}', content)

        # 5.1 Inject tcolorbox if used but missing
        if "tcolorbox" in content and "{tcolorbox}" not in content:
            # Inject after xcolor or documentclass
            if "{xcolor}" in content:
                content = content.replace("{xcolor}", "{xcolor}\n\\usepackage{tcolorbox}")
            else:
                 # Fallback injection
                 if "\\documentclass" in content:
                     def inject_package(match):
                         return match.group(1) + "\n\\usepackage{tcolorbox}\n"
                     content = re.sub(r'(\\documentclass\[.*?\]\{.*?\})', inject_package, content)

        # 6. Backend switch (biber -> bibtex)
        if "backend=biber" in content:
            content = content.replace("backend=biber", "backend=bibtex")

        # 7. Duplicate labels
        # Scan for \label{...} and keep only first occurrence of each unique label
        # We need to use a function-level set for labels?
        # NO, labels must be unique GLOBALLY.
        # But here we are processing file-by-file.
        # If we want global uniqueness, we need to pass a shared set.
        # However, processing sequentially allows this if we pass the set.
        # Let's pass a set? No, that requires changing the signature in the loop.
        # Ideally, main.py passes a set?
        # Or, we just fix LOCAL duplicates (LLM repeating same section).
        # Global duplicates (between files) are rare unless files are duplicated.
        # Let's stick to local uniqueness for now as in main.py.
        
        label_pattern = re.compile(r'\\label\{([^}]+)\}')
        seen_labels = set()
        
        def replace_label(match):
            lbl = match.group(1)
            if lbl in seen_labels:
                return f"% Duplicate label removed: {lbl}"
            seen_labels.add(lbl)
            return match.group(0)
            
        content = label_pattern.sub(replace_label, content)
        
        # 8. Escaped braces fix
        content = content.replace(r"\ }", r"\}")
        content = content.replace(r"\ {", r"\{")
        
        # 9. Unicode replacement / Safety
        # (Implicit via file writing encoding)
        
        if content != original_content:
            logger.debug(f"Applied Post-Processing fixes to {file_name}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
    except Exception as e:
        logger.error(f"Post-processing failed for {file_path}: {e}")
