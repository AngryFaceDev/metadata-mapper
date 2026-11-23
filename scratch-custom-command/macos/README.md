# macOS Custom Command setup

**Use `ExportResolveCSVAuto.acc`.** On macOS, neither a Custom Command's
`<input>` fields nor its "Additional Parameters" field (whether fired from
the manual button or from a post-render action) ever reach the script's
argv -- confirmed by direct testing (the `=== STARTUP ===` log line showed
`argv=[<script path>]` with nothing appended, no matter what was typed into
either field, on three separate invocation paths). This contradicts
Assimilate's own documentation, which claims Custom Command input values
are always passed through as command-line parameters -- that just doesn't
hold on macOS. `ExportResolveCSV.acc` is included in this folder only as a
reference in case a future SCRATCH update changes this.

## Setup

1. Copy the whole `script/` folder from this repo onto the SCRATCH Mac,
   e.g. to `/Users/Shared/SCRATCH-Tools/`.
2. `chmod +x metadata_to_resolve_csv.py` on the copied script -- SCRATCH
   invokes it directly via its shebang line, which needs the executable
   bit set.
3. Copy `scratch_rest_config.example.json` (from `script/`) to
   `scratch_rest_config.json` in that same folder, and fill in
   `default_mapping_template` / `default_output_folder` (point
   `default_mapping_template` at one of the files in this repo's
   `examples/` folder, or your own exported mapping template). **Write this
   file from Terminal** (e.g. a `cat > file <<'EOF' ... EOF` heredoc), not
   from TextEdit's rich-text mode -- it silently converts straight quotes
   to curly quotes and breaks the JSON in a way that's hard to trace back.
   Validate with `python3 -m json.tool scratch_rest_config.json` before
   trusting it.
4. Edit `ExportResolveCSVAuto.acc`'s `<cmdline>` path if you didn't use
   `/Users/Shared/SCRATCH-Tools/`.
5. In SCRATCH: System Settings -> enable the built-in web server, then load
   `ExportResolveCSVAuto.acc` as a Custom Command (player menu button)
   and/or as a post-render action.

## If you need more than one mapping template on demand

Since no runtime parameter reaches the script on macOS, offering more than
one mapping/output choice as separate buttons means sidestepping argv
entirely: duplicate the whole `script/` folder once per mapping you want on
demand (e.g. `SCRATCH-Tools-Basic/`, `SCRATCH-Tools-VFX/`), give each copy
its own `scratch_rest_config.json` with a different
`default_mapping_template`, and load one `ExportResolveCSVAuto.acc` per
copy (edit its `<cmdline>` to that copy's path, and give it a distinct
`<title>`). Picking a mapping becomes picking which button you click -- no
argv needed.

## Debugging a run

Check `metadata_to_resolve_csv.log`, written next to the script (and, as a
fallback, under `/tmp`). The `=== STARTUP ===` line's `argv=[...]` is the
complete, unfiltered record of what SCRATCH actually handed the process --
if something typed into a field doesn't show up there, it didn't arrive,
full stop. A `python3\r: No such file or directory`-style error in
SCRATCH's own log (rather than this script's log) usually means the script
file has Windows-style CRLF line endings -- fix with
`sed -i '' 's/\r$//' metadata_to_resolve_csv.py` and re-`chmod +x` it.

See the top-level repo README for the full writeup of this platform
difference, and why it affects the manual button, the post-render action,
and the Custom Command's own "Additional Parameters" field all the same
way on macOS.
