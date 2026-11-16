from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "markdown_paste_hygiene_check", ROOT / "scripts" / "markdown_paste_hygiene_check.py"
)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def _reasons(text: str) -> set[str]:
    return {finding.reason for finding in gate.scan_text(text)}


class MarkdownPasteHygieneTests(unittest.TestCase):
    def test_agent_shell_marker_in_prose_is_flagged(self) -> None:
        text = "# Title\n\nSome prose.\n<shellId: 0 completed with exit code 0>\n"
        findings = gate.scan_text(text, "doc.md")
        self.assertEqual([f.reason for f in findings], ["agent_shell_marker"])
        self.assertEqual(findings[0].line, 4)

    def test_terminal_output_inside_fenced_block_is_allowed(self) -> None:
        text = (
            "# Title\n\n"
            "```console\n"
            "$ git remote -v\n"
            "origin\thttps://example.invalid/repo (fetch)\n"
            "<shellId: 0 completed with exit code 0>\n"
            "npm ERR! code E404\n"
            "```\n\n"
            "Closing prose.\n"
        )
        self.assertEqual(gate.scan_text(text, "doc.md"), [])

    def test_tilde_fence_is_tracked_independently_of_backtick_fence(self) -> None:
        text = "~~~text\n```\n<shellId: 7 completed with exit code 1>\n~~~\n"
        self.assertEqual(gate.scan_text(text, "doc.md"), [])

    def test_git_remote_listing_in_prose_is_flagged(self) -> None:
        text = (
            "origin\thttp://localhost:26831/owner/repo (fetch)\n"
            "origin\thttp://localhost:26831/owner/repo (push)\n\n"
            "# Title\n"
        )
        findings = gate.scan_text(text, "doc.md")
        self.assertEqual([f.reason for f in findings], ["git_remote_listing", "git_remote_listing"])

    def test_long_bare_directory_listing_is_flagged_but_short_run_is_not(self) -> None:
        entries = [
            "Cargo.toml",
            "LICENSE",
            "README.md",
            "blackjack.html",
            "index.html",
            "package.json",
            "plinko.html",
            "wheel.html",
        ]
        long_listing = "# Title\n\n" + "\n".join(entries) + "\n"
        self.assertIn("bare_directory_listing", _reasons(long_listing))

        short_listing = "# Title\n\n" + "\n".join(entries[:4]) + "\n"
        self.assertNotIn("bare_directory_listing", _reasons(short_listing))

    def test_markdown_list_of_filenames_is_not_treated_as_a_listing(self) -> None:
        text = "# Title\n\n" + "\n".join(f"- file_{index}.md" for index in range(20)) + "\n"
        self.assertEqual(gate.scan_text(text, "doc.md"), [])

    def test_other_terminal_signatures_are_flagged_in_prose(self) -> None:
        self.assertIn("ansi_escape_sequence", _reasons("# T\n\n\x1b[32mdone\x1b[0m\n"))
        self.assertIn("shell_prompt", _reasons("# T\n\n$ git status\n"))
        self.assertIn("python_traceback", _reasons("# T\n\nTraceback (most recent call last):\n"))
        self.assertIn("command_not_found", _reasons("# T\n\nbash: foo: command not found\n"))
        self.assertIn("npm_diagnostic", _reasons("# T\n\nnpm ERR! code E404\n"))

    def test_repository_markdown_tree_is_clean(self) -> None:
        findings = gate.scan_repository(ROOT)
        self.assertEqual(
            findings,
            [],
            "Pasted terminal output detected in Markdown: "
            + ", ".join(f"{f.path}:{f.line} ({f.reason})" for f in findings),
        )


if __name__ == "__main__":
    unittest.main()
