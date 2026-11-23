# macOS build (Tauri, Apple Silicon)

Two files are included:

- `MetadataMapper-macOS.app.zip` - the app bundle, zipped (unzip, then drag `Metadata Mapper.app` wherever you like - Applications, or just run it in place).
- `MetadataMapper-macOS.dmg` - a standard disk-image installer (open it, drag the app into Applications).

Built with Tauri (tauri.app) against the app's live web version (the "Metadata Mapper" Claude artifact), using Apple's native WebKit webview rather than bundling a full browser - hence the small size (~10MB) for the app binary itself.

The app is ad-hoc code-signed (via Tauri's default `codesign -s -`), which is enough for it to launch on Apple Silicon. It is not notarized by Apple, so on first launch Gatekeeper may require right-click -> Open (or System Settings -> Privacy & Security -> "Open Anyway") instead of a plain double-click.

See `script/metadata_to_resolve_csv.py` and the top-level README for how this fits into the SCRATCH -> Resolve workflow.
