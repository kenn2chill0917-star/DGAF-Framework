#!/usr/bin/env python3
"""Block accidental terminal/shell output pasted into Markdown prose.

Markdown linting checks structure, not provenance: a captured shell transcript
dropped above a document heading is structurally valid Markdown. This gate scans
Markdown prose for artefacts that only occur in copied terminal output and fails
closed when it finds them.

Fenced code blocks are skipped, so documented command transcripts remain allowed
when they are presented as code.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".md"}
EXCLUDED_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__", "htmlcov"}

# Markdown files exempted from this gate, as repository-relative POSIX paths.
ALLOWLIST: frozenset[str] = frozenset()

LINE_PATTERNS = (
    ("agent_shell_marker", re.compile(r"<shell[Ii][Dd]:\s*\S+\s+completed with exit code")),
    ("git_remote_listing", re.compile(r"^(?:origin|upstream)\t\S+\s+\((?:fetch|push)\)\s*$")),
    ("ansi_escape_sequence", re.compile(r"\x1b\[[0-9;]*[A-Za-z]")),
    ("shell_prompt", re.compile(r"^\s*[$#>]\s+(?:git|npm|pip|python|ls|cd|cat|echo|curl|gh)\b")),
    ("python_traceback", re.compile(r"^Traceback \(most recent call last\):\s*$")),
    ("command_not_found", re.compile(r"^(?:bash|sh|zsh): .*: command not found\s*$")),
    ("npm_diagnostic", re.compile(r"^npm (?:ERR!|WARN) ")),
)

FENCE_PATTERN = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
BARE_ENTRY_PATTERN = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._\-]*(?:\.[A-Za-z0-9]{1,8})?$")
BARE_LISTING_THRESHOLD = 8


class Finding(NamedTuple):
    path: str
    line: int
    reason: str
    text: str


def _is_bare_listing_entry(line: str) -> bool:
    """A directory-listing entry: unindented, no Markdown syntax, filename-shaped."""
    return line == line.strip() and bool(BARE_ENTRY_PATTERN.match(line))


def scan_text(text: str, path: str = "<memory>") -> list[Finding]:
    """Return terminal-paste findings for one Markdown document."""
    findings: list[Finding] = []
    fence_char: str | None = None
    listing_run = 0
    listing_start = 0

    for lineno, line in enumerate(text.splitlines(), 1):
        fence = FENCE_PATTERN.match(line)
        if fence:
            token = fence.group(1)[0]
            if fence_char is None:
                fence_char = token
            elif fence_char == token:
                fence_char = None
            listing_run = 0
            continue

        if fence_char is not None:
            listing_run = 0
            continue

        for reason, pattern in LINE_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(path, lineno, reason, line.strip()))

        if line.strip() and _is_bare_listing_entry(line):
            listing_run += 1
            if listing_run == 1:
                listing_start = lineno
            if listing_run == BARE_LISTING_THRESHOLD:
                findings.append(
                    Finding(
                        path,
                        listing_start,
                        "bare_directory_listing",
                        f"{BARE_LISTING_THRESHOLD} consecutive bare filename lines starting here",
                    )
                )
        else:
            listing_run = 0

    return findings


def iter_markdown_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in ALLOWLIST or any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        yield path, rel


def scan_repository(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path, rel in iter_markdown_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(text, rel.as_posix()))
    return findings


def main() -> int:
    findings = scan_repository()
    if findings:
        for finding in findings:
            print(
                f"::error file={finding.path},line={finding.line}::"
                f"Pasted terminal output in Markdown ({finding.reason}): {finding.text}"
            )
        print(
            f"Markdown paste-hygiene check FAILED: {len(findings)} finding(s). "
            "Remove the captured shell output, or present it inside a fenced code block.",
            file=sys.stderr,
        )
        return 1

    print("Markdown paste-hygiene check passed: no pasted terminal output detected in Markdown prose.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
