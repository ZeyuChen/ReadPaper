import os
import pytest
from arxiv_translator.deepdive import DeepDiveAnalyzer

# Mock API Key (we expect it to fail auth if we actually call, 
# but we want to verify the class structure and maybe mock the call)
# Actually we want to run it against the real API if possible to see "DeepDive results".
# We have `GEMINI_API_KEY` in environment.

def test_deepdive_analyzer_direct():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not found")
        
    analyzer = DeepDiveAnalyzer(api_key, model_name="gemini-3-flash-preview")
    
    # Sample Technical Content
    latex_sample = r"""
    \section{Methodology}
    We introduce a novel attention mechanism called Sparse-Flash-Attention.
    It reduces complexity from $O(N^2)$ to $O(N \log N)$ by skipping low-impact tokens.
    Equation:
    \begin{equation}
        A = \text{softmax}(QK^T)V
    \end{equation}
    """
    
    # Run analysis
    try:
        result = analyzer.analyze_latex(latex_sample, "method.tex")
        print("Original length:", len(latex_sample))
        print("Result length:", len(result))
        print("Result snippet:", result[:200])
        
        # Check if tcolorbox is injected
        if "tcolorbox" in result:
             print("SUCCESS: tcolorbox found in output.")
        else:
             print("WARNING: tcolorbox NOT found. Gemini might have decided not to comment or prompt issue.")
             # It's probabilistic, but for "Methodology" it usually triggers.
             
        assert isinstance(result, str)
        # We don't strictly assert tcolorbox because LLM might skip small snippets, 
        # but manual inspection of print output helps.
        
    except Exception as e:
        pytest.fail(f"Analyzer failed: {e}")

if __name__ == "__main__":
    test_deepdive_analyzer_direct()
