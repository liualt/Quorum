"""Content-addressed archive of the scenario inputs a run executed against.

A run's outcome depends on more than the version labels on its row: the
fixture JSON, the runner wrapper, `index.py`, the editable-file defaults that
fill in what a snapshot omits, and the check definitions. A label can stay
`v1` while any of those is edited in place, and then a replay that loaded the
installed scenario would silently be reproducing something else.

So every run is executed from an archive entry keyed by the sha256 of exactly
those bytes, stored under `<SNAPSHOT_DIR>/archive/<sha256>/`. Identical inputs
share one entry; a replay loads the original's entry and refuses to start when
it is gone. Loading re-hashes what is on disk, so a tampered entry is refused
rather than trusted.
"""

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass

from app.scenario import Check, Scenario
from app.scenario.loader import _parse_check

ARCHIVE_DIRNAME = "archive"
MANIFEST_NAME = "manifest.json"
CHECKS_NAME = "checks.json"
DEFAULTS_PREFIX = "defaults/"
READONLY_PREFIX = "readonly/"


class ArchiveError(LookupError):
    """An archive entry that is missing or does not hash to its own name."""


@dataclass
class RunInputs:
    """What `_execute` needs from a scenario, whether installed or archived."""

    fixture_version: str
    check_version: str
    editable_files: dict[str, str]
    readonly_files: dict[str, str]
    checks: list[Check]

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "RunInputs":
        return cls(
            fixture_version=scenario.fixture_version,
            check_version=scenario.check_version,
            editable_files=dict(scenario.editable_files),
            readonly_files=dict(scenario.readonly_files),
            checks=list(scenario.checks),
        )

    def entries(self) -> dict[str, str]:
        """Relative archive path -> text, the exact bytes the hash covers."""
        files = {f"{DEFAULTS_PREFIX}{name}": text for name, text in self.editable_files.items()}
        files.update({f"{READONLY_PREFIX}{name}": text for name, text in self.readonly_files.items()})
        files[CHECKS_NAME] = json.dumps(
            {"checks": [asdict(check) for check in self.checks]}, sort_keys=True, indent=1
        )
        return files

    def manifest(self) -> dict:
        return {"fixture_version": self.fixture_version, "check_version": self.check_version}


def inputs_hash(inputs: RunInputs) -> str:
    """sha256 over the archive entries and version labels, in a fixed order."""
    digest = hashlib.sha256()
    digest.update(json.dumps(inputs.manifest(), sort_keys=True).encode())
    files = inputs.entries()
    for path in sorted(files):
        data = files[path].encode("utf-8")
        digest.update(f"\0{path}\0{len(data)}\0".encode())
        digest.update(data)
    return digest.hexdigest()


def _archive_root(snapshot_dir) -> str:
    return os.path.join(str(snapshot_dir), ARCHIVE_DIRNAME)


def entry_path(snapshot_dir, digest: str) -> str:
    return os.path.join(_archive_root(snapshot_dir), digest)


def store(snapshot_dir, inputs: RunInputs) -> str:
    """Write the entry for `inputs` if it is not there yet; return its hash.

    The entry is built in a sibling temporary directory and renamed into place,
    so a concurrent writer of the same hash either wins the rename or finds the
    finished entry — never a half-written one.
    """
    digest = inputs_hash(inputs)
    final = entry_path(snapshot_dir, digest)
    if os.path.isfile(os.path.join(final, MANIFEST_NAME)):
        return digest

    root = _archive_root(snapshot_dir)
    os.makedirs(root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f".{digest[:12]}-", dir=root)
    try:
        for path, text in inputs.entries().items():
            target = os.path.join(staging, *path.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        with open(os.path.join(staging, MANIFEST_NAME), "w", encoding="utf-8", newline="") as handle:
            json.dump(inputs.manifest(), handle, sort_keys=True)
        try:
            os.rename(staging, final)
        except OSError:
            if not os.path.isfile(os.path.join(final, MANIFEST_NAME)):
                raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return digest


def load(snapshot_dir, digest: str) -> RunInputs:
    """Read one entry back and refuse it unless it still hashes to `digest`."""
    if not digest:
        raise ArchiveError("the run has no archived inputs")
    directory = entry_path(snapshot_dir, digest)
    manifest_path = os.path.join(directory, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        raise ArchiveError(f"archived run inputs {digest} are missing")

    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    editable, readonly = {}, {}
    for prefix, target in ((DEFAULTS_PREFIX, editable), (READONLY_PREFIX, readonly)):
        base = os.path.join(directory, prefix.rstrip("/"))
        for dirpath, _, filenames in os.walk(base):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                name = os.path.relpath(full, base).replace(os.sep, "/")
                with open(full, encoding="utf-8", newline="") as handle:
                    target[name] = handle.read()
    with open(os.path.join(directory, CHECKS_NAME), encoding="utf-8") as handle:
        checks = [_parse_check(raw) for raw in json.load(handle)["checks"]]

    inputs = RunInputs(
        fixture_version=manifest["fixture_version"],
        check_version=manifest["check_version"],
        editable_files=editable,
        readonly_files=readonly,
        checks=checks,
    )
    if inputs_hash(inputs) != digest:
        raise ArchiveError(f"archived run inputs {digest} do not match their hash")
    return inputs
