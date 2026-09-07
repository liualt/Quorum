"""Candidate source snapshots: validation, content hashing, and disk layout.

Snapshots live at `<SNAPSHOT_DIR>/<interview_id>/<snapshot_id>/<name>` so an
interview's whole history can be deleted by removing one directory. The file
names are fixed by the scenario's editable set; nothing else is ever written,
which is what keeps a candidate-supplied name from escaping the directory.
"""

import hashlib
import os
import shutil

ALLOWED_FILES = ("search.py", "cache.py", "permissions.py")


class SnapshotError(ValueError):
    """A candidate-supplied file set that must be refused."""


def validate_files(files: dict[str, str], limit_bytes: int) -> None:
    total = 0
    for name, content in files.items():
        if name not in ALLOWED_FILES:
            raise SnapshotError(f"unknown file: {name}")
        if not isinstance(content, str):
            raise SnapshotError(f"file content must be text: {name}")
        if "\x00" in content:
            raise SnapshotError(f"file contains a NUL byte: {name}")
        total += len(content.encode("utf-8"))
    if total > limit_bytes:
        raise SnapshotError(f"source is {total} bytes, over the {limit_bytes} byte limit")


def content_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(f"{name}\0{files[name]}\0".encode())
    return digest.hexdigest()


def _snapshot_path(snapshot_dir: str, interview_id: str, snapshot_id: str) -> str:
    return os.path.join(snapshot_dir, interview_id, snapshot_id)


def write_snapshot(snapshot_dir, interview_id: str, snapshot_id: str, files: dict[str, str]) -> None:
    """Write one snapshot. Refuses any name it does not own, so this is never
    an arbitrary-file-write primitive even if a caller skips `validate_files`."""
    unknown = [name for name in files if name not in ALLOWED_FILES]
    if unknown:
        raise SnapshotError(f"refusing to write unknown files: {', '.join(sorted(unknown))}")

    directory = _snapshot_path(str(snapshot_dir), interview_id, snapshot_id)
    os.makedirs(directory, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
            handle.write(content)


def read_snapshot(snapshot_dir, interview_id: str, snapshot_id: str) -> dict[str, str]:
    directory = _snapshot_path(str(snapshot_dir), interview_id, snapshot_id)
    files = {}
    for name in ALLOWED_FILES:
        path = os.path.join(directory, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                files[name] = handle.read()
    return files


def delete_interview_dir(snapshot_dir, interview_id: str) -> None:
    shutil.rmtree(os.path.join(str(snapshot_dir), interview_id), ignore_errors=True)
