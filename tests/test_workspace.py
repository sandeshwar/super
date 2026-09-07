"""Workspace path resolution + load_workspace."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from super import config, fsutil
from super.tools.base import resolve_path, safe_path


class ResolvePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="super-ws-")
        self.cfg = {"_root": self.root}

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_relative_under_workspace(self) -> None:
        p = resolve_path(self.cfg, "src/a.py")
        self.assertEqual(p, os.path.join(self.root, "src", "a.py"))

    def test_absolute_outside_allowed(self) -> None:
        outside = tempfile.mkdtemp(prefix="super-out-")
        try:
            p = resolve_path(self.cfg, outside)
            self.assertEqual(p, os.path.abspath(outside))
            self.assertEqual(safe_path(self.cfg, outside), os.path.abspath(outside))
        finally:
            import shutil
            shutil.rmtree(outside, ignore_errors=True)

    def test_tilde_expands(self) -> None:
        home = os.path.expanduser("~")
        p = resolve_path(self.cfg, "~")
        self.assertEqual(p, os.path.abspath(home))


class LoadWorkspaceTests(unittest.TestCase):
    def test_defaults_pin_root(self) -> None:
        root = tempfile.mkdtemp(prefix="super-load-")
        try:
            cfg = config.load_workspace(root)
            self.assertEqual(cfg["_root"], os.path.abspath(root))
            self.assertIsNone(cfg["_config_path"])
            self.assertTrue(cfg["state_dir"].startswith(os.path.abspath(root)))
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_loads_config_json(self) -> None:
        root = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            Path(root, "super.config.json").write_text(
                '{"llm": {"model": "test-model-xyz"}}', encoding="utf-8",
            )
            cfg = config.load_workspace(root)
            self.assertEqual(cfg["llm"]["model"], "test-model-xyz")
            self.assertEqual(cfg["_root"], os.path.abspath(root))
            self.assertTrue(cfg["_config_path"].endswith("super.config.json"))
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)


class PickDirectoryTests(unittest.TestCase):
    def test_cancelled_returns_none(self) -> None:
        with mock.patch.object(fsutil, "_pick_macos", return_value=None), \
             mock.patch.object(fsutil, "platform") as plat:
            plat.system.return_value = "Darwin"
            self.assertIsNone(fsutil.pick_directory("/tmp"))

    def test_macos_path_normalized(self) -> None:
        with mock.patch.object(fsutil.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="/Users/me/proj/\n")
            with mock.patch.object(fsutil, "platform") as plat:
                plat.system.return_value = "Darwin"
                path = fsutil.pick_directory()
            self.assertEqual(path, "/Users/me/proj")


if __name__ == "__main__":
    unittest.main()
