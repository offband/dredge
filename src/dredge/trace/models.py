from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from typing import Any

TRACE_SCHEMA_VERSION = "dredge.trace.v1"
TRACE_EVENT_SCHEMA_VERSION = "dredge.trace_event.v1"
TRACE_RUN_RESULT_SCHEMA_VERSION = "dredge.trace_run_result.v1"


class TraceStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AccessOperation(StrEnum):
    READ = "READ"
    LIST = "LIST"
    STAT = "STAT"
    CREATE = "CREATE"
    WRITE = "WRITE"
    RENAME = "RENAME"
    DELETE = "DELETE"
    EXEC = "EXEC"


class AccessTargetKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    COMMAND = "command"
    UNKNOWN = "unknown"


class AccessEffect(StrEnum):
    OBSERVED = "observed"
    ALLOWED = "allowed"
    DENIED = "denied"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AccessFidelity(StrEnum):
    NATIVE_EVENT = "native_event"
    WRAPPED_PROCESS = "wrapped_process"
    METADATA_DIFF = "metadata_diff"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class Platform:
    os: str
    arch: str
    version: str | None = None


@dataclass(frozen=True)
class TraceScope:
    working_directory: str | None = None
    command: str | None = None
    agent_label: str | None = None
    include_children: bool = True
    roots: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    content_hashes: bool = True
    max_hash_bytes: int = 10 * 1024 * 1024


@dataclass(frozen=True)
class TraceDisclosure:
    contains_file_content: bool = False
    contains_full_event_log: bool = False
    contains_path_metadata: bool = True
    contains_sensitive_content: bool = False
    artifact_scope: str = "trace_summary_plus_hints"


@dataclass(frozen=True)
class AccessActor:
    pid: int | None = None
    ppid: int | None = None
    uid: int | None = None
    user: str | None = None
    executable: str | None = None
    command: str | None = None
    agent_label: str | None = None
    parent_event_id: str | None = None


@dataclass(frozen=True)
class AccessTarget:
    kind: AccessTargetKind
    path: str | None = None
    previous_path: str | None = None
    path_hash: str | None = None
    file_id: str | None = None
    content_hash_before: str | None = None
    content_hash_after: str | None = None
    process_id: int | None = None


@dataclass(frozen=True)
class AccessSource:
    collector: str
    surface: str
    fidelity: AccessFidelity


@dataclass(frozen=True)
class AccessProvenance:
    source: str
    status: str
    message: str | None = None


@dataclass(frozen=True)
class TraceEvent:
    schema_version: str
    event_id: str
    trace_id: str
    observed_at: str
    operation: AccessOperation
    actor: AccessActor
    target: AccessTarget
    effect: AccessEffect
    source: AccessSource
    provenance: list[AccessProvenance] = field(default_factory=list)


@dataclass(frozen=True)
class TraceSession:
    schema_version: str
    trace_id: str
    started_at: str
    finished_at: str | None
    status: TraceStatus
    platform: Platform
    root_process: AccessActor | None
    scope: TraceScope
    event_count: int
    event_log_hash: str | None
    disclosure_summary: TraceDisclosure


def to_jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return str(value)
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value
