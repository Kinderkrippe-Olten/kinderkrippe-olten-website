#!/usr/bin/env python3
"""Tests for apply-stellen-sync.py.

Builds a staging tree and a fake content tree in a temp dir, runs the script as a
subprocess, and asserts on the resulting files and exit status.

Run with:  python3 scripts/test-apply-stellen-sync.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APPLY = os.path.join(HERE, "apply-stellen-sync.py")

SITES = ("bifang-säli", "hagmatt", "sonnhalde")
SITES_YAML = "".join(f"- dir: {s}\n  title: {s.title()}\n" for s in SITES)

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


def build(tmp, staging_files, content_files, staging_dirs=()):
    """Create staging/ and content/ trees; return (staging, content, sites_path)."""
    staging = os.path.join(tmp, "staging")
    content = os.path.join(tmp, "content")
    for p in (staging, content):
        shutil.rmtree(p, ignore_errors=True)
    for s in SITES:
        os.makedirs(os.path.join(staging, s), exist_ok=True)
        os.makedirs(os.path.join(content, s), exist_ok=True)
        open(os.path.join(content, s, ".gitkeep"), "a").close()
    for d in staging_dirs:
        os.makedirs(os.path.join(staging, d), exist_ok=True)

    for tree, files in ((staging, staging_files), (content, content_files)):
        for rel, body in files.items():
            full = os.path.join(tree, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(body)

    sites_path = os.path.join(tmp, "stellen.yaml")
    with open(sites_path, "w", encoding="utf-8") as fh:
        fh.write(SITES_YAML)
    return staging, content, sites_path


def run(staging, content, sites, *extra):
    p = subprocess.run(
        [sys.executable, APPLY, "--staging", staging, "--content", content,
         "--sites", sites, *extra],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout, p.stderr


def pdfs(content, site):
    d = os.path.join(content, site)
    return sorted(n for n in os.listdir(d) if not n.startswith("."))


A = "sonnhalde/sonnhalde 20260728 Koch oder Köchin (10%) per 1.9.2026.pdf"
B = "hagmatt/hagmatt 20260423 Aushilfe per sofort.pdf"


def main():
    tmp = tempfile.mkdtemp(prefix="stellen-apply-")
    try:
        print("adds new ads")
        st, co, sy = build(tmp, {A: b"%PDF-a", B: b"%PDF-b"}, {})
        rc, out, err = run(st, co, sy)
        check("exit 0", rc == 0, f"rc={rc} {err[:200]}")
        check("both copied", pdfs(co, "sonnhalde") == [os.path.basename(A)]
              and pdfs(co, "hagmatt") == [os.path.basename(B)],
              f"{pdfs(co,'sonnhalde')} {pdfs(co,'hagmatt')}")
        check("reports adds", out.count("add:") == 2, out)

        print("removes ads deleted in OpenCloud")
        st, co, sy = build(tmp, {A: b"%PDF-a"}, {A: b"%PDF-a", B: b"%PDF-b"})
        rc, out, err = run(st, co, sy)
        check("exit 0", rc == 0, f"rc={rc} {err[:200]}")
        check("stale ad gone", pdfs(co, "hagmatt") == [], str(pdfs(co, "hagmatt")))
        check("reports removal", "remove:" in out, out)

        print("updates changed content")
        st, co, sy = build(tmp, {A: b"%PDF-new"}, {A: b"%PDF-old"})
        rc, out, err = run(st, co, sy)
        check("reports update", "update:" in out, out)
        with open(os.path.join(co, A), "rb") as fh:
            check("content replaced", fh.read() == b"%PDF-new")

        print("no-op when identical")
        st, co, sy = build(tmp, {A: b"%PDF-a"}, {A: b"%PDF-a"})
        rc, out, err = run(st, co, sy)
        check("exit 0", rc == 0, f"rc={rc}")
        check("reports no changes", "no changes" in out, out)

        print("wipeout guard")
        st, co, sy = build(tmp, {}, {A: b"%PDF-a", B: b"%PDF-b"})
        rc, out, err = run(st, co, sy)
        check("exit 3", rc == 3, f"rc={rc} {err[:200]}")
        check("nothing deleted", pdfs(co, "sonnhalde") and pdfs(co, "hagmatt"),
              "files were removed despite the guard")
        check("explains itself", "--allow-empty" in err, err[:200])

        rc, out, err = run(st, co, sy, "--allow-empty")
        check("--allow-empty overrides", rc == 0, f"rc={rc} {err[:200]}")
        check("now emptied", pdfs(co, "sonnhalde") == [] and pdfs(co, "hagmatt") == [],
              "files remained")

        print("empty staging AND empty repo is fine")
        st, co, sy = build(tmp, {}, {})
        rc, out, err = run(st, co, sy)
        check("exit 0", rc == 0, f"rc={rc} {err[:200]}")

        print(".gitkeep survives the mirror")
        st, co, sy = build(tmp, {A: b"%PDF-a"}, {})
        os.remove(os.path.join(co, "hagmatt", ".gitkeep"))
        rc, out, err = run(st, co, sy)
        check("recreated where missing",
              os.path.exists(os.path.join(co, "hagmatt", ".gitkeep")))
        check("kept where present",
              os.path.exists(os.path.join(co, "sonnhalde", ".gitkeep")))

        print("OpenCloud folder spelling is canonicalised")
        st, co, sy = build(tmp, {"Hagmatt/hagmatt 20260423 Grossbuchstabe.pdf": b"%PDF"},
                           {}, staging_dirs=["Hagmatt"])
        rc, out, err = run(st, co, sy)
        check("exit 0", rc == 0, f"rc={rc} {err[:200]}")
        check("landed in lowercase dir",
              pdfs(co, "hagmatt") == ["hagmatt 20260423 Grossbuchstabe.pdf"],
              str(pdfs(co, "hagmatt")))

        print("rejected files do not block the good ones")
        st, co, sy = build(tmp, {A: b"%PDF-a", "hagmatt/kaputt.pdf": b"%PDF-x"}, {})
        rc, out, err = run(st, co, sy)
        check("exit 1", rc == 1, f"rc={rc}")
        check("valid ad still applied", pdfs(co, "sonnhalde") == [os.path.basename(A)],
              str(pdfs(co, "sonnhalde")))
        check("bad file not copied", pdfs(co, "hagmatt") == [], str(pdfs(co, "hagmatt")))

        print("--dry-run changes nothing")
        st, co, sy = build(tmp, {A: b"%PDF-a"}, {B: b"%PDF-b"})
        rc, out, err = run(st, co, sy, "--dry-run")
        check("exit 0", rc == 0, f"rc={rc} {err[:200]}")
        check("says would", "would add:" in out and "would remove:" in out, out)
        check("staging ad NOT copied", pdfs(co, "sonnhalde") == [], str(pdfs(co, "sonnhalde")))
        check("stale ad NOT removed", pdfs(co, "hagmatt") == [os.path.basename(B)],
              str(pdfs(co, "hagmatt")))

        print("fatal inputs exit 2 without touching content")
        st, co, sy = build(tmp, {A: b"%PDF-a"}, {B: b"%PDF-b"})
        rc, out, err = run(st, os.path.join(tmp, "nope"), sy)
        check("missing content dir exits 2", rc == 2, f"rc={rc}")
        rc, out, err = run(os.path.join(tmp, "nope"), co, sy)
        check("missing staging dir exits 2", rc == 2, f"rc={rc}")
        rc, out, err = run(st, co, os.path.join(tmp, "nope.yaml"))
        check("missing site list exits 2", rc == 2, f"rc={rc}")
        check("content untouched", pdfs(co, "hagmatt") == [os.path.basename(B)],
              str(pdfs(co, "hagmatt")))
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
