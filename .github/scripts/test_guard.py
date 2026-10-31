#!/usr/bin/env python3
"""test-guard of an agent repository (asome-platform templates/agent-repo, F5).

    test_guard.py summarize OUT        JSON {"tests", "skipped", "failed", "coverage"} on stdout
    test_guard.py compare BASE HEAD    exit 1 when the PR has fewer tests, fewer executed (more
                                       skipped) tests or lower line coverage than its base

Reports in OUT/reports (recursively): JUnit XML (pytest --junitxml, Gradle, Maven surefire) and
JaCoCo XML (Gradle, Maven); OUT/coverage.json of pycov.py. Without a baseline (a new repository, the first CI
PR) nothing is compared. A summary goes to $GITHUB_STEP_SUMMARY when set.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

COVERAGE_TOLERANCE = 0.1  # percentage points (rounding, timing-dependent lines)


def summarize(out: Path) -> dict[str, Any]:
    tests = skipped = failed = 0
    junit = False
    covered = missed = 0
    jacoco = False
    for path in sorted((out / "reports").rglob("*.xml")):
        try:
            root = ET.parse(path).getroot()  # noqa: S314 (see the import)
        except (ET.ParseError, OSError):
            continue
        if root.tag in ("testsuite", "testsuites"):
            junit = True
            for case in root.iter("testcase"):
                tests += 1
                if case.find("skipped") is not None:
                    skipped += 1
                elif case.find("failure") is not None or case.find("error") is not None:
                    failed += 1
        elif root.tag == "report":
            for counter in root.findall("counter"):
                if counter.get("type") == "LINE":
                    jacoco = True
                    covered += int(counter.get("covered", "0"))
                    missed += int(counter.get("missed", "0"))
    coverage = None
    if jacoco and covered + missed:
        coverage = round(100 * covered / (covered + missed), 2)
    pycov = out / "coverage.json"
    if pycov.is_file():
        try:
            coverage = json.loads(pycov.read_text())["percent"]
        except (ValueError, KeyError):
            coverage = None
    return {
        "tests": tests if junit else None,
        "skipped": skipped,
        "failed": failed,
        "coverage": coverage,
    }


def compare(base: dict[str, Any], head: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not base or not base.get("tests"):
        return problems  # no baseline yet
    if head.get("tests") is None:
        return ["the PR has no test results at all"]
    if head["tests"] < base["tests"]:
        problems.append(f"fewer tests: {head['tests']} < {base['tests']}")
    executed_base = base["tests"] - base.get("skipped", 0)
    executed_head = head["tests"] - head.get("skipped", 0)
    if executed_head < executed_base:
        problems.append(f"fewer executed tests (more skipped): {executed_head} < {executed_base}")
    if base.get("coverage") is not None:
        if head.get("coverage") is None:
            problems.append("the PR has no coverage report, the base has one")
        elif head["coverage"] < base["coverage"] - COVERAGE_TOLERANCE:
            problems.append(f"lower line coverage: {head['coverage']} % < {base['coverage']} %")
    return problems


def step_summary(base: dict[str, Any], head: dict[str, Any], problems: list[str]) -> str:
    rows = ["| | base | PR |", "|---|---|---|"]
    for key in ("tests", "skipped", "failed", "coverage"):
        rows.append(f"| {key} | {base.get(key, '–')} | {head.get(key, '–')} |")
    verdict = "\n".join(f"- ❌ {p}" for p in problems) if problems else "- ✅ no fewer tests, no lower coverage"
    return "### test-guard\n\n" + "\n".join(rows) + "\n\n" + verdict + "\n"


def load(path: str) -> dict[str, Any]:
    text = Path(path).read_text().strip()
    data = json.loads(text) if text else {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "summarize":
        print(json.dumps(summarize(Path(args[1]))))
        return 0
    if len(args) == 3 and args[0] == "compare":
        base, head = load(args[1]), load(args[2])
        problems = compare(base, head)
        text = step_summary(base, head, problems)
        print(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(text)
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
