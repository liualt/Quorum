"""Start the isolated browser-test backend with a fresh temporary data directory."""

import os
import sys
import tempfile
from pathlib import Path

import uvicorn


if __name__ == "__main__":
    # Keep all test data under the ignored server/data directory. No shell
    # deletion or reuse of a database another server might have open.
    data_root = Path(__file__).resolve().parents[1] / "server" / "data"
    sys.path.insert(0, str(data_root.parent))
    data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="e2e-", dir=data_root) as directory:
        os.environ["DATABASE_PATH"] = str(Path(directory) / "quorum.db")
        os.environ["SNAPSHOT_DIR"] = str(Path(directory) / "snapshots")
        uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8010)
