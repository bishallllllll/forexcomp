#!/usr/bin/env python3
import os
import subprocess
import time
from typing import List

POLL_INTERVAL_SECONDS = int(os.getenv("ACP_POLL_INTERVAL", "5"))
DEBOUNCE_SECONDS = int(os.getenv("ACP_DEBOUNCE_SECONDS", "5"))
MIN_SECONDS_BETWEEN_COMMITS = int(os.getenv("ACP_MIN_COMMIT_INTERVAL", "120"))

def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def _get_changed_files() -> List[str]:
    result = _run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        return []
    files = []
    for line in result.stdout.splitlines():
        if len(line) > 3:
            files.append(line[3:])
    return files

def _has_staged_changes() -> bool:
    result = _run(["git", "diff", "--cached", "--quiet"])
    return result.returncode != 0

def _infer_message(files: List[str]) -> str:
    if not files:
        return "Update project files"
    if len(files) == 1:
        return f"Update {files[0]}"
    top_dirs = {f.split("/")[0] for f in files if "/" in f}
    if len(top_dirs) == 1:
        return f"Update {top_dirs.pop()} changes"
    return "Update project files"

def _has_origin() -> bool:
    result = _run(["git", "remote", "get-url", "origin"])
    return result.returncode == 0

def main() -> None:
    last_commit = 0.0
    while True:
        changed = _get_changed_files()
        if not changed:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        time.sleep(DEBOUNCE_SECONDS)
        changed = _get_changed_files()
        if not changed:
            continue

        now = time.time()
        if now - last_commit < MIN_SECONDS_BETWEEN_COMMITS:
            time.sleep(MIN_SECONDS_BETWEEN_COMMITS - (now - last_commit))

        _run(["git", "add", "-A"])
        if not _has_staged_changes():
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        message = _infer_message(changed)
        commit = _run(["git", "commit", "-m", message])
        if commit.returncode != 0:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        if _has_origin():
            _run(["git", "push", "origin", "main"])

        last_commit = time.time()
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
