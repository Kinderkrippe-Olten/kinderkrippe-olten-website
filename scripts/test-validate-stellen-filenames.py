#!/usr/bin/env python3
"""Tests for validate-stellen-filenames.py.

Self-contained: builds fixture directories in a temp dir and runs the validator as a
subprocess, so it exercises the real command-line contract.

Run with:  python3 scripts/test-validate-stellen-filenames.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATOR = os.path.join(HERE, "validate-stellen-filenames.py")

SITES_YAML = """\
# comment line, must be skipped
- dir: bifang-säli
  title: Hort Bifang-Säli
- dir: hagmatt
  title: Kita Hagmatt
- dir: sonnhalde
  title: Kita Sonnhalde
"""

failures = []


def run(tmp, files, dirs=()):
    """Build a staging tree, run the validator, return (rc, valid_list, stderr)."""
    staging = os.path.join(tmp, "staging")
    shutil.rmtree(staging, ignore_errors=True)
    for d in ("bifang-säli", "hagmatt", "sonnhalde"):
        os.makedirs(os.path.join(staging, d), exist_ok=True)
    for d in dirs:
        os.makedirs(os.path.join(staging, d), exist_ok=True)
    for rel in files:
        full = os.path.join(staging, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(b"%PDF-1.4\n")

    sites = os.path.join(tmp, "stellen.yaml")
    with open(sites, "w", encoding="utf-8") as fh:
        fh.write(SITES_YAML)

    p = subprocess.run(
        [sys.executable, VALIDATOR, "--sites", sites, staging],
        capture_output=True, text=True,
    )
    valid = [l for l in p.stdout.splitlines() if l]
    return p.returncode, valid, p.stderr


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="stellen-validate-")
    try:
        print("accepts valid filenames")
        rc, valid, err = run(tmp, [
            "sonnhalde/sonnhalde 20260728 Koch oder Köchin (10% und Ferienvertretung) per 1.9.2026.pdf",
            "hagmatt/hagmatt-20260423-Aushilfe per sofort.pdf",          # hyphen separators
            "bifang-säli/bifang-säli_20260805_Pädagogische Fachperson (30 – 50%).pdf",  # underscores
            "bifang-säli/Bifang-Säli 20260617 Aushilfe.pdf",             # uppercase + umlaut
            "hagmatt/hagmatt 20260101 Grossbuchstaben.PDF",              # uppercase extension
        ])
        check("exit 0", rc == 0, f"rc={rc} stderr={err.strip()[:200]}")
        check("all five accepted", len(valid) == 5, f"got {len(valid)}: {valid}")

        print("rejects malformed filenames")
        cases = [
            ("wrong site prefix",   "sonnhalde/hagmatt 20260101 Falscher Ordner.pdf"),
            ("no date",             "sonnhalde/sonnhalde Ohne Datum.pdf"),
            ("short date",          "sonnhalde/sonnhalde 2026 Kurzes Datum.pdf"),
            ("non-digit date",      "sonnhalde/sonnhalde 2026abcd Buchstaben.pdf"),
            ("no separator",        "sonnhalde/sonnhalde20260101 Kein Trenner.pdf"),
            ("no link text",        "sonnhalde/sonnhalde 20260101 .pdf"),
            ("non-PDF",             "sonnhalde/sonnhalde 20260101 Falsches Format.docx"),
            ("no extension",        "sonnhalde/sonnhalde 20260101 Ohne Endung"),
        ]
        for label, rel in cases:
            rc, valid, err = run(tmp, [rel])
            check(f"rejects {label}", rc == 1 and not valid, f"rc={rc} valid={valid}")

        print("rejects structural problems")
        rc, valid, err = run(tmp, ["sonnhalde/nested/sonnhalde 20260101 Tief.pdf"])
        check("rejects subdirectory", rc == 1 and not valid, f"rc={rc} valid={valid}")
        check("names the subdirectory", "nested" in err, err.strip()[:200])

        rc, valid, err = run(tmp, [], dirs=["verein"])
        check("rejects unlisted site folder", rc == 1, f"rc={rc}")
        check("names the folder", "verein" in err, err.strip()[:200])

        rc, valid, err = run(tmp, ["streuner.pdf"])
        check("rejects top-level file", rc == 1 and not valid, f"rc={rc} valid={valid}")

        print("ignores noise")
        rc, valid, err = run(tmp, [
            "sonnhalde/.DS_Store",
            "sonnhalde/Thumbs.db",
            ".hidden-at-root",
            "sonnhalde/sonnhalde 20260728 Gut.pdf",
        ])
        check("exit 0 despite noise", rc == 0, f"rc={rc} stderr={err.strip()[:200]}")
        check("only the real ad is valid", valid == ["sonnhalde/sonnhalde 20260728 Gut.pdf"], str(valid))

        print("partial success: good ones still pass through")
        rc, valid, err = run(tmp, [
            "sonnhalde/sonnhalde 20260728 Gut.pdf",
            "hagmatt/hagmatt 20260423 Auch gut.pdf",
            "bifang-säli/kaputt.pdf",
        ])
        check("exit 1", rc == 1, f"rc={rc}")
        check("two valid still emitted", len(valid) == 2, str(valid))
        check("error names the bad file", "kaputt.pdf" in err, err.strip()[:200])

        print("empty staging is clean, not an error")
        rc, valid, err = run(tmp, [])
        check("exit 0", rc == 0, f"rc={rc} stderr={err.strip()[:200]}")
        check("no valid files", valid == [], str(valid))

        print("--print0 for filenames with spaces")
        staging = os.path.join(tmp, "staging")
        p = subprocess.run(
            [sys.executable, VALIDATOR, "--sites", os.path.join(tmp, "stellen.yaml"),
             "--print0", staging],
            capture_output=True,
        )
        check("empty tree prints nothing", p.stdout == b"", repr(p.stdout))
        rc, _, _ = run(tmp, ["sonnhalde/sonnhalde 20260728 Mit Leerzeichen.pdf"])
        p = subprocess.run(
            [sys.executable, VALIDATOR, "--sites", os.path.join(tmp, "stellen.yaml"),
             "--print0", staging],
            capture_output=True,
        )
        check("NUL-terminated", p.stdout.endswith(b"\0"), repr(p.stdout))
        check("one record", p.stdout.count(b"\0") == 1, repr(p.stdout))

        print("bad invocation")
        p = subprocess.run(
            [sys.executable, VALIDATOR, "--sites", os.path.join(tmp, "stellen.yaml"),
             os.path.join(tmp, "does-not-exist")],
            capture_output=True, text=True,
        )
        check("missing staging dir exits 2", p.returncode == 2, f"rc={p.returncode}")

        p = subprocess.run(
            [sys.executable, VALIDATOR, "--sites", os.path.join(tmp, "nope.yaml"), staging],
            capture_output=True, text=True,
        )
        check("missing site list exits 2", p.returncode == 2, f"rc={p.returncode}")

        # Drift guard. The convention lives here and in layouts/_shortcodes/stellen.html.
        # Everything committed under content/docs/stellen/ already builds, so this
        # script must accept all of it; if it does not, the two have diverged.
        print("agrees with the live repository content")
        repo = os.path.dirname(HERE)
        live = os.path.join(repo, "content", "docs", "stellen")
        if os.path.isdir(live):
            p = subprocess.run(
                [sys.executable, VALIDATOR, "--sites",
                 os.path.join(repo, "data", "stellen.yaml"), live],
                capture_output=True, text=True,
            )
            check("accepts every committed job ad", p.returncode == 0,
                  f"rc={p.returncode} stderr={p.stderr.strip()[:300]}")
            check("found at least one", len([l for l in p.stdout.splitlines() if l]) > 0,
                  p.stdout)
        else:
            check("live content dir present", False, f"{live} missing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
