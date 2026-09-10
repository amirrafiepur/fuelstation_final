"""
Phase 10 desktop integration tests that do not require launching Qt.

The actual QWebEngineView startup is intentionally left to a Windows
integration smoke test because CI/test runners may not have Qt WebEngine
or a graphical desktop session.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop import main


class DesktopCommandTests(unittest.TestCase):
    def test_source_server_command_uses_module(self):
        with patch.object(sys, "frozen", False, create=True):
            command = main._server_command(8765)

        self.assertEqual(
            command,
            [sys.executable, "-m", "desktop.main", "--server", "8765"],
        )

    def test_free_port_is_positive(self):
        port = main._find_free_port()
        self.assertGreater(port, 0)

    def test_project_root_exists(self):
        self.assertTrue(Path(main._project_root()).exists())

    def test_environment_uses_desktop_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            main._configure_environment()
            self.assertEqual(
                os.environ["DJANGO_SETTINGS_MODULE"],
                "config.settings.desktop",
            )


if __name__ == "__main__":
    unittest.main()
