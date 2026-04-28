from __future__ import annotations

import argparse
import sys

from dredge import __version__
from dredge.trace.runner import explain_event, run_trace, summarize_trace
from dredge.trace.store import DredgeStoreError, TraceStore, print_json


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "version":
            print_json(
                {
                    "package": "dredge",
                    "version": __version__,
                    "runtime": "python",
                    "schemas": {
                        "trace": "dredge.trace.v1",
                        "trace_event": "dredge.trace_event.v1",
                    },
                }
            )
            return 0
        if args.command == "doctor":
            print_json(doctor())
            return 0
        if args.command == "trace":
            return trace_command(args)
        parser.print_help()
        return 2
    except (DredgeStoreError, ValueError, OSError) as error:
        print(f"dredge: {error}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dredge",
        description="trace an agent command's filesystem interactions",
    )
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("version", help="print runtime and schema versions")
    subcommands.add_parser("doctor", help="check local tracing prerequisites")

    trace = subcommands.add_parser("trace", help="work with command-scoped filesystem traces")
    trace_subcommands = trace.add_subparsers(dest="trace_command", required=True)

    run = trace_subcommands.add_parser(
        "run",
        help="run an agent command under a filesystem trace",
        description=(
            "Run a command, record wrapper provenance, and compare filesystem metadata "
            "before and after execution. The current collector reports outcomes such as "
            "create/write/delete/rename; it does not observe every read/list/stat syscall."
        ),
    )
    run.add_argument("--agent-label", help="optional label for the traced agent or tool")
    run.add_argument(
        "--root",
        action="append",
        dest="roots",
        help=(
            "filesystem root to scan; may be repeated. Defaults to DREDGE_TRACE_ROOTS "
            "or cwd. Broad roots such as /, $HOME, and the user directory parent require "
            "--allow-broad-root"
        ),
    )
    run.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="path to exclude from filesystem scans; may be repeated",
    )
    run.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="scan .git, .venv, node_modules, and __pycache__ instead of excluding them by default",
    )
    run.add_argument(
        "--max-hash-bytes",
        type=int,
        default=None,
        help=(
            "maximum file size to content-hash during scans. Defaults to "
            "DREDGE_MAX_HASH_BYTES or 10485760; larger files keep metadata only"
        ),
    )
    run.add_argument(
        "--no-content-hash",
        action="store_true",
        help="record metadata changes without hashing file contents",
    )
    run.add_argument(
        "--allow-broad-root",
        action="store_true",
        help="allow broad scan roots such as /, $HOME, or the user directory parent",
    )
    run.add_argument("trace_argv", nargs=argparse.REMAINDER, help="command after --")

    trace_subcommands.add_parser("latest", help="print the latest trace session")

    events = trace_subcommands.add_parser("events", help="print trace events")
    events.add_argument("trace_id", help='trace id, prefix, or "latest"')

    summary = trace_subcommands.add_parser("summary", help="print a bounded trace summary")
    summary.add_argument("trace_id", help='trace id, prefix, or "latest"')

    explain = trace_subcommands.add_parser("explain", help="explain one trace event")
    explain.add_argument("event_id", help="event id or prefix")

    return parser


def trace_command(args: argparse.Namespace) -> int:
    store = TraceStore()
    if args.trace_command == "run":
        command = normalize_command(args.trace_argv)
        result = run_trace(
            command,
            agent_label=args.agent_label,
            roots=args.roots,
            excludes=args.exclude,
            content_hashes=not args.no_content_hash,
            max_hash_bytes=args.max_hash_bytes,
            use_default_excludes=not args.no_default_excludes,
            allow_broad_roots=args.allow_broad_root,
        )
        print_json(result)
        exit_code = result.get("exit_code")
        return exit_code if isinstance(exit_code, int) else 1
    if args.trace_command == "latest":
        print_json(store.latest_session())
        return 0
    if args.trace_command == "events":
        trace_id = store.resolve_trace_id(args.trace_id)
        print_json(store.read_events(trace_id))
        return 0
    if args.trace_command == "summary":
        trace_id = store.resolve_trace_id(args.trace_id)
        print_json(summarize_trace(store, trace_id))
        return 0
    if args.trace_command == "explain":
        print_json(explain_event(store, args.event_id))
        return 0
    raise ValueError(f"unknown trace command: {args.trace_command}")


def normalize_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("missing command after --")
    return command


def doctor() -> dict:
    store = TraceStore()
    return {
        "status": "ok",
        "runtime": {
            "name": "python",
            "version": sys.version.split()[0],
        },
        "state_dir": {
            "path": str(store.root),
            "status": "ok" if store.root.exists() or store.root.parent.exists() else "missing_parent",
        },
        "collectors": [
            {
                "name": "process_wrapper",
                "status": "ok",
                "fidelity": "wrapped_process",
            },
            {
                "name": "filesystem_diff",
                "status": "ok",
                "fidelity": "metadata_diff",
            },
            {
                "name": "endpoint_security",
                "status": "not_implemented",
                "fidelity": "native_event",
                "message": "future optional collector for higher-fidelity command-scoped filesystem events",
            },
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
