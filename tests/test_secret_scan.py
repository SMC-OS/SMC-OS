"""The secret scanner must catch real credential shapes and ignore the repository's safe lookalikes."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("scan", Path(__file__).resolve().parents[1] / "scripts/qa/scan_secrets.py")
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)

# Assembled at run time so this file itself never contains a credential-shaped literal.
CANARIES = {
    "stripe live secret key": "sk_" + "live_" + "a" * 24,
    "stripe webhook signing secret": "whsec" + "_" + "b" * 32,
    "private key block": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "github token": "ghp" + "_" + "c" * 36,
    "hosted database url with password": "postgresql://app:" + "hunter22secret" + "@db.proxy.rlwy.net:5432/railway",
}
SAFE = ["sk_test_dummy", "postgresql://simo:simo@localhost:5432/simo_os", "whsec_test", "revision = '94e5f6a7b8c9'",
        "STRIPE_SECRET_KEY=", "ci-test-secret"]


def test_every_canary_is_detected_by_name():
    for name, value in CANARIES.items():
        assert any(n == name for n, _ in scan.scan_text(f'x = "{value}"')), name


def test_safe_lookalikes_are_ignored():
    for value in SAFE:
        assert scan.scan_text(value) == [], value


def test_hits_report_location_not_value():
    hits = scan.scan_text("a\nb\n" + CANARIES["stripe live secret key"])
    assert hits == [("stripe live secret key", 3)]


def test_the_repository_tree_is_clean():
    assert scan.scan_tree() == []
