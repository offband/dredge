from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from dredge.trace.hash import sha256_bytes

DEFAULT_EXCLUDE_NAMES = (".git", ".venv", "node_modules", "__pycache__")


@dataclass(frozen=True)
class FileRecord:
    path: str
    kind: str
    size: int
    modified_ns: int | None
    content_hash: str | None
    file_id: str | None


@dataclass(frozen=True)
class ScanOptions:
    content_hashes: bool = True
    max_hash_bytes: int = 10 * 1024 * 1024


def scan_roots(
    roots: list[Path],
    excludes: list[Path] | None = None,
    options: ScanOptions | None = None,
) -> dict[str, FileRecord]:
    records: dict[str, FileRecord] = {}
    resolved_excludes = [path.resolve() for path in excludes or []]
    scan_options = options or ScanOptions()
    for root in roots:
        try:
            _walk(root, records, resolved_excludes, scan_options)
        except OSError:
            continue
    return records


def default_roots(cwd: Path) -> list[Path]:
    env_roots = os.environ.get("DREDGE_TRACE_ROOTS")
    if env_roots:
        return [Path(part).expanduser().resolve() for part in env_roots.split(os.pathsep) if part]
    return [cwd.resolve()]


def default_excludes_for_roots(roots: list[Path]) -> list[Path]:
    excludes: list[Path] = []
    for root in roots:
        excludes.extend(root / name for name in DEFAULT_EXCLUDE_NAMES)
    return excludes


def _walk(path: Path, records: dict[str, FileRecord], excludes: list[Path], options: ScanOptions) -> None:
    try:
        resolved_path = path.resolve()
    except OSError:
        resolved_path = path
    if any(_is_relative_to(resolved_path, excluded) for excluded in excludes):
        return

    try:
        metadata = path.lstat()
    except OSError:
        return

    resolved = str(resolved_path)
    kind = _kind(metadata.st_mode)
    content_hash = _content_hash(path, metadata, options) if kind == "file" else None
    records[resolved] = FileRecord(
        path=resolved,
        kind=kind,
        size=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        content_hash=content_hash,
        file_id=f"{metadata.st_dev}:{metadata.st_ino}",
    )

    if kind != "directory":
        return

    try:
        children = sorted(path.iterdir(), key=lambda item: str(item))
    except OSError:
        return
    for child in children:
        _walk(child, records, excludes, options)


def _kind(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISCHR(mode):
        return "char_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    return "other"


def _content_hash(path: Path, metadata: os.stat_result, options: ScanOptions) -> str | None:
    if not options.content_hashes:
        return None
    if metadata.st_size > options.max_hash_bytes:
        return None
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def env_max_hash_bytes() -> int:
    value = os.environ.get("DREDGE_MAX_HASH_BYTES", "10485760")
    try:
        parsed = int(value)
    except ValueError:
        return 10 * 1024 * 1024
    return max(parsed, 0)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
