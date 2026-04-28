from __future__ import annotations

import os
import platform as platform_module
import shlex
import subprocess
import uuid
from collections import Counter
from pathlib import Path

from dredge.trace.fsdiff import (
    FileRecord,
    ScanOptions,
    default_excludes_for_roots,
    default_roots,
    env_max_hash_bytes,
    scan_roots,
)
from dredge.trace.hash import sha256_json
from dredge.trace.models import (
    TRACE_EVENT_SCHEMA_VERSION,
    TRACE_RUN_RESULT_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
    AccessActor,
    AccessEffect,
    AccessFidelity,
    AccessOperation,
    AccessProvenance,
    AccessSource,
    AccessTarget,
    AccessTargetKind,
    Platform,
    TraceDisclosure,
    TraceEvent,
    TraceScope,
    TraceSession,
    TraceStatus,
)
from dredge.trace.store import TraceStore, write_json
from dredge.trace.time import now_rfc3339


def run_trace(
    command: list[str],
    *,
    agent_label: str | None = None,
    cwd: Path | None = None,
    roots: list[str] | None = None,
    excludes: list[str] | None = None,
    content_hashes: bool = True,
    max_hash_bytes: int | None = None,
    use_default_excludes: bool = True,
    allow_broad_roots: bool = False,
) -> dict:
    if not command:
        raise ValueError("missing command after --")
    if max_hash_bytes is not None and max_hash_bytes < 0:
        raise ValueError("--max-hash-bytes must be greater than or equal to 0")

    working_directory = (cwd or Path.cwd()).resolve()
    trace_roots = resolve_paths(roots) if roots else default_roots(working_directory)
    broad_roots = find_broad_roots(trace_roots)
    if broad_roots and not allow_broad_roots:
        formatted = ", ".join(str(path) for path in broad_roots)
        raise ValueError(
            "broad trace root requires --allow-broad-root: "
            f"{formatted}. Choose a narrower --root when possible."
        )
    trace_id = "trace-" + uuid.uuid4().hex[:16]
    store = TraceStore()
    started_at = now_rfc3339()
    user_excludes = resolve_paths(excludes or [])
    default_excludes = default_excludes_for_roots(trace_roots) if use_default_excludes else []
    all_excludes = [store.root.resolve(), *default_excludes, *user_excludes]
    scan_options = ScanOptions(
        content_hashes=content_hashes,
        max_hash_bytes=env_max_hash_bytes() if max_hash_bytes is None else max_hash_bytes,
    )
    scope = TraceScope(
        working_directory=str(working_directory),
        command=shlex.join(command),
        agent_label=agent_label,
        include_children=True,
        roots=[str(root) for root in trace_roots],
        excludes=[str(path) for path in all_excludes],
        content_hashes=scan_options.content_hashes,
        max_hash_bytes=scan_options.max_hash_bytes,
    )
    session = TraceSession(
        schema_version=TRACE_SCHEMA_VERSION,
        trace_id=trace_id,
        started_at=started_at,
        finished_at=None,
        status=TraceStatus.RUNNING,
        platform=Platform(
            os=platform_module.system().lower(),
            arch=platform_module.machine(),
            version=platform_module.platform(),
        ),
        root_process=None,
        scope=scope,
        event_count=0,
        event_log_hash=None,
        disclosure_summary=TraceDisclosure(),
    )
    store.create_trace(session)

    actor = AccessActor(
        ppid=os.getpid(),
        uid=os.getuid() if hasattr(os, "getuid") else None,
        user=os.environ.get("USER"),
        executable=command[0],
        command=shlex.join(command),
        agent_label=agent_label,
    )
    return_code: int | None = None
    status = TraceStatus.FAILED
    error: str | None = None
    process: subprocess.Popen | None = None
    before: dict[str, FileRecord] = {}
    event_count = 0

    try:
        before = scan_roots(trace_roots, excludes=all_excludes, options=scan_options)
        process = subprocess.Popen(command, cwd=working_directory)
        actor = AccessActor(
            pid=process.pid,
            ppid=actor.ppid,
            uid=actor.uid,
            user=actor.user,
            executable=actor.executable,
            command=actor.command,
            agent_label=actor.agent_label,
        )
        store.append_event(
            build_event(
                trace_id=trace_id,
                operation=AccessOperation.EXEC,
                actor=actor,
                target=AccessTarget(kind=AccessTargetKind.COMMAND, process_id=process.pid),
                effect=AccessEffect.OBSERVED,
                source=AccessSource(
                    collector="process_wrapper",
                    surface="subprocess.Popen",
                    fidelity=AccessFidelity.WRAPPED_PROCESS,
                ),
                provenance=[AccessProvenance(source="dredge trace run", status="ok")],
            )
        )
        event_count += 1
        return_code = process.wait()
        after = scan_roots(trace_roots, excludes=all_excludes, options=scan_options)
        diff_events = file_diff_events(trace_id, actor, before, after)
        for event in diff_events:
            store.append_event(event)
        event_count += len(diff_events)
        status = TraceStatus.COMPLETED if return_code == 0 else TraceStatus.FAILED
    except Exception as exc:
        error = str(exc)
        store.append_event(
            build_event(
                trace_id=trace_id,
                operation=AccessOperation.EXEC,
                actor=actor,
                target=AccessTarget(
                    kind=AccessTargetKind.COMMAND,
                    process_id=process.pid if process else None,
                ),
                effect=AccessEffect.FAILED,
                source=AccessSource(
                    collector="process_wrapper",
                    surface="subprocess.Popen",
                    fidelity=AccessFidelity.WRAPPED_PROCESS,
                ),
                provenance=[AccessProvenance(source="dredge trace run", status="failed", message=error)],
            )
        )
        event_count += 1
        status = TraceStatus.FAILED
    finally:
        finished = TraceSession(
            schema_version=TRACE_SCHEMA_VERSION,
            trace_id=trace_id,
            started_at=started_at,
            finished_at=now_rfc3339(),
            status=status,
            platform=session.platform,
            root_process=actor,
            scope=scope,
            event_count=event_count,
            event_log_hash=store.event_log_hash(trace_id),
            disclosure_summary=TraceDisclosure(),
        )
        store.write_session(finished)
        write_indexes(store, trace_id)

    return {
        "schema_version": TRACE_RUN_RESULT_SCHEMA_VERSION,
        "trace_id": trace_id,
        "status": str(status),
        "exit_code": return_code,
        "event_count": event_count,
        "trace_path": str(store.trace_dir(trace_id)),
        "error": error,
    }


def build_event(
    *,
    trace_id: str,
    operation: AccessOperation,
    actor: AccessActor,
    target: AccessTarget,
    effect: AccessEffect,
    source: AccessSource,
    provenance: list[AccessProvenance],
) -> TraceEvent:
    observed_at = now_rfc3339()
    event_id = sha256_json(
        {
            "trace_id": trace_id,
            "observed_at": observed_at,
            "operation": str(operation),
            "actor": actor.command,
            "target": target.path or target.process_id or target.path_hash,
            "source": source.collector,
        }
    )
    return TraceEvent(
        schema_version=TRACE_EVENT_SCHEMA_VERSION,
        event_id=event_id,
        trace_id=trace_id,
        observed_at=observed_at,
        operation=operation,
        actor=actor,
        target=target,
        effect=effect,
        source=source,
        provenance=provenance,
    )


def file_diff_events(
    trace_id: str,
    actor: AccessActor,
    before: dict[str, FileRecord],
    after: dict[str, FileRecord],
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    source = AccessSource(
        collector="filesystem_diff",
        surface="metadata_before_after",
        fidelity=AccessFidelity.METADATA_DIFF,
    )
    provenance = [AccessProvenance(source="DREDGE_TRACE_ROOTS", status="ok")]
    deleted_paths = set(before.keys() - after.keys())
    created_paths = set(after.keys() - before.keys())
    renamed = detect_renames(before, after, deleted_paths, created_paths)

    for old, new in renamed:
        events.append(
            build_event(
                trace_id=trace_id,
                operation=AccessOperation.RENAME,
                actor=actor,
                target=target_from_record(new, before_record=old, after_record=new, previous_path=old.path),
                effect=AccessEffect.OBSERVED,
                source=source,
                provenance=provenance,
            )
        )
        deleted_paths.discard(old.path)
        created_paths.discard(new.path)

    for path in sorted(deleted_paths):
        old = before[path]
        events.append(
            build_event(
                trace_id=trace_id,
                operation=AccessOperation.DELETE,
                actor=actor,
                target=target_from_record(old, before_record=old, after_record=None),
                effect=AccessEffect.OBSERVED,
                source=source,
                provenance=provenance,
            )
        )

    for path in sorted(created_paths):
        new = after[path]
        events.append(
            build_event(
                trace_id=trace_id,
                operation=AccessOperation.CREATE,
                actor=actor,
                target=target_from_record(new, before_record=None, after_record=new),
                effect=AccessEffect.OBSERVED,
                source=source,
                provenance=provenance,
            )
        )

    for path in sorted(before.keys() & after.keys()):
        old = before[path]
        new = after[path]
        if old.kind != new.kind or old.size != new.size or old.modified_ns != new.modified_ns or old.content_hash != new.content_hash:
            events.append(
                build_event(
                    trace_id=trace_id,
                    operation=AccessOperation.WRITE,
                    actor=actor,
                    target=target_from_record(new, before_record=old, after_record=new),
                    effect=AccessEffect.OBSERVED,
                    source=source,
                    provenance=provenance,
                )
            )

    return events


def target_from_record(
    record: FileRecord,
    *,
    before_record: FileRecord | None,
    after_record: FileRecord | None,
    previous_path: str | None = None,
) -> AccessTarget:
    kind = AccessTargetKind.DIRECTORY if record.kind == "directory" else AccessTargetKind.FILE
    return AccessTarget(
        kind=kind,
        path=record.path,
        previous_path=previous_path,
        path_hash=sha256_json(record.path),
        file_id=record.file_id,
        content_hash_before=before_record.content_hash if before_record else None,
        content_hash_after=after_record.content_hash if after_record else None,
    )


def detect_renames(
    before: dict[str, FileRecord],
    after: dict[str, FileRecord],
    deleted_paths: set[str],
    created_paths: set[str],
) -> list[tuple[FileRecord, FileRecord]]:
    created = [after[path] for path in created_paths]
    unmatched = created[:]
    renames: list[tuple[FileRecord, FileRecord]] = []
    for old_path in sorted(deleted_paths):
        old = before[old_path]
        match = find_rename_match(old, unmatched)
        if match is None:
            continue
        renames.append((old, match))
        unmatched.remove(match)
    return renames


def find_rename_match(old: FileRecord, candidates: list[FileRecord]) -> FileRecord | None:
    file_id_matches = [
        candidate
        for candidate in candidates
        if old.file_id is not None and candidate.file_id == old.file_id and candidate.kind == old.kind
    ]
    if len(file_id_matches) == 1:
        return file_id_matches[0]

    hash_matches = [
        candidate
        for candidate in candidates
        if old.kind == candidate.kind
        and old.kind == "file"
        and old.content_hash is not None
        and candidate.content_hash == old.content_hash
        and candidate.size == old.size
    ]
    if len(hash_matches) == 1:
        return hash_matches[0]
    return None


def summarize_trace(store: TraceStore, trace_id: str) -> dict:
    session = store.read_session(trace_id)
    events = store.read_events(trace_id)
    operations = Counter(event["operation"] for event in events)
    target_kinds = Counter(event["target"]["kind"] for event in events)
    paths_read = set()
    paths_changed = set()
    for event in events:
        path = event["target"].get("path")
        if not path:
            continue
        if event["operation"] in {"READ", "LIST", "STAT"}:
            paths_read.add(path)
        if event["operation"] in {"CREATE", "WRITE", "RENAME", "DELETE"}:
            paths_changed.add(path)
    return {
        "schema_version": "dredge.trace_summary.v1",
        "trace_id": trace_id,
        "started_at": session["started_at"],
        "finished_at": session["finished_at"],
        "status": session["status"],
        "event_count": len(events),
        "operations": dict(sorted(operations.items())),
        "target_kinds": dict(sorted(target_kinds.items())),
        "read_path_count": len(paths_read),
        "changed_path_count": len(paths_changed),
        "inspect_hints": [f"dredge trace events {trace_id}"]
        + [f"dredge trace explain {event['event_id']}" for event in events[:10]],
        "disclosure_summary": session["disclosure_summary"],
        "collector_limitations": [
            "metadata_diff observes before/after filesystem outcomes, not every read/list/stat syscall",
            "child-process attribution is inherited from the wrapped root command unless a native collector is used",
        ],
    }


def explain_event(store: TraceStore, event_reference: str) -> dict:
    for session in store.list_sessions():
        trace_id = session["trace_id"]
        for event in store.read_events(trace_id):
            if event["event_id"] == event_reference or event["event_id"].startswith(event_reference):
                return {
                    "schema_version": "dredge.trace_explain.v1",
                    "trace": session,
                    "event": event,
                }
    raise ValueError(f"event not found: {event_reference}")


def write_indexes(store: TraceStore, trace_id: str) -> None:
    events = store.read_events(trace_id)
    by_path: dict[str, list[str]] = {}
    by_process: dict[str, list[str]] = {}
    by_operation: dict[str, list[str]] = {}
    for event in events:
        event_id = event["event_id"]
        path = event["target"].get("path")
        pid = event["actor"].get("pid")
        operation = event["operation"]
        if path:
            by_path.setdefault(path, []).append(event_id)
        if pid is not None:
            by_process.setdefault(str(pid), []).append(event_id)
        by_operation.setdefault(operation, []).append(event_id)

    index_dir = store.trace_dir(trace_id) / "indexes"
    write_json(index_dir / "by-path.json", by_path)
    write_json(index_dir / "by-process.json", by_process)
    write_json(index_dir / "by-operation.json", by_operation)


def resolve_paths(values: list[str]) -> list[Path]:
    return [Path(value).expanduser().resolve() for value in values]


def find_broad_roots(roots: list[Path]) -> list[Path]:
    home = Path.home().resolve()
    broad = {Path("/").resolve(), home}
    if home.parent != home:
        broad.add(home.parent.resolve())
    return [root for root in roots if root.resolve() in broad]
