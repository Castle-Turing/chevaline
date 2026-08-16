#!/usr/bin/env python3
"""chevaline.py — reference validator + resolver CLI for the Chevaline
profile standard (SPEC.md v0.2).

    python3 chevaline.py validate <profile-dir>
    python3 chevaline.py resolve  <profile-dir> [--explain] [--json]
                                   [--cwd PATH] [--hostname NAME] [--git-org ORG]

Standard library only. Requires Python 3.11+ (tomllib).

This tool is deliberately conservative: it implements exactly the checks and
resolution semantics normatively described in SPEC.md, and is silent about
anything SPEC.md itself leaves open. Where SPEC.md was ambiguous, the
judgment call taken is noted in a comment near the relevant code.
"""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import os
import re
import socket
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------
# Constants (the closed vocabularies SPEC.md defines)
# --------------------------------------------------------------------------

SUPPORTED_SPEC_MAJMIN = "0.2"

KNOWN_SELECTORS = {"path", "hostname", "git_org", "env"}
KNOWN_TIERS = {"cheap", "standard", "deep"}
KNOWN_ON_EXCEED = {"halt", "warn"}
KNOWN_WINDOW = {"session", "day"}
KNOWN_AUTHORITY_LEVELS = {"silent", "reported", "approval"}
KNOWN_ACTION_CLASSES = {
    "fs.write",
    "vcs.commit",
    "vcs.push",
    "vcs.publish",
    "deps.change",
    "net.fetch",
    "exec.install",
}
KNOWN_ISOLATION = {"worktree", "branch", "in-place", "container"}
KNOWN_COMPOSE = {"layer", "defer", "insist"}

ISO4217_SHAPED = re.compile(r"^[A-Z]{3}$")
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

# Sections that flatten_sources / merge_tables treat as genuine TOML
# "array of tables" ([[x]]) at the top level, matching SPEC.md's own
# rendering of them. budget.limits is also an array-of-dicts but SPEC.md
# renders it as an inline array literal, so it is intentionally excluded
# here and handled by the generic inline-value formatter instead.
ARRAY_OF_TABLES_KEYS = {"instructions", "gates", "extensions"}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def has_aggregate(limits: Any) -> bool:
    """True if `limits` (a budget.limits array) contains a scope='*' entry."""
    if not isinstance(limits, list):
        return False
    return any(isinstance(e, dict) and e.get("scope") == "*" for e in limits)


def load_manifest(profile_dir: Path) -> tuple[dict | None, list[str]]:
    """Load and parse chevaline.toml. Returns (manifest_or_None, errors)."""
    toml_path = profile_dir / "chevaline.toml"
    if not toml_path.is_file():
        return None, [f"chevaline.toml not found in profile directory '{profile_dir}'"]
    try:
        raw = tomllib.loads(toml_path.read_text())
    except tomllib.TOMLDecodeError as e:
        return None, [f"TOML parse error in {toml_path}: {e}"]
    except OSError as e:
        return None, [f"could not read {toml_path}: {e}"]
    if not isinstance(raw, dict):
        return None, ["chevaline.toml did not parse to a table at the top level"]
    return raw, []


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_limit_entry(entry: Any, ctx_path: str, errors: list[str]) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{ctx_path}: limit entry must be a table, got {entry!r}")
        return
    for field in ("scope", "window", "amount", "unit"):
        if field not in entry:
            errors.append(f"{ctx_path}: limit entry missing required field '{field}'")
    if "window" in entry and entry["window"] not in KNOWN_WINDOW:
        errors.append(
            f"{ctx_path}.window must be one of {sorted(KNOWN_WINDOW)}, got {entry['window']!r}"
        )
    if "amount" in entry:
        amt = entry["amount"]
        if isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt <= 0:
            errors.append(f"{ctx_path}.amount must be a positive number, got {amt!r}")
    if "unit" in entry:
        unit = entry["unit"]
        ok = (
            unit == "tokens"
            or (isinstance(unit, str) and ISO4217_SHAPED.match(unit))
            or (isinstance(unit, str) and unit.startswith("x."))
        )
        if not ok:
            errors.append(
                f"{ctx_path}.unit must be 'tokens', a 3-uppercase-letter ISO-4217-shaped "
                f"code, or start with 'x.' — there is no default unit, got {unit!r}"
            )


def validate_budget_table(budget: Any, ctx_path: str, errors: list[str]) -> None:
    if not isinstance(budget, dict):
        errors.append(f"{ctx_path} must be a table")
        return
    if "on_exceed" in budget and budget["on_exceed"] not in KNOWN_ON_EXCEED:
        errors.append(
            f"{ctx_path}.on_exceed must be one of {sorted(KNOWN_ON_EXCEED)}, "
            f"got {budget['on_exceed']!r}"
        )
    if "limits" in budget:
        limits = budget["limits"]
        if not isinstance(limits, list):
            errors.append(f"{ctx_path}.limits must be an array")
        else:
            for i, entry in enumerate(limits):
                validate_limit_entry(entry, f"{ctx_path}.limits[{i}]", errors)


def validate_models_table(models: Any, ctx_path: str, errors: list[str]) -> None:
    if not isinstance(models, dict):
        errors.append(f"{ctx_path} must be a table")
        return
    for key in models:
        if key not in KNOWN_TIERS and not key.startswith("x."):
            errors.append(
                f"{ctx_path}: unknown tier key '{key}' "
                f"(must be one of {sorted(KNOWN_TIERS)} or 'x.'-prefixed)"
            )


def validate_authority_table(
    auth: Any, ctx_path: str, errors: list[str], warnings: list[str]
) -> None:
    if not isinstance(auth, dict):
        errors.append(f"{ctx_path} must be a table")
        return
    if "default" in auth and auth["default"] not in KNOWN_AUTHORITY_LEVELS:
        errors.append(
            f"{ctx_path}.default must be one of {sorted(KNOWN_AUTHORITY_LEVELS)}, "
            f"got {auth['default']!r}"
        )
    actions = auth.get("actions", {})
    if not isinstance(actions, dict):
        errors.append(f"{ctx_path}.actions must be a table")
        return
    for key, val in actions.items():
        if val not in KNOWN_AUTHORITY_LEVELS:
            errors.append(
                f"{ctx_path}.actions.{key!r} must be one of "
                f"{sorted(KNOWN_AUTHORITY_LEVELS)}, got {val!r}"
            )
        if key not in KNOWN_ACTION_CLASSES and not key.startswith("x."):
            warnings.append(
                f"{ctx_path}.actions: unknown action class '{key}' "
                f"(not a known class in SPEC §3.9 and not 'x.'-prefixed)"
            )


def validate_referenced_paths(
    group: dict, profile_dir: Path, label: str, errors: list[str]
) -> None:
    for arr_key, field in (("instructions", "path"), ("gates", "run"), ("extensions", "run")):
        if arr_key not in group:
            continue
        entries = group[arr_key]
        if not isinstance(entries, list):
            errors.append(f"{label}.{arr_key} must be an array")
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"{label}.{arr_key}[{i}] must be a table")
                continue
            if field in entry:
                relpath = entry[field]
                if not isinstance(relpath, str):
                    errors.append(f"{label}.{arr_key}[{i}].{field} must be a string")
                    continue
                full = profile_dir / relpath
                if not full.exists():
                    errors.append(
                        f"{label}.{arr_key}[{i}].{field} references a path that does not "
                        f"exist on disk: '{relpath}' (resolved: {full})"
                    )


def validate_common_sections(
    group: dict, profile_dir: Path, label: str, errors: list[str], warnings: list[str]
) -> None:
    """Applies the section-shape checks that can occur both at the base
    manifest level and inside any [environment.NAME] override (SPEC §2.1
    permits an environment to override any section except the header).
    """
    if "budget" in group:
        validate_budget_table(group["budget"], f"{label}budget", errors)
    if "models" in group:
        validate_models_table(group["models"], f"{label}models", errors)
    if "authority" in group:
        validate_authority_table(group["authority"], f"{label}authority", errors, warnings)
    if "sessions" in group:
        sessions = group["sessions"]
        if not isinstance(sessions, dict):
            errors.append(f"{label}sessions must be a table")
        elif "isolation" in sessions and sessions["isolation"] not in KNOWN_ISOLATION:
            errors.append(
                f"{label}sessions.isolation must be one of {sorted(KNOWN_ISOLATION)}, "
                f"got {sessions['isolation']!r}"
            )
    validate_referenced_paths(group, profile_dir, label.rstrip("."), errors)


def scan_compose(node: Any, path: str, errors: list[str]) -> None:
    """Any `compose` key anywhere in the manifest must be a known mode."""
    if isinstance(node, dict):
        for k, v in node.items():
            newpath = f"{path}.{k}" if path else k
            if k == "compose":
                if v not in KNOWN_COMPOSE:
                    errors.append(
                        f"{newpath} must be one of {sorted(KNOWN_COMPOSE)}, got {v!r}"
                    )
            else:
                scan_compose(v, newpath, errors)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            scan_compose(item, f"{path}[{i}]", errors)


def validate_spec_field(raw: dict, errors: list[str], warnings: list[str]) -> None:
    spec = raw.get("spec")
    if spec is None:
        errors.append("missing required field 'spec'")
        return
    if not isinstance(spec, str):
        errors.append(f"'spec' must be a string, got {spec!r}")
        return
    parts = spec.split(".")
    majmin = parts[0] if len(parts) < 2 else f"{parts[0]}.{parts[1]}"
    if majmin != SUPPORTED_SPEC_MAJMIN:
        warnings.append(
            f"spec = {spec!r} (major.minor {majmin!r}) is not known to this tool; "
            f"this tool knows {SUPPORTED_SPEC_MAJMIN!r}"
        )


def validate_budget_aggregate(raw: dict, errors: list[str]) -> None:
    """SPEC §3.5: the RESOLVED budget MUST contain a scope='*' limit. Because
    `limits` is an array (replaced wholesale, never merged — SPEC §2.1), the
    only context-independent way to guarantee this holds for every possible
    runtime resolution is to check every array that could end up being the
    final `limits`: the base's own array (the case where no environment
    matches), and each environment's own array where it overrides `limits`
    (the case where that environment is the last matching one to do so).
    See the JUDGMENT CALLS note in this file's module docstring companion
    (reported to the caller) for why this N+1 enumeration is equivalent to
    checking every reachable resolution rather than an approximation of it.
    """
    base_budget = raw.get("budget", {})
    base_limits = base_budget.get("limits") if isinstance(base_budget, dict) else None
    if not has_aggregate(base_limits):
        errors.append(
            "BUDGET AGGREGATE MISSING: base [budget].limits does not contain a "
            '`scope = "*"` entry — if no environment matches, the resident would '
            "run uncapped (SPEC §3.5)"
        )
    for env_name, env_table in raw.get("environment", {}).items():
        if not isinstance(env_table, dict):
            continue
        env_budget = env_table.get("budget")
        if isinstance(env_budget, dict) and "limits" in env_budget:
            if not has_aggregate(env_budget["limits"]):
                errors.append(
                    f"BUDGET AGGREGATE MISSING: [environment.{env_name}.budget].limits "
                    'replaces the base array wholesale but does not restate a '
                    '`scope = "*"` aggregate entry of its own (SPEC §3.5) — if this '
                    "environment is the last matching one to set `limits`, the "
                    "resident would run uncapped"
                )


def validate_environments_structure(
    raw: dict, profile_dir: Path, errors: list[str], warnings: list[str]
) -> None:
    environment = raw.get("environment", {})
    if not isinstance(environment, dict):
        errors.append("[environment] must be a table of named environments")
        return
    for env_name, env_table in environment.items():
        if not isinstance(env_table, dict):
            errors.append(f"[environment.{env_name}] must be a table")
            continue
        when = env_table.get("when", {})
        if not isinstance(when, dict):
            errors.append(f"environment.{env_name}.when must be a table")
        else:
            for k in when:
                if k not in KNOWN_SELECTORS:
                    # JUDGMENT CALL: SPEC §2.1 / the task brief is explicit that an
                    # unknown selector is a *resolution* behavior (fail-closed
                    # non-match), not a hard validation error — so this is a
                    # warning, not an error, and does not affect `validate`'s
                    # exit code. `resolve --explain` is where it becomes visible
                    # as the reason an environment never matches.
                    warnings.append(
                        f"environment.{env_name}.when has unknown selector '{k}' — "
                        "this environment will fail closed (never match) per SPEC §2.1"
                    )
        validate_common_sections(
            env_table, profile_dir, f"environment.{env_name}.", errors, warnings
        )


def validate_profile(profile_dir: Path) -> tuple[list[str], list[str], dict | None]:
    """Returns (errors, warnings, manifest). manifest is None if unparsable."""
    raw, load_errors = load_manifest(profile_dir)
    if raw is None:
        return load_errors, [], None

    errors: list[str] = []
    warnings: list[str] = []

    validate_spec_field(raw, errors, warnings)
    validate_common_sections(raw, profile_dir, "", errors, warnings)
    validate_environments_structure(raw, profile_dir, errors, warnings)
    scan_compose(raw, "", errors)
    validate_budget_aggregate(raw, errors)

    return errors, warnings, raw


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


class Context:
    def __init__(self, cwd: str, hostname: str, git_org: str | None):
        self.cwd = cwd
        self.hostname = hostname
        self.git_org = git_org


def detect_git_org(cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if not url:
        return None
    m = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?/?$", url)
    return m.group(1) if m else None


def build_context(cwd_arg: str | None, hostname_arg: str | None, git_org_arg: str | None) -> Context:
    cwd = os.path.abspath(cwd_arg) if cwd_arg else os.getcwd()
    hostname = hostname_arg if hostname_arg is not None else socket.gethostname()
    if git_org_arg is not None:
        git_org = git_org_arg
    else:
        git_org = detect_git_org(cwd)
    return Context(cwd=cwd, hostname=hostname, git_org=git_org)


def evaluate_when(when: dict, ctx: Context) -> tuple[bool, str]:
    """Returns (matched, reason). `reason` names the first failing predicate
    (in the order the `when` table declares them) or, on a match, says so.
    An unknown selector is itself treated as a first-failing-predicate case
    (fail closed, SPEC §2.1), in whatever position it appears in the table.
    """
    if not when:
        return False, "no `when` block — environments with no selectors never match automatically"
    for key, val in when.items():
        if key not in KNOWN_SELECTORS:
            return False, f"unknown selector '{key}' — fails closed per SPEC §2.1"
        if key == "path":
            pattern = os.path.expanduser(str(val))
            cwd = os.path.expanduser(ctx.cwd)
            if not fnmatch.fnmatch(cwd, pattern):
                return False, f"path: cwd '{cwd}' does not match glob '{val}'"
        elif key == "hostname":
            if ctx.hostname != val:
                return False, f"hostname: '{ctx.hostname}' != '{val}'"
        elif key == "git_org":
            if ctx.git_org != val:
                return False, f"git_org: {ctx.git_org!r} != {val!r}"
        elif key == "env":
            if not isinstance(val, str) or "=" not in val:
                return False, f"env: malformed selector {val!r} (expected \"NAME=value\")"
            name, _, value = val.partition("=")
            actual = os.environ.get(name)
            if actual != value:
                return False, f"env: {name}={actual!r} != {value!r}"
    return True, "all predicates held"


def merge_tables(base: dict, override: dict, env_name: str, source: dict) -> None:
    """Mutates `base` (the accumulating effective config) and `source` (a
    parallel tree recording provenance) in place, applying SPEC §2.1 merge
    semantics: tables merge recursively, scalars and arrays replace
    wholesale. A `source` leaf of a plain string means "this whole subtree
    came from environment `string`"; a dict means "descend for finer-grained
    provenance."
    """
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            if not isinstance(source.get(key), dict):
                source[key] = {}
            merge_tables(base[key], val, env_name, source[key])
        else:
            base[key] = copy.deepcopy(val)
            source[key] = env_name


def flatten_sources(
    effective: dict, source: dict, prefix: str, inherited_env: str | None, out: dict
) -> None:
    for key, val in effective.items():
        path = f"{prefix}.{key}" if prefix else key
        s = source.get(key) if isinstance(source, dict) else None
        effective_env = s if isinstance(s, str) else inherited_env
        if isinstance(val, dict):
            child_source = s if isinstance(s, dict) else {}
            flatten_sources(val, child_source, path, effective_env, out)
        else:
            if effective_env is not None:
                out[path] = effective_env


def resolve_profile(
    profile_dir: Path, ctx: Context
) -> tuple[dict | None, list[str], list[str], dict | None]:
    """Returns (effective_config_or_None, errors, warnings, explain_info_or_None)."""
    errors, warnings, raw = validate_profile(profile_dir)
    if errors or raw is None:
        return None, errors, warnings, None

    effective = {k: copy.deepcopy(v) for k, v in raw.items() if k != "environment"}
    source: dict = {}
    env_reports = []

    for env_name, env_table in raw.get("environment", {}).items():
        when = env_table.get("when", {}) if isinstance(env_table, dict) else {}
        matched, reason = evaluate_when(when if isinstance(when, dict) else {}, ctx)
        env_reports.append({"name": env_name, "matched": matched, "reason": reason})
        if matched:
            override = {k: v for k, v in env_table.items() if k != "when"}
            merge_tables(effective, override, env_name, source)

    # Defense in depth: validate_profile already proves this holds for every
    # *reachable* resolution (see validate_budget_aggregate), so this should
    # be unreachable in practice — but resolve refuses to hand back an
    # uncapped config rather than trust that proof blindly (SPEC §4.1).
    budget = effective.get("budget", {})
    limits = budget.get("limits") if isinstance(budget, dict) else None
    if not has_aggregate(limits):
        errors.append(
            'BUDGET AGGREGATE MISSING: the resolved budget lacks a `scope = "*"` '
            "aggregate limit after environment resolution (SPEC §3.5) — refusing "
            "to resolve rather than report an uncapped profile as usable"
        )
        return None, errors, warnings, None

    sources: dict = {}
    flatten_sources(effective, source, "", None, sources)
    explain_info = {"environments": env_reports, "sources": sources}
    return effective, errors, warnings, explain_info


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------


def fmt_key(k: str) -> str:
    return k if BARE_KEY.match(k) else json.dumps(k)


def fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(fmt_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{fmt_key(k)} = {fmt_value(val)}" for k, val in v.items()) + " }"
    return json.dumps(str(v))


def dump_subtable(prefix: str, table: dict, lines: list[str]) -> None:
    scalars = {}
    subtables = {}
    for k, v in table.items():
        if isinstance(v, dict):
            subtables[k] = v
        else:
            scalars[k] = v
    lines.append(f"[{prefix}]")
    for k, v in scalars.items():
        lines.append(f"{fmt_key(k)} = {fmt_value(v)}")
    lines.append("")
    for k, v in subtables.items():
        dump_subtable(f"{prefix}.{k}", v, lines)


def dump_toml_ish(effective: dict) -> str:
    lines: list[str] = []
    root_scalars = {}
    subtables = {}
    array_tables = {}
    for k, v in effective.items():
        if k in ARRAY_OF_TABLES_KEYS and isinstance(v, list):
            array_tables[k] = v
        elif isinstance(v, dict):
            subtables[k] = v
        else:
            root_scalars[k] = v
    for k, v in root_scalars.items():
        lines.append(f"{fmt_key(k)} = {fmt_value(v)}")
    if root_scalars:
        lines.append("")
    for k, v in subtables.items():
        dump_subtable(k, v, lines)
    for k, entries in array_tables.items():
        for entry in entries:
            lines.append(f"[[{k}]]")
            if isinstance(entry, dict):
                for kk, vv in entry.items():
                    lines.append(f"{fmt_key(kk)} = {fmt_value(vv)}")
            lines.append("")
    text = "\n".join(lines).rstrip("\n") + "\n"
    return text


def render_explain_prose(explain_info: dict) -> str:
    lines = []
    lines.append("# Environments considered (declaration order):")
    for rep in explain_info["environments"]:
        status = "MATCHED" if rep["matched"] else "did not match"
        lines.append(f"#   {rep['name']}: {status} — {rep['reason']}")
    if not explain_info["environments"]:
        lines.append("#   (none declared)")
    lines.append("#")
    lines.append("# Effective values that did not come from the base:")
    if explain_info["sources"]:
        for path, env in sorted(explain_info["sources"].items()):
            lines.append(f"#   {path} <- environment '{env}'")
    else:
        lines.append("#   (none — every effective value came from the base)")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> int:
    profile_dir = Path(args.profile_dir)
    errors, warnings, _raw = validate_profile(profile_dir)
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"\nProfile is INVALID: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1
    print(f"Profile is valid ({len(warnings)} warning(s)).")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    profile_dir = Path(args.profile_dir)
    ctx = build_context(args.cwd, args.hostname, args.git_org)
    effective, errors, warnings, explain_info = resolve_profile(profile_dir, ctx)

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"\nProfile could not be resolved: {len(errors)} error(s).", file=sys.stderr)
        return 1

    assert effective is not None and explain_info is not None

    if args.json:
        payload: dict[str, Any] = {"config": effective}
        if args.explain:
            payload["explain"] = explain_info
        print(json.dumps(payload, indent=2, sort_keys=False))
    else:
        if args.explain:
            print(render_explain_prose(explain_info))
        print(dump_toml_ish(effective), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chevaline.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate a profile directory")
    p_validate.add_argument("profile_dir", help="Path to the profile directory")
    p_validate.set_defaults(func=cmd_validate)

    p_resolve = sub.add_parser("resolve", help="Resolve a profile's effective configuration")
    p_resolve.add_argument("profile_dir", help="Path to the profile directory")
    p_resolve.add_argument("--explain", action="store_true", help="Explain environment resolution")
    p_resolve.add_argument("--json", action="store_true", help="Emit JSON instead of TOML-ish text")
    p_resolve.add_argument("--cwd", default=None, help="Override the working directory used for `path` selectors")
    p_resolve.add_argument("--hostname", default=None, help="Override the hostname used for `hostname` selectors")
    p_resolve.add_argument("--git-org", dest="git_org", default=None, help="Override the git org used for `git_org` selectors")
    p_resolve.set_defaults(func=cmd_resolve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
