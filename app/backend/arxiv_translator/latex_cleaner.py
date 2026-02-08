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
    
    # 4. Fix potential environment Imbalance (caused by chunked translation)
    result = fix_latex_imbalance(result)
    
    # 5. Fix known packaging conflicts (e.g. booktabs vs colortbl)
    result = fix_package_conflicts(result)
    
    return result

def fix_package_conflicts(content: str) -> str:
    """
    Reorders packages to prevent known LaTeX conflicts.
    1. Ensures 'colortbl' is loaded BEFORE 'booktabs'.
    """
    # Regex to capture usepackage lines
    # We want to identify if booktabs and colortbl exist
    # Pattern: \usepackage[opt]{name} or \usepackage{name}
    pkg_pattern = re.compile(r'\\usepackage(?:\[.*?\])?\{(.*?)\}')
    
    # Check for presence
    has_booktabs = 'booktabs' in content
    has_colortbl = 'colortbl' in content
    
    if has_booktabs and has_colortbl:
        # Find indices
        booktabs_matches = [(m.start(), m.end(), m.group(0)) for m in pkg_pattern.finditer(content) if 'booktabs' in m.group(1)]
        colortbl_matches = [(m.start(), m.end(), m.group(0)) for m in pkg_pattern.finditer(content) if 'colortbl' in m.group(1)]
        
        if booktabs_matches and colortbl_matches:
            first_booktabs_start = booktabs_matches[0][0]
            last_colortbl_end = colortbl_matches[-1][1]
            
            if first_booktabs_start < last_colortbl_end:
                logger.info("Found booktabs loaded before colortbl. Reordering...")
                
                # Strategy: Comment out all booktabs lines, and append them after the last colortbl
                # To be safe, we reconstruct the string.
                
                # 1. Capture all booktabs lines
                booktabs_lines = [m[2] for m in booktabs_matches]
                
                # 2. Replace them in content with comment
                # We use a placeholder to avoid shifting indices if we did it iteratively? 
                # Better: just replace them with % commented version
                for start, end, text in booktabs_matches:
                     # This replacement is risky if we have duplicates in regex finding.
                     # But finditer returns distinct matches.
                     # We can't modify string in place while iterating indices.
                     pass
                     
                # Let's do a simple string replace for now? No, identical lines might exist.
                # Let's use string slicing.
                
                # Actually, simpler: 
                # Remove all booktabs lines.
                # Insert them after the last colortbl line.
                
                # We need to handle potential newlines.
                
                new_content = content
                removed_lines = []
                
                # Iterate in reverse to avoid index shift issues
                for start, end, text in reversed(booktabs_matches):
                    removed_lines.append(text)
                    new_content = new_content[:start] + "% " + new_content[start:]
                
                # Now insert them after the last colortbl (which might have shifted because we added "% ")
                # Actually, we added "% " (2 chars).
                # Indices shifted.
                
                # Re-find colortbl in new_content
                colortbl_matches_new = [(m.start(), m.end(), m.group(0)) for m in pkg_pattern.finditer(new_content) if 'colortbl' in m.group(1)]
                if colortbl_matches_new:
                    insert_pos = colortbl_matches_new[-1][1]
                    # Restore lines (reversed means we have them in reverse order, so reverse back)
                    to_insert = '\n'.join(reversed(removed_lines))
                    new_content = new_content[:insert_pos] + "\n" + to_insert + new_content[insert_pos:]
                    
                    return new_content

    return content

def fix_latex_imbalance(content: str) -> str:
    """
    Heuristic fix for extra \\end{...} tags which cause 'Extra \\endgroup' errors.
    Common scenario: LLM auto-completes an environment in a chunk, creating duplicates.
    """
    # Environments to check
    envs = ['quote', 'quotation', 'itemize', 'enumerate', 'description', 'definition', 'theorem', 'lemma', 'proof']
    
    for env in envs:
        # Regex for begin and end tags
        begin_pat = re.compile(r'\\begin\{' + env + r'\}')
        end_pat = re.compile(r'\\end\{' + env + r'\}')
        
        starts = len(begin_pat.findall(content))
        ends = len(end_pat.findall(content))
        
        if ends > starts:
            # We have extra end tags. Remove the LAST (ends - starts) occurrences.
            # Why last? Because usually the extra one is appended at the end of a chunk?
            # Or maybe the first one?
            # If we have: \begin ... \end ... \end
            # The last one is likely the surplus if the first pair matched.
            diff = ends - starts
            logger.info(f"Fixing imbalance in '{env}': {starts} begins, {ends} ends. Removing {diff} extra ends.")
            
            # Reverse replace
            # Split by the tag, join all but the last 'diff' parts with the tag, then join the rest with empty string?
            # Easier: finditer and remove specific spans.
            
            matches = list(end_pat.finditer(content))
            # matches to remove are the last 'diff' ones
            to_remove = matches[-diff:]
            
            # Reconstruct string excluding these ranges
            # Do it in reverse order to not mess up indices
            for m in reversed(to_remove):
                content = content[:m.start()] + content[m.end():]
                
    return content

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
