#!/usr/bin/env python3
"""End-to-end tests for apply-medien-sync.py, run as a subprocess.

Run with:  python3 scripts/test-apply-medien-sync.py
"""

import datetime
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
APPLY = os.path.join(HERE, "apply-medien-sync.py")
FIXTURES = os.path.join(HERE, "fixtures", "medien")
DOCX = "20260904_MM_EröffnungHort.docx"

SITES = "sonnhalde:\n  Name: Sonnhalde\nhagmatt:\n  Name: Hagmatt\nbifang-säli:\n  Name: Hort\nverein:\n  Name: Verein\n"
ALIASES = "aliases:\n  hort: bifang-säli\n"

HANDMADE = '---\nTitle: "Von Hand"\nDate: 2026-09-04\n---\n\nvon Hand geschrieben\n'

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


def setup(tmp, folders, extra_top_level=()):
    """folders: {name: [filenames from FIXTURES, or ('meta.yaml', text)]}"""
    staging = os.path.join(tmp, "staging")
    content = os.path.join(tmp, "content")
    os.makedirs(staging, exist_ok=True)
    os.makedirs(content, exist_ok=True)
    for name, files in folders.items():
        d = os.path.join(staging, name)
        os.makedirs(d, exist_ok=True)
        for f in files:
            if isinstance(f, tuple):
                with open(os.path.join(d, f[0]), "w", encoding="utf-8") as fh:
                    fh.write(f[1])
            else:
                shutil.copy2(os.path.join(FIXTURES, f), os.path.join(d, f))
    for f in extra_top_level:
        open(os.path.join(staging, f), "w").close()
    sites = os.path.join(tmp, "sites.yaml")
    aliases = os.path.join(tmp, "aliases.yaml")
    open(sites, "w", encoding="utf-8").write(SITES)
    open(aliases, "w", encoding="utf-8").write(ALIASES)
    return staging, content, sites, aliases


def run(staging, content, sites, aliases, *extra):
    p = subprocess.run(
        [sys.executable, APPLY, "--staging", staging, "--content", content,
         "--sites", sites, "--aliases", aliases, *extra],
        capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def load_module():
    """Import apply-medien-sync.py, whose file name is not a Python identifier."""
    spec = importlib.util.spec_from_file_location("apply_medien_sync", APPLY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tmp = tempfile.mkdtemp()
    try:
        imgs = [n for n in sorted(os.listdir(FIXTURES)) if n.startswith("IMG_")]

        # --- the happy path ---
        s, c, si, al = setup(tmp, {"2026-09-04_hort": [DOCX] + imgs},
                             extra_top_level=("Anleitung.pdf",))
        rc, out = run(s, c, si, al)
        page = os.path.join(c, "2026-09-04_Hort")
        check("happy: rc 0", rc == 0, out)
        check("happy: directory is title-cased", os.path.isdir(page), os.listdir(c))
        text = open(os.path.join(page, "index.md"), encoding="utf-8").read()
        check("happy: Date from the folder name", "Date: 2026-09-04" in text, text[:200])
        check("happy: Site resolved through the alias", "Site: bifang-säli" in text, text[:200])
        check("happy: marker written",
              "SyncedFrom: Medienmitteilungen/2026-09-04_hort" in text, text[:200])
        # Values that can carry arbitrary author text are quoted; the ones the
        # repository controls -- and the marker blog_mirror matches -- are not.
        check("happy: Autor from the document",
              'Autor: "Melanie von Arx"' in text, text[:200])
        check("happy: Title is quoted", 'Title: "' in text, text[:200])
        check("happy: no TeaserTitle without meta.yaml", "TeaserTitle:" not in text)
        check("happy: teaser written", os.path.isfile(os.path.join(page, "teaser.jpeg")))
        check("happy: 12 gallery files",
              len(os.listdir(os.path.join(page, "gallery"))) == 12)
        check("happy: a file at the staging root is ignored, not rejected",
              "Anleitung" not in out, out)

        # --- re-running changes nothing (determinism) ---
        rc, out = run(s, c, si, al)
        check("no-op: rc 0", rc == 0, out)
        check("no-op: reports no changes", "no changes" in out, out)

        # --- meta.yaml overrides ---
        s, c, si, al = setup(tmp + "/m", {"2026-09-04_hort": [
            DOCX, ("meta.yaml", "TeaserTitle: Eröffnung Hort\nAutor: F. Giori\n")]})
        rc, out = run(s, c, si, al)
        text = open(os.path.join(c, "2026-09-04_Hort", "index.md"), encoding="utf-8").read()
        check("meta: TeaserTitle applied",
              'TeaserTitle: "Eröffnung Hort"' in text, text[:200])
        check("meta: Autor overridden", 'Autor: "F. Giori"' in text, text[:200])

        # --- a key meta.yaml does not know is reported, not silently dropped ---
        s, c, si, al = setup(tmp + "/mu", {"2026-09-04_hort": [
            DOCX, ("meta.yaml", "Teasertitle: falsch geschrieben\n")]})
        rc, out = run(s, c, si, al)
        check("meta: an unknown key is reported", "Teasertitle" in out, out)
        check("meta: an unknown key is a note, not a rejection", rc == 0, out)
        check("meta: an unknown key still publishes the page",
              os.path.isdir(os.path.join(c, "2026-09-04_Hort")), os.listdir(c))

        # --- meta.yaml's Site goes through the same alias map as the folder name ---
        s, c, si, al = setup(tmp + "/msa", {"2026-09-04_sonnhalde": [
            DOCX, ("meta.yaml", "Site: hort\n")]})
        rc, out = run(s, c, si, al)
        md = os.path.join(c, "2026-09-04_Sonnhalde", "index.md")
        check("meta: an aliased Site -> rc 0", rc == 0, out)
        check("meta: Site resolved through the alias",
              os.path.isfile(md)
              and "Site: bifang-säli" in open(md, encoding="utf-8").read(), out)

        # --- an unusable Site in meta.yaml is a rejection, not broken front matter ---
        s, c, si, al = setup(tmp + "/ms", {"2026-09-04_hort": [
            DOCX, ("meta.yaml", "Site: kantine\n")]})
        rc, out = run(s, c, si, al, "--allow-empty")
        check("meta: an unknown Site -> rc 1", rc == 1, out)
        check("meta: an unknown Site publishes nothing", os.listdir(c) == [], os.listdir(c))
        check("meta: an unknown Site is reported, not a crash",
              "not a site in" in out and "Traceback" not in out, out)

        # --- folder-name rejections ---
        for folder, why in (("hort", "no date"),
                            ("2026-13-45_hort", "impossible date"),
                            ("2026-09-04_kantine", "unknown location"),
                            ("2026-09-04_hort_Titel: kaputt", "yaml-hostile name")):
            s, c, si, al = setup(tmp + "/r" + folder, {folder: [DOCX]})
            rc, out = run(s, c, si, al, "--allow-empty")
            check(f"reject: {why} -> rc 1", rc == 1, out)
            check(f"reject: {why} publishes nothing", os.listdir(c) == [], os.listdir(c))

        # RULING-6: a folder whose name cannot be parsed never had a page, so the
        # report must not claim one was left as-is.
        s, c, si, al = setup(tmp + "/r6", {"hort": [DOCX]})
        rc, out = run(s, c, si, al, "--allow-empty")
        check("reject: an unparseable name does not claim a page was left as-is",
              "left as-is" not in out, out)

        # --- content rejections ---
        cases = [
            ([], "no-document"),
            ([DOCX, ("zweites.pdf", "%PDF-1.4\n")], "two-documents"),
            ([DOCX, ("notes.zip", "x")], "stray-file"),
        ]
        for files, why in cases:
            s, c, si, al = setup(os.path.join(tmp, "c-" + why),
                                 {"2026-09-04_hort": files})
            rc, out = run(s, c, si, al, "--allow-empty")
            check(f"reject: {why} -> rc 1", rc == 1, out)
            check(f"reject: {why} publishes nothing", os.listdir(c) == [], os.listdir(c))

        # --- two folders, one page name: neither is published silently ---
        s, c, si, al = setup(tmp + "/coll",
                             {"2026-09-04_hort": [DOCX], "2026-09-04_Hort": [DOCX]})
        rc, out = run(s, c, si, al, "--allow-empty")
        check("collide: rc 1", rc == 1, out)
        check("collide: neither folder is published", os.listdir(c) == [], os.listdir(c))
        check("collide: both folders are named",
              "2026-09-04_hort/" in out and "2026-09-04_Hort/" in out, out)

        # --- an image Pillow cannot read is one folder's problem, not the run's ---
        s, c, si, al = setup(tmp + "/img", {
            "2026-09-04_hort": [DOCX, ("x.jpg", "not an image")],
            "2026-09-04_sonnhalde": [DOCX]})
        rc, out = run(s, c, si, al)
        check("corrupt image: rc 1", rc == 1, out)
        check("corrupt image: the other folder in the same run still publishes",
              os.listdir(c) == ["2026-09-04_Sonnhalde"], os.listdir(c))
        check("corrupt image: the folder is named as rejected, not crashed on",
              "2026-09-04_hort/" in out and "Traceback" not in out, out)

        # --- --dry-run reports what it would do and writes nothing ---
        s, c, si, al = setup(tmp + "/dry", {"2026-09-04_hort": [DOCX]})
        rc, out = run(s, c, si, al, "--dry-run")
        check("dry-run: rc 0", rc == 0, out)
        check("dry-run: says what it would add", "would add: 2026-09-04_Hort" in out, out)
        check("dry-run: nothing written", os.listdir(c) == [], os.listdir(c))

        # --- RULING-9: a hand-made page of the same name is not overwritten, and the
        #     run must not report success ---
        s, c, si, al = setup(tmp + "/own", {"2026-09-04_hort": [DOCX]})
        os.makedirs(os.path.join(c, "2026-09-04_Hort"))
        open(os.path.join(c, "2026-09-04_Hort", "index.md"), "w",
             encoding="utf-8").write(HANDMADE)
        rc, out = run(s, c, si, al)
        check("unowned: rc 1", rc == 1, out)
        check("unowned: the hand-made page is untouched",
              open(os.path.join(c, "2026-09-04_Hort", "index.md"),
                   encoding="utf-8").read() == HANDMADE)
        check("unowned: the folder is named in the summary",
              "2026-09-04_hort" in out and "not owned" in out, out)

        # --- pandoc's backslash escapes do not reach the front matter ---
        mod = load_module()
        fm = mod.front_matter(
            types.SimpleNamespace(title=r"Titel mit {{\< a \>}} darin", author=""),
            datetime.date(2026, 9, 4), "bifang-säli",
            "Medienmitteilungen/2026-09-04_hort", {})
        check("title: pandoc's escapes are gone from the Title: line",
              'Title: "Titel mit {{< a >}} darin"' in fm, fm)

        # --- A REJECTED FOLDER MUST NOT UNPUBLISH ITS PAGE ---
        s, c, si, al = setup(tmp + "/p", {"2026-09-04_hort": [DOCX] + imgs})
        rc, out = run(s, c, si, al)
        check("protect: published first", rc == 0, out)
        open(os.path.join(s, "2026-09-04_hort", "notes.zip"), "w").close()
        rc, out = run(s, c, si, al)
        check("protect: rc 1 on the rejection", rc == 1, out)
        check("protect: the page is still there",
              os.path.isdir(os.path.join(c, "2026-09-04_Hort")), out)
        check("protect: report says it was left alone", "left as-is" in out, out)

        # --- deletion, and the wipeout guard ---
        shutil.rmtree(os.path.join(s, "2026-09-04_hort"))
        rc, out = run(s, c, si, al)
        check("guard: rc 3 on an empty set", rc == 3, out)
        check("guard: page survives", os.path.isdir(os.path.join(c, "2026-09-04_Hort")))
        rc, out = run(s, c, si, al, "--allow-empty")
        check("delete: rc 0 with --allow-empty", rc == 0, out)
        check("delete: page removed", not os.path.exists(os.path.join(c, "2026-09-04_Hort")))

        # --- an EMPTY staged folder is what an over-25M upload looks like ---
        # rclone's --max-size drops the files; --create-empty-src-dirs in
        # sync-medienmitteilungen.yaml is what keeps the folder itself, so the
        # syncer can tell "too big to fetch" from "withdrawn". Empty means "I cannot
        # read this", so it is inert -- the page must survive, and the run go red.
        s, c, si, al = setup(tmp + "/big", {"2026-09-04_hort": [DOCX] + imgs})
        rc, out = run(s, c, si, al)
        check("oversized: published first", rc == 0, out)
        for n in os.listdir(os.path.join(s, "2026-09-04_hort")):
            os.remove(os.path.join(s, "2026-09-04_hort", n))
        rc, out = run(s, c, si, al)
        check("oversized: an empty folder is rejected, not treated as a withdrawal",
              rc == 1 and "no .docx or .pdf found" in out, (rc, out))
        check("oversized: the published page is left exactly as it was",
              os.path.isdir(os.path.join(c, "2026-09-04_Hort"))
              and "remove:" not in out, out)
        check("oversized: the report says the page was left alone",
              "left as-is" in out, out)

        # --- an NFD folder name, which is what macOS and iOS hand out ---
        # 'ä' as 'a' + U+0308. TOKEN_RE's [^\W_] does not match a combining mark,
        # so the author saw their exactly-correct folder name quoted back as
        # "unusable" with nothing on screen to show what differed -- and the
        # Anleitung teaches this very name and expects iPhone users.
        nfd = unicodedata.normalize("NFD", "2026-09-04_Bifang-Säli_Eroeffnung")
        check("nfd: the fixture name really is decomposed",
              nfd != unicodedata.normalize("NFC", nfd) and "̈" in nfd, nfd)
        s, c, si, al = setup(tmp + "/nfd", {nfd: [DOCX]})
        rc, out = run(s, c, si, al)
        check("nfd: accepted, not reported as unusable", rc == 0, out)
        want = unicodedata.normalize("NFC", "2026-09-04_Bifang-Säli_Eroeffnung")
        check("nfd: the page directory is composed, so the URL is stable",
              os.listdir(c) == [want], os.listdir(c))
        index = open(os.path.join(c, want, "index.md"), encoding="utf-8").read()
        check("nfd: the SyncedFrom marker is composed too",
              f"SyncedFrom: Medienmitteilungen/{want}" in index,
              [l for l in index.splitlines() if l.startswith("SyncedFrom")])
        check("nfd: the Site resolved through the alias map",
              "Site: bifang-säli" in index,
              [l for l in index.splitlines() if l.startswith("Site")])

        # meta.yaml's Site: goes through the same normalisation
        s, c, si, al = setup(tmp + "/nfdmeta", {"2026-09-04_hort": [
            DOCX, ("meta.yaml", "Site: "
                   + unicodedata.normalize("NFD", "Bifang-Säli") + "\n")]})
        rc, out = run(s, c, si, al)
        check("nfd: a decomposed meta.yaml Site: resolves", rc == 0, out)

        # a site key that is itself decomposed in data/sites.yaml
        s, c, si, al = setup(tmp + "/nfdsites", {"2026-09-04_bifang-säli": [DOCX]})
        open(si, "w", encoding="utf-8").write(unicodedata.normalize("NFD", SITES))
        rc, out = run(s, c, si, al)
        check("nfd: a decomposed key in data/sites.yaml still matches", rc == 0, out)

        # --- one non-UTF-8 index.md must not kill the whole sync ---
        # content/blog/ holds ~19 hand-made posts no syncer wrote. A
        # UnicodeDecodeError in read_marker escapes the CLI's caught-exception
        # tuple, and it exits 1 -- which the workflow reads as "applied with
        # rejections, commit anyway" and proceeds to build, commit and dispatch on
        # a traceback.
        s, c, si, al = setup(tmp + "/latin1", {"2026-09-04_hort": [DOCX]})
        os.makedirs(os.path.join(c, "alt-post"))
        with open(os.path.join(c, "alt-post", "index.md"), "wb") as fh:
            fh.write('---\nTitle: "Grüezi mitenand"\nDate: 2026-01-01\n---\n\ntext\n'
                     .encode("latin-1"))
        rc, out = run(s, c, si, al)
        check("latin-1: the sync survives a post it cannot decode",
              rc == 0 and "Traceback" not in out, out)
        check("latin-1: the synced page still published",
              os.path.isdir(os.path.join(c, "2026-09-04_Hort")), os.listdir(c))
        check("latin-1: the undecodable post is left alone",
              os.path.isfile(os.path.join(c, "alt-post", "index.md")))
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
