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


class PersistentDataLocationTests(unittest.TestCase):
    """The customer's database must live outside the application files."""

    def test_source_run_uses_development_layout(self):
        from config import runtime

        with patch.object(sys, "frozen", False, create=True), patch.dict(
            os.environ, {}, clear=True
        ):
            self.assertIsNone(runtime.get_app_data_dir())

    def test_frozen_run_uses_local_app_data_folder(self):
        import tempfile
        from config import runtime

        with tempfile.TemporaryDirectory() as tmp:
            local_app_data = Path(tmp) / "Local"
            install_dir = Path(tmp) / "Local" / "Programs" / "140JahanPour"
            install_dir.mkdir(parents=True)
            fake_exe = install_dir / "FuelStation.exe"
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(fake_exe)
            ), patch.object(sys, "_MEIPASS", str(install_dir / "_internal"), create=True), patch.dict(
                os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=True
            ):
                data_dir = runtime.get_app_data_dir()

            self.assertEqual(data_dir, local_app_data / "140JahanPour")
            self.assertTrue(data_dir.is_dir())

    def test_frozen_run_refuses_data_inside_application_files(self):
        import tempfile
        from config import runtime

        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "app"
            install_dir.mkdir()
            fake_exe = install_dir / "FuelStation.exe"
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(fake_exe)
            ), patch.object(sys, "_MEIPASS", str(install_dir / "_internal"), create=True), patch.dict(
                os.environ,
                {runtime.DATA_DIR_ENV_VAR: str(install_dir / "data")},
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    runtime.get_app_data_dir()

    def test_override_directory_is_honoured(self):
        import tempfile
        from config import runtime

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sys, "frozen", False, create=True), patch.dict(
                os.environ, {runtime.DATA_DIR_ENV_VAR: str(Path(tmp) / "d")}, clear=True
            ):
                self.assertEqual(runtime.get_app_data_dir(), Path(tmp) / "d")


class PreMigrationBackupTests(unittest.TestCase):
    def _make_db(self, path):
        import sqlite3

        connection = sqlite3.connect(str(path))
        connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        connection.execute("INSERT INTO t (v) VALUES ('customer data')")
        connection.commit()
        connection.close()

    def test_backup_is_a_readable_copy(self):
        import sqlite3
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite3"
            self._make_db(db_path)

            backup_path = main._backup_sqlite_file(db_path, Path(tmp) / "backups")

            self.assertTrue(backup_path.is_file())
            self.assertNotEqual(backup_path, db_path)
            connection = sqlite3.connect(str(backup_path))
            try:
                rows = connection.execute("SELECT v FROM t").fetchall()
            finally:
                connection.close()
            self.assertEqual(rows, [("customer data",)])

    def test_old_backups_are_pruned_but_recent_kept(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite3"
            self._make_db(db_path)
            backup_dir = Path(tmp) / "backups"

            for _ in range(5):
                main._backup_sqlite_file(db_path, backup_dir, keep=3)

            self.assertEqual(len(list(backup_dir.glob("db-before-migrate-*.sqlite3"))), 3)


if __name__ == "__main__":
    unittest.main()
