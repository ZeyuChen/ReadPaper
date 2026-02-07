
import unittest
import os
import re

class TestFix260204705(unittest.TestCase):
    def test_posttraining_frac_fix(self):
        """Verifies that posttraining.tex has correctly closed \\frac braces."""
        file_path = "/home/zeyuc/ReadPaper/paper_storage/2602.04705v1/workspace_2602.04705v1/source_zh/latex_files/content/posttraining.tex"
        if not os.path.exists(file_path):
            self.skipTest("File not found (local workspace specific)")
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Check for the fixed pattern in line 100/116
        # Expected: \frac{\pi...)}{\pi...}
        # The buggy version was \frac{\pi...}{\pi...} (missing })
        
        # Regex for fixed version:
        # \frac{\pi_{train\(y_i\|x;\\theta\)}}{\pi_{train}\(y_i\|x;\\theta_{old}\)}
        
        # We search for the specific fixed string
        fixed_fragment = r"\frac{\pi_{train(y_i|x;\theta)}}{\pi_{train}(y_i|x;\theta_{old})}"
        
        # We can also just count braces in that specific line if we can ID it, but string match is safer for regression
        self.assertIn(fixed_fragment, content, "posttraining.tex does not contain the fixed \\frac syntax")

    def test_evaluation_table_fix(self):
        """Verifies that evaluation.tex has \\end{table*} matching \\begin{table*}."""
        file_path = "/home/zeyuc/ReadPaper/paper_storage/2602.04705v1/workspace_2602.04705v1/source_zh/latex_files/content/evaluation.tex"
        if not os.path.exists(file_path):
            self.skipTest("File not found (local workspace specific)")
            
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Find the table block with label tab:posttrain-eval-text
        # Ensure it ends with \end{table*}
        
        found_label = False
        found_end_star = False
        
        for i, line in enumerate(lines):
            if "\\label{tab:posttrain-eval-text}" in line:
                found_label = True
                # Check next few lines for \end{table*}
                for j in range(1, 5):
                    if i + j < len(lines):
                        if "\\end{table*}" in lines[i+j]:
                            found_end_star = True
                            break
                        if "\\end{table}" in lines[i+j] and "*" not in lines[i+j]:
                            self.fail(f"Found wrong \\end{{table}} at line {i+j+1}")
                break
                
        if found_label:
            self.assertTrue(found_end_star, "Did not find \\end{table*} after label {tab:posttrain-eval-text}")
        else:
             self.skipTest("Label tab:posttrain-eval-text not found")

if __name__ == '__main__':
    unittest.main()
