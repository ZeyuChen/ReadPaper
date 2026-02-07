
import unittest
from arxiv_translator.main import strip_latex_comments

class TestLatexCleaning(unittest.TestCase):
    def test_strip_comments(self):
        latex_content = """
\\documentclass{article}
% This is a comment
\\begin{document}
    % Indented comment
Hello World % Inline comment (should be kept based on current implementation, or removed if logic is improved)
% Another full line comment
\\end{document}
"""
        expected_content = """
\\documentclass{article}
\\begin{document}
Hello World % Inline comment (should be kept based on current implementation, or removed if logic is improved)
\\end{document}
"""
        cleaned = strip_latex_comments(latex_content)
        # Normalize whitespace for comparison (simpler)
        self.assertEqual(cleaned.strip(), expected_content.strip())
        
        # Check line count reduction
        original_lines = len(latex_content.splitlines())
        cleaned_lines = len(cleaned.splitlines())
        print(f"Original lines: {original_lines}, Cleaned lines: {cleaned_lines}")
        self.assertTrue(cleaned_lines < original_lines)

if __name__ == '__main__':
    unittest.main()
