"""Reject internal task residue from public-facing repository documents."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
FORBIDDEN = {
    "local Windows project path": re.compile(r"[A-Za-z]:[\\/](?:myproject|Users)[\\/]"),
    "local Unix home path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "internal release decisions": re.compile(r"Repository And Release Decisions", re.I),
    "provider budget instructions": re.compile(r"(remaining provider budget|budget guidance)", re.I),
    "defensive authenticity claim": re.compile(r"(not fake|real product workflow|not by promises)", re.I),
    "internal acceptance language": re.compile(r"not accepted as completion", re.I),
    "institutional simulation framing": re.compile(r"simulates institutional private data ingestion", re.I),
}


def main() -> None:
    findings: list[str] = []
    for path in PUBLIC_FILES:
        text = path.read_text(encoding="utf-8-sig")
        for label, pattern in FORBIDDEN.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        raise SystemExit("Public-boundary check failed:\n" + "\n".join(findings))


if __name__ == "__main__":
    main()
