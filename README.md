# Dredge

Dredge is a Python CLI for command-scoped filesystem tracing. The current collector records wrapper provenance plus before/after filesystem metadata outcomes for a CLI-launched command; it does not observe every read, list, or stat syscall.

It runs an agent or tool command under a bounded trace, records the filesystem evidence Dredge can observe for that run, and stores it as append-only structured data. It is built for developers and local automation workflows that need a stable interface for what an agent touched without handing over the whole machine or turning Dredge into a background monitor.

## Why Dredge Exists

Most agent tooling can perform work, but it does not always leave a clear local trail of its filesystem interaction. Dredge gives a command run a durable shape: trace sessions, filesystem events, event provenance, bounded summaries, and inspect hints.

Dredge is intentionally conservative:

- No remote service.
- No telemetry.
- No automatic remediation.
- No risk scoring.
- No file contents in trace contexts by default.

The result is a local source of truth that an agent can query carefully and a human can audit later.

## What You Get

- **Append-only trace sessions** for bounded agent commands.
- **Filesystem interaction events** for writes, creates, deletes, and renames with the current diff collector; read/list/stat are reserved for higher-fidelity collectors.
- **Command provenance** linking filesystem events to the wrapped agent process.
- **Deterministic hashes** for trace logs and summaries.
- **Factual explanations** that trace summaries back to source events.
- **Bounded agent contexts** that summarize activity without full event logs or file contents.
- **Archive-aware history** so older local artifacts stay discoverable after compression.

## Who It Is For

Dredge is for technical macOS users who want local history of an agent command's filesystem interaction as structured evidence.

It is a good fit if you want:

- a local timeline of what an agent command touched
- safer first inputs for coding and automation agents
- deterministic JSON outputs that can be tested and inspected
- a source-first tool you can inspect and run without a service account

It is not a SIEM, EDR, monitoring dashboard, policy engine, or autonomous security agent.

## Support Status

Dredge is currently a `v0.2.0` Python source release focused on command-scoped filesystem tracing.

- The implementation is Python.
- The design target is a macOS-friendly CLI wrapper for agent filesystem interaction. See [Access tracing design](docs/ACCESS_TRACING_DESIGN.md).
- Pre-`1.0` schemas with public JSON contracts documented in [SCHEMA.md](SCHEMA.md).
- Source checkout installation today; packaged binaries are roadmap work.

## Install

Dredge installs as a Python CLI. Install it on the machine where you want to run traced commands.

Recommended for a CLI install:

```sh
brew install pipx
pipx install git+https://github.com/offband/dredge.git
```

If you prefer a project-local virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install git+https://github.com/offband/dredge.git
```

Use `python -m pip`, not `python3 -m pip`, after activating the virtual environment. On Homebrew Python, `python3 -m pip install ...` can still target the externally managed system interpreter.

Or install from a source checkout.

Preview installer actions:

```sh
./scripts/install.sh --dry-run
```

Install from a checkout:

```sh
./scripts/install.sh
```

Install to a custom prefix:

```sh
./scripts/install.sh --prefix /usr/local
```

During development:

```sh
PYTHONPATH=src python3 -m dredge --help
```

The primary workflow is:

```sh
dredge trace run --root . -- <agent-command>
dredge trace latest
dredge trace events <trace-id>
dredge trace summary <trace-id>
```

Useful trace controls:

```sh
dredge trace run --root . --exclude .venv --max-hash-bytes 1048576 -- <agent-command>
dredge trace run --root . --no-content-hash -- <agent-command>
dredge trace run --root . --no-default-excludes -- <agent-command>
```

By default, trace scans exclude Dredge's state directory plus `.git`, `.venv`, `node_modules`, and `__pycache__` under each trace root. Broad roots such as `/`, `$HOME`, and the user directory parent require `--allow-broad-root`.

## Help

Usage lives in the CLI help so it stays close to the implementation:

- `dredge --help`
- `dredge trace --help`
- `dredge trace run --help`

CLI command errors are written to stderr as plain `dredge: ...` messages and return a non-zero exit code. JSON error envelopes are not part of the current public contract.

## Project Reference

- [Agent operating guide](AGENTS.md)
- [Public JSON schemas](SCHEMA.md)

## Contributing And Security

- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

MIT. See [LICENSE](LICENSE).
