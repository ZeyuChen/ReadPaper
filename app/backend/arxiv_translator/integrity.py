"""
Translation integrity validation.

Multi-layer checks to ensure translated LaTeX content is complete and valid
before writing to cache. Prevents corrupted/truncated translations from
polluting the cache.
"""

import re
from typing import Tuple


def validate_translation(
    original: str,
    translated: str,
    filename: str,
    is_main_file: bool = False,
) -> Tuple[bool, str]:
    """
    Validate that a translation is complete and structurally sound.

    Returns:
        (is_valid, reason) — reason is empty string if valid, otherwise
        a human-readable explanation of the failure.
    """
    # ── Layer 1: Basic non-empty check ────────────────────────────────────
    if not translated or len(translated.strip()) < 20:
        return False, f"Translation too short ({len(translated) if translated else 0} chars)"

    # ── Layer 2: LaTeX structural completeness ────────────────────────────
    # If original has \end{document}, translated must too
    if r"\end{document}" in original and r"\end{document}" not in translated:
        return False, r"Missing \end{document} in translation"

    if r"\begin{document}" in original and r"\begin{document}" not in translated:
        return False, r"Missing \begin{document} in translation"

    # Check \begin{env} / \end{env} pairing counts are roughly balanced
    orig_begins = len(re.findall(r"\\begin\{(\w+)\}", original))
    orig_ends = len(re.findall(r"\\end\{(\w+)\}", original))
    trans_begins = len(re.findall(r"\\begin\{(\w+)\}", translated))
    trans_ends = len(re.findall(r"\\end\{(\w+)\}", translated))

    # The translated file should have similar environment counts
    # Allow some tolerance (±20%) since the model might merge/split some envs
    if orig_begins > 0:
        begin_ratio = trans_begins / orig_begins
        if begin_ratio < 0.5 or begin_ratio > 2.0:
            return False, (
                f"Environment count mismatch: original has {orig_begins} "
                f"\\begin, translated has {trans_begins}"
            )

    # \begin and \end should be roughly balanced within the translated file
    if trans_begins > 0 and abs(trans_begins - trans_ends) > max(1, trans_begins * 0.15):
        return False, (
            f"Unbalanced environments: {trans_begins} \\begin vs "
            f"{trans_ends} \\end in translation"
        )

    # ── Layer 3: Key structure preservation ────────────────────────────────
    # \section / \subsection counts should match exactly
    orig_sections = len(re.findall(r"\\(?:sub)*section\*?\{", original))
    trans_sections = len(re.findall(r"\\(?:sub)*section\*?\{", translated))
    if orig_sections > 0 and trans_sections != orig_sections:
        # Allow ±1 tolerance for edge cases (model might consolidate)
        if abs(orig_sections - trans_sections) > 1:
            return False, (
                f"Section count mismatch: original {orig_sections}, "
                f"translated {trans_sections}"
            )

    # \cite, \ref, \label counts should not drop significantly
    for cmd in (r"\\cite\{", r"\\ref\{", r"\\label\{"):
        orig_count = len(re.findall(cmd, original))
        trans_count = len(re.findall(cmd, translated))
        if orig_count > 3:  # Only check if there's a meaningful number
            drop_pct = (orig_count - trans_count) / orig_count
            if drop_pct > 0.15:  # More than 15% lost
                cmd_name = cmd.replace("\\\\", "\\").rstrip(r"\{")
                return False, (
                    f"{cmd_name} count dropped significantly: "
                    f"original {orig_count}, translated {trans_count} "
                    f"({drop_pct:.0%} loss)"
                )

    # ── Layer 4: Truncation detection ─────────────────────────────────────
    # Check for unclosed braces (sign of mid-sentence truncation)
    open_braces = translated.count("{") - translated.count("}")
    if open_braces > 3:  # A few unclosed braces are OK (latex can be messy)
        return False, f"Possible truncation: {open_braces} unclosed braces"

    # Check if the file ends mid-command (e.g. "\sec" instead of "\section{...}")
    # Look at last 50 chars for a dangling backslash-command without completion
    tail = translated.rstrip()[-50:] if len(translated.rstrip()) > 50 else translated.rstrip()
    dangling = re.search(r"\\[a-zA-Z]+$", tail)
    if dangling and dangling.group(0) not in (r"\end", r"\par", r"\item", r"\newline", r"\\\\"):
        # Ends with an incomplete command
        return False, f"Possible truncation: file ends with dangling command '{dangling.group(0)}'"

    # ── All checks passed ─────────────────────────────────────────────────
    return True, ""
