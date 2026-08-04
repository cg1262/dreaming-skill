from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def load_script_module(module_name: str, script_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / script_name)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {script_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, objects: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(obj) + "\n" for obj in objects),
        encoding="utf-8",
    )


class FindClaudeProjectTests(unittest.TestCase):
    def test_extracts_matching_project_transcript_text(self) -> None:
        module = load_script_module("find_claude_project_for_test", "find_claude_project.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            (project / "CLAUDE.md").write_text("# Memory\n", encoding="utf-8")

            claude_home = root / "claude-home"
            encoded = module.encode_project_path(project.resolve())
            transcript = claude_home / "projects" / encoded / "session.jsonl"
            write_jsonl(
                transcript,
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "remember the build command"},
                    },
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "build command is make site"},
                                {"type": "tool_use", "name": "ignored"},
                            ],
                        },
                    },
                    {
                        "type": "user",
                        "isSidechain": True,
                        "message": {"role": "user", "content": "sidechain text"},
                    },
                ],
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPTS_DIR / "find_claude_project.py"),
                    str(project),
                    "--claude-home",
                    str(claude_home),
                    "--limit",
                    "1",
                    "--extract",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"memory_file: {project / 'CLAUDE.md'}", result.stdout)
        self.assertIn("transcripts: 1 found", result.stdout)
        self.assertIn("[user]\nremember the build command", result.stdout)
        self.assertIn("[assistant]\nbuild command is make site", result.stdout)
        self.assertNotIn("sidechain text", result.stdout)

    def test_rejects_non_positive_limit_and_marks_unreadable_extract(self) -> None:
        module = load_script_module("find_claude_project_for_error_test", "find_claude_project.py")
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "find_claude_project.py"), "--limit", "0"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a positive integer", result.stderr)
        self.assertIn("[unreadable:", module.extract_text(Path("/missing-transcript.jsonl")))

    def test_truncation_marker_is_explicit(self) -> None:
        module = load_script_module("find_claude_project_for_truncate_test", "find_claude_project.py")

        self.assertEqual(
            module.truncate_text("abcdef", 3),
            "abc\n\n[... 3 characters truncated ...]",
        )


class FindCodexProjectTests(unittest.TestCase):
    def test_filters_rollouts_by_session_meta_cwd_and_warns_on_corrupt_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            (project / "AGENTS.md").write_text("# Memory\n", encoding="utf-8")

            codex_home = root / "codex-home"
            sessions_dir = codex_home / "sessions" / "2026" / "08" / "04"
            matching = sessions_dir / "rollout-good.jsonl"
            write_jsonl(
                matching,
                [
                    {"type": "session_meta", "payload": {"cwd": str(project.resolve())}},
                    {
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "capture this preference"},
                    },
                    {
                        "type": "event_msg",
                        "payload": {"type": "agent_message", "message": "preference captured"},
                    },
                    {
                        "type": "response_item",
                        "payload": {"content": "raw model payload should be ignored"},
                    },
                ],
            )
            (sessions_dir / "rollout-corrupt.jsonl").write_text("{not json\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPTS_DIR / "find_codex_project.py"),
                    str(project),
                    "--codex-home",
                    str(codex_home),
                    "--limit",
                    "2",
                    "--extract",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"memory_file: {project / 'AGENTS.md'}", result.stdout)
        self.assertIn("transcripts: 1 found", result.stdout)
        self.assertIn("[user]\ncapture this preference", result.stdout)
        self.assertIn("[assistant]\npreference captured", result.stdout)
        self.assertNotIn("raw model payload", result.stdout)
        self.assertIn("additional session file(s) could not be read or parsed", result.stdout)
        self.assertIn("warning: could not read/parse session file", result.stderr)

    def test_rejects_non_positive_limit_and_marks_unreadable_extract(self) -> None:
        module = load_script_module("find_codex_project_for_error_test", "find_codex_project.py")
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "find_codex_project.py"), "--limit", "-1"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a positive integer", result.stderr)
        self.assertIn("[unreadable:", module.extract_text(Path("/missing-rollout.jsonl")))


class NextDreamPathTests(unittest.TestCase):
    def test_reserves_unique_paths_with_same_timestamp_collision(self) -> None:
        module = load_script_module("next_dream_path_for_test", "next_dream_path.py")

        original_datetime = module.datetime

        class FrozenDateTime:
            @classmethod
            def now(cls):
                return original_datetime(2026, 8, 4, 12, 13, 14)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            try:
                module.datetime = FrozenDateTime
                first = module.reserve_dream_path(directory, "AGENTS")
                second = module.reserve_dream_path(directory, "AGENTS")
            finally:
                module.datetime = original_datetime

            self.assertEqual(first.name, "AGENTS.dream.20260804-121314.md")
            self.assertEqual(second.name, "AGENTS.dream.20260804-121314-2.md")
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())


class DreamDiffTests(unittest.TestCase):
    def test_prints_unified_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "AGENTS.md"
            dream = root / "AGENTS.dream.20260804-121314.md"
            original.write_text("one\ntwo\n", encoding="utf-8")
            dream.write_text("one\nthree\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SCRIPTS_DIR / "dream_diff.py"), str(original), str(dream)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"--- {original}", result.stdout)
        self.assertIn(f"+++ {dream}", result.stdout)
        self.assertIn("-two", result.stdout)
        self.assertIn("+three", result.stdout)

    def test_missing_original_uses_empty_baseline_and_output_can_be_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "CLAUDE.md"
            dream = root / "CLAUDE.dream.20260804-121314.md"
            dream.write_text("new memory line\n" * 20, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPTS_DIR / "dream_diff.py"),
                    str(original),
                    str(dream),
                    "--limit-bytes",
                    "80",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(missing; empty baseline)", result.stdout)
        self.assertIn("[diff truncated:", result.stdout)

    def test_identical_files_report_no_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "AGENTS.md"
            dream = root / "AGENTS.dream.20260804-121314.md"
            original.write_text("same\n", encoding="utf-8")
            dream.write_text("same\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SCRIPTS_DIR / "dream_diff.py"), str(original), str(dream)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), "(diff produced no output; files are identical)"
        )


class PromoteDreamTests(unittest.TestCase):
    def test_promotes_dream_and_backs_up_existing_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "AGENTS.md"
            dream = root / "AGENTS.dream.20260804-121314.md"
            original.write_text("old memory\n", encoding="utf-8")
            dream.write_text("new memory\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", str(SCRIPTS_DIR / "promote_dream.sh"), str(dream)],
                text=True,
                capture_output=True,
                check=False,
            )
            backups = list(root.glob("AGENTS.md.bak.*"))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(original.read_text(encoding="utf-8"), "new memory\n")
            self.assertTrue(dream.exists())
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "old memory\n")
            self.assertIn("Promoted dream file:", result.stdout)

    def test_promotes_first_ever_dream_without_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "CLAUDE.md"
            dream = root / "CLAUDE.dream.20260804-121314.md"
            dream.write_text("new memory\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", str(SCRIPTS_DIR / "promote_dream.sh"), str(dream)],
                text=True,
                capture_output=True,
                check=False,
            )
            backups = list(root.glob("CLAUDE.md.bak.*"))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(original.read_text(encoding="utf-8"), "new memory\n")
            self.assertEqual(backups, [])
            self.assertIn("skipping backup", result.stdout)


class InstallScriptTests(unittest.TestCase):
    def test_installs_symlinks_with_expanded_config_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["CLAUDE_CONFIG_DIR"] = "~/claude-config"
            env["CODEX_HOME"] = "$HOME/codex-config"

            result = subprocess.run(
                ["bash", str(REPO_ROOT / "install.sh")],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            claude_link = home / "claude-config" / "skills" / "dreaming"
            codex_link = home / "codex-config" / "skills" / "dreaming"

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(claude_link.is_symlink())
            self.assertTrue(codex_link.is_symlink())
            self.assertEqual(
                claude_link.resolve(), (REPO_ROOT / "claude-code" / "dreaming").resolve()
            )
            self.assertEqual(
                codex_link.resolve(), (REPO_ROOT / "codex" / "dreaming").resolve()
            )


if __name__ == "__main__":
    unittest.main()
