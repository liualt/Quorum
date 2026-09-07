"""Quorum check runner. Not editable.

Reads a JSON script from stdin, runs each check in a fresh interpreter so
module state (cache contents, permissions) cannot leak between checks, and
prints one JSON object describing what search() returned. It never decides
pass or fail; the backend compares against expectations it holds itself.
"""
import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PER_CHECK_TIMEOUT = 8


def run_one(check):
    sys.path.insert(0, HERE)
    import index
    import permissions
    import search

    steps_out = []
    for step in check["steps"]:
        entry = {"returned": None, "error": None}
        try:
            if step["op"] == "search":
                result = search.search(step["user"], step["query"])
                entry["returned"] = [item["id"] if isinstance(item, dict) else str(item) for item in list(result)]
            elif step["op"] == "revoke":
                permissions.revoke(step["user"], step["document"])
                entry["returned"] = []
            else:
                entry["error"] = "unknown op %s" % step["op"]
        except Exception:
            entry["error"] = traceback.format_exc(limit=3)[-1500:]
        steps_out.append(entry)
    return {"check_id": check["id"], "steps": steps_out,
            "search_calls": getattr(index, "SEARCH_CALLS", None), "error": None}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        print("\n" + json.dumps(run_one(json.loads(sys.argv[2]))))
        return
    script = json.load(sys.stdin)
    results = []
    for check in script["checks"]:
        try:
            proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", json.dumps(check)],
                                  capture_output=True, text=True, cwd=HERE, timeout=PER_CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            results.append({"check_id": check["id"], "steps": [], "search_calls": None,
                            "error": "check timed out after %ss" % PER_CHECK_TIMEOUT})
            continue
        parsed = None
        for line in reversed(proc.stdout.strip().splitlines()):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if proc.returncode == 0 and isinstance(parsed, dict) and parsed.get("check_id") == check["id"]:
            results.append(parsed)
        else:
            results.append({"check_id": check["id"], "steps": [], "search_calls": None,
                            "error": (proc.stderr or proc.stdout)[-2000:] or "exit %s" % proc.returncode})
    print(json.dumps({"results": results}))


if __name__ == "__main__":
    main()
