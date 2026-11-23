# Windows Custom Command setup

1. Copy the whole `script/` folder from this repo onto the SCRATCH machine,
   e.g. to `C:\SCRATCH-Tools\`.
2. Copy `scratch_rest_config.example.json` (from `script/`) to
   `scratch_rest_config.json` in that same folder, and fill in
   `default_mapping_template` / `default_output_folder` (point
   `default_mapping_template` at one of the files in this repo's
   `examples/` folder, or your own exported mapping template).
3. Load whichever `.acc` file here fits how you want to use it:
   - **`ExportResolveCSVAuto.acc`** -- no prompt, always uses
     `scratch_rest_config.json`'s defaults. Recommended for a post-render
     action, or for the button if you don't want to be asked every time.
   - **`ExportResolveCSV.acc`** -- prompts for a mapping file / output
     folder / timeline name every run. Confirmed working as a **post-render
     action** on Windows (values typed into the action's own "Additional
     Parameters" field, *not* this file's `<inputs>`, reach the script --
     see the top-level README's "Known platform behavior" section). The
     plain on-demand button's own `<input>` fields are unconfirmed on
     Windows -- check `metadata_to_resolve_csv.log` after a run to see
     whether `Parsed inputs:` actually matches what you typed.
4. If you didn't use `C:\SCRATCH-Tools\`, edit the `<cmdline>` path in
   whichever `.acc` file you loaded to match your actual script location.
5. In SCRATCH: System Settings -> enable the built-in web server (needed
   either way), then load the `.acc` file as a Custom Command (player menu
   button) and/or point a post-render action at `metadata_to_resolve_csv.py`
   directly with `--mapping "..." --output "..."` in its Additional
   Parameters field.

See the top-level repo README for the full writeup of how SCRATCH invokes
the script on Windows vs. macOS, and `metadata_to_resolve_csv.log` (written
next to the script) for debugging any run.
