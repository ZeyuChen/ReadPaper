import os
import re
import shutil
from .logging_utils import logger
from .compiler import compile_pdf

class LatexRescuer:
    """
    Attempts to generate a readable PDF even when the original LaTeX is broken.
    Strategies:
    1.  Standardize Preamble: Replace complex custom preambles with a minimal XeLaTeX/ctex compatible one.
    2.  Strip Floats: If compilation still fails, remove figures/tables (often sources of error).
    """
    def __init__(self, source_dir: str, main_tex: str):
        self.source_dir = source_dir
        self.main_tex = main_tex
        self.backup_path = os.path.join(source_dir, f"{main_tex}.bak")

    def rescue(self) -> bool:
        """
        Executes the rescue pipeline.
        Returns entries (success, log).
        """
        logger.info("Initiating LaTeX Rescue Protocol...")
        
        # 1. Backup original
        if not os.path.exists(self.backup_path):
            shutil.copy(os.path.join(self.source_dir, self.main_tex), self.backup_path)
            
        original_content = ""
        with open(self.backup_path, 'r', encoding='utf-8', errors='ignore') as f:
            original_content = f.read()

        # Strategy 1: Safe Preamble (Preserve body, replace head)
        logger.info("Rescue Strategy 1: Injecting Safe Preamble...")
        rescued_content = self._inject_safe_preamble(original_content)
        if self._try_compile(rescued_content):
            return True
            
        # Strategy 2: Safe Preamble + Strip Figures/Tables/Algorithms
        logger.info("Rescue Strategy 2: Stripping Complex Environments...")
        stripped_content = self._strip_environments(rescued_content)
        if self._try_compile(stripped_content):
            return True
            
        logger.error("All rescue strategies failed.")
        # Restore backup for manual inspection? Or leave last attempt?
        # Leaving last attempt might allow user to debug "simplified" version.
        # But maybe better to restore original for "full context" debugging.
        # Let's restore original.
        shutil.copy(self.backup_path, os.path.join(self.source_dir, self.main_tex))
        return False

    def _try_compile(self, content: str) -> bool:
        # Write content
        with open(os.path.join(self.source_dir, self.main_tex), 'w', encoding='utf-8') as f:
            f.write(content)
            
        success, _ = compile_pdf(self.source_dir, self.main_tex)
        return success

    def _inject_safe_preamble(self, content: str) -> str:
        """
        Keeps the document body but replaces the preamble with a robust CJK-aware one.
        """
        # Find \begin{document}
        match = re.search(r'\\begin\{document\}', content)
        if not match:
            return content # Can't rescue if no document start
            
        body = content[match.start():] # \begin{document} ...
        
        # Robust Preamble
        preamble = r"""\documentclass[11pt, a4paper]{article}
\usepackage[UTF8]{ctex}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath, amssymb, amsfonts}
\usepackage{graphicx}
\usepackage{url}
\usepackage{hyperref}
\usepackage{geometry}
\geometry{left=2.5cm, right=2.5cm, top=2.5cm, bottom=2.5cm}

% Tolerant settings
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{3}
\setlength{\parskip}{0.5em}

% Mock common missing commands to prevent errors
\providecommand{\keywords}[1]{\textbf{Keywords:} #1}
\providecommand{\email}[1]{\texttt{#1}}
\providecommand{\address}[1]{#1}
\providecommand{\corresp}[1]{#1}

% Fix for common missing environments (simple fallbacks)
% (If listing packages aren't loaded, these might fail, but ctex usually implies standard setup)
"""
        return preamble + "\n" + body

    def _strip_environments(self, content: str) -> str:
        """
        Comments out figures, tables, and algorithms.
        """
        # Regex for environments
        envs = ['figure', 'figure*', 'table', 'table*', 'algorithm', 'algorithm*', 'listing', 'minted']
        
        new_content = content
        for env in envs:
            # Replace \begin{env} ... \end{env} with a placeholder
            # Use DOTALL
            pattern = re.compile(r'(\\begin\{' + env + r'\}.*?\\end\{' + env + r'\})', re.DOTALL)
            
            # Function to comment out usage
            def comment_out(match):
                block = match.group(1)
                return "\n% [RESCUED: Removed complex environment to ensure compilation]\n% " + block.replace('\n', '\n% ') + "\n"
                
            new_content = pattern.sub(comment_out, new_content)
            
        return new_content
