#!/usr/bin/env python3
"""adapter.py — Chevaline reference adapter for OpenCode (SPEC.md §4).

    python3 adapter.py render <profile-dir> [--opencode-dir DIR] [--dry-run]
                              [--allow-install] [--plugin-store DIR]
                              [--cwd PATH] [--hostname NAME] [--git-org ORG]
                              [--environment NAME ...]

Renders a Chevaline profile into OpenCode's user-level config:

  ~/.config/opencode/AGENTS.md            instructions, inside marker
                                          comments (SPEC §4 item 3)
  ~/.config/opencode/opencode.json[c]     `plugin` array entries for
                                          declared [[plugins]]
  ~/.config/opencode/opencode.chevaline.json
                                          sidecar recording exactly which
                                          plugin entries this adapter owns

OpenCode reads its global config from `opencode.jsonc` or `opencode.json`;
the adapter edits whichever exists (preferring `.jsonc`) and creates
`opencode.json` when neither does. JSON with comments cannot be rewritten
by this adapter without destroying the comments, so a config file that does
not parse as plain JSON is declined loudly rather than clobbered (SPEC §4
item 3: never clobber hand-written config).

Plugins (SPEC §3.11, §4.2): the shared plugin store checkout's
`.opencode/plugins/*.mjs` entry points are added to the config's `plugin`
array as absolute paths — OpenCode's documented plugin surface. A checkout
with no `.opencode/plugins/` carries no OpenCode packaging and is reported,
not guessed at. Materialization honors the resolved `exec.install`
authority exactly as SPEC §4.2 requires.

Sections with no surface here yet — models (OpenCode wants provider/model
identifiers, which tier values in the wild are not), authority, budget,
gates, sessions — are reported, never silently dropped. Budget and gate
prose comparable to the claude-code adapter's is future work; the render
report says so on every run.

Standard library only. Requires Python 3.11+ (tomllib, via tools/chevaline.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import chevaline as ch  # noqa: E402
import plugstore  # noqa: E402

HARNESS_NAME = "opencode"

BEGIN_MARKER = "<!-- chevaline:begin — rendered by the opencode adapter; do not edit between markers, edits will be overwritten on re-render -->"
END_MARKER = "<!-- chevaline:end -->"

SIDECAR_NAME = "opencode.chevaline.json"


class Report:
    def __init__(self) -> None:
        self.environments: list[dict] = []
        self.rendered: list[str] = []
        self.skipped: list[str] = []
        self.conflicts: list[str] = []
        self.notes: list[str] = []
        self.errors: list[str] = []

    def print(self, file=None) -> None:
        out = file or sys.stdout
        print("Chevaline → OpenCode render report", file=out)
        print("===================================", file=out)
        print("Environments considered (declaration order):", file=out)
        if not self.environments:
            print("  (none declared)", file=out)
        for rep in self.environments:
            status = "MATCHED" if rep["matched"] else "did not match"
            print(f"  {rep['name']}: {status} — {rep['reason']}", file=out)
        if self.rendered:
            print("Rendered:", file=out)
            for line in self.rendered:
                print(f"  {line}", file=out)
        if self.conflicts:
            print("Yielded to hand-written config (left untouched):", file=out)
            for line in self.conflicts:
                print(f"  {line}", file=out)
        if self.skipped:
            print("Skipped — no native OpenCode surface (SPEC §4 item 5):", file=out)
            for line in self.skipped:
                print(f"  {line}", file=out)
        if self.errors:
            print("ERRORS:", file=out)
            for line in self.errors:
                print(f"  !! {line}", file=out)
        if self.notes:
            print("Notes:", file=out)
            for line in self.notes:
                print(f"  {line}", file=out)


# --------------------------------------------------------------------------
# AGENTS.md region (instructions)
# --------------------------------------------------------------------------


def applicable_instructions(effective: dict) -> list[dict]:
    out = []
    for entry in effective.get("instructions", []) or []:
        if not isinstance(entry, dict):
            continue
        harnesses = entry.get("harnesses")
        if harnesses is None or HARNESS_NAME in harnesses:
            out.append(entry)
    return out


def render_region(effective: dict, profile_dir: Path, report: Report) -> str:
    parts: list[str] = []
    resident = effective.get("resident", {})
    name = resident.get("name") if isinstance(resident, dict) else None
    who = f" of {name}" if name else ""
    parts.append(
        f"# Chevaline profile{who}\n\n"
        f"Rendered from the Chevaline profile at `{profile_dir}`. To change\n"
        "anything below, edit the profile and re-render — not this file.\n"
    )
    blocks = applicable_instructions(effective)
    for entry in blocks:
        path = profile_dir / entry["path"]
        parts.append(path.read_text().strip() + "\n")
    skipped = len(effective.get("instructions", []) or []) - len(blocks)
    if skipped:
        report.notes.append(
            f"instructions: {skipped} block(s) filtered out by a `harnesses` key "
            f"not naming {HARNESS_NAME}"
        )
    return "\n".join(parts)


def splice_agents_md(existing: str | None, region: str) -> str:
    block = f"{BEGIN_MARKER}\n\n{region}\n{END_MARKER}\n"
    if existing is None or existing.strip() == "":
        return block
    begin = existing.find(BEGIN_MARKER)
    end = existing.find(END_MARKER)
    if begin == -1 and end == -1:
        sep = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
        return existing + sep + block
    if begin == -1 or end == -1 or end < begin:
        raise SystemExit(
            "ERROR: the OpenCode AGENTS.md contains a damaged chevaline marker "
            "pair (one marker missing, or end before begin). Refusing to guess "
            "at the owned region — fix the markers by hand and re-render."
        )
    return existing[:begin] + block.rstrip("\n") + existing[end + len(END_MARKER):]


# --------------------------------------------------------------------------
# Plugins → opencode.json[c] `plugin` array
# --------------------------------------------------------------------------


def applicable_plugins(effective: dict) -> list[dict]:
    out = []
    for entry in effective.get("plugins", []) or []:
        if not isinstance(entry, dict):
            continue
        harnesses = entry.get("harnesses")
        if harnesses is None or HARNESS_NAME in harnesses:
            out.append(entry)
    return out


def install_authority(effective: dict) -> str:
    """Resolved authority for exec.install; unresolved behaves as
    `approval` (SPEC §4.2)."""
    auth = effective.get("authority", {})
    if not isinstance(auth, dict):
        return "approval"
    actions = auth.get("actions", {})
    level = actions.get("exec.install") if isinstance(actions, dict) else None
    if level is None:
        level = auth.get("default")
    return level if level in ("silent", "reported", "approval") else "approval"


def desired_plugin_entries(
    effective: dict,
    args: argparse.Namespace,
    profile_dir: Path,
    prior_owned: list[str],
    report: Report,
) -> list[str]:
    """The absolute .mjs paths the config's `plugin` array should carry.
    Materializes checkouts (authority-gated) except under --dry-run."""
    entries: list[str] = []
    declared = effective.get("plugins", []) or []
    plugins = applicable_plugins(effective)
    filtered = len(declared) - len(plugins)
    if filtered:
        report.notes.append(
            f"plugins: {filtered} entr{'y' if filtered == 1 else 'ies'} filtered out by a "
            f"`harnesses` key not naming {HARNESS_NAME}"
        )
    level = install_authority(effective)
    store = (
        Path(args.plugin_store).expanduser().resolve()
        if args.plugin_store
        else plugstore.default_store()
    )

    for entry in plugins:
        pid, pin = entry["id"], entry["pin"]
        compose = entry.get("compose", "layer")
        if compose != "layer":
            # A config `plugin` entry is unconditional: it cannot express
            # "only where the project has no plugin opinion" (defer) or
            # "stop on a conflict" (insist), and project-opinion detection
            # is out of scope for v0.3 (RFC 0005). Silently layering would
            # override the declared mode.
            report.skipped.append(
                f"plugins.{pid} (compose={compose!r}) — a config plugin entry is "
                "unconditional, and this adapter cannot detect a project's own "
                "plugin opinion (RFC 0005), so a non-layer mode cannot be "
                "honored natively; not rendered"
            )
            continue
        source = plugstore.resolve_source(entry["source"], profile_dir)
        checkout = plugstore.checkout_dir(store, pid, pin)
        materialized = checkout.exists()

        if not materialized and level == "approval" and not args.allow_install:
            report.skipped.append(
                f"plugins.{pid} — materializing {source} at {pin[:12]} is an "
                "exec.install-class action and the resolved authority is "
                "'approval' (or unresolved, which behaves the same, SPEC §4.2); "
                "re-run with --allow-install to authorize this invocation"
            )
            continue
        if args.dry_run and not materialized:
            report.notes.append(
                f"plugins.{pid}: DRY RUN — would materialize into {checkout} and add "
                "its .opencode plugin entry points to the config's `plugin` array"
            )
            retained = [
                e for e in prior_owned
                if e.startswith(str(store / pid) + "/")
            ]
            if retained:
                # The fetch was skipped only because this is a dry run;
                # projecting the prior entries as removed would describe a
                # removal no real render performs.
                entries.extend(retained)
                report.notes.append(
                    f"plugins.{pid}: DRY RUN — post-fetch state unknown; the "
                    "projection retains the prior entries"
                )
            continue
        # Runs in dry-run mode too when the checkout exists: materialize is
        # offline and mutation-free there, and it is the only HEAD-versus-pin
        # verification — a dry run must not call a drifted store entry usable.
        try:
            checkout, fetched = plugstore.materialize(pid, source, pin, store)
        except plugstore.PlugstoreError as e:
            report.errors.append(f"plugins.{pid}: {e}")
            continue
        if fetched:
            verb = {
                "silent": "materialized",
                "reported": "materialized (exec.install is 'reported': saying so)",
                "approval": "materialized (exec.install is 'approval'; authorized by --allow-install)",
            }[level]
            report.rendered.append(f"plugins.{pid}: {verb} {source} @ {pin[:12]} → {checkout}")

        # OpenCode plugins are JavaScript or TypeScript entry points, and
        # both documented directory spellings are honored — `plugin/` and
        # `plugins/`. `.cjs` helpers are deliberately excluded (they are
        # modules the entry points require, not plugins of their own).
        # Every discovered entry must be a regular file whose real path
        # stays inside the pinned checkout: a tracked symlink pointing
        # outside would load mutable content the pin never covered.
        real_checkout = checkout.resolve()
        points: list[Path] = []
        escaped: list[Path] = []
        for dirname in ("plugin", "plugins"):
            plugin_dir = checkout / ".opencode" / dirname
            if plugin_dir.is_dir():
                for pattern in ("*.mjs", "*.js", "*.ts"):
                    for candidate in plugin_dir.glob(pattern):
                        resolved = candidate.resolve()
                        if resolved.is_file() and resolved.is_relative_to(real_checkout):
                            points.append(candidate)
                        else:
                            escaped.append(candidate)
        if escaped:
            report.errors.append(
                f"plugins.{pid}: entry point(s) "
                + ", ".join(str(e) for e in escaped)
                + " resolve outside the pinned checkout (or are not regular "
                "files) — loading them would execute content the pin never "
                "verified (SPEC §4.2); refusing"
            )
            continue
        if not points:
            report.skipped.append(
                f"plugins.{pid} — the checkout has no .opencode/plugin[s]/*.mjs|js|ts "
                "entry point, so there is no OpenCode packaging to reference; the "
                f"entry lists {HARNESS_NAME} (or lists no harnesses), which looks "
                "like a mismatch with what the plugin repo actually ships (SPEC §4.2)"
            )
            continue
        for path in sorted(points):
            entries.append(str(path))
    return entries


def config_path(opencode_dir: Path) -> Path:
    jsonc = opencode_dir / "opencode.jsonc"
    if jsonc.is_file():
        return jsonc
    return opencode_dir / "opencode.json"


def apply_config(
    config: dict, sidecar: dict, wanted: list[str], target_name: str, report: Report
) -> tuple[dict, dict]:
    """Ownership model matches the claude-code adapter's list handling: the
    adapter removes only entries it previously owned, adds what the profile
    wants now, and owns only what it added. Hand-written `plugin` entries
    are never touched."""
    config = dict(config)
    previously_ours: list[str] = (sidecar.get("owned") or {}).get("plugin", [])
    current = config.get("plugin")
    if current is not None and not isinstance(current, list):
        # A hand-written non-list value is a conflict, not raw material:
        # replacing it would clobber state this adapter never owned.
        report.conflicts.append(
            f"opencode config plugin is {type(current).__name__}-shaped, not "
            "an array — hand-written config wins (SPEC §4 item 3); fix it by "
            "hand and re-render to let the profile add plugin entries"
        )
        new_sidecar = {
            "_comment": sidecar.get("_comment") or "",
            "owned": {"plugin": []},
            "target": target_name,
        }
        return config, new_sidecar
    current_list = list(current) if isinstance(current, list) else []
    kept = [e for e in current_list if e not in previously_ours]
    added = []
    for entry in wanted:
        if entry not in kept and entry not in added:
            added.append(entry)
    result = kept + added
    if result:
        config["plugin"] = result
    elif "plugin" in config:
        del config["plugin"]
    if added:
        report.rendered.append(
            f"opencode config plugin: +{len(added)} entr{'y' if len(added) == 1 else 'ies'} {added}"
        )
    removed = [e for e in previously_ours if e in current_list and e not in added]
    if removed:
        report.rendered.append(f"opencode config plugin: removed formerly-owned {removed}")
    new_sidecar = {
        "_comment": (
            "Sidecar manifest for the Chevaline opencode adapter (SPEC §4 item "
            "3): the config is JSON, which has no stable comment channel this "
            "adapter can rely on, so the plugin entries the adapter owns are "
            "recorded here instead. Do not edit; re-rendering rewrites it."
        ),
        "owned": {"plugin": added},
        "target": target_name,
    }
    return config, new_sidecar


# --------------------------------------------------------------------------
# Reporting for everything with no surface here yet
# --------------------------------------------------------------------------


def report_unrenderable(effective: dict, report: Report) -> None:
    if isinstance(effective.get("models"), dict):
        report.skipped.append(
            "models — OpenCode addresses models as provider/model identifiers; "
            "mapping tiers onto that is not rendered yet"
        )
    if isinstance(effective.get("authority"), dict):
        report.skipped.append(
            "authority — OpenCode's permission config is a real candidate "
            "surface, but this adapter does not render it yet"
        )
    if isinstance(effective.get("budget"), dict):
        report.skipped.append(
            "budget — declared policy is NOT rendered and NOT enforced here "
            "(SPEC §4.1: saying so loudly is the obligation); the claude-code "
            "adapter's launcher-directive prose has no counterpart here yet"
        )
    for gate in effective.get("gates", []) or []:
        if isinstance(gate, dict):
            report.skipped.append(
                f"gates.{gate.get('id')} — no OpenCode surface fires on "
                f"{gate.get('on')!r}; not rendered"
            )
    if isinstance(effective.get("sessions"), dict) and "isolation" in effective["sessions"]:
        report.skipped.append(
            f"sessions.isolation = {effective['sessions']['isolation']!r} — no "
            "OpenCode surface; not rendered"
        )
    for ext in effective.get("extensions", []) or []:
        if isinstance(ext, dict):
            report.skipped.append(
                f"extensions.{ext.get('id')} — v0.3 defines identification only "
                "(SPEC §3.10); not rendered"
            )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_render(args: argparse.Namespace) -> int:
    profile_dir = Path(args.profile_dir).resolve()
    opencode_dir = Path(args.opencode_dir).expanduser()
    ctx = ch.build_context(args.cwd, args.hostname, args.git_org)
    explicit = set(args.environment) if args.environment else None

    effective, errors, warnings, explain = ch.resolve_profile(profile_dir, ctx, explicit)
    for w in warnings:
        ch.print_warning(w, file=sys.stderr)
    if errors or effective is None or explain is None:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print("Profile invalid or unresolvable; nothing rendered (SPEC §4 item 1).", file=sys.stderr)
        return 1

    harnesses = effective.get("harnesses", {})
    prefer = harnesses.get("prefer") if isinstance(harnesses, dict) else None
    if isinstance(prefer, list) and prefer and HARNESS_NAME not in prefer:
        print(
            f"harnesses.prefer = {prefer!r} does not include {HARNESS_NAME!r}; "
            "declining to render.",
            file=sys.stderr,
        )
        return 1

    report = Report()
    report.environments = explain["environments"]

    # AGENTS.md
    region = render_region(effective, profile_dir, report)
    md_path = opencode_dir / "AGENTS.md"
    existing_md = md_path.read_text() if md_path.is_file() else None
    new_md = splice_agents_md(existing_md, region)
    if new_md != (existing_md or ""):
        report.rendered.append(
            f"{md_path} — chevaline region "
            f"({'created file' if existing_md is None else 'updated in place'}, "
            f"{len(region)} chars)"
        )
    else:
        report.notes.append(f"{md_path}: already up to date")

    # opencode.json[c] plugin entries. The sidecar is read first because it
    # records which config file the owned entries were written to, and that
    # target stays stable: if a render wrote opencode.json and a .jsonc
    # later appears, switching targets would strand the owned entries in a
    # file OpenCode still loads.
    sidecar_path = opencode_dir / SIDECAR_NAME
    sidecar = json.loads(sidecar_path.read_text()) if sidecar_path.is_file() else {}
    recorded_target = sidecar.get("target")
    # Only the adapter's own config basenames are honored: a corrupted or
    # hand-edited sidecar must not be able to point writes at an arbitrary
    # file (SPEC §4 item 6).
    if recorded_target not in ("opencode.json", "opencode.jsonc"):
        recorded_target = None
    if isinstance(recorded_target, str) and (opencode_dir / recorded_target).is_file():
        cfg_path = opencode_dir / recorded_target
        preferred = config_path(opencode_dir)
        if preferred != cfg_path:
            report.notes.append(
                f"config target stays {cfg_path.name}: the sidecar's owned "
                f"entries live there, and {preferred.name} appearing later "
                "does not move them"
            )
    else:
        cfg_path = config_path(opencode_dir)
    if cfg_path.is_file():
        try:
            config = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            config = None  # handled below with the same decline
        if config is not None and not isinstance(config, dict):
            print(
                f"ERROR: {cfg_path} is valid JSON but not an object; rewriting "
                "it would clobber what the resident wrote, so this adapter "
                "declines to touch it (SPEC §4 item 3).",
                file=sys.stderr,
            )
            return 1
        if config is None:
            print(
                f"ERROR: {cfg_path} is not plain JSON (comments?). Rewriting it "
                "would destroy what the resident wrote, so this adapter declines "
                "to touch it (SPEC §4 item 3). Move the comments elsewhere or "
                "add the plugin entries by hand.",
                file=sys.stderr,
            )
            return 1
    else:
        config = {}

    prior_owned = (sidecar.get("owned") or {}).get("plugin", [])
    wanted = desired_plugin_entries(effective, args, profile_dir, prior_owned, report)
    new_config, new_sidecar = apply_config(config, sidecar, wanted, cfg_path.name, report)

    report_unrenderable(effective, report)

    if args.dry_run:
        report.notes.append("DRY RUN: nothing was written.")
        report.print()
        return 1 if report.errors else 0

    opencode_dir.mkdir(parents=True, exist_ok=True)
    if new_md != (existing_md or ""):
        md_path.write_text(new_md)
    if new_config != config or new_sidecar != sidecar or not sidecar_path.is_file():
        cfg_path.write_text(json.dumps(new_config, indent=2) + "\n")
        sidecar_path.write_text(json.dumps(new_sidecar, indent=2) + "\n")
    report.print()
    return 1 if report.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adapter.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render", help="Render a profile into OpenCode user config")
    p.add_argument("profile_dir", help="Path to the Chevaline profile directory")
    p.add_argument("--opencode-dir", default="~/.config/opencode", help="OpenCode config dir (default ~/.config/opencode)")
    p.add_argument("--dry-run", action="store_true", help="Report without writing")
    p.add_argument(
        "--allow-install",
        action="store_true",
        help=(
            "Authorize exec.install-class plugin materialization for this "
            "invocation (SPEC §4.2) — required when the profile's resolved "
            "authority for exec.install is 'approval' or unresolved"
        ),
    )
    p.add_argument(
        "--plugin-store",
        default=None,
        help="Override the plugin store directory (default: $XDG_DATA_HOME/chevaline/plugins)",
    )
    p.add_argument("--cwd", default=None, help="Context cwd for `path` selectors")
    p.add_argument("--hostname", default=None, help="Context hostname for `hostname` selectors")
    p.add_argument("--git-org", dest="git_org", default=None, help="Context git org for `git_org` selectors")
    p.add_argument("--environment", action="append", default=None, metavar="NAME",
                   help="Explicitly activate an environment by name (SPEC §3.2)")
    p.set_defaults(func=cmd_render)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
