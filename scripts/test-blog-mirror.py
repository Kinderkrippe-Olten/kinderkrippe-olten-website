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

        # --- update rewrites generated files and prunes dropped gallery images ---
        content = os.path.join(tmp, "blog4")
        staging = os.path.join(tmp, "stage4")
        os.makedirs(content)
        bundle(content, "2026-09-04_Hort", marker=f"{PREFIX}/2026-09-04_hort",
               body="# Alt\n", gallery=("a.jpeg", "b.jpeg"))
        new = bundle(staging, "2026-09-04_Hort", marker=f"{PREFIX}/2026-09-04_hort",
                     body="# Neu\n", gallery=("a.jpeg",))
        lines, status = blog_mirror.apply({"2026-09-04_Hort": new}, content, PREFIX)
        with open(os.path.join(content, "2026-09-04_Hort", "index.md"), encoding="utf-8") as fh:
            got = fh.read()
        check("update: body replaced", "# Neu" in got, got[:80])
        check("update: dropped gallery image pruned",
              not os.path.exists(os.path.join(content, "2026-09-04_Hort", "gallery", "b.jpeg")))
        check("update: reported", any(l.startswith("update:") for l in lines), lines)

        # --- re-running the same input changes nothing (proves determinism end) ---
        lines, status = blog_mirror.apply({"2026-09-04_Hort": new}, content, PREFIX)
        check("no-op: reports no changes", lines == ["no changes"], lines)

        # --- delete removes an owned bundle whose source is gone ---
        content = os.path.join(tmp, "blog5")
        os.makedirs(content)
        bundle(content, "2026-09-04_Hort", marker=f"{PREFIX}/2026-09-04_hort")
        bundle(content, "2024-03-18_Osterprojekt", marker=None)
        lines, status = blog_mirror.apply({}, content, PREFIX, allow_empty=True)
        check("delete: owned bundle removed",
              not os.path.exists(os.path.join(content, "2026-09-04_Hort")))
        check("delete: hand-made post survives",
              os.path.isdir(os.path.join(content, "2024-03-18_Osterprojekt")))

        # --- the wipeout guard refuses an empty set while owned bundles exist ---
        content = os.path.join(tmp, "blog6")
        os.makedirs(content)
        bundle(content, "2026-09-04_Hort", marker=f"{PREFIX}/2026-09-04_hort")
        lines, status = blog_mirror.apply({}, content, PREFIX)
        check("guard: status 3", status == 3, status)
        check("guard: nothing deleted",
              os.path.isdir(os.path.join(content, "2026-09-04_Hort")))

        # --- a REJECTED folder must not unpublish its page ---
        content = os.path.join(tmp, "blog7")
        os.makedirs(content)
        bundle(content, "2026-09-04_Hort", marker=f"{PREFIX}/2026-09-04_hort")
        bundle(content, "2026-07-20_Hort", marker=f"{PREFIX}/2026-07-20_hort")
        lines, status = blog_mirror.apply(
            {"2026-07-20_Hort": bundle(os.path.join(tmp, "stage7"), "2026-07-20_Hort",
                                       marker=f"{PREFIX}/2026-07-20_hort")},
            content, PREFIX, protected={"2026-09-04_Hort"})
        check("rejected: page left as-is",
              os.path.isdir(os.path.join(content, "2026-09-04_Hort")), lines)

        # --- dry run touches nothing ---
        content = os.path.join(tmp, "blog8")
        os.makedirs(content)
        lines, status = blog_mirror.apply(
            {"2026-09-04_Hort": src}, content, PREFIX, dry_run=True)
        check("dry-run: nothing written",
              not os.path.exists(os.path.join(content, "2026-09-04_Hort")))
        check("dry-run: says 'would'", any(l.startswith("would add:") for l in lines), lines)
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
