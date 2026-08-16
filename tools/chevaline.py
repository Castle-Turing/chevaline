#!/usr/bin/env python3
"""chevaline.py — reference validator + resolver CLI for the Chevaline
profile standard (SPEC.md v0.3).

    python3 chevaline.py validate <profile-dir>
    python3 chevaline.py resolve  <profile-dir> [--explain] [--json]
                                   [--cwd PATH] [--hostname NAME] [--git-org ORG]
                                   [--environment NAME ...]

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

SUPPORTED_SPEC_VERSION = "0.3"
SUPPORTED_SPEC_TUPLE = (0, 3)

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

# SPEC §2.2: the four canonical composition modes.
KNOWN_COMPOSE = {"layer", "defer", "insist", "restrict"}

# SPEC §2.2's shape table. Which modes are *valid* (not just which is the
# default) differs by the shape of the preference:
#   - Additive (a set of checks, e.g. gates): layer/defer/insist, default layer.
#   - Single-valued (an enum or scalar, e.g. session isolation): defer/insist
#     only, default defer. `layer` is incoherent here (SPEC §3.8).
#   - Permission or limit (authority): restrict only, default restrict.
# In v0.3 as corrected, authority is the only permission-or-limit-shaped
# section, and it now REJECTS an explicit `compose` key outright (SPEC §3.9:
# "the mode is not settable") rather than accepting `restrict` as a written
# value. PERMISSION_COMPOSE_MODES is therefore kept only for documentation
# parity with the SPEC §2.2 table; nothing in v0.3 validates a field against
# it, since the one section that shape describes doesn't take a `compose`
# key at all. See the JUDGMENT CALLS this file's docstring companion
# reports for how [models] came to be treated as single-valued below.
SINGLE_VALUED_COMPOSE_MODES = {"defer", "insist"}
ADDITIVE_COMPOSE_MODES = {"layer", "defer", "insist"}
PERMISSION_COMPOSE_MODES = {"restrict"}  # documentation only — see above.

# The forward-compatible-unknown-selector case (SPEC §2.1) must be surfaced
# "prominently rather than as a quiet warning." This marker prefixes such
# warning strings so CLI output (validate) and --explain (resolve) can both
# single them out for prominent display instead of treating them as an
# ordinary warning.
FORWARD_COMPAT_MARKER = "FORWARD-COMPATIBLE UNKNOWN SELECTOR"

ISO4217_SHAPED = re.compile(r"^[A-Z]{3}$")
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

# Sections that flatten_sources / merge_tables treat as genuine TOML
# "array of tables" ([[x]]) at the top level, matching SPEC.md's own
# rendering of them. budget.limits is also an array-of-dicts but SPEC.md
# renders it as an inline array literal, so it is intentionally excluded
# here and handled by the generic inline-value formatter instead.
# NOTE: `environment` is also `[[environment]]` (SPEC §3.2, §2.1) but is
# never present in an *effective* (resolved) config — it is consumed during
# resolution, not rendered — so it deliberately does not appear here; see
# resolve_profile, which strips "environment" out of `effective` up front.
ARRAY_OF_TABLES_KEYS = {"instructions", "gates", "extensions"}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def has_aggregate(limits: Any) -> bool:
    """True if `limits` (a budget.limits array) contains a scope='*' entry."""
    if not isinstance(limits, list):
        return False
    return any(isinstance(e, dict) and e.get("scope") == "*" for e in limits)


def parse_majmin(spec_str: str) -> tuple[int, int] | None:
    """Parse a `spec` string's major.minor as a comparable tuple. `spec` may
    omit the patch component (SPEC §3.1: `"0.3"` means `0.3.x`), so only the
    first two dot-separated components are read; anything unparseable as
    integers returns None.
    """
    parts = spec_str.split(".")
    if len(parts) < 1:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None
    return (major, minor)


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


def check_compose(value: Any, valid_modes: set[str], ctx_path: str, errors: list[str]) -> None:
    """Validate a `compose` value against both the four canonical modes
    (SPEC §2.2) and the narrower set valid for this preference's shape.
    """
    if not isinstance(value, str) or value not in KNOWN_COMPOSE:
        errors.append(f"{ctx_path}.compose must be one of {sorted(KNOWN_COMPOSE)}, got {value!r}")
        return
    if value not in valid_modes:
        errors.append(
            f"{ctx_path}.compose = {value!r} is not valid for this preference's shape "
            f"(SPEC §2.2) — valid modes here are {sorted(valid_modes)}"
        )


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
    # Budget carries no `compose` key at all (SPEC §2.2, §3.5) — deliberately
    # not specially checked/rejected here; an explicit `compose` under
    # [budget] would only be caught by the generic scan_compose() fallback
    # (valid if it happens to be one of the four canonical modes). See the
    # JUDGMENT CALLS note near scan_compose().


def validate_models_table(models: Any, ctx_path: str, errors: list[str]) -> None:
    if not isinstance(models, dict):
        errors.append(f"{ctx_path} must be a table")
        return
    for key in models:
        if key == "compose":
            continue
        if key not in KNOWN_TIERS and not key.startswith("x."):
            errors.append(
                f"{ctx_path}: unknown tier key '{key}' "
                f"(must be one of {sorted(KNOWN_TIERS)} or 'x.'-prefixed)"
            )
    if "compose" in models:
        # JUDGMENT CALL: SPEC §3.4 (as corrected) says [models] carries
        # `compose`, defaulting to `defer`, and explicitly disqualifies
        # `restrict` ("a tier-to-identifier mapping has no stated
        # ordering"). SPEC §2.2's shape table doesn't name a row for
        # [models] directly. By elimination — restrict is out, default is
        # defer, and nothing suggests a resident's tier mapping "layers on
        # top of" a project's model requirement any more coherently than a
        # session-isolation preference does — [models] is validated here as
        # single-valued shape (defer/insist only, `layer` rejected), the
        # same treatment SPEC §3.3 gives [harnesses] ("single-valued in
        # effect"). RFC 0004 already flags this section as unsettled.
        check_compose(models["compose"], SINGLE_VALUED_COMPOSE_MODES, ctx_path, errors)


def validate_harnesses_table(harnesses: Any, ctx_path: str, errors: list[str]) -> None:
    if not isinstance(harnesses, dict):
        errors.append(f"{ctx_path} must be a table")
        return
    if "prefer" in harnesses and not isinstance(harnesses["prefer"], list):
        errors.append(f"{ctx_path}.prefer must be an array")
    if "compose" in harnesses:
        # SPEC §3.3: "single-valued in effect; defer is the default."
        check_compose(harnesses["compose"], SINGLE_VALUED_COMPOSE_MODES, ctx_path, errors)


def validate_sessions_table(sessions: Any, ctx_path: str, errors: list[str]) -> None:
    if not isinstance(sessions, dict):
        errors.append(f"{ctx_path} must be a table")
        return
    if "isolation" in sessions and sessions["isolation"] not in KNOWN_ISOLATION:
        errors.append(
            f"{ctx_path}.isolation must be one of {sorted(KNOWN_ISOLATION)}, "
            f"got {sessions['isolation']!r}"
        )
    if "compose" in sessions:
        # SPEC §3.8: single-valued, so only defer/insist are valid; `layer`
        # is rejected outright (falls out of SINGLE_VALUED_COMPOSE_MODES not
        # containing "layer" — check_compose() reports it as invalid for
        # this shape rather than needing a session-specific special case).
        check_compose(sessions["compose"], SINGLE_VALUED_COMPOSE_MODES, ctx_path, errors)


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
    if "compose" in auth:
        # SPEC §3.9 (as corrected): "Authority composes with `restrict`,
        # always, and the mode is not settable. Writing a `compose` key here
        # is an error rather than a preference." This is unconditional —
        # unlike every other section's compose check, there is no valid
        # value to write, so this rejects the key's presence outright rather
        # than validating its value.
        errors.append(
            f"{ctx_path}.compose is not a valid field — authority composes with "
            "`restrict` always and the mode is not settable (SPEC §3.9); remove this key"
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


def validate_array_item_compose(
    group: dict, key: str, valid_modes: set[str], ctx_path_prefix: str, errors: list[str]
) -> None:
    """Validates `compose` on each entry of an array-of-tables section
    (`[[gates]]` / `[[extensions]]`). Entry-shape errors themselves (missing
    `id`, etc.) are out of scope for this reference tool beyond what already
    existed in v0.2; only `compose` is new here.
    """
    entries = group.get(key)
    if not isinstance(entries, list):
        return
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and "compose" in entry:
            check_compose(entry["compose"], valid_modes, f"{ctx_path_prefix}{key}[{i}]", errors)


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
    manifest level and inside any `[[environment]]` override (SPEC §3.2
    permits an environment to override any section except the header).
    `label` is either "" (base manifest) or "environment.<ref>." (an
    environment override), matching the v0.2 convention.
    """
    if "budget" in group:
        validate_budget_table(group["budget"], f"{label}budget", errors)
    if "models" in group:
        validate_models_table(group["models"], f"{label}models", errors)
    if "harnesses" in group:
        validate_harnesses_table(group["harnesses"], f"{label}harnesses", errors)
    if "authority" in group:
        validate_authority_table(group["authority"], f"{label}authority", errors, warnings)
    if "sessions" in group:
        validate_sessions_table(group["sessions"], f"{label}sessions", errors)
    validate_array_item_compose(group, "gates", ADDITIVE_COMPOSE_MODES, label, errors)
    validate_array_item_compose(group, "extensions", ADDITIVE_COMPOSE_MODES, label, errors)
    validate_referenced_paths(group, profile_dir, label.rstrip("."), errors)


def scan_compose(node: Any, path: str, errors: list[str]) -> None:
    """Any `compose` key anywhere in the manifest must be a known mode. This
    is a generic safety net over the whole tree, on top of (and partially
    redundant with) the section-specific shape checks in
    validate_common_sections(): it exists so a `compose` key showing up
    somewhere SPEC.md doesn't specifically discuss (e.g. inside a custom
    `x.`-prefixed section, or on [budget]/[instructions], which SPEC §2.2
    says "carry no compose key" but does not say is a validation error to
    write anyway) is still checked against the four canonical modes rather
    than silently accepted as an arbitrary string.
    """
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


def validate_spec_field(raw: dict, errors: list[str], warnings: list[str]) -> str | None:
    """Validates the `spec` field and returns its relation to
    SUPPORTED_SPEC_TUPLE: "newer", "known", "older", or None (missing /
    unparseable — the caller should treat this like "known", i.e. the
    strict branch, since forward-compat leniency cannot be granted without
    a parseable version to compare).
    """
    spec = raw.get("spec")
    if spec is None:
        errors.append("missing required field 'spec'")
        return None
    if not isinstance(spec, str):
        errors.append(f"'spec' must be a string, got {spec!r}")
        return None
    parsed = parse_majmin(spec)
    if parsed is None:
        errors.append(f"'spec' could not be parsed as a major.minor version, got {spec!r}")
        return None
    if parsed > SUPPORTED_SPEC_TUPLE:
        warnings.append(
            f"spec = {spec!r} declares a version newer than this tool implements "
            f"({SUPPORTED_SPEC_VERSION!r}); unrecognized selectors are therefore treated as "
            "forward-compatible (SPEC §2.1) rather than errors"
        )
        return "newer"
    if parsed == SUPPORTED_SPEC_TUPLE:
        return "known"
    # JUDGMENT CALL: SPEC §2.1's two named branches are "newer than the
    # adapter implements" (forward-compat leniency) and "one the adapter
    # fully implements" (strict). It does not name a third branch for a
    # spec version OLDER than what the tool implements. An older-than-tool
    # declaration cannot be a from-the-future selector, so there is no
    # forward-compat rationale for leniency here either — this tool treats
    # "older" the same as "known" for unknown-selector severity (strict:
    # an error, not a warning), while still separately warning that the
    # declared version itself is not what this tool was built against.
    warnings.append(
        f"spec = {spec!r} declares a version older than this tool implements "
        f"({SUPPORTED_SPEC_VERSION!r}); this tool validates against 0.3 semantics, which may "
        "not match what an older-versioned profile intended"
    )
    return "older"


def validate_budget_aggregate(raw: dict, errors: list[str]) -> None:
    """SPEC §3.5: the RESOLVED budget MUST contain a scope='*' limit. Because
    `limits` is an array (replaced wholesale, never merged — SPEC §2.1), the
    only context-independent way to guarantee this holds for every possible
    runtime resolution is to check every array that could end up being the
    final `limits`: the base's own array (the case where no environment
    matches), and each environment's own array where it overrides `limits`
    (the case where that environment is the last matching one to do so).
    """
    base_budget = raw.get("budget", {})
    base_limits = base_budget.get("limits") if isinstance(base_budget, dict) else None
    if not has_aggregate(base_limits):
        errors.append(
            "BUDGET AGGREGATE MISSING: base [budget].limits does not contain a "
            '`scope = "*"` entry — if no environment matches, the resident would '
            "run uncapped (SPEC §3.5)"
        )
    environments = raw.get("environment", [])
    if not isinstance(environments, list):
        return  # structural error already reported elsewhere
    for i, env_table in enumerate(environments):
        if not isinstance(env_table, dict):
            continue
        env_ref = env_table.get("name") if isinstance(env_table.get("name"), str) else f"[{i}]"
        env_budget = env_table.get("budget")
        if isinstance(env_budget, dict) and "limits" in env_budget:
            if not has_aggregate(env_budget["limits"]):
                errors.append(
                    f"BUDGET AGGREGATE MISSING: [[environment]] '{env_ref}' .budget.limits "
                    'replaces the base array wholesale but does not restate a '
                    '`scope = "*"` aggregate entry of its own (SPEC §3.5) — if this '
                    "environment is the last matching one to set `limits`, the "
                    "resident would run uncapped"
                )


def validate_environments_structure(
    raw: dict, profile_dir: Path, spec_relation: str | None, errors: list[str], warnings: list[str]
) -> None:
    environments = raw.get("environment", [])
    if not isinstance(environments, list):
        errors.append(
            "[environment] must be declared as an array of tables `[[environment]]` "
            "(SPEC §2.1, §3.2) — TOML guarantees array order but not table order, which is "
            "why v0.3 requires this form instead of named `[environment.NAME]` tables"
        )
        return

    seen_names: set[str] = set()
    for i, env_table in enumerate(environments):
        if not isinstance(env_table, dict):
            errors.append(f"environment[{i}] must be a table")
            continue

        name = env_table.get("name")
        if not isinstance(name, str) or not name:
            errors.append(
                f"environment[{i}] is missing required field 'name' (SPEC §3.2) — "
                "every [[environment]] entry must be named, and the name is what "
                "`explain` output and error messages refer to"
            )
            ref = f"[{i}]"
        else:
            if name in seen_names:
                errors.append(
                    f"environment[{i}]: duplicate environment name '{name}' — "
                    "environment names must be unique (SPEC §3.2)"
                )
            seen_names.add(name)
            ref = name

        label = f"environment.{ref}."
        when = env_table.get("when", {})
        if not isinstance(when, dict):
            errors.append(f"{label}when must be a table")
        else:
            for k in when:
                if k not in KNOWN_SELECTORS:
                    # JUDGMENT CALL: SPEC §2.1 is explicit that an unknown
                    # selector's severity depends on the profile's declared
                    # `spec` version relative to what this tool implements:
                    #   - "known" (== 0.3, what this tool fully implements)
                    #     or "older": this cannot be a from-the-future
                    #     selector, so it is a validation ERROR.
                    #   - "newer": this may be a real selector from a future
                    #     minor version this tool doesn't know about yet, so
                    #     it is a WARNING (and, per SPEC's own caveat that
                    #     0.x permits breaking renames, an unusually
                    #     prominent one — see FORWARD_COMPAT_MARKER).
                    #   - None (spec missing/unparseable): treated as the
                    #     strict branch, since leniency cannot be granted
                    #     without a version to compare against.
                    if spec_relation == "newer":
                        warnings.append(
                            f"{FORWARD_COMPAT_MARKER}: {label}when has unknown selector "
                            f"'{k}' — profile declares spec {raw.get('spec')!r}, newer than "
                            f"this tool's {SUPPORTED_SPEC_VERSION!r}; treated as "
                            "forward-compatible (this environment fails closed and never "
                            "matches, SPEC §2.1) rather than a typo. NOTE: SPEC §2.1 also "
                            "warns that 0.x permits selector renames without notice, so a "
                            "renamed (not just new) selector would land here too — verify "
                            "this is really unrecognized, not a rename, before trusting the "
                            "forward-compat read."
                        )
                    else:
                        errors.append(
                            f"{label}when has unknown selector '{k}' — spec "
                            f"{raw.get('spec')!r} is fully implemented (or older than what "
                            "this tool implements), so an unrecognized selector cannot be a "
                            "forward-compat case and is treated as a typo (SPEC §2.1)"
                        )

        validate_common_sections(env_table, profile_dir, label, errors, warnings)


def validate_profile(profile_dir: Path) -> tuple[list[str], list[str], dict | None]:
    """Returns (errors, warnings, manifest). manifest is None if unparsable."""
    raw, load_errors = load_manifest(profile_dir)
    if raw is None:
        return load_errors, [], None

    errors: list[str] = []
    warnings: list[str] = []

    spec_relation = validate_spec_field(raw, errors, warnings)
    validate_common_sections(raw, profile_dir, "", errors, warnings)
    validate_environments_structure(raw, profile_dir, spec_relation, errors, warnings)
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
    # SPEC §3.2: "`git_org` reads the `origin` remote specifically. A
    # repository may have several remotes and matching must not depend on
    # which one an adapter happened to pick." `remote.origin.url` below
    # already names `origin` explicitly rather than e.g. asking git for
    # "the" remote generically, so this already satisfies that rule.
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
    Explicit activation (SPEC §3.2, "Adapters MAY support...") bypasses this
    function entirely rather than being handled inside it — see
    resolve_profile, which only calls evaluate_when for environments not
    named via --environment.
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
    profile_dir: Path, ctx: Context, explicit_names: set[str] | None = None
) -> tuple[dict | None, list[str], list[str], dict | None]:
    """Returns (effective_config_or_None, errors, warnings, explain_info_or_None).

    `explicit_names`, if given, is a set of environment names to activate by
    SPEC §3.2's "explicit activation": matching bypasses `when` entirely for
    those environments (they are treated as matched unconditionally,
    regardless of whether they even declare a `when` block), and is the only
    way a `when`-less environment ever applies. A name in `explicit_names`
    that does not correspond to any declared `[[environment]]` is a resolve
    -time error — almost certainly a typo, and silently ignoring it would
    mean the resident's explicit request was quietly dropped.
    """
    errors, warnings, raw = validate_profile(profile_dir)
    if errors or raw is None:
        return None, errors, warnings, None

    environments = raw.get("environment", []) or []
    declared_names = {
        env["name"] for env in environments if isinstance(env, dict) and isinstance(env.get("name"), str)
    }
    if explicit_names:
        unknown = explicit_names - declared_names
        if unknown:
            for name in sorted(unknown):
                errors.append(
                    f"--environment {name!r} does not match any declared [[environment]] "
                    f"name (declared: {sorted(declared_names)})"
                )
            return None, errors, warnings, None

    effective = {k: copy.deepcopy(v) for k, v in raw.items() if k != "environment"}
    source: dict = {}
    env_reports = []

    for env_table in environments:
        env_name = env_table["name"]
        when = env_table.get("when", {}) if isinstance(env_table, dict) else {}
        if explicit_names and env_name in explicit_names:
            matched, reason = True, "explicitly activated via --environment (bypasses `when`, SPEC §3.2)"
        else:
            matched, reason = evaluate_when(when if isinstance(when, dict) else {}, ctx)
        env_reports.append({"name": env_name, "matched": matched, "reason": reason})
        if matched:
            override = {k: v for k, v in env_table.items() if k not in ("when", "name")}
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
        if FORWARD_COMPAT_MARKER in rep["reason"] or "unknown selector" in rep["reason"]:
            # Made conspicuous per SPEC §2.1's caveat that a forward-
            # compatible unknown should be surfaced prominently, not as a
            # quiet warning: this environment's non-match may not be
            # authoritative, since a newer tool version could recognize the
            # selector (or the selector could be a 0.x rename rather than a
            # genuine addition — SPEC §2.1 warns 0.x permits that too).
            lines.append(
                "#     >>> NOTICE: this non-match rests on an unrecognized `when` "
                "selector. Do not treat it as final without checking whether the "
                "selector is a forward-compatible addition, a rename this tool "
                "doesn't know about, or a plain typo. <<<"
            )
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


def print_warning(w: str, file=None) -> None:
    """Prints a warning, giving forward-compatible-unknown-selector warnings
    a visibly different label so they aren't lost among ordinary warnings
    (SPEC §2.1: "adapters SHOULD surface any forward-compatible unknown
    prominently rather than as a quiet warning").
    """
    if w.startswith(FORWARD_COMPAT_MARKER):
        print(f"NOTICE (forward-compatible — verify before trusting): {w}", file=file)
    else:
        print(f"WARNING: {w}", file=file)


def cmd_validate(args: argparse.Namespace) -> int:
    profile_dir = Path(args.profile_dir)
    errors, warnings, _raw = validate_profile(profile_dir)
    for w in warnings:
        print_warning(w)
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
    explicit_names = set(args.environment) if args.environment else None
    effective, errors, warnings, explain_info = resolve_profile(profile_dir, ctx, explicit_names)

    for w in warnings:
        print_warning(w, file=sys.stderr)
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
    p_resolve.add_argument(
        "--environment",
        action="append",
        default=None,
        metavar="NAME",
        help=(
            "Explicitly activate an environment by name, bypassing its `when` block "
            "entirely (SPEC §3.2 'explicit activation'); the only way a `when`-less "
            "environment ever applies. May be repeated to activate several."
        ),
    )
    p_resolve.set_defaults(func=cmd_resolve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
