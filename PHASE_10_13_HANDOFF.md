# 140 Jahan Pour — Phase 10–13 Handoff

## What was completed in this package

### Phase 10 — Desktop integration
- Added `desktop/main.py`.
- Normal mode starts a local Waitress child process and opens the site in `QWebEngineView`.
- The child process is the same executable in a PyInstaller build (`--server` mode), so the final package does not need a separate visible console.
- Uses an automatically selected localhost port.
- Waits for the server before opening the UI.
- Terminates the Waitress child when the main window closes.
- Added non-GUI desktop smoke tests in `desktop/tests.py`.
- Added WhiteNoise because `DEBUG=False` in desktop mode means Django cannot otherwise serve the CSS/JS tree without another web server.

### Phase 11 — Test/optimization preparation
- Existing application tests are preserved.
- Desktop tests avoid requiring Qt GUI support.
- Actual QWebEngine memory/CPU benchmarking is intentionally left for the user's Windows 10 target machine.
- The target-machine benchmark cannot be truthfully performed inside this development environment.

### Phase 12 — PyInstaller preparation
- Added `FuelStation.spec`.
- Build is `onedir` + `windowed`, which is preferable to `onefile` for this Chromium/QWebEngine application.
- Django templates/static files and dynamic app/migration imports are included.
- Added `build_windows.ps1`.

### Phase 13 — Installer preparation
- Added `installer.iss` for Inno Setup.
- Installs under `%LOCALAPPDATA%\Programs\140JahanPour`.
- Database/runtime data is intentionally kept outside the install directory so uninstall does not delete accounting data.

## Requirements

`requirements.txt` is pinned for Python 3.11.x / Windows x86-64:

- Django 5.2.17
- Waitress 3.0.2
- PySide6 6.9.3
- WeasyPrint 69.0
- pypdf 6.16.2
- PyInstaller 6.22.2
- WhiteNoise 6.12.0

## Important actions required on your Windows machine

The following cannot be reliably completed here:

1. Activate the project's Python 3.11 virtual environment.
2. Install `requirements.txt`.
3. Run the full Django test suite.
4. Start the desktop shell and verify QWebEngineView.
5. Benchmark RAM/CPU on the actual Pentium G3220/4 GB target.
6. Build the Windows executable with PyInstaller.
7. Install and test the Inno Setup package on a clean Windows 10 x64 environment.

### Recommended commands

```powershell
# Activate venv
.env\Scripts\Activate.ps1

# Install
python -m pip install -r requirements.txt

# Verify Python
python --version

# Django checks
python manage.py check

# Full tests
python manage.py test

# Run the desktop application from source
python -m desktop.main
```

For the PySide6 installation, the package is large. If a download timeout occurs, retry with:

```powershell
python -m pip install PySide6==6.9.3 --timeout 600
```

## First source-run setup

The packaged server automatically runs migrations and idempotently seeds the fixed station/nozzle configuration. Initial operator creation and license activation are now a single atomic first-run setup action; no license code is required for initial activation. The package does NOT silently invent a license, operator account, tank capacities, or other accounting data.

If the database is new, use the project's existing management workflow, for example:

```powershell
python manage.py migrate
python manage.py seed_station
python manage.py createsuperuser
```

Then create/activate the License through the established setup path before normal login. Real tank capacities still need to replace the placeholder `0` values before production use.

## Known finalization items

- `Tank.capacity` is still seeded as 0 and must be replaced with the real capacities.
- QWebEngineView memory footprint must be measured on the target hardware.
- The license renewal mechanism remains the architecture's intentionally unresolved business decision.
- New-nozzle mid-month/monthly beginning-meter behavior remains an open architecture question.
- Monthly immutable audit snapshots remain undecided.
- A local copy of the Vazirmatn web font would make the packaged/offline UI fully self-contained; the current templates retain the existing CDN reference with Tahoma fallback.

## Suggested validation order

1. `pip install -r requirements.txt`
2. `python manage.py check`
3. `python manage.py test`
4. `python -m desktop.main`
5. Test login/dashboard/sales/purchases/inventory/reports/printing.
6. Close the window and verify the server process disappears.
7. Run the application on the actual target hardware.
8. Only after that, run `build_windows.ps1`.
9. Test `dist\FuelStation\FuelStation.exe`.
10. Build the Inno Setup installer from `installer.iss`.
11. Install on a clean Windows 10 x64 machine and repeat the smoke test.

## Important packaging note

The current package deliberately does not add an automatic first-run operator/license wizard because that behavior was not part of the approved Phase 1 architecture. Adding one would be a business-flow change and should be explicitly approved before implementation.
