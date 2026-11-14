"""Render and validate the authoritative release execution ledger.

Data: artifacts/qa/stone-hard-2026-11-05/15-release-execution-ledger.json
Rules enforced (a violation is an error, not a warning):
  * status is one of VERIFIED / FAILING / BLOCKED / UNKNOWN / NOT_APPLICABLE
  * VERIFIED needs at least one evidence entry in an environment listed in the gate's `verified_in`
  * NOT_APPLICABLE needs a written justification
  * evidence is tagged with its environment and is never counted for another environment
Usage: python scripts/qa/release_ledger.py [--markdown OUT.md]
"""

import argparse
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "artifacts/qa/stone-hard-2026-11-05/15-release-execution-ledger.json"
STATUSES = ("VERIFIED", "FAILING", "BLOCKED", "UNKNOWN", "NOT_APPLICABLE")
ENVIRONMENTS = ("local", "ci", "isolated_qa_public", "isolated_qa", "shared_staging", "production")
REQUIRED = ("id", "purpose", "verified_in", "sha", "evidence", "status", "owner", "remaining", "blocks_initial_release")


def validate(doc: dict) -> list[str]:
    errors = []
    seen = set()
    for g in doc["gates"]:
        gid = g.get("id", "?")
        for key in REQUIRED:
            if key not in g:
                errors.append(f"{gid}: missing {key}")
        if g.get("id") in seen:
            errors.append(f"{gid}: duplicate id")
        seen.add(g.get("id"))
        if g.get("status") not in STATUSES:
            errors.append(f"{gid}: invalid status {g.get('status')!r}")
        for env in g.get("verified_in", []):
            if env not in ENVIRONMENTS:
                errors.append(f"{gid}: unknown environment {env!r}")
        for item in g.get("evidence", []):
            if item.get("env") not in ENVIRONMENTS or not item.get("what"):
                errors.append(f"{gid}: malformed evidence {item!r}")
        if g.get("status") == "VERIFIED" and not any(e["env"] in g["verified_in"] for e in g.get("evidence", [])):
            errors.append(f"{gid}: VERIFIED without evidence in {g.get('verified_in')}")
        if g.get("status") == "NOT_APPLICABLE" and not g.get("justification"):
            errors.append(f"{gid}: NOT_APPLICABLE without justification")
    return errors


def render(doc: dict) -> str:
    gates = doc["gates"]
    counts = {s: sum(1 for g in gates if g["status"] == s) for s in STATUSES}
    blocking = [g for g in gates if g["blocks_initial_release"] and g["status"] not in ("VERIFIED", "NOT_APPLICABLE")]
    lines = [f"# {doc['title']}", "", f"_As of {doc['as_of']}. Verdict: **{doc['verdict']}**._", "",
             "Status counts: " + ", ".join(f"{s} {n}" for s, n in counts.items()) + f". Launch-blocking gates not yet VERIFIED: **{len(blocking)}** of {sum(1 for g in gates if g['blocks_initial_release'])}.", "",
             doc.get("relation_to_existing_ledger", ""), "",
             "| Gate | Status | Must be proven in | Evidence so far (environment: what) | Owner | Remaining |", "|---|---|---|---|---|---|"]
    for g in gates:
        ev = "<br>".join(f"**{e['env']}**: {e['what']}" for e in g["evidence"]) or "none"
        lines.append(f"| **{g['id']}** {g['purpose']} | {g['status']}{'' if g['blocks_initial_release'] else ' (not launch-blocking)'} | {', '.join(g['verified_in'])} | {ev} | {g['owner']} | {g['remaining']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown")
    args = parser.parse_args()
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    errors = validate(doc)
    for e in errors:
        print("ERROR", e)
    if args.markdown:
        Path(args.markdown).write_text(render(doc), encoding="utf-8")
    print(f"{len(doc['gates'])} gates, {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
