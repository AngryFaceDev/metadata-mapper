# Metadata Mapper

A small toolchain for getting camera/shot metadata out of **Assimilate
SCRATCH** and into **DaVinci Resolve**'s metadata import, correctly wired to
Resolve's fixed column names.

SCRATCH reads camera metadata as-is and can export it as an ALE file (a
TAB-delimited CSV variant). Resolve doesn't read ALE metadata directly — it
imports a plain CSV, but only against its own fixed, 212-column schema.
Column names essentially never match between the two, so a straight
export/import doesn't work: something has to translate SCRATCH's column
names into Resolve's.

**[Metadata Mapper](https://claude.ai/code/artifact/6b9049dc-7dfb-47be-8aac-a4f30cd0bc45)**
is the web app that does that translation visually — load a SCRATCH ALE (or
plain CSV), drag wires from its columns to Resolve's columns, handle
Resolve's constrained enum/checkbox columns (`Clip Color`, `Good Take`,
etc.), save the wiring as a reusable mapping template, and export a
Resolve-ready CSV.

This repo packages everything needed to **use** that mapping without
touching the web app each time: a standalone desktop build of the app
itself, and a SCRATCH Custom Command that pulls metadata directly from a
running SCRATCH instance via its REST API and writes the Resolve CSV
without an ALE export step at all.

## What's in this repo

| Path | What it is |
|---|---|
| `executables/windows/` | Standalone Windows build of the Metadata Mapper app (Tauri — a portable `.exe` and an installer). No Python/Node/etc. needed to run it. |
| `executables/macos/` | Standalone macOS build of the same app (Tauri — a `.app` and a `.dmg`), Apple Silicon. |
| `scratch-custom-command/windows/` | SCRATCH Custom Command (`.acc`) files for Windows, plus setup notes. |
| `scratch-custom-command/macos/` | The same, for macOS — **read this one's README first**, SCRATCH behaves differently here (see below). |
| `script/` | `metadata_to_resolve_csv.py`, the Python script the Custom Commands run, and its config file template. Platform-independent — the same file is used by both the Windows and macOS Custom Commands. |
| `examples/` | A small sample SCRATCH ALE, the "Default Basic" mapping template as it exports from the app, and the exact Resolve CSV that mapping produces from that ALE — see below. |

## Quick start

**Just want to wire a mapping visually and export a CSV from an ALE you
already have?** Use the desktop app in `executables/` for your platform —
no setup, just run it.

**Want SCRATCH to export straight to a Resolve CSV with one click, no ALE
step?**

1. In the desktop app (or the [web app](https://claude.ai/code/artifact/6b9049dc-7dfb-47be-8aac-a4f30cd0bc45)), wire up your mapping and save it as a
   template, then **Manage Mappings… → Export JSON** to get a portable
   `mapping-template-*.json` file. (Or start from
   `examples/mapping-template-default-basic.json` in this repo.)
2. Follow the setup README in `scratch-custom-command/windows/` or
   `scratch-custom-command/macos/`, matching your SCRATCH machine's OS.
3. In SCRATCH, enable the built-in REST server (System Settings → web
   server), and point `scratch_rest_config.json` at your exported mapping
   template.
4. Run the Custom Command from SCRATCH's player menu, or wire it up as a
   post-render action for a fully hands-off export after every render.

## Known platform behavior (read before setting up the Custom Command)

Real-world testing surfaced a meaningful platform difference in how
SCRATCH actually invokes a Custom Command script — this isn't a bug in
`metadata_to_resolve_csv.py`, it's how SCRATCH behaves on each OS:

- **Windows**: a **post-render action** pointed at the script directly
  passes its own "Additional Parameters" field through to the script as a
  single unsplit string, which the script re-splits itself — confirmed
  working end to end, `--mapping`/`--output`/`--timeline` all reach the
  script this way. The plain on-demand Custom Command *button*'s own
  `<input>` fields are unconfirmed on Windows — nobody's actually fired it
  outside the post-render path yet.
- **macOS**: confirmed that **nothing** reaches the script's argv on any
  invocation path — not a Custom Command's `<input>` fields, not its own
  "Additional Parameters" field, and not a post-render action's Additional
  Parameters either (macOS routes a post-render action through the Custom
  Command mechanism rather than launching the script directly the way
  Windows does, so it inherits the same dead end). This contradicts
  Assimilate's own documentation. The reliable path on macOS is
  `scratch_rest_config.json`'s `default_mapping_template` /
  `default_output_folder`, via the no-`<input>` `...Auto.acc` Custom
  Command — see `scratch-custom-command/macos/README.md` for the full
  writeup and a way to offer more than one mapping template on demand
  despite this.

## The example files

`examples/sample_scratch_metadata.ale` is a small (3-shot) illustrative ALE
— it does not represent SCRATCH's full ALE column set, just enough columns
to exercise every field the default mapping below uses, plus a couple of
camera fields for flavor.

`examples/mapping-template-default-basic.json` is the app's built-in
"Default Basic" mapping template, in the exact JSON shape **Manage
Mappings… → Export JSON** produces (`{app, exportedTemplateFormat,
exportedAt, name, mapping, valueMaps, sourceColumnsSnapshot,
targetColumnsSnapshot}`), including its one shipped value-map default
(`Good Take`: a raw `Y` classifies as `Yes`).

`examples/sample_resolve_media_metadata.csv` is the **exact, verified
output** of running the sample ALE through that mapping template with
`metadata_to_resolve_csv.py`'s own mapping logic (`build_rows`) — not a
hand-typed guess. Byte-for-byte the same format the script and app both
write (UTF-8 with BOM, CRLF line endings). It's an illustrative 11-column
subset, not Resolve's full 212-column schema — the toolchain here only
ever writes columns a mapping template actually wires (equivalent to the
app's "Export wired Columns only" mode), so a full-schema example wouldn't
reflect real output anyway.

## License

MIT — see `LICENSE`.
