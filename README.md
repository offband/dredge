# Dredge

Dredge is a command-line tool that records what changes on your filesystem when a command runs.

It captures the state before and after execution and logs the differences.

It does not track every file read or system call — only the changes it can observe from the command’s execution.

## Why Dredge Exists

Most agent tools can do work, but they don’t leave a clear record of what they changed on your system.

Dredge turns a command run into a trace you can inspect later:
• a timeline of filesystem changes  
• records of what was created, modified, or removed  
• a summary of what happened

Dredge runs locally and keeps everything on your machine. It does not send data out, take automatic action, assign risk, or include file contents in traces by default.

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

Dredge is an early developer release (v0.2.0), currently available as Python source. It focuses on tracking filesystem changes during individual command runs.

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


## License

MIT. See [LICENSE](LICENSE).
