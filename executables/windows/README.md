# Windows build (Tauri)

Two files are included:

- `MetadataMapper-Windows-Portable.exe` - a single, no-install portable executable. Just double-click it to run.
- `MetadataMapper-Windows-Setup.exe` - an NSIS installer that installs the app under your user profile and adds a Start Menu entry.

Both are built with Tauri (tauri.app) against the app's live web version (the "Metadata Mapper" Claude artifact), using the OS-provided WebView2 runtime rather than bundling a full browser - hence the small size (~22MB) compared to an Electron build.

Nothing to install beyond WebView2, which ships with Windows 10/11 by default. Unsigned build: Windows SmartScreen may show an "unknown publisher" warning on first run - click "More info" -> "Run anyway".

See `script/metadata_to_resolve_csv.py` and the top-level README for how this fits into the SCRATCH -> Resolve workflow.
