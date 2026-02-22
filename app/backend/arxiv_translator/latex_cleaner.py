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
    3. Inline % comments (preserving \\% escapes)

    Inspired by MathTranslate's remove_tex_comments() — correctly handles
    \\\\  (literal backslash) and \\% (escaped percent) before stripping.
    """
    original = content

    # 1. Remove 'comment' environments
    comment_env_pattern = re.compile(
        r'\\begin\{comment\}.*?\\end\{comment\}',
        re.DOTALL
    )
    content = comment_env_pattern.sub('', content)

    # 2. Smart comment removal (ported from MathTranslate)
    #    Temporarily encode \\\\ and \\% to prevent false matches.
    _MATH_CODE = "ZZLATEXGUARD"
    content = content.replace('\\\\', f'{_MATH_CODE}_BSLASH')
    content = content.replace('\\%', f'{_MATH_CODE}_PCNT')

    # Remove full-line comments (lines starting with %)
    content = re.sub(r'\n\s*%.*?(?=\n)', '', content)
    # Remove trailing inline comments (% to end of line)
    content = re.sub(r'%.*?(?=\n)', '', content)

    # Restore encoded chars
    content = content.replace(f'{_MATH_CODE}_PCNT', '\\%')
    content = content.replace(f'{_MATH_CODE}_BSLASH', '\\\\')

    if content != original:
        removed_lines = original.count('\n') - content.count('\n')
        logger.info(f"Cleaned {removed_lines} comment lines")

    return content


def expand_newcommands(content: str) -> str:
    """
    Expand user-defined \\newcommand / \\def macros that wrap translation-sensitive
    environments (equation, align, theorem, itemize, etc.).

    Ported from MathTranslate's process_newcommands(): when a \\newcommand body
    contains environments that need to be recognized by the text extractor, the
    macro is expanded inline so the extractor can properly classify skip regions.

    Only expands macros containing sensitive keywords; leaves others untouched.
    """
    # Sensitive keywords that trigger expansion
    sensitive_keywords = [
        'equation', 'align', 'gather', 'multline', 'array',
        'theorem', 'lemma', 'proof', 'corollary', 'proposition',
        'itemize', 'enumerate', 'description',
        'figure', 'table', 'tabular',
        'displaymath', 'eqnarray', 'cases',
        'textcolor', 'textbf', 'emph',
        'section', 'subsection', 'subsubsection',
        'caption', 'footnote',
    ]

    # Pattern: \newcommand{\name}[n_args]{body} or \newcommand{\name}{body}
    newcmd_pattern = re.compile(
        r'\\(?:newcommand|renewcommand)\s*\{\\([a-zA-Z]+)\}\s*(?:\[(\d+)\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.DOTALL
    )

    matches = list(newcmd_pattern.finditer(content))
    expanded_count = 0

    for match in matches:
        name = match.group(1)
        n_args_str = match.group(2)
        body = match.group(3)

        # Only expand if body contains sensitive keywords
        should_expand = any(kw in body for kw in sensitive_keywords)
        if not should_expand:
            continue

        n_args = int(n_args_str) if n_args_str else 0

        # Build replacement pattern for \name{arg1}{arg2}...
        if n_args == 0:
            # Simple: replace \name (not followed by letter) with body
            usage_pattern = re.compile(r'\\' + re.escape(name) + r'(?![a-zA-Z])')
            content = usage_pattern.sub(body, content)
        else:
            # With args: replace \name{...}{...} with body substituting #1, #2, etc.
            arg_pattern = r'\\' + re.escape(name)
            for i in range(n_args):
                arg_pattern += r'\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'
            usage_regex = re.compile(arg_pattern, re.DOTALL)

            def make_replacement(m, _body=body, _n=n_args):
                result = _body
                for i in range(_n):
                    result = result.replace(f'#{i+1}', m.group(i + 1))
                return result

            content = usage_regex.sub(make_replacement, content)
        expanded_count += 1

    if expanded_count > 0:
        logger.info(f"Expanded {expanded_count} \\newcommand definitions containing sensitive environments")

    return content

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
        cleaned = expand_newcommands(cleaned)
        
        if len(cleaned) < len(content) or cleaned != content:
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
