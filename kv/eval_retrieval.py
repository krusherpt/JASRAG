#!/usr/bin/env python3
"""Evaluate active Knowledge Vault retrieval against a small golden set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kv import KnowledgeVault


EVAL_PATH = Path(__file__).with_name("eval_queries.jsonl")


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return cases


def contains(value: Any, expected: str) -> bool:
    return expected.lower() in str(value or "").lower()


def matches(result: dict[str, Any], expected: dict[str, Any]) -> bool:
    if title := expected.get("title_contains"):
        if not contains(result.get("title"), title):
            return False
    if source_type := expected.get("source_type"):
        if result.get("source_type") != source_type:
            return False
    if "category" in expected:
        if result.get("category") != expected["category"]:
            return False
    if content := expected.get("content_contains"):
        if not contains(result.get("content"), content):
            return False
    return True


def first_actual(results: list[dict[str, Any]]) -> str:
    if not results:
        return "<no results>"
    first = results[0]
    return (
        f"{first.get('title')} | {first.get('source_type')} | "
        f"{first.get('category')} | chunk {first.get('chunk_index')}"
    )


def evaluate(kv: KnowledgeVault, cases: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    health = kv.health()
    health_ok = health["orphan_docs_fts"] == 0 and health["orphan_chunks_fts"] == 0

    rows = []
    top1_hits = 0
    top3_hits = 0
    empty_pass = 0
    empty_total = 0

    for case in cases:
        results = kv.index.search_chunks(case["query"], limit=top_k)
        if case.get("expect_empty"):
            empty_total += 1
            passed = not results
            empty_pass += int(passed)
            rows.append({**case, "top1": passed, "top3": passed, "actual": first_actual(results)})
            continue

        expected = case.get("expect", {})
        top1 = bool(results[:1] and matches(results[0], expected))
        top3 = any(matches(result, expected) for result in results[:3])
        top1_hits += int(top1)
        top3_hits += int(top3)
        rows.append({**case, "top1": top1, "top3": top3, "actual": first_actual(results)})

    scored_total = len([case for case in cases if not case.get("expect_empty")])
    return {
        "health": health,
        "health_ok": health_ok,
        "case_count": len(cases),
        "scored_count": scored_total,
        "top1_hits": top1_hits,
        "top3_hits": top3_hits,
        "top1_rate": top1_hits / scored_total if scored_total else 0.0,
        "top3_rate": top3_hits / scored_total if scored_total else 0.0,
        "empty_pass": empty_pass,
        "empty_total": empty_total,
        "rows": rows,
    }


def print_report(report: dict[str, Any]) -> None:
    print("KV Retrieval Eval")
    print("=================")
    print(f"health: {'PASS' if report['health_ok'] else 'FAIL'}")
    print(f"cases: {report['case_count']} ({report['scored_count']} scored)")
    print(f"top1: {report['top1_hits']}/{report['scored_count']} ({report['top1_rate']:.0%})")
    print(f"top3: {report['top3_hits']}/{report['scored_count']} ({report['top3_rate']:.0%})")
    if report["empty_total"]:
        print(f"empty: {report['empty_pass']}/{report['empty_total']}")
    print()

    for row in report["rows"]:
        status = "PASS" if row["top3"] else "FAIL"
        print(f"{status} {row['id']}")
        print(f"  query: {row['query']}")
        print(f"  top1: {row['top1']} top3: {row['top3']}")
        print(f"  actual: {row['actual']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate KV retrieval quality")
    parser.add_argument("--cases", type=Path, default=EVAL_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    kv = KnowledgeVault()
    try:
        report = evaluate(kv, cases, args.top_k)
    finally:
        kv.close()

    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)

    failed = not report["health_ok"] or report["top3_hits"] < report["scored_count"]
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
