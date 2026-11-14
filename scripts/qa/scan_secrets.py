"""High-precision secret scan of tracked files and (optionally) the whole git history.

Why not a generic entropy scanner: on this repository one finds ~770 "secrets" that are migration
revision ids, lockfile hashes and test passwords, so it cannot be a gate. These patterns are real
credential FORMATS only (Stripe, GitHub, AWS, Google, Slack, SendGrid/Resend, private keys, signed
JWTs, and database URLs carrying a password for a hosted provider). A hit prints the file and line
but never the value. Exit 1 on any hit.

  python scripts/qa/scan_secrets.py            # tracked files
  python scripts/qa/scan_secrets.py --history  # also every commit on every ref (needs full clone)
"""

import argparse
import re
import subprocess
import sys

PATTERNS = {
    "stripe live secret key": r"sk_live_[0-9A-Za-z]{16,}",
    "stripe live restricted key": r"rk_live_[0-9A-Za-z]{16,}",
    "stripe test secret key": r"sk_test_[0-9A-Za-z]{16,}",
    "stripe webhook signing secret": r"whsec_[0-9A-Za-z]{20,}",
    "stripe live publishable key": r"pk_live_[0-9A-Za-z]{16,}",
    "aws access key id": r"AKIA[0-9A-Z]{16}",
    "github token": r"gh[pousr]_[0-9A-Za-z]{30,}",
    "github fine-grained token": r"github_pat_[0-9A-Za-z_]{40,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "slack token": r"xox[baprs]-[0-9A-Za-z-]{20,}",
    "google api key": r"AIza[0-9A-Za-z_-]{35}",
    "signed jwt": r"eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}",
    "hosted database url with password": r"postgres(ql)?(\+[a-z]+)?://[^:/@ ]+:[^@ ]{6,}@[A-Za-z0-9.-]+\.(rlwy\.net|railway\.app|railway\.internal|supabase\.co|neon\.tech|amazonaws\.com)",
    "resend api key": r"\bre_[A-Za-z0-9]{24,}",
    "sendgrid api key": r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}",
}
COMPILED = {name: re.compile(p) for name, p in PATTERNS.items()}
EXCLUDE = (":!pnpm-lock.yaml", ":!tests/test_secret_scan.py")


def scan_text(text: str) -> list[tuple[str, int]]:
    """Return (pattern name, line number) pairs; never the matched value."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for name, rx in COMPILED.items():
            if rx.search(line):
                hits.append((name, number))
    return hits


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def scan_tree() -> list[str]:
    found = []
    for path in git("ls-files", "--", ".", *EXCLUDE).splitlines():
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        found += [f"{path}:{n} {name}" for name, n in scan_text(text)]
    return found


def scan_history() -> list[str]:
    regex = "|".join(PATTERNS.values())
    commits = git("log", "--all", "--format=%H", "-G", regex, "--", ".", *EXCLUDE).split()
    return [f"commit {c[:12]} adds a credential-shaped string (inspect with: git show {c[:12]})" for c in commits]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    findings = scan_tree() + (scan_history() if args.history else [])
    for line in findings:
        print(line)
    print(f"secret scan: {len(findings)} finding(s) in {'tree + history' if args.history else 'tree'}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
