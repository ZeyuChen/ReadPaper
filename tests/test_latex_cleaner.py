import unittest
import os
import shutil
import tempfile
from app.backend.arxiv_translator.latex_cleaner import clean_latex_content, clean_latex_file, clean_latex_directory

class TestLatexCleaner(unittest.TestCase):
    def test_clean_content(self):
        content = """
% This is a comment
Hello World
% Another comment
\\begin{comment}
This is a block comment
\\end{comment}
Code
"""
        expected = """
Hello World
Code
"""
        cleaned = clean_latex_content(content)
        # Normalize newlines for comparison
        self.assertEqual(cleaned.strip(), expected.strip())

    def test_clean_file(self):
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.tex') as tmp:
            tmp.write("% Comment\nContent")
            tmp_path = tmp.name
            
        try:
            modified = clean_latex_file(tmp_path)
            self.assertTrue(modified)
            with open(tmp_path, 'r') as f:
                self.assertEqual(f.read().strip(), "Content")
        finally:
            os.remove(tmp_path)

    def test_clean_directory(self):
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, 'a.tex'), 'w') as f:
                f.write("% Comment\nA")
            with open(os.path.join(test_dir, 'b.txt'), 'w') as f:
                f.write("% Comment\nB")
                
            count = clean_latex_directory(test_dir)
            self.assertEqual(count, 1) # Only .tex should be cleaned
            
            with open(os.path.join(test_dir, 'a.tex'), 'r') as f:
                self.assertEqual(f.read().strip(), "A")
            with open(os.path.join(test_dir, 'b.txt'), 'r') as f:
                self.assertEqual(f.read().strip(), "% Comment\nB")
        finally:
            shutil.rmtree(test_dir)

if __name__ == '__main__':
    unittest.main()
