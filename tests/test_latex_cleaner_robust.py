import unittest
from app.backend.arxiv_translator.latex_cleaner import clean_latex_content

class TestLatexCleanerRobust(unittest.TestCase):
    
    def test_basic_comment_removal(self):
        src = """Line 1
% Comment line
Line 2"""
        expected = """Line 1
Line 2"""
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

    def test_indented_comment_removal(self):
        src = """    % Indented comment
Line 1
\t% Tab indented comment
Line 2"""
        expected = """Line 1
Line 2"""
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

    def test_escaped_percent_preservation(self):
        """Ensure \% is strictly preserved and not treated as a comment start."""
        src = """Accuracy is 99\\%
\\% starts a line
Line with \\% inside"""
        expected = """Accuracy is 99\\%
\\% starts a line
Line with \\% inside"""
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

    def test_comment_environment_removal(self):
        src = """Line 1
\\begin{comment}
This is a block
comment that should be removed
\\end{comment}
Line 2"""
        expected = """Line 1
Line 2"""
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

    def test_inline_comments_preserved(self):
        """Current logic only removes full line comments. Inline comments are risky to remove with simple regex (escapes), so we keep them."""
        src = "x = 1 % This is inline"
        expected = "x = 1 % This is inline"
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

    def test_verbatim_environment_safety(self):
        """CRITICAL: Content inside verbatim should NOT be cleaned even if it starts with %."""
        src = """\\begin{verbatim}
% This is code in verbatim
print("% not a comment")
\\end{verbatim}"""
        # Ideally, this should stay as is.
        # But our current naive cleaner might strip it.
        # This test documents CURRENT behavior or DESIRED behavior.
        # User asked for "strict" correctness. Stripping verbatim content is INCORRECT.
        expected = src 
        
        cleaned = clean_latex_content(src)
        self.assertEqual(cleaned.strip(), expected.strip())

    def test_trailing_newlines_cleanup(self):
        src = """Line 1
% Comment


Line 2"""
        # Should collapse to max 2 newlines (one empty line)
        expected = """Line 1

Line 2"""
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

    def test_complex_mix(self):
        src = """\\documentclass{article}
% Preamble comment
\\begin{document}
Hello world. % inline
\\begin{comment}
IGNORED
\\end{comment}
End.
\\end{document}"""
        expected = """\\documentclass{article}
\\begin{document}
Hello world. % inline
End.
\\end{document}"""
        self.assertEqual(clean_latex_content(src).strip(), expected.strip())

if __name__ == '__main__':
    unittest.main()
