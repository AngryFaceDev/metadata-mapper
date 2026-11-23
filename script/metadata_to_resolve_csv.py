#!/usr/bin/env python3
# coding: utf-8
"""
metadata_to_resolve_csv.py

SCRATCH Custom Command companion script for the "Metadata Mapper" project.

Fetches all shot metadata for a timeline (Construct) from a running
Assimilate SCRATCH instance via its REST API, applies a mapping template
exported from the Metadata Mapper web app (Manage Mappings... -> Export
JSON, added in app v30), and writes a DaVinci Resolve-compatible metadata
CSV -- the same output the web app itself produces from an ALE file, just
sourced live from SCRATCH instead of a hand-exported ALE.

If no output folder is given (via --output, or a post-render action's
Additional Parameters), the current project's own default render path
(ProjectData.project_paths.render_path) is used instead -- see main().

Pair this script with the Custom Command files in scratch-custom-command/
(see this repo's top-level README, and the platform-specific README in
each of scratch-custom-command/windows/ and scratch-custom-command/macos/)
to expose it as a button in SCRATCH's player/construct menu.

Requires the official Assimilate Python wrapper:
    pip install git+https://github.com/Assimilate-Inc/Assimilate-REST.git

-----------------------------------------------------------------------------
STATUS -- confirmed working end-to-end on both Windows and macOS
-----------------------------------------------------------------------------
As a post-render action: confirmed working end to end on Windows, including
reading --mapping/--output/--timeline out of the action's "Additional
Parameters" field (SCRATCH invokes the script with two fixed positional
args of its own first -- an event name and a UUID -- then appends
whatever's typed into Additional Parameters as a single unsplit string;
parse_args() below strips the fixed prefix and re-splits that blob itself).

On macOS, confirmed that NEITHER a Custom Command's <input> fields NOR its
"Additional Parameters" field (manual button or post-render action) ever
reach this script's argv at all -- SCRATCH hands the process zero extra
arguments on that platform, contrary to Assimilate's own documentation.
The reliable path on macOS is scratch_rest_config.json's
default_mapping_template/default_output_folder, via the no-inputs
"...Auto" Custom Command. See scratch-custom-command/macos/README.md for
the full writeup and a workaround for using more than one mapping
template on macOS.

Still open / not yet confirmed:

  1. Whether the plain .acc Custom Command *button* (as opposed to the
     post-render action, which is confirmed working) on Windows passes
     <input> values into argv the way Assimilate's own RenderSelectedShot.py
     example implies (sys.argv[2 + n*2] per input) -- untested, since all
     Windows testing so far exercised the post-render action specifically.
  2. How this performs / whether level="ALL" holds up on a timeline with
     many shots -- only tested against small (2-3 shot) timelines so far.
  3. The output-folder-from-render-path fallback (leaving Output Folder
     blank falls back to ProjectData.project_paths.render_path) is untested
     against a real SCRATCH instance -- confirmed only against the SDK's
     documented schema and a stubbed API.
-----------------------------------------------------------------------------
"""

from __future__ import annotations

import csv
import getpass
import json
import os
import re
import sys
from datetime import datetime

# =============================================================================
# Logging -- prints AND appends to a log file, tried at several locations in
# order (see CANDIDATE_LOG_DIRS below) in case the account/process this runs
# under can't write next to the script (e.g. a render-action worker process
# with different permissions than an interactive terminal). Defined before
# anything else so even an import failure below gets logged. Every run
# appends; delete the file(s) if they grow too large -- nothing here rotates
# or truncates automatically.
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CANDIDATE_LOG_DIRS = [SCRIPT_DIR]
for _env_var in ("TEMP", "TMP"):
    _p = os.environ.get(_env_var)
    if _p and _p not in CANDIDATE_LOG_DIRS:
        CANDIDATE_LOG_DIRS.append(_p)
if r"C:\Windows\Temp" not in CANDIDATE_LOG_DIRS:
    CANDIDATE_LOG_DIRS.append(r"C:\Windows\Temp")


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line)
    for d in CANDIDATE_LOG_DIRS:
        try:
            with open(os.path.join(d, "metadata_to_resolve_csv.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            continue  # logging is best-effort -- try the next candidate location


# Unconditional startup probe -- fires no matter what happens below, so a run
# that mysteriously produces no output has at least this to go on: proof the
# process started at all, which interpreter ran it, as which account, from
# what working directory, and with exactly what arguments (argv IS the
# complete, unfiltered list of everything the host application handed this
# process -- if something you typed into a "parameters" field doesn't show
# up here, it did not arrive via argv, full stop).
log(
    "=== STARTUP === "
    f"interpreter={sys.executable!r} "
    f"python_version={sys.version.split()[0]} "
    f"user={getpass.getuser()!r} "
    f"cwd={os.getcwd()!r} "
    f"argv={sys.argv!r} "
    f"log_dirs_tried={CANDIDATE_LOG_DIRS!r}"
)


def _redacted_env():
    """A copy of os.environ with anything secret-looking blanked out --
    logged so we can check whether a host application passes parameters
    through an environment variable instead of argv on some platform, since
    argv alone wouldn't show that."""
    sensitive = ("SECRET", "PASSWORD", "TOKEN", "APIKEY", "API_KEY", "PRIVATE", "CREDENTIAL")
    return {
        k: ("***REDACTED***" if any(s in k.upper() for s in sensitive) else v)
        for k, v in sorted(os.environ.items())
    }


log(f"=== STARTUP ENV === {_redacted_env()!r}")


try:
    from assimilate_client import Configuration, ApiClient
    from assimilate_client.api import ProjectsApi
    from assimilate_client.rest import ApiException
except ImportError:
    log("ERROR: the 'assimilate_client' package isn't installed.")
    log("Install it with:")
    log("  pip install git+https://github.com/Assimilate-Inc/Assimilate-REST.git")
    sys.exit(1)


# =============================================================================
# Configuration (server URL / optional access key) -- kept in a small JSON
# file next to this script rather than typed into the Custom Command's input
# form every time, since it's a one-time-per-install setting, not something
# that changes per run. See scratch_rest_config.example.json in this folder.
# =============================================================================

CONFIG_PATH = os.path.join(SCRIPT_DIR, "scratch_rest_config.json")
DEFAULT_HOST = "http://127.0.0.1:8080/APIV2"


def load_config():
    cfg = {
        "host": DEFAULT_HOST,
        "access_key": None,
        # Fallback mapping/output when a post-render action's "Additional
        # Parameters" field doesn't end up passing them (see parse_args()) --
        # set these here so a bare POST_RENDER trigger still has somewhere
        # to read from and write to. Also the ONLY reliable source of these
        # values on macOS -- see the module docstring and
        # scratch-custom-command/macos/README.md.
        "default_mapping_template": None,
        "default_output_folder": None,
    }
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg["host"] = data.get("host") or DEFAULT_HOST
            cfg["access_key"] = data.get("access_key") or None
            cfg["default_mapping_template"] = data.get("default_mapping_template") or None
            cfg["default_output_folder"] = data.get("default_output_folder") or None
        except Exception as e:
            log(f"Warning: could not read {CONFIG_PATH} ({e}) -- using defaults.")
    return cfg


# =============================================================================
# Input parsing -- supports THREE distinct calling conventions, since this
# script can be launched three different ways:
#
#   1. A SCRATCH "post-render action". Confirmed by real-world testing:
#      SCRATCH invokes the script with two FIXED positional args of its own
#      -- an event name and a UUID -- e.g.:
#        metadata_to_resolve_csv.py POST_RENDER 4327bcc5-91af-4955-92ce-455522eb84b3
#      Whatever is typed into the action's "Additional Parameters" field (if
#      anything) is appended *after* those two, not instead of them -- so
#      this script has to recognize and strip that fixed prefix before
#      looking for --mapping/--output/--timeline in whatever follows.
#      Confirmed working end to end on Windows. On macOS, confirmed that
#      NOTHING reaches argv this way either -- see module docstring.
#   2. A SCRATCH Custom Command (.acc), positional, see get_acc_inputs().
#      Unconfirmed on Windows; confirmed NOT to deliver anything on macOS.
#   3. Plain flags for manual testing from a terminal, e.g.:
#        python metadata_to_resolve_csv.py --mapping template.json --output out\
# =============================================================================

# Event names SCRATCH is known to prefix a post-render-action invocation
# with. Add more here if other action types (e.g. a post-export hook) turn
# out to use the same convention with a different event name.
KNOWN_RENDER_EVENTS = {"POST_RENDER"}


def _looks_like_unsplit_blob(tokens):
    """True if `tokens` is really just ONE argv item that itself contains
    multiple whitespace-separated --flags -- i.e. SCRATCH handed the whole
    "Additional Parameters" field through as a single un-split argument
    instead of tokenizing it like a shell would (confirmed on Windows)."""
    return len(tokens) == 1 and " " in tokens[0].strip() and tokens[0].count("--") >= 1


def _resplit_blob(s):
    """Re-tokenize a single unsplit "--mapping X --output Y ..." string the
    way a shell would. Also copes with a stray unmatched quote at the end
    (observed in practice -- looks like SCRATCH wraps the whole field in its
    own quotes, which can collide with a trailing "" typed for an empty
    --timeline value). Never raises; worst case falls back to a naive
    whitespace split."""
    import shlex
    try:
        tokens = shlex.split(s, posix=False)
    except ValueError:
        try:
            tokens = shlex.split(s.rstrip('"'), posix=False)
        except ValueError:
            return s.split()
    # posix=False leaves a matched pair of quotes on a token (e.g. a path
    # with spaces) -- strip those so callers get plain values.
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t for t in tokens]


def get_acc_inputs():
    """Read the 3 .acc <input> values, matching the double-argv-slot pattern
    observed in Assimilate's own RenderSelectedShot.py example (input N's
    value sits at sys.argv[2 + N*2]). Unconfirmed on Windows; confirmed to
    never actually receive anything on macOS (see module docstring)."""
    def slot(n):
        idx = 2 + n * 2
        return sys.argv[idx] if len(sys.argv) > idx else ""
    return slot(0), slot(1), slot(2)


def parse_args():
    argv = sys.argv[1:]

    event_name, event_uuid = None, None
    rest = argv
    if len(argv) >= 2 and argv[0] in KNOWN_RENDER_EVENTS:
        event_name, event_uuid = argv[0], argv[1]
        rest = argv[2:]
        log(f"Detected a SCRATCH render-action invocation: event={event_name!r} uuid={event_uuid!r}")

    if _looks_like_unsplit_blob(rest):
        original = rest[0]
        rest = _resplit_blob(original)
        log(f"Additional Parameters arrived as a single unsplit token ({original!r}) -- re-split into: {rest!r}")

    if any(a.startswith("--") for a in rest):
        import argparse
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument("--mapping", default=None, help="Path to a mapping template JSON file exported from Metadata Mapper")
        p.add_argument("--output", default=None, help="Folder to write the Resolve CSV into")
        p.add_argument("--timeline", nargs="?", const="", default="",
                       help="Timeline (Construct) name. Omit this flag entirely, or pass it "
                            "with no value / an empty string, to use whatever's currently "
                            "active in SCRATCH.")
        ns, unknown = p.parse_known_args(rest)
        if unknown:
            log(f"Warning: ignoring unrecognized arguments: {unknown!r}")
        mapping_path, output_folder, timeline_name = ns.mapping, ns.output, ns.timeline
    elif event_name is None and rest:
        # No render-event prefix and no --flags: this is the old .acc
        # positional convention.
        log(f"Raw argv: {sys.argv!r}")
        mapping_path, output_folder, timeline_name = get_acc_inputs()
        if not mapping_path and not output_folder and len(sys.argv) >= 3:
            # Fallback: plain sequential positional args (e.g. sys.argv[1:]
            # were passed straight through by something other than a
            # SCRATCH .acc).
            mapping_path = sys.argv[1] if len(sys.argv) > 1 else ""
            output_folder = sys.argv[2] if len(sys.argv) > 2 else ""
            timeline_name = sys.argv[3] if len(sys.argv) > 3 else ""
    else:
        # A render-event prefix with nothing (recognizable) after it -- e.g.
        # the action's "Additional Parameters" field was left blank, or
        # (confirmed on macOS) the platform never delivers it at all. Leave
        # mapping/output unset here; main() falls back to
        # scratch_rest_config.json's "default_mapping_template" /
        # "default_output_folder" if those are configured.
        mapping_path, output_folder, timeline_name = None, None, ""

    log(f"Parsed inputs: mapping={mapping_path!r} output={output_folder!r} timeline={timeline_name!r} event_uuid={event_uuid!r}")
    return mapping_path, output_folder, timeline_name, event_uuid


# =============================================================================
# Small safe-access helpers (mirrors the pattern used in Assimilate's own
# project_explorer.py example -- works whether the SDK hands back a model
# object or, in some edge cases, a plain dict)
# =============================================================================

def safe_get_attr(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def stringify(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else ""
    return str(value)


# =============================================================================
# Value-mapping logic -- ported line-for-line from Metadata Mapper's own
# ENUM_TARGET_COLUMNS / CHECKBOX_TARGET_COLUMNS / CHECKBOX_TRUE_TOKENS
# constants and resolveConstrainedValue()/autoMatchEnumValue()/
# autoMatchCheckboxValue() functions, so a raw SCRATCH metadata value
# resolves to *exactly* the same Resolve-accepted value the web app would
# produce from the same value in an ALE. If Resolve's accepted vocabulary or
# checkbox column list ever changes, re-sync these three constants from the
# web app's own source.
# =============================================================================

ENUM_TARGET_COLUMNS = {
    "Clip Color": {
        "values": ["Orange", "Apricot", "Yellow", "Lime", "Olive", "Green", "Teal", "Navy",
                    "Blue", "Purple", "Violet", "Pink", "Tan", "Beige", "Brown", "Chocolate"],
        "multi": False,
    },
    "Flags": {
        "values": ["Pink", "Mint", "Blue", "Cyan", "Green", "Yellow", "Red", "Purple",
                    "Fuchsia", "Cream", "Cocoa", "Sand", "Lemon", "Sky", "Lavender", "Rose"],
        "multi": True,
    },
    "Category": {
        "values": ["Uncategorized", "Dialogue", "Effect", "Music", "Silence"],
        "multi": False,
    },
}

CHECKBOX_TARGET_COLUMNS = {
    "Good Take", "Monitor LUT", "H-Flip", "V-Flip", "LUT Used On Set", "S3D Shot",
    "Framing Chart", "Color Chart", "Grey Chart", "Lens Chart", "VFX Grey Ball", "VFX Mirror Ball",
    "Reviewed By - DOP Reviewed", "Reviewed By - Director Reviewed", "Reviewed By - Focus Reviewed",
    "Reviewed By - VFX Svsr Reviewed", "Reviewed By - Colorist Reviewed", "Reviewed By - 2nd DOP Reviewed",
    "Reviewed By - 2nd Dir Reviewed", "Reviewed By - Sound Reviewed", "Reviewed By - Continuity Reviewed",
    "Reviewed By - Wardrobe Reviewed", "Reviewed By - Send to Studio",
}

CHECKBOX_TRUE_TOKENS = {"1", "true", "yes"}


def get_column_constraint(target_col):
    if target_col in ENUM_TARGET_COLUMNS:
        return "enum", ENUM_TARGET_COLUMNS[target_col]
    if target_col in CHECKBOX_TARGET_COLUMNS:
        return "checkbox", None
    return None, None


def auto_match_checkbox_value(raw):
    if not raw:
        return "No"
    return "Yes" if raw.strip().lower() in CHECKBOX_TRUE_TOKENS else "No"


def auto_match_enum_value(enum_def, raw):
    if not raw:
        return ""
    values = enum_def["values"]
    if enum_def["multi"]:
        parts = [p.strip() for p in re.split(r"[;,]", raw) if p.strip()]
        if not parts:
            return None
        matched = []
        for p in parts:
            hit = next((v for v in values if v.lower() == p.lower()), None)
            if hit is None:
                return None
            matched.append(hit)
        return ";".join(matched)
    return next((v for v in values if v.lower() == raw.lower()), None)


def resolve_constrained_value(target_col, raw, value_maps):
    kind, enum_def = get_column_constraint(target_col)
    if kind is None:
        return raw or ""
    if not raw:
        return ""
    vm = value_maps.get(target_col) or {}
    vm_map = vm.get("map") or {}
    if kind == "enum":
        if raw in vm_map:
            return vm_map[raw]
        auto = auto_match_enum_value(enum_def, raw)
        if auto is not None:
            return auto
        return raw if vm.get("passthrough") else ""
    # checkbox
    selection = vm_map.get(raw)
    if selection is None:
        selection = auto_match_checkbox_value(raw)
    return "1" if selection == "Yes" else ""


# =============================================================================
# SCRATCH shot -> "source row" flattening
# =============================================================================

def build_source_row(shot):
    """Builds a flat {columnName: value} dict for one Shot, combining a
    handful of explicit ShotData fields (aliased to the names SCRATCH's own
    ALE exporter uses for them) with the shot's free-form `metadata` list.
    The metadata entries are overlaid last and win on any name collision,
    since they're the values SCRATCH itself would put in a real ALE export.
    """
    row = {
        "Name": stringify(safe_get_attr(shot, "name")),
        "Tape": stringify(safe_get_attr(shot, "reel_id")),
        "Scene": stringify(safe_get_attr(shot, "scene")),
        "Take": stringify(safe_get_attr(shot, "take")),
        "Circled": "Y" if safe_get_attr(shot, "circled") else "",
        "Duration": stringify(safe_get_attr(shot, "length")),
        "Start": stringify(safe_get_attr(shot, "timecode")),
        "UUID": stringify(safe_get_attr(shot, "uuid")),
        "File": stringify(safe_get_attr(shot, "file")),
    }

    metadata = safe_get_attr(shot, "metadata")
    # The generated `Metadata` model has no properties of its own (it's a
    # bare array type in the OpenAPI spec) -- in practice this deserializes
    # to a plain list of MetadataInner-like {key, value} entries. Handle
    # that as the primary case, with a defensive fallback for a wrapper
    # object exposing its own `.metadata`/`.items` list instead.
    if isinstance(metadata, list):
        entries = metadata
    else:
        entries = safe_get_attr(metadata, "metadata") or safe_get_attr(metadata, "items") or []

    for item in entries or []:
        key = safe_get_attr(item, "key")
        if key:
            row[key] = stringify(safe_get_attr(item, "value"))

    return row


def build_rows(source_rows, mapping, value_maps):
    """mapping: {targetCol: sourceCol}, exactly as exported from Metadata
    Mapper. Only the columns present in `mapping` are written -- equivalent
    to the web app's "Export wired Columns only" mode, since a mapping
    template alone doesn't carry the full ~212-column Resolve schema for
    blank-filling unwired columns."""
    target_cols = list(mapping.keys())
    rows = []
    for row in source_rows:
        out = []
        for tc in target_cols:
            src_col = mapping.get(tc)
            raw = row.get(src_col, "") if src_col else ""
            out.append(resolve_constrained_value(tc, raw, value_maps))
        rows.append(out)
    return target_cols, rows


def write_csv(path, target_cols, rows):
    # utf-8-sig writes the UTF-8 BOM Resolve's CSV importer expects, matching
    # the web app's own buildCSV() ('\ufeff' + ... + '\r\n').
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, lineterminator="\r\n")
        writer.writerow(target_cols)
        writer.writerows(rows)


# =============================================================================
# Main
# =============================================================================

def main():
    cfg = load_config()
    mapping_path, output_folder, timeline_name, event_uuid = parse_args()

    # A post-render action with nothing usable in "Additional Parameters"
    # (or, on macOS, ANY invocation at all -- see module docstring) falls
    # back to whatever's configured in scratch_rest_config.json.
    if not mapping_path and cfg.get("default_mapping_template"):
        log(f"No --mapping given -- using default_mapping_template from config: {cfg['default_mapping_template']!r}")
        mapping_path = cfg["default_mapping_template"]
    if not output_folder and cfg.get("default_output_folder"):
        log(f"No --output given -- using default_output_folder from config: {cfg['default_output_folder']!r}")
        output_folder = cfg["default_output_folder"]

    if not mapping_path:
        log("ERROR: no mapping template file given, and no default_mapping_template set in "
            "scratch_rest_config.json. Either add --mapping to the action's Additional "
            "Parameters, or set default_mapping_template in the config file.")
        sys.exit(1)
    if not os.path.isfile(mapping_path):
        log(f"ERROR: mapping template file not found: {mapping_path}")
        sys.exit(1)

    with open(mapping_path, "r", encoding="utf-8") as f:
        template = json.load(f)
    mapping = template.get("mapping") or {}
    value_maps = template.get("valueMaps") or {}
    log(f"Loaded mapping template '{template.get('name', '(unnamed)')}' -- {len(mapping)} wired column(s).")
    if not mapping:
        log("This mapping template has no wired columns -- nothing to export.")
        sys.exit(1)

    config = Configuration()
    config.host = cfg["host"]
    api_client = ApiClient(config)
    if cfg.get("access_key"):
        try:
            api_client.set_default_header("Authorization", cfg["access_key"])
        except AttributeError:
            api_client.default_headers["Authorization"] = cfg["access_key"]
    projects_api = ProjectsApi(api_client)

    log(f"Connecting to {cfg['host']} ...")

    if not output_folder:
        # Still nothing -- fall back to the current project's own default
        # render path (ProjectData.project_paths.render_path) rather than
        # giving up. This is what "leave Output Folder blank" resolves to.
        log("No output folder given -- looking up the current project's default render path...")
        try:
            project = projects_api.get_projects_current()
            render_path = safe_get_attr(safe_get_attr(project, "project_paths"), "render_path")
            if render_path:
                log(f"Using the current project's render path: {render_path}")
                output_folder = render_path
            else:
                log("The current project has no render path set either.")
        except Exception as e:
            log(f"Could not look up the current project's render path: {e}")

    if not output_folder:
        log("ERROR: no output folder given, no default_output_folder set in "
            "scratch_rest_config.json, and the current project has no render path "
            "either. Add --output to the action's Additional Parameters, set "
            "default_output_folder in the config file, or set a render path on "
            "the project in SCRATCH.")
        sys.exit(1)

    # A post-render action's event_uuid is confirmed NOT to be a
    # construct/timeline UUID -- get_construct(event_uuid) 404s with
    # "Construct not found". It's logged above for traceability (it may be
    # a render-job or output id -- not investigated further, since plain
    # timeline-name/current resolution below already does the job), but
    # there's no point spending a REST round-trip confirming that 404 again
    # on every run, so it's not used to resolve the construct.
    if timeline_name:
        log(f"Looking up timeline '{timeline_name}' in the active group...")
        constructs = projects_api.get_constructs().constructs or []
        found = next(
            (c for c in constructs
             if (safe_get_attr(c, "name") or "").strip().lower() == timeline_name.strip().lower()),
            None,
        )
        if not found:
            names = [safe_get_attr(c, "name") for c in constructs]
            log(f"ERROR: no timeline named '{timeline_name}' found in the active group.")
            log(f"Timelines available there: {names}")
            sys.exit(1)
        construct_uuid = safe_get_attr(found, "uuid")
        projects_api.select_construct(construct_uuid)
        construct = projects_api.get_construct(construct_uuid, level="ALL")
    else:
        # For a post-render action specifically, this is exactly the right
        # default: it fires right after rendering, so "whatever's currently
        # active" is the timeline that was just rendered.
        log("No timeline name given -- using whatever's currently active in SCRATCH.")
        construct = projects_api.get_constructs_current(level="ALL")

    construct_name = safe_get_attr(construct, "name") or "timeline"
    log(f"Timeline: {construct_name}")

    source_rows = []
    for slot in (safe_get_attr(construct, "slots") or []):
        for shot in (safe_get_attr(slot, "shots") or []):
            source_rows.append(build_source_row(shot))

    log(f"Found {len(source_rows)} shot(s).")
    if not source_rows:
        log("No shots on this timeline -- nothing to export.")
        sys.exit(0)

    target_cols, rows = build_rows(source_rows, mapping, value_maps)

    os.makedirs(output_folder, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", construct_name).strip("_") or "timeline"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_folder, f"{safe_name}_{timestamp}_resolve.csv")
    write_csv(out_path, target_cols, rows)

    log(f"Wrote {len(rows)} row(s), {len(target_cols)} column(s) -> {out_path}")


if __name__ == "__main__":
    try:
        main()
    except ApiException as e:
        log("Assimilate REST API error:")
        if e.body:
            try:
                log(json.dumps(json.loads(e.body.decode("utf-8")), indent=2))
            except Exception:
                log(str(e.body))
        else:
            log(str(e))
        sys.exit(1)
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)
