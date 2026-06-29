from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from dredge.cli import main
from dredge.trace.runner import run_trace
from dredge.trace.store import TraceStore


REPO_ROOT = Path(__file__).resolve().parents[1]


class DocumentedWorkflowSmokeTests(unittest.TestCase):
    def test_cli_version_and_help_are_available_from_source(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["version"]), 0)
        self.assertIn('"package": "dredge"', output.getvalue())

        result = subprocess.run(
            [sys.executable, "-m", "dredge", "--help"],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: dredge", result.stdout)

    def test_installer_dry_run_does_not_write_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "prefix"
            result = subprocess.run(
                ["bash", "scripts/install.sh", "--dry-run", "--prefix", str(prefix)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"DRY RUN: would install Python launcher to {prefix}/bin/dredge", result.stdout)
            self.assertFalse((prefix / "bin" / "dredge").exists())

    def test_installer_rejects_python_below_declared_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            python = bin_dir / "python3"
            python.write_text(
                "#!/usr/bin/env bash\n"
                "echo 3.10.12\n"
                "exit 1\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            result = subprocess.run(
                ["bash", "scripts/install.sh", "--dry-run", "--skip-deps"],
                cwd=REPO_ROOT,
                env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("python3 3.11+ is required", result.stderr)

    def test_trace_run_records_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            state = Path(tmp) / "state"
            root.mkdir()
            created = root / "created.txt"
            command = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('created.txt').write_text('created by test')",
            ]

            with patch.dict(os.environ, {"DREDGE_STATE_DIR": str(state)}):
                result = run_trace(command, cwd=root, roots=[str(root)])
                events = TraceStore(state).read_events(result["trace_id"])

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertTrue(created.exists())
            self.assertTrue(
                any(
                    event["operation"] == "CREATE"
                    and event["target"].get("path") == str(created.resolve())
                    for event in events
                ),
                events,
            )


if __name__ == "__main__":
    unittest.main()
