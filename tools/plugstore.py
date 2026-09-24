#!/usr/bin/env python3
"""plugstore.py — the shared plugin store (SPEC §3.11, §4.2).

Materializes a `[[plugins]]` entry's `source` at its `pin` into
`$XDG_DATA_HOME/chevaline/plugins/<id>/<pin>` (default
`~/.local/share/chevaline/plugins/...`), the one cross-harness location
the spec names. Adapters call this; the authority decision (§4.2:
materializing is an `exec.install`-class action) is the CALLER's to make
before calling — nothing here checks authority, so an adapter must not
reach this code without having settled it.

Standard library only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class PlugstoreError(RuntimeError):
    """A materialization failure. The message is resident-facing."""


def default_store() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "chevaline" / "plugins"


def _head_of(checkout: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def checkout_dir(store: Path, plugin_id: str, pin: str) -> Path:
    return store / plugin_id / pin


def materialize(
    plugin_id: str, source: str, pin: str, store: Path | None = None
) -> tuple[Path, bool]:
    """Ensure `source` at commit `pin` exists in the store; return
    (checkout_path, fetched) where `fetched` says whether the network was
    touched. Idempotent: a store entry already at the pin is verified and
    returned without fetching (§4.2). Raises PlugstoreError on any failure,
    and never leaves a half-materialized directory at the final path — the
    clone lands in a scratch path and is renamed in only after the pin
    verifies.
    """
    store = store if store is not None else default_store()
    dest = checkout_dir(store, plugin_id, pin)

    if dest.exists():
        head = _head_of(dest)
        if head == pin:
            return dest, False
        raise PlugstoreError(
            f"plugin store entry {dest} exists but its HEAD is {head!r}, not "
            f"the declared pin {pin} — refusing to use or repair it silently; "
            "remove the directory and re-render"
        )

    scratch = dest.parent / f".{pin}.partial"
    if scratch.exists():
        shutil.rmtree(scratch)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clone = subprocess.run(
        ["git", "clone", "--quiet", source, str(scratch)],
        capture_output=True,
        text=True,
    )
    if clone.returncode != 0:
        shutil.rmtree(scratch, ignore_errors=True)
        raise PlugstoreError(
            f"git clone of {source!r} failed: {clone.stderr.strip() or clone.stdout.strip()}"
        )
    pinned = subprocess.run(
        ["git", "-C", str(scratch), "checkout", "--quiet", "--detach", pin],
        capture_output=True,
        text=True,
    )
    if pinned.returncode != 0:
        shutil.rmtree(scratch, ignore_errors=True)
        raise PlugstoreError(
            f"commit {pin} does not exist in {source!r}: "
            f"{pinned.stderr.strip() or pinned.stdout.strip()}"
        )
    head = _head_of(scratch)
    if head != pin:
        shutil.rmtree(scratch, ignore_errors=True)
        raise PlugstoreError(
            f"checkout of {source!r} verified to HEAD {head!r}, not the "
            f"declared pin {pin} — refusing the checkout (SPEC §4.2)"
        )
    scratch.rename(dest)
    return dest, True
