"""Build the GeoCore requirements-to-evidence matrix and the next ledger.

Inputs (read-only):
  --ledger   the exported acceptance ledger JSON (never modified)
  --evidence a JSON list of evidence records produced by real runs
  --out      output directory

Outputs:
  01-requirements-matrix.csv   every ledger cell/journey/gate/defect item,
                               every current API operation and app/marketing
                               page, one row each
  04-ledger-reconciled.json    the original ledger content plus provenance;
                               statuses change ONLY where an evidence record
                               names a `target` environment of "staging" and
                               an existing evidence file (see RULES below)
  coverage.json                machine-readable counts per status

RULES (fail-closed):
  * An item becomes Verified only with an evidence record whose
    environment == "staging", whose release_sha matches --release-sha, and
    whose evidence path exists. Local/CI evidence can at most record
    "Pending" with a note; it never upgrades a ledger status.
  * Unknown is never promoted by inference from code, docs or a spec.
  * Free-text notes are escaped (no HTML/script reaches any consumer).
  * The input ledger's SHA-256 is recorded and re-checked at the end.

Run from the repository root with the application importable (for the
API inventory): python scripts/qa/build_qa_matrix.py --ledger ... --out ...
"""

import argparse
import copy
import csv
import hashlib
import html
import json
import pathlib
import sys
from datetime import datetime, timezone

STATUSES = ("Verified", "Defective", "Blocked", "Pending", "Unknown")
CSV_FIELDS = [
    "id", "kind", "feature", "batch", "actor_tenant", "release_sha", "preconditions", "expected",
    "actual", "evidence", "datetime_utc", "environment", "tester", "defect_ref", "severity", "status", "reason",
]


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(text) -> str:
    return html.escape(str(text or ""), quote=True).replace("\r", " ").replace("\n", " ")


def api_inventory(root: pathlib.Path):
    sys.path.insert(0, str(root))
    from app.main import app

    rows = []
    for path, ops in sorted(app.openapi()["paths"].items()):
        for method, op in sorted(ops.items()):
            rows.append({"method": method.upper(), "path": path, "tags": ",".join(op.get("tags", []))})
    return rows


def page_inventory(root: pathlib.Path):
    pages = []
    for app_name in ("web", "marketing"):
        base = root / "apps" / app_name / "app"
        for page in sorted(base.rglob("page.tsx")):
            route = "/" + "/".join(page.relative_to(base).parts[:-1])
            pages.append({"app": app_name, "route": route})
    return pages


def load_evidence(path: pathlib.Path | None, root: pathlib.Path):
    if path is None:
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    by_item = {}
    for record in records:
        ref = record.get("ref", "")
        local = root / ref if ref and not ref.startswith("http") else None
        record["ref_exists"] = bool(ref.startswith("http") or (local is not None and local.exists()))
        if not record["ref_exists"]:
            raise SystemExit(f"evidence reference does not exist: {ref!r} (item {record.get('item')})")
        by_item.setdefault(record["item"], []).append(record)
    return by_item


def decide(original_status: str, records: list, release_sha: str):
    """Returns (status, reason, chosen_record). Never upgrades without
    staging evidence on the release SHA."""
    staging = [r for r in records if r.get("environment") == "staging" and r.get("release_sha") == release_sha]
    if staging:
        if all(r.get("result") == "pass" for r in staging):
            return "Verified", "staging evidence on release SHA", staging[-1]
        return "Defective", "staging evidence shows a failure", next(r for r in staging if r.get("result") != "pass")
    if records:
        return original_status, "local/CI evidence only - not target-environment proof; status unchanged", records[-1]
    return original_status, "no evidence recorded", None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=pathlib.Path)
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--release-sha", default="")
    parser.add_argument("--repo-root", default=".", type=pathlib.Path)
    args = parser.parse_args()

    root = args.repo_root.resolve()
    input_hash = sha256(args.ledger)
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    evidence = load_evidence(args.evidence, root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    reconciled = copy.deepcopy(ledger)
    events = list(reconciled.get("events") or [])

    def ledger_row(item_id, kind, record, feature="", batch="", severity="", defect_ref=""):
        records = evidence.get(item_id, [])
        status, reason, chosen = decide(record["status"], records, args.release_sha)
        if status != record["status"]:
            events.append({"at": now, "item": item_id, "from": record["status"], "to": status,
                           "evidence": chosen["ref"], "by": "scripts/qa/build_qa_matrix.py"})
            record["status"] = status
            record["evidence"] = {"ref": chosen["ref"], "datetime": chosen.get("datetime", ""),
                                  "environment": chosen.get("environment", ""),
                                  "tester": chosen.get("tester", ""), "result": chosen.get("result", "")}
        latest = chosen or {}
        rows.append({
            "id": item_id, "kind": kind, "feature": feature, "batch": batch, "actor_tenant": latest.get("actor", ""),
            "release_sha": latest.get("release_sha", ""), "preconditions": latest.get("preconditions", ""),
            "expected": latest.get("expected", ""), "actual": latest.get("actual", ""),
            "evidence": latest.get("ref", ""), "datetime_utc": latest.get("datetime", ""),
            "environment": latest.get("environment", ""), "tester": latest.get("tester", ""),
            "defect_ref": defect_ref, "severity": severity, "status": status, "reason": reason,
        })

    for key, record in reconciled["cells"].items():
        batch, feature = key.split("::", 1)
        ledger_row(key, "ledger-cell", record, feature=feature, batch=batch)
    for key, record in reconciled["journeys"].items():
        ledger_row(key, "ledger-journey", record, feature=key)
    for key, record in reconciled["gates"].items():
        ledger_row(key, "ledger-gate", record, feature=key)
    for defect in reconciled["defects"]:
        ledger_row(defect["id"], "ledger-defect", defect["record"], feature=defect["title"],
                   severity=defect["severity"], defect_ref=defect["id"])
        for item in defect["checklist"]:
            item_records = evidence.get(f"{defect['id']}.{item['id']}", [])
            status, reason, chosen = decide("Pending" if not item["done"] else "Verified", item_records,
                                            args.release_sha)
            if status == "Verified" and not item["done"]:
                item["done"] = True
                events.append({"at": now, "item": f"{defect['id']}.{item['id']}", "from": "open", "to": "done",
                               "evidence": chosen["ref"], "by": "scripts/qa/build_qa_matrix.py"})
            latest = chosen or {}
            rows.append({
                "id": f"{defect['id']}.{item['id']}", "kind": "defect-checklist", "feature": item["label"],
                "batch": "", "actor_tenant": latest.get("actor", ""), "release_sha": latest.get("release_sha", ""),
                "preconditions": "", "expected": item["label"], "actual": latest.get("actual", ""),
                "evidence": latest.get("ref", ""), "datetime_utc": latest.get("datetime", ""),
                "environment": latest.get("environment", ""), "tester": latest.get("tester", ""),
                "defect_ref": defect["id"], "severity": defect["severity"], "status": status, "reason": reason,
            })

    for op in api_inventory(root):
        item_id = f"API {op['method']} {op['path']}"
        status, reason, chosen = decide("Unknown", evidence.get(item_id, []), args.release_sha)
        latest = chosen or {}
        rows.append({**{f: "" for f in CSV_FIELDS}, "id": item_id, "kind": "api-operation", "feature": op["tags"],
                     "evidence": latest.get("ref", ""), "environment": latest.get("environment", ""),
                     "status": status, "reason": reason})
    for page in page_inventory(root):
        item_id = f"PAGE {page['app']} {page['route']}"
        status, reason, chosen = decide("Unknown", evidence.get(item_id, []), args.release_sha)
        latest = chosen or {}
        rows.append({**{f: "" for f in CSV_FIELDS}, "id": item_id, "kind": "ui-page", "feature": page["app"],
                     "evidence": latest.get("ref", ""), "environment": latest.get("environment", ""),
                     "status": status, "reason": reason})

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "01-requirements-matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: clean(row.get(k, "")) for k in CSV_FIELDS})

    reconciled["events"] = events
    reconciled["provenance"] = {
        "source_ledger_sha256": input_hash,
        "generated_at": now,
        "generator": "scripts/qa/build_qa_matrix.py",
        "release_sha": args.release_sha,
        "rule": "status upgraded only by staging evidence on release_sha; local/CI evidence never upgrades",
        "site_sync": "BLOCKED - acceptance site requires ChatGPT sign-in; no source or API access",
    }
    (args.out / "04-ledger-reconciled.json").write_text(json.dumps(reconciled, indent=2, ensure_ascii=False),
                                                         encoding="utf-8")

    counts = {}
    for row in rows:
        counts.setdefault(row["kind"], {s: 0 for s in STATUSES})
        counts[row["kind"]][row["status"]] = counts[row["kind"]].get(row["status"], 0) + 1
    coverage = {
        "generated_at": now, "release_sha": args.release_sha, "source_ledger_sha256": input_hash,
        "denominator": {kind: sum(v.values()) for kind, v in counts.items()},
        "by_kind_and_status": counts,
        "go_possible": all(row["status"] == "Verified" for row in rows if row["kind"].startswith(("ledger", "defect"))),
    }
    (args.out / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    if sha256(args.ledger) != input_hash:
        raise SystemExit("input ledger changed during the run")
    print(json.dumps(coverage["denominator"]), "go_possible:", coverage["go_possible"])


if __name__ == "__main__":
    sys.exit(main())
