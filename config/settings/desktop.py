"""
Settings used when the application runs inside the packaged PySide6 desktop
shell (served locally via Waitress). Imported by desktop/main.py before the
server starts.
"""

from .base import *  # noqa: F401,F403

import os
import sys
from pathlib import Path

# The packaged build must never run with DEBUG on: it would leak tracebacks
# to the local QWebEngineView and slow down template rendering.
DEBUG = False

# Still local-only -- the Waitress server only ever binds to 127.0.0.1.
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# SECURITY WARNING: for a real packaged build, generate a unique SECRET_KEY
# per installation (e.g. at first-run, written to a local config file next
# to db.sqlite3) rather than reusing the development key from base.py.


# In a PyInstaller build, the bundled application directory is not a safe
# place for mutable accounting data (it may be under Program Files and may
# be read-only). Keep the SQLite database in the per-user LocalAppData
# directory instead. Source/development runs continue using BASE_DIR/db.sqlite3.
if getattr(sys, "frozen", False):
    _local_app_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    APP_DATA_DIR = _local_app_data / "140JahanPour"
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASES["default"]["NAME"] = APP_DATA_DIR / "db.sqlite3"

# The packaged/source desktop runtime serves static assets locally through
# WhiteNoise. The actual resource tree is bundled by FuelStation.spec.
