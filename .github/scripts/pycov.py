#!/usr/bin/env python3
"""pytest with line coverage measured by a small sys.settrace tracer, so CI needs nothing beyond
pytest from the hash-locked requirements (asome-platform templates/agent-repo, F5).

    pycov.py --junit OUT/junit.xml --json OUT/coverage.json [-- PYTEST_ARGS...]

Coverage = executed / executable lines of the project's Python files (tests, .github and virtual
environments excluded); executable lines come from the compiled code objects. Only frames of files
under the project directory are traced. Exit code: pytest's.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SKIP_DIRS = {"tests", "test", "build", "dist", "node_modules", "venv", "__pycache__"}


class Tracer:
    """Lines executed in files under `root` (absolute path -> line numbers)."""

    def __init__(self, root: Path) -> None:
        self.prefix = str(root) + os.sep
        self.lines: dict[str, set[int]] = {}
        self._wanted: dict[str, str | None] = {}

    def global_trace(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        filename = frame.f_code.co_filename
        if filename not in self._wanted:
            path = os.path.abspath(filename)
            self._wanted[filename] = path if path.startswith(self.prefix) else None
        path = self._wanted[filename]
        if path is None:
            return None
        lines = self.lines.setdefault(path, set())
        lines.add(frame.f_lineno)

        def local(frame: types.FrameType, event: str, arg: Any) -> Any:
            if event == "line":
                lines.add(frame.f_lineno)
            return local

        return local

    def run(self, func: Any, *args: Any) -> Any:
        threading.settrace(self.global_trace)
        sys.settrace(self.global_trace)
        try:
            return func(*args)
        finally:
            sys.settrace(None)
            threading.settrace(None)  # type: ignore[arg-type]


def sources(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            test = name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
            if name.endswith(".py") and not test:
                yield Path(dirpath, name).resolve()


def executable(path: Path) -> set[int]:
    try:
        code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return set()
    lines: set[int] = set()
    stack = [code]
    while stack:
        co = stack.pop()
        lines.update(line for _, _, line in co.co_lines() if line)
        stack.extend(c for c in co.co_consts if isinstance(c, types.CodeType))
    return lines


def report(root: Path, executed: dict[str, set[int]]) -> dict[str, Any]:
    resolved = {str(Path(p).resolve()): lines for p, lines in executed.items()}
    files, total, hit = {}, 0, 0
    for path in sources(root):
        lines = executable(path)
        if not lines:
            continue
        done = lines & resolved.get(str(path), set())
        files[path.relative_to(root).as_posix()] = round(100 * len(done) / len(lines), 2)
        total += len(lines)
        hit += len(done)
    return {"percent": round(100 * hit / total, 2) if total else None, "lines": total, "covered": hit, "files": files}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("pytest_args", nargs="*")
    args = ap.parse_args(argv)
    import pytest

    root = Path.cwd().resolve()
    tracer = Tracer(root)
    rc = tracer.run(pytest.main, [f"--junitxml={args.junit}", "-p", "no:cacheprovider", *args.pytest_args])
    Path(args.json).write_text(json.dumps(report(root, tracer.lines), indent=1))
    return int(rc)


if __name__ == "__main__":
    sys.exit(main())
