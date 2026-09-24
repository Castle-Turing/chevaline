# opencode adapter

The reference adapter for OpenCode. Given a Chevaline profile, it renders
the resolved (effective) configuration into OpenCode's user-level config,
per the adapter contract in SPEC.md §4.

```
python3 adapters/opencode/adapter.py render <profile-dir> [--dry-run]
```

Run `--dry-run` first: it prints the full render report without touching
anything. The same flags as `tools/chevaline.py resolve` control the
environment-resolution context (`--cwd`, `--hostname`, `--git-org`,
`--environment`).

## Targets and ownership

| File | Mechanism |
|---|---|
| `~/.config/opencode/AGENTS.md` | Marker-comment-delimited region; text outside the markers is never touched. A damaged marker pair aborts the render. |
| `~/.config/opencode/opencode.json[c]` | The `plugin` array. Whichever of `.jsonc`/`.json` exists is edited (preferring `.jsonc`); `opencode.json` is created when neither does. A config that does not parse as plain JSON — comments — is declined loudly rather than rewritten, because re-serializing would destroy what the resident wrote. |
| `~/.config/opencode/opencode.chevaline.json` | The sidecar: which `plugin` entries the adapter owns. Hand-written entries survive re-renders; dropping a plugin from the profile removes exactly what the adapter added. |

## Mapping

| Manifest section | OpenCode surface |
|---|---|
| `[[instructions]]` | `AGENTS.md` region (harness-filtered, concatenated in order) |
| `[[plugins]]` | Plugin store checkout (SPEC §3.11) → absolute paths to the checkout's `.opencode/plugins/*.mjs` entry points in the config's `plugin` array |
| `[harnesses]` | Decides whether this adapter runs at all (`prefer` without `opencode` → decline) |
| `[[environment]]` | Resolved before rendering; the report names what matched and why |
| `[models]`, `[authority]`, `[budget]`, `[[gates]]`, `[sessions]`, `[[extensions]]` | Reported as skipped — no rendering yet. Budget is additionally reported as NOT ENFORCED per SPEC §4.1; the claude-code adapter's budget/gate prose has no counterpart here yet |

## Plugins

Materialization shares the plugin store with every other adapter
(`$XDG_DATA_HOME/chevaline/plugins/<id>/<pin>`; `--plugin-store`
overrides) and honors the resolved `exec.install` authority per SPEC
§4.2: `approval` — or unresolved — requires `--allow-install` on the
invocation; `reported` fetches and says so; a store entry already at
the pin is used offline. Enablement is OpenCode's own documented
mechanism, the `plugin` array in the global config: OpenCode is a
client/server system whose server loads plugins from config in every
mode, so entries here reach TUI sessions and programmatically driven
servers alike. A checkout with no `.opencode/plugins/*.mjs` carries no
OpenCode packaging and is reported, not guessed at.
