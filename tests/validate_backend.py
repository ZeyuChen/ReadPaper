#!/usr/bin/env python3
"""
Backend Validation Script — Real Pipeline, 3 Test Cases
=========================================================
Tests the full arxiv_translator pipeline locally (no backend server needed).
Each test case runs: Download → Extract → Pre-flight → Translate → Compile → PDF check.

Usage:
    cd /Users/chenzeyu01/ReadPaper
    python -m tests.validate_backend

Requirements: .env with GEMINI_API_KEY set, TeX Live installed locally OR
              run inside the Docker container.
"""

import os
import sys
import subprocess
import shutil
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# ── Configure ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent.resolve()
RESULTS_DIR = BASE_DIR / "validation_results"

@dataclass
class TestCase:
    name: str
    arxiv_id: str
    deepdive: bool = False
    description: str = ""
    expected_min_pages: int = 1   # sanity-check: PDF must be > 0 bytes

TEST_CASES = [
    TestCase(
        name="Case 1 — Attention Is All You Need (short, clean LaTeX, no DeepDive)",
        arxiv_id="1706.03762",
        deepdive=False,
        description="Classic Transformer paper. Short, clean LaTeX. Good baseline.",
    ),
    TestCase(
        name="Case 2 — Mistral 7B (short paper + DeepDive mode)",
        arxiv_id="2310.06825",
        deepdive=True,
        description="Short paper. Tests DeepDive analysis + standard translation.",
    ),
    TestCase(
        name="Case 3 — DeepSeek-R1 (multi-file, recent paper, no DeepDive)",
        arxiv_id="2602.04705",
        deepdive=False,
        description="Multi-file LaTeX paper. Tests file-level parallelism & segmented translation.",
    ),
]

# ── Helpers ──────────────────────────────────────────────────────────────────
def banner(msg: str):
    print(f"\n{'='*70}")
    print(f"  {msg}")
    print(f"{'='*70}")

def section(msg: str):
    print(f"\n── {msg}")

def ok(msg: str):   print(f"  ✅ {msg}")
def fail(msg: str): print(f"  ❌ {msg}")
def info(msg: str): print(f"  ℹ  {msg}")


def run_case(tc: TestCase) -> dict:
    """
    Run a single test case through the real arxiv_translator pipeline.
    Returns a result dict with pass/fail and details.
    """
    banner(tc.name)
    info(tc.description)

    work_dir = BASE_DIR / f"workspace_{tc.arxiv_id}"
    url = f"https://arxiv.org/abs/{tc.arxiv_id}"
    suffix = "_zh_deepdive" if tc.deepdive else "_zh"
    expected_pdf = BASE_DIR / f"{tc.arxiv_id}{suffix}.pdf"
    results_pdf  = RESULTS_DIR / f"{tc.arxiv_id}{suffix}.pdf"

    # Clean previous run
    if work_dir.exists():
        info(f"Removing old workspace: {work_dir}")
        shutil.rmtree(work_dir)
    if expected_pdf.exists():
        expected_pdf.unlink()

    # Build command
    cmd = [
        sys.executable, "-m", "app.backend.arxiv_translator.main",
        url,
        "--model", "flash",
        "--keep",                       # preserve workspace for post-run inspection
    ]
    if tc.deepdive:
        cmd.append("--deepdive")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    section(f"Running: {' '.join(cmd)}")
    start = time.time()

    result = subprocess.run(
        cmd,
        env=env,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=900,   # 15-minute hard limit per paper
    )

    elapsed = time.time() - start
    section(f"Finished in {elapsed:.1f}s (exit code: {result.returncode})")

    # ── Print stdout IPC messages (log_ipc goes to stdout) ──
    ipc_lines = [l for l in result.stdout.splitlines() if l.strip()]
    if ipc_lines:
        print("\n  IPC messages (stdout):")
        for l in ipc_lines[-40:]:   # last 40 lines
            print(f"    {l}")

    # ── Print last stderr lines on failure ──
    if result.returncode != 0:
        stderr_tail = result.stderr.splitlines()[-30:]
        print("\n  STDERR (last 30 lines):")
        for l in stderr_tail:
            print(f"    {l}")

    # ── Verify outputs ──
    section("Validating outputs")
    passed = True

    # 1. Exit code
    if result.returncode == 0:
        ok("Process exited cleanly (code 0)")
    else:
        fail(f"Process failed with exit code {result.returncode}")
        passed = False

    # 2. COMPLETED IPC in stdout
    if "PROGRESS:COMPLETED" in result.stdout:
        ok("IPC COMPLETED signal emitted")
    elif "PROGRESS:COMPLETED_WITH_WARNINGS" in result.stdout:
        ok("IPC COMPLETED_WITH_WARNINGS signal emitted (some segments kept in English)")
    else:
        fail("No PROGRESS:COMPLETED signal in stdout")
        passed = False

    # 3. PDF file exists and is non-trivial
    pdf_to_check: Optional[Path] = None
    if expected_pdf.exists():
        pdf_to_check = expected_pdf
    else:
        # Sometimes the PDF is inside the workspace
        for candidate in work_dir.rglob("*.pdf") if work_dir.exists() else []:
            if "_zh" in candidate.name or candidate.name.endswith(".pdf"):
                pdf_to_check = candidate
                break

    if pdf_to_check and pdf_to_check.exists():
        size_kb = pdf_to_check.stat().st_size / 1024
        if size_kb > 5:
            ok(f"PDF found: {pdf_to_check.name} ({size_kb:.1f} KB)")
            # Copy to results dir for inspection
            RESULTS_DIR.mkdir(exist_ok=True)
            shutil.copy(pdf_to_check, RESULTS_DIR / pdf_to_check.name)
            info(f"Copied to: {RESULTS_DIR / pdf_to_check.name}")
        else:
            fail(f"PDF exists but suspiciously small: {size_kb:.1f} KB — likely empty/corrupt")
            passed = False
    else:
        fail(f"Expected PDF not found: {expected_pdf}")
        passed = False

    # 4. Workspace sanity check
    if work_dir.exists():
        source_zh = work_dir / "source_zh"
        if source_zh.exists():
            tex_files = list(source_zh.glob("*.tex"))
            ok(f"source_zh dir exists with {len(tex_files)} .tex file(s)")
        else:
            fail("source_zh directory not found — translation likely failed early")
            passed = False
    else:
        fail("workspace directory not found — something failed before translation")
        passed = False

    # 5. If DeepDive: check deepdive output in stdout
    if tc.deepdive:
        if "deepdive" in result.stdout.lower() or "ANALYZING" in result.stdout:
            ok("DeepDive analysis output detected in stdout")
        else:
            fail("No DeepDive analysis output found in stdout — --deepdive may have been ignored")
            passed = False

    return {
        "case": tc.name,
        "arxiv_id": tc.arxiv_id,
        "deepdive": tc.deepdive,
        "passed": passed,
        "elapsed_s": round(elapsed, 1),
        "exit_code": result.returncode,
        "pdf_path": str(pdf_to_check) if pdf_to_check and pdf_to_check.exists() else None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    banner("ReadPaper Backend Validation — 3 Real-Pipeline Test Cases")
    info(f"BASE_DIR: {BASE_DIR}")
    info(f"Results will be saved to: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(exist_ok=True)

    # Check GEMINI_API_KEY
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        fail("GEMINI_API_KEY not set in .env — cannot run translation")
        sys.exit(1)
    ok(f"GEMINI_API_KEY found ({api_key[:8]}...)")

    results = []
    for tc in TEST_CASES:
        try:
            r = run_case(tc)
        except subprocess.TimeoutExpired:
            fail(f"TIMEOUT: Case '{tc.name}' exceeded 15 minutes")
            r = {"case": tc.name, "arxiv_id": tc.arxiv_id, "passed": False,
                 "elapsed_s": 900, "exit_code": -1, "pdf_path": None, "deepdive": tc.deepdive}
        except Exception as e:
            fail(f"UNEXPECTED ERROR in case '{tc.name}': {e}")
            r = {"case": tc.name, "arxiv_id": tc.arxiv_id, "passed": False,
                 "elapsed_s": 0, "exit_code": -1, "pdf_path": None, "deepdive": tc.deepdive}
        results.append(r)

    # ── Summary ──
    banner("VALIDATION SUMMARY")
    all_passed = True
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        deepdive_tag = " [+DeepDive]" if r.get("deepdive") else ""
        print(f"  {status}  {r['arxiv_id']}{deepdive_tag}  ({r['elapsed_s']}s)  — {r['case']}")
        if r["pdf_path"]:
            print(f"         PDF: {r['pdf_path']}")
        if not r["passed"]:
            all_passed = False

    print()
    if all_passed:
        ok("ALL 3 TEST CASES PASSED — backend pipeline is healthy")
        sys.exit(0)
    else:
        fail("ONE OR MORE TEST CASES FAILED — see details above")
        sys.exit(1)


if __name__ == "__main__":
    main()
