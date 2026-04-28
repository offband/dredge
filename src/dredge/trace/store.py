from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from dredge.trace.hash import sha256_bytes
from dredge.trace.models import TraceEvent, TraceSession, to_jsonable


def default_state_dir() -> Path:
    override = os.environ.get("DREDGE_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "dredge"


class TraceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_state_dir()

    @property
    def traces_dir(self) -> Path:
        return self.root / "traces"

    def trace_dir(self, trace_id: str) -> Path:
        return self.traces_dir / trace_id

    def create_trace(self, session: TraceSession) -> Path:
        trace_dir = self.trace_dir(session.trace_id)
        (trace_dir / "indexes").mkdir(parents=True, exist_ok=False)
        self.write_session(session)
        (trace_dir / "events.jsonl").touch()
        return trace_dir

    def write_session(self, session: TraceSession) -> None:
        trace_dir = self.trace_dir(session.trace_id)
        trace_dir.mkdir(parents=True, exist_ok=True)
        write_json(trace_dir / "trace.json", session)

    def append_event(self, event: TraceEvent) -> None:
        path = self.trace_dir(event.trace_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(to_jsonable(event), sort_keys=True, separators=(",", ":")))
            handle.write("\n")

    def read_session(self, trace_id: str) -> dict:
        with (self.trace_dir(trace_id) / "trace.json").open(encoding="utf-8") as handle:
            return json.load(handle)

    def read_events(self, trace_id: str) -> list[dict]:
        path = self.trace_dir(trace_id) / "events.jsonl"
        events = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def list_sessions(self) -> list[dict]:
        sessions = []
        if not self.traces_dir.exists():
            return sessions
        for trace_dir in sorted(self.traces_dir.iterdir(), key=lambda item: str(item)):
            trace_path = trace_dir / "trace.json"
            if trace_path.exists():
                with trace_path.open(encoding="utf-8") as handle:
                    sessions.append(json.load(handle))
        sessions.sort(key=lambda item: (item.get("started_at", ""), item.get("trace_id", "")))
        return sessions

    def latest_session(self) -> dict:
        sessions = self.list_sessions()
        if not sessions:
            raise DredgeStoreError("no trace sessions found")
        return sessions[-1]

    def resolve_trace_id(self, reference: str) -> str:
        if reference == "latest":
            return self.latest_session()["trace_id"]
        matches = [
            session["trace_id"]
            for session in self.list_sessions()
            if session.get("trace_id") == reference or session.get("trace_id", "").startswith(reference)
        ]
        if not matches:
            raise DredgeStoreError(f"trace not found: {reference}")
        if len(matches) > 1:
            raise DredgeStoreError(f"ambiguous trace id: {reference}")
        return matches[0]

    def event_log_hash(self, trace_id: str) -> str:
        return sha256_bytes((self.trace_dir(trace_id) / "events.jsonl").read_bytes())


class DredgeStoreError(Exception):
    pass


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(value), handle, indent=2, sort_keys=True)
        handle.write("\n")


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)
