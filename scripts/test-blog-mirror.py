#!/usr/bin/env python3
"""Tests for blog_mirror.py.  Run with:  python3 scripts/test-blog-mirror.py"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blog_mirror  # noqa: E402

PREFIX = "Medienmitteilungen"
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


def bundle(root, name, marker=None, body="# Hallo\n", teaser=b"jpegbytes", gallery=()):
    """Build a page bundle on disk and return its path."""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    fm = ["---", "Title: Hallo", "Date: 2026-09-04", "Site: bifang-säli"]
    if marker:
        fm.append(f"SyncedFrom: {marker}")
    fm.append("---")
    with open(os.path.join(d, "index.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fm) + "\n" + body)
    if teaser is not None:
        with open(os.path.join(d, "teaser.jpeg"), "wb") as fh:
            fh.write(teaser)
    for g in gallery:
        os.makedirs(os.path.join(d, "gallery"), exist_ok=True)
        with open(os.path.join(d, "gallery", g), "wb") as fh:
            fh.write(g.encode())
    return d


def main():
    tmp = tempfile.mkdtemp()
    try:
        # --- creates a bundle that is not there yet ---
        content = os.path.join(tmp, "blog1")
        staging = os.path.join(tmp, "stage1")
        os.makedirs(content)
        src = bundle(staging, "2026-09-04_Hort",
                     marker=f"{PREFIX}/2026-09-04_hort", gallery=("a.jpeg",))
        lines, status = blog_mirror.apply(
            {"2026-09-04_Hort": src}, content, PREFIX)
        check("create: status 0", status == 0, status)
        check("create: index.md written",
              os.path.isfile(os.path.join(content, "2026-09-04_Hort", "index.md")))
        check("create: gallery copied",
              os.path.isfile(os.path.join(content, "2026-09-04_Hort", "gallery", "a.jpeg")))
        check("create: reported", any(l.startswith("add: 2026-09-04_Hort") for l in lines), lines)

        # --- a target that exists WITHOUT a marker is never touched ---
        content = os.path.join(tmp, "blog2")
        os.makedirs(content)
        bundle(content, "2026-09-04_Hort", marker=None, body="# Von Hand\n")
        lines, status = blog_mirror.apply(
            {"2026-09-04_Hort": src}, content, PREFIX)
        with open(os.path.join(content, "2026-09-04_Hort", "index.md"), encoding="utf-8") as fh:
            kept = fh.read()
        check("unowned: left alone", "Von Hand" in kept, kept[:80])
        check("unowned: reported",
              any("not owned" in l for l in lines), lines)

        # --- a bundle marked by ANOTHER syncer survives ---
        content = os.path.join(tmp, "blog3")
        os.makedirs(content)
        bundle(content, "2026-05-01_Story", marker="Geschichten/2026-05-01_story")
        lines, status = blog_mirror.apply({}, content, PREFIX, allow_empty=True)
        check("foreign prefix: survives",
              os.path.isdir(os.path.join(content, "2026-05-01_Story")), lines)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
