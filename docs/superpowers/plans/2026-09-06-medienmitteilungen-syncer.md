# Medienmitteilungen Syncer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a press-release folder dropped into OpenCloud's `Medienmitteilungen/` into a Hugo page bundle under `content/blog/`, kept as a full mirror.

**Architecture:** Three Python modules with one seam each. `medien_convert.py` turns a `.docx`/`.pdf` plus loose photos into Markdown and images (pure — no repo, no network). `blog_mirror.py` creates, updates and deletes page bundles under `content/blog/`, owning only those whose front matter carries a `SyncedFrom` under its source prefix. `apply-medien-sync.py` is the CLI glue: folder-name grammar, `meta.yaml`, front matter. A GitHub Actions workflow fetches with rclone, applies, builds, commits, and dispatches the deploy.

**Tech Stack:** Python 3 (stdlib, plus Pillow + numpy for de-duplication only), pandoc, poppler-utils, rclone, Hugo, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-06-opencloud-medienmitteilungen-sync-design.md`

**Companion plan:** `docs/superpowers/plans/2026-09-06-medien-dispatcher.md` (the `oep-k8s` side). This plan ships working software without it — the workflow runs on its cron and on manual dispatch.

## Global Constraints

- Python 3, stdlib only, **except** Pillow and numpy in `medien_convert.py` for perceptual de-duplication. No PyYAML: parse the flat `meta.yaml` and `data/*.yaml` with regexes, as `validate-stellen-filenames.py` already does.
- Exit codes, identical to `apply-stellen-sync.py`: **0** clean · **1** applied but something was rejected · **2** could not run, repository untouched · **3** wipeout guard tripped.
- Ownership marker: `SyncedFrom: <OpenCloud path>` in the generated front matter. Update and delete consider **only** bundles whose marker equals the source prefix or starts with `<prefix>/`.
- **A rejected folder is inert** — never created, never updated, never deleted.
- Source prefix for this syncer: `Medienmitteilungen`.
- Address-block detection: `^\d{4}\s+[A-ZÄÖÜ]` against each line of a paragraph (Python `re` has no `\p{Lu}`).
- Front-matter keys are CamelCase, matching existing posts: `Title`, `TeaserTitle`, `Autor`, `Date`, `Site`, `SyncedFrom`.
- Tests are plain self-checking scripts run as `python3 scripts/test-<name>.py`, printing `ok`/`FAIL` per check and exiting non-zero on any failure. No pytest.

## File Structure

| File | Responsibility |
|---|---|
| `data/medienmitteilungen.yaml` | Folder-name tokens that aren't keys in `data/sites.yaml` |
| `scripts/blog_mirror.py` | Marker ownership, create/update/delete over `content/blog/`, wipeout guard |
| `scripts/medien_convert.py` | Document → Markdown; image pool, filter, dedup, teaser/gallery |
| `scripts/apply-medien-sync.py` | CLI: folder grammar, `meta.yaml`, front matter, report |
| `scripts/test-blog-mirror.py` | Unit tests for the mirror (importable module) |
| `scripts/test-medien-convert.py` | Unit tests for conversion, incl. the real-document fixture |
| `scripts/test-apply-medien-sync.py` | End-to-end tests, script run as a subprocess |
| `scripts/fixtures/medien/` | The real `.docx` + 13 downscaled JPEGs (~1.4 MB) |
| `.github/workflows/sync-medienmitteilungen.yaml` | The sync workflow |
| `.github/workflows/test-scripts.yaml` | Runs every `scripts/test-*.py` in CI |
| `.github/workflows/sync-stellen.yaml` | **Modified**: shared concurrency group |
| `docs/medienmitteilungen-anleitung.md` | Author-facing instructions (German) |

---

### Task 1: Marker ownership and bundle creation

**Files:**
- Create: `scripts/blog_mirror.py`
- Test: `scripts/test-blog-mirror.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `read_marker(bundle_dir) -> str|None`, `owned(bundle_dir, prefix) -> bool`, `apply(desired, content_dir, prefix, protected=(), dry_run=False, allow_empty=False) -> (list[str], int)`. `desired` is `{target_dir_name: staged_bundle_path}`; the staged bundle already contains `index.md`, optional `teaser.*` and optional `gallery/`.

- [ ] **Step 1: Write the failing test**

Create `scripts/test-blog-mirror.py`:

```python
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
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 scripts/test-blog-mirror.py`
Expected: `ModuleNotFoundError: No module named 'blog_mirror'`

- [ ] **Step 3: Write the minimal implementation**

Create `scripts/blog_mirror.py`:

```python
#!/usr/bin/env python3
"""Mirror generated Hugo page bundles into content/blog/.

content/blog/ is NOT owned wholesale by any syncer -- it holds hand-made posts that
predate every one of them. So a bundle is only ever updated or deleted here when its
front matter carries a SyncedFrom marker naming a path under the caller's source
prefix.

Prefix, not merely presence: a second syncer (Geschichten/) writes into this same
directory, and "has a marker" would make each run delete the other's work.
"""

import filecmp
import os
import re
import shutil

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
MARKER_RE = re.compile(r"^SyncedFrom:\s*(.+?)\s*$", re.M)


def read_marker(bundle_dir):
    """The bundle's SyncedFrom value, or None if it has none."""
    try:
        with open(os.path.join(bundle_dir, "index.md"), encoding="utf-8") as fh:
            head = fh.read(8192)
    except OSError:
        return None
    fm = FRONT_MATTER_RE.match(head)
    if not fm:
        return None
    m = MARKER_RE.search(fm.group(1))
    return m.group(1) if m else None


def owned(bundle_dir, prefix):
    """True when this bundle was generated by the syncer for `prefix`."""
    marker = read_marker(bundle_dir)
    if marker is None:
        return False
    return marker == prefix or marker.startswith(prefix + "/")


def _generated(root):
    """Relative paths of the files a syncer generates, so an update can prune them."""
    out = set()
    if not os.path.isdir(root):
        return out
    for name in os.listdir(root):
        if name == "index.md" or name.startswith("teaser."):
            out.add(name)
    gallery = os.path.join(root, "gallery")
    if os.path.isdir(gallery):
        out.update("gallery/" + n for n in os.listdir(gallery))
    return out


def _sync_bundle(src, dst, dry_run):
    """Make dst's generated files match src's. Returns True if anything changed."""
    changed = False
    want = _generated(src)
    for rel in sorted(want):
        s, d = os.path.join(src, rel), os.path.join(dst, rel)
        if os.path.isfile(d) and filecmp.cmp(s, d, shallow=False):
            continue
        changed = True
        if not dry_run:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
    for rel in sorted(_generated(dst) - want):
        changed = True
        if not dry_run:
            os.remove(os.path.join(dst, rel))
    return changed


def apply(desired, content_dir, prefix, protected=(), dry_run=False, allow_empty=False):
    """Make content_dir match `desired` for bundles owned by `prefix`.

    desired    {target directory name: staged bundle path}
    protected  target names whose source folder was REJECTED. They are neither
               updated nor deleted -- rejection means "I cannot read this", which is
               not the same claim as "this was withdrawn".

    Returns (report lines, exit status): 0 clean, 3 wipeout guard tripped.
    """
    lines = []
    protected = set(protected)

    current = {}
    for name in sorted(os.listdir(content_dir)):
        path = os.path.join(content_dir, name)
        if os.path.isdir(path) and owned(path, prefix):
            current[name] = path

    if not desired and current and not allow_empty:
        lines.append(
            f"refusing to remove all {len(current)} synced page(s): the validated set "
            "is empty.\nThis is what an expired token or a WebDAV outage looks like. "
            "If the last page really\nis being withdrawn, re-run with --allow-empty."
        )
        return lines, 3

    prefix_word = "would " if dry_run else ""

    for name, src in sorted(desired.items()):
        dst = os.path.join(content_dir, name)
        if os.path.isdir(dst) and not owned(dst, prefix):
            lines.append(f"exists, not owned -- skipped: {name}")
            continue
        if not os.path.isdir(dst):
            lines.append(f"{prefix_word}add: {name}")
            if not dry_run:
                shutil.copytree(src, dst)
            continue
        if _sync_bundle(src, dst, dry_run):
            lines.append(f"{prefix_word}update: {name}")

    for name in sorted(set(current) - set(desired) - protected):
        lines.append(f"{prefix_word}remove: {name}")
        if not dry_run:
            shutil.rmtree(os.path.join(content_dir, name))

    if not lines:
        lines.append("no changes")
    return lines, 0
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 scripts/test-blog-mirror.py`
Expected: every check `ok`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/blog_mirror.py scripts/test-blog-mirror.py
git commit -m "Blog mirror: own only bundles marked with our own source prefix"
```

---

### Task 2: Update, delete, wipeout guard and rejection protection

**Files:**
- Modify: `scripts/test-blog-mirror.py` (add cases to `main()`, before the final `print()`)
- Test: `scripts/test-blog-mirror.py`

**Interfaces:**
- Consumes: `blog_mirror.apply` from Task 1.
- Produces: no new functions — this task proves the branches Task 1 wrote.

- [ ] **Step 1: Write the failing tests**

Insert into `main()` in `scripts/test-blog-mirror.py`, immediately before the `finally:`:

```python
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
```

- [ ] **Step 2: Run the tests**

Run: `python3 scripts/test-blog-mirror.py`
Expected: all `ok`. Task 1's implementation already covers these branches; if any fail, fix `blog_mirror.py` — do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add scripts/test-blog-mirror.py
git commit -m "Blog mirror: cover update, delete, the wipeout guard and rejection protection"
```

---

### Task 3: Document text shaping

**Files:**
- Create: `scripts/medien_convert.py`
- Create: `scripts/test-medien-convert.py`
- Create: `scripts/fixtures/medien/20260904_MM_EröffnungHort.docx` (copied from the sample)
- Create: `scripts/fixtures/medien/IMG_*.jpeg` (13 files, downscaled to 400px wide)

**Interfaces:**
- Consumes: nothing.
- Produces: `ConversionError`, `shape_document(text, bold_aware=True) -> (title, blocks, caption, image_at)` where `blocks` is a list of Markdown strings, `caption` is `str|None`, and `image_at` is the index in `blocks` where the document's image sat (`None` if it had none).

- [ ] **Step 1: Build the fixtures**

The real folder is at `/scratch/zaucker/2026-09-04_hort/`. The 13 JPEGs total ~10 MB, which is too much to commit; downscaling them to 400px wide costs ~535 KB and *widens* the de-duplication margin (verified: 0.0089 for the true twin vs 0.9189 for the next-nearest).

```bash
mkdir -p scripts/fixtures/medien
cp "/scratch/zaucker/2026-09-04_hort/20260904_MM_EröffnungHort.docx" scripts/fixtures/medien/
python3 - <<'PY'
from PIL import Image
import glob, os
for f in sorted(glob.glob('/scratch/zaucker/2026-09-04_hort/IMG_*.jpeg')):
    im = Image.open(f); w, h = im.size
    im.resize((400, round(400 * h / w)), Image.LANCZOS).save(
        os.path.join('scripts/fixtures/medien', os.path.basename(f)), 'JPEG', quality=82)
    print(os.path.basename(f))
PY
du -sh scripts/fixtures/medien
```

Expected: 14 files, roughly 1.4 MB in total.

- [ ] **Step 2: Write the failing test**

Create `scripts/test-medien-convert.py`:

```python
#!/usr/bin/env python3
"""Tests for medien_convert.py.  Run with:  python3 scripts/test-medien-convert.py"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "medien")
DOCX = os.path.join(FIXTURES, "20260904_MM_EröffnungHort.docx")
sys.path.insert(0, HERE)
import medien_convert  # noqa: E402

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


SAMPLE = """**MEDIENMITTEILUNG**

**Schülerhort Bifang-Säli startet erfolgreich – freie Plätze verfügbar**

**Seit Anfang August bietet der Verein ein Betreuungsangebot an.**

An der Eröffnung nahmen unter anderem Stadtpräsident Thomas Marbet teil.

**Erfolgreicher Start**

Der Betrieb ist erfreulich angelaufen.

**Hort Bifang-Säli**\\
Reiserstrasse 91\\
4600 Olten\\
Telefon 062 526 85 13

![](/tmp/media/image1.jpeg){width="6.29in" height="4.23in"}

Bildlegende: Die Verantwortlichen eröffnen den Hort (Foto: Melanie von Arx)
"""


def main():
    title, blocks, caption, image_at = medien_convert.shape_document(SAMPLE)

    check("title taken from the first block after the label",
          title == "Schülerhort Bifang-Säli startet erfolgreich – freie Plätze verfügbar", title)
    check("MEDIENMITTEILUNG label dropped",
          not any("MEDIENMITTEILUNG" in b for b in blocks), blocks)
    check("lead paragraph stays bold",
          blocks[0] == "**Seit Anfang August bietet der Verein ein Betreuungsangebot an.**", blocks[0])
    check("later bold block becomes a sub-heading",
          "## Erfolgreicher Start" in blocks, blocks)
    check("address block dropped",
          not any("Reiserstrasse" in b for b in blocks), blocks)
    check("telephone line went with the address",
          not any("062 526" in b for b in blocks), blocks)
    check("caption extracted without its prefix",
          caption == "Die Verantwortlichen eröffnen den Hort (Foto: Melanie von Arx)", caption)
    check("image position recorded", image_at == 3, (image_at, blocks))
    check("image markdown not left in the body",
          not any(b.startswith("![") for b in blocks), blocks)

    # a body sentence naming a postcode must NOT be mistaken for the address
    t, b, _, _ = medien_convert.shape_document(
        "**Titel**\n\nDer Hort liegt in 4600 Olten und ist gut erreichbar.\n")
    check("postcode inside a sentence survives",
          any("4600 Olten" in x for x in b), b)

    # shortcode delimiters are escaped
    t, b, _, _ = medien_convert.shape_document(
        "**Titel**\n\nWir schreiben {{< stellen >}} in den Text.\n")
    check("'{{' escaped", "&#123;&#123;" in b[0] and "{{<" not in b[0], b)

    # a document that is nothing but a title
    t, b, c, i = medien_convert.shape_document("**Nur ein Titel**\n")
    check("title-only document", (t, b, c, i) == ("Nur ein Titel", [], None, None), (t, b, c, i))

    # an empty document is a ConversionError, not a crash
    try:
        medien_convert.shape_document("")
        check("empty document rejected", False, "no exception")
    except medien_convert.ConversionError:
        check("empty document rejected", True)

    # the real document, through pandoc
    import tempfile as _tf
    _media = _tf.mkdtemp(prefix="medien-test-")
    text = medien_convert.docx_to_markdown(DOCX, _media)
    title, blocks, caption, image_at = medien_convert.shape_document(text)
    check("real docx: title",
          title.startswith("Schülerhort Bifang-Säli startet erfolgreich"), title)
    check("real docx: en-dash preserved", "–" in title, title)
    check("real docx: three sub-headings",
          sum(1 for b in blocks if b.startswith("## ")) == 3,
          [b for b in blocks if b.startswith("## ")])
    check("real docx: address gone",
          not any("Reiserstrasse" in b for b in blocks), blocks)
    check("real docx: caption found",
          caption is not None and caption.startswith("Die Verantwortlichen"), caption)

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `python3 scripts/test-medien-convert.py`
Expected: `ModuleNotFoundError: No module named 'medien_convert'`

- [ ] **Step 4: Write the minimal implementation**

Create `scripts/medien_convert.py`:

```python
#!/usr/bin/env python3
"""Turn a press-release .docx or .pdf, plus the photos beside it, into a Hugo page body.

Pure with respect to the repository: it reads a document and a list of image paths and
writes into a destination directory. It knows nothing about git, content/blog/ or
OpenCloud.

Conversion must be DETERMINISTIC -- the mirror detects change by regenerating and
comparing bytes. That is why the workflow pins pandoc by version and checksum.
"""

import os
import re
import subprocess

# A paragraph that is one single bold run: the title, the lead, a sub-heading.
BOLD_RE = re.compile(r"\A\*\*(.+)\*\*\Z", re.S)
# Pandoc renders an image as ![alt](path) with optional {width=... height=...}
# attributes, which Goldmark does not understand -- so the whole block is replaced
# by a blog-pic shortcode rather than passed through.
IMAGE_RE = re.compile(r"\A!\[[^\]]*\]\(([^)]+)\)(?:\{[^}]*\})?\Z", re.S)
# Swiss postcode + town. Spelled out rather than \p{Lu}: Python's re has no
# Unicode property classes.
ADDRESS_RE = re.compile(r"^\d{4}\s+[A-ZÄÖÜ]")
CAPTION_PREFIX = "bildlegende:"
LABEL = "MEDIENMITTEILUNG"


class ConversionError(Exception):
    """The document cannot be published. The message is shown to the author."""


def docx_to_markdown(path, media_dir):
    """Pandoc's Markdown for a .docx, with body images extracted into media_dir.

    markdown-smart, not markdown: the plain writer turns the document's en-dash into
    '--', and every other post on this site carries a real en-dash.
    """
    return subprocess.run(
        ["pandoc", "-f", "docx", "-t", "markdown-smart", "--wrap=none",
         f"--extract-media={media_dir}", path],
        capture_output=True, text=True, check=True,
    ).stdout


def _blocks(text):
    return [b.strip("\n") for b in re.split(r"\n[ \t]*\n", text.strip()) if b.strip()]


def _bold_inner(block):
    """The text inside a wholly-bold paragraph, or None."""
    m = BOLD_RE.match(block.strip())
    if not m or "**" in m.group(1):
        return None
    return m.group(1).strip()


def _plain(block):
    inner = _bold_inner(block)
    return inner if inner is not None else block.strip()


def _is_address(block):
    """A paragraph carrying a postcode line.

    --wrap=none puts a paragraph on one line and renders in-paragraph hard breaks as a
    trailing backslash, so the address arrives as one block of backslash-separated
    lines. Testing each line rather than the whole block keeps a body sentence that
    merely mentions '4600 Olten' from being mistaken for it.
    """
    for line in block.split("\n"):
        if ADDRESS_RE.match(line.rstrip("\\").strip().strip("*").strip()):
            return True
    return False


def _escape(text):
    """Hugo evaluates shortcodes in page content before Markdown ever runs.

    An unescaped '{{<' in a press release fails the whole site build -- not just this
    page -- and the error names content/blog/ rather than the document it came from.
    """
    return text.replace("{{", "&#123;&#123;")


def shape_document(text, bold_aware=True):
    """(title, body blocks, caption, index in blocks where the image sat).

    bold_aware=False for PDF, which carries no bold: everything becomes a paragraph.
    """
    blocks = _blocks(text)
    if blocks and _plain(blocks[0]).upper() == LABEL:
        blocks.pop(0)
    if not blocks:
        raise ConversionError("the document has no text")

    title = _plain(blocks.pop(0))
    body, caption, image_at = [], None, None

    for block in blocks:
        if IMAGE_RE.match(block.strip()):
            image_at = len(body)
            continue
        if _is_address(block):
            continue
        plain = _plain(block)
        if plain.lower().startswith(CAPTION_PREFIX):
            caption = plain[len(CAPTION_PREFIX):].strip()
            continue
        inner = _bold_inner(block) if bold_aware else None
        if inner is None:
            body.append(_escape(block))
        elif not body:
            body.append("**" + _escape(inner) + "**")   # the lead paragraph
        else:
            body.append("## " + _escape(inner))          # a sub-heading
    return title, body, caption, image_at
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `python3 scripts/test-medien-convert.py`
Expected: every check `ok`, exit 0. `pandoc` must be on `PATH` (`mise exec -- pandoc --version` or the system one).

- [ ] **Step 6: Commit**

```bash
git add scripts/medien_convert.py scripts/test-medien-convert.py scripts/fixtures/medien
git commit -m "Medien convert: shape a press-release document into Markdown blocks"
```

---

### Task 4: Image pool, de-duplication, teaser and gallery

**Files:**
- Modify: `scripts/medien_convert.py`
- Modify: `scripts/test-medien-convert.py`

**Interfaces:**
- Consumes: `shape_document` from Task 3.
- Produces: `select_images(doc_images, loose_images, threshold=0.15, min_pixels=40000) -> (teaser_path|None, [gallery_paths])`, `signature(path)`, `distance(a, b)`.

- [ ] **Step 1: Write the failing test**

Add to `main()` in `scripts/test-medien-convert.py`, before the final `print()`:

```python
    # --- de-duplication against the real folder ---
    import glob
    import zipfile
    import tempfile
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(DOCX) as z:
        embedded = [z.extract(n, tmp) for n in z.namelist() if n.startswith("word/media/")]
    loose = sorted(glob.glob(os.path.join(FIXTURES, "IMG_*.jpeg")))
    check("fixture has 13 loose images", len(loose) == 13, len(loose))
    check("document embeds exactly one image", len(embedded) == 1, embedded)

    teaser, gallery = medien_convert.select_images(embedded, loose)
    check("teaser is the document's own image",
          os.path.basename(teaser) == "image1.jpeg", teaser)
    check("gallery drops the duplicate: 12 not 13", len(gallery) == 12, len(gallery))
    check("IMG_0090 recognised as the same photo",
          not any("IMG_0090" in g for g in gallery),
          [os.path.basename(g) for g in gallery])
    check("gallery is filename-ordered",
          gallery == sorted(gallery, key=os.path.basename), gallery)

    # the margin is wide, not marginal -- guard against a future "simplification"
    sig_emb = medien_convert.signature(embedded[0])
    twin = next(g for g in loose if "IMG_0090" in g)
    other = next(g for g in loose if "IMG_0108" in g)
    d_twin = medien_convert.distance(sig_emb, medien_convert.signature(twin))
    d_other = medien_convert.distance(sig_emb, medien_convert.signature(other))
    check("twin distance well under threshold", d_twin < 0.05, d_twin)
    check("next-nearest well over threshold", d_other > 0.5, d_other)

    # exact comparison provably cannot do this job
    import hashlib
    h = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()
    check("duplicate is NOT byte-identical", h(embedded[0]) != h(twin))

    # a logo below the area floor is filtered out
    from PIL import Image
    logo = os.path.join(tmp, "logo.png")
    Image.new("RGB", (300, 100), "white").save(logo)
    teaser2, gallery2 = medien_convert.select_images([embedded[0], logo], loose)
    check("small logo filtered from the pool",
          not any("logo" in g for g in gallery2), gallery2)

    # no document image at all: the first pooled image becomes the teaser
    teaser3, gallery3 = medien_convert.select_images([], loose)
    check("teaser falls back to the first loose image",
          os.path.basename(teaser3) == "IMG_0083.jpeg", teaser3)
    check("fallback teaser is not also in the gallery",
          teaser3 not in gallery3 and len(gallery3) == 12, len(gallery3))

    # nothing at all
    check("no images at all is allowed", medien_convert.select_images([], []) == (None, []))

    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 scripts/test-medien-convert.py`
Expected: `AttributeError: module 'medien_convert' has no attribute 'select_images'`

- [ ] **Step 3: Write the minimal implementation**

Append to `scripts/medien_convert.py`:

```python
# --- images ---------------------------------------------------------------
#
# Every image is a candidate, from both sources: embedded in the document and loose
# beside it. The author normally puts the same photo in both places, so the pool has
# to be de-duplicated -- and the duplicate is NEVER byte-identical, because Word and
# PDF re-encode and rescale on the way in. Measured on the sample folder:
#
#   word/media/image1.jpeg  1385x931  md5 5800d062...
#   IMG_0090.jpeg           1280x860  md5 120b34a0...   the same photograph
#
# so md5/filecmp cannot find it. A normalised 16x16 luminance signature can, and not
# marginally: the true twin scores 0.0089 while the next-nearest of the other twelve
# scores 0.9189. Do not "simplify" this to a hash -- it would ship the same photo
# twice on every page.
DEDUP_THRESHOLD = 0.15
# Removes letterhead logos, bullets and rules. A 300x100 logo is 30,000 px.
MIN_PIXELS = 200 * 200


def signature(path, n=16):
    from PIL import Image
    import numpy as np
    grey = Image.open(path).convert("L").resize((n, n), Image.LANCZOS)
    a = np.asarray(grey, dtype=float)
    return (a - a.mean()) / (a.std() + 1e-6)


def distance(a, b):
    import numpy as np
    return float(np.abs(a - b).mean())


def _pixels(path):
    from PIL import Image
    w, h = Image.open(path).size
    return w * h


def select_images(doc_images, loose_images, threshold=DEDUP_THRESHOLD,
                  min_pixels=MIN_PIXELS):
    """(teaser, gallery) from the document's images and the loose files.

    The teaser is the document's own image -- the one the author placed beside the
    text and the one the Bildlegende describes. Where a loose file is the same photo,
    the larger copy survives and the other is not repeated in the gallery.
    """
    docs = [p for p in doc_images if _pixels(p) >= min_pixels]
    loose = [p for p in loose_images if _pixels(p) >= min_pixels]
    sigs = {p: signature(p) for p in docs + loose}

    teaser = docs[0] if docs else None
    gallery = []
    for p in loose:
        twin = next((d for d in docs if distance(sigs[p], sigs[d]) < threshold), None)
        if twin is None:
            gallery.append(p)
        elif twin == teaser and _pixels(p) > _pixels(twin):
            teaser = p          # keep the higher-resolution copy of the same photo
    gallery.extend(d for d in docs[1:] if d != teaser)

    if teaser is None and gallery:
        teaser = gallery.pop(0)
    gallery.sort(key=os.path.basename)
    return teaser, gallery
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 scripts/test-medien-convert.py`
Expected: every check `ok`. Needs `python3-pil` and `python3-numpy`.

- [ ] **Step 5: Commit**

```bash
git add scripts/medien_convert.py scripts/test-medien-convert.py
git commit -m "Medien convert: pool and de-duplicate images perceptually"
```

---

### Task 5: PDF input and bundle assembly

**Files:**
- Modify: `scripts/medien_convert.py`
- Modify: `scripts/test-medien-convert.py`

**Interfaces:**
- Consumes: `shape_document`, `select_images` from Tasks 3-4.
- Produces: `convert(doc_path, loose_images, out_dir) -> Bundle`, a namedtuple with fields `title` (str), `author` (str|None), `body` (str, the Markdown body without front matter), `teaser` (filename in `out_dir`, or None), `gallery` (list of filenames under `out_dir/gallery/`), `warnings` (list of str). Raises `ConversionError`.

- [ ] **Step 1: Write the failing test**

Add to `main()` in `scripts/test-medien-convert.py`, before the final `print()`:

```python
    # --- full bundle assembly from the real document ---
    out = tempfile.mkdtemp()
    b = medien_convert.convert(DOCX, loose, out)
    check("bundle: title", b.title.startswith("Schülerhort Bifang-Säli"), b.title)
    check("bundle: author from docProps", b.author == "Melanie von Arx", b.author)
    check("bundle: teaser written", b.teaser == "teaser.jpeg", b.teaser)
    check("bundle: teaser on disk", os.path.isfile(os.path.join(out, "teaser.jpeg")))
    check("bundle: 12 gallery files", len(b.gallery) == 12, len(b.gallery))
    check("bundle: gallery on disk",
          len(os.listdir(os.path.join(out, "gallery"))) == 12)
    check("bundle: blog-pic uses the real extension",
          '{{< blog-pic src="teaser.jpeg"' in b.body, b.body[:400])
    check("bundle: caption is the shortcode's inner text",
          "Die Verantwortlichen eröffnen den Hort" in b.body)
    check("bundle: slider appended",
          b.body.rstrip().endswith('{{< picture-slider dir="gallery" height="250px" >}}'),
          b.body[-200:])
    check("bundle: heading emitted once",
          b.body.count("# Schülerhort Bifang-Säli") == 1, b.body[:200])
    _sh.rmtree(out, ignore_errors=True)

    # no caption -> explicit alt, never an empty one
    body = medien_convert.assemble_body("Titel", ["Ein Absatz."], None, 0, "teaser.jpg", [])
    check("no caption: alt falls back to the title",
          'alt="Titel"' in body, body)

    # no images at all: no shortcodes
    body = medien_convert.assemble_body("Titel", ["Ein Absatz."], None, None, None, [])
    check("no images: no blog-pic", "blog-pic" not in body, body)
    check("no images: no slider", "picture-slider" not in body, body)

    # --- PDF input ---
    pdf = os.path.join(tempfile.mkdtemp(), "mm.pdf")
    subprocess.run(["pandoc", "-f", "docx", "-o", pdf, DOCX], check=True)
    out = tempfile.mkdtemp()
    b = medien_convert.convert(pdf, [], out)
    check("pdf: title recovered", "Schülerhort" in b.title, b.title)
    check("pdf: body has text", "Eröffnung" in b.body, b.body[:200])
    check("pdf: no sub-headings, and it says so",
          any("no bold" in w for w in b.warnings), b.warnings)
    _sh.rmtree(out, ignore_errors=True)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 scripts/test-medien-convert.py`
Expected: `AttributeError: module 'medien_convert' has no attribute 'convert'`

- [ ] **Step 3: Write the minimal implementation**

Append to `scripts/medien_convert.py`:

```python
# --- PDF ------------------------------------------------------------------

def pdf_to_text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"],
                          capture_output=True, text=True, check=True).stdout


def pdf_images(path, out_dir):
    """Extract only the real photographs from a PDF, in page order.

    `pdfimages -list` reports every image XObject, and a single visible photo is
    routinely more than one of them: a JPEG with transparency is stored as the image
    PLUS its soft mask, and large images are split into bands. The `type` column
    distinguishes 'image' from 'smask' and 'stencil' exactly -- a pixel-area floor
    cannot, because a mask has the same dimensions as the image it belongs to.
    """
    listing = subprocess.run(["pdfimages", "-list", path],
                             capture_output=True, text=True, check=True).stdout
    keep = set()
    for line in listing.splitlines()[2:]:
        fields = line.split()
        if len(fields) > 2 and fields[2] == "image":
            keep.add(int(fields[1]))
    root = os.path.join(out_dir, "pdfimg")
    subprocess.run(["pdfimages", "-all", path, root], check=True)
    found = []
    for name in sorted(os.listdir(out_dir)):
        m = re.match(r"pdfimg-(\d+)\.", name)
        if m and int(m.group(1)) in keep:
            found.append(os.path.join(out_dir, name))
    return found


# --- metadata -------------------------------------------------------------

def document_author(path):
    """The author recorded by the tool that produced the document, or None."""
    if path.lower().endswith(".docx"):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                core = z.read("docProps/core.xml").decode("utf-8", "replace")
        except (KeyError, OSError):
            return None
        m = re.search(r"<dc:creator>(.*?)</dc:creator>", core, re.S)
        return (m.group(1).strip() or None) if m else None
    info = subprocess.run(["pdfinfo", path], capture_output=True, text=True).stdout
    m = re.search(r"^Author:\s*(.+?)\s*$", info, re.M)
    return m.group(1) if m else None


# --- assembly -------------------------------------------------------------

import collections  # noqa: E402

Bundle = collections.namedtuple(
    "Bundle", "title author body teaser gallery warnings")


def assemble_body(title, blocks, caption, image_at, teaser_name, gallery_names):
    """The Markdown body: heading, prose, the teaser figure, then the slider."""
    parts = list(blocks)
    if teaser_name and image_at is not None:
        if caption:
            figure = (f'{{{{< blog-pic src="{teaser_name}" >}}}}\n'
                      f'{caption}\n'
                      f'{{{{< /blog-pic >}}}}')
        else:
            # blog-pic.html derives alt from its inner text; with no Bildlegende that
            # would be empty, so name the alt explicitly.
            figure = (f'{{{{< blog-pic src="{teaser_name}" alt="{title}" >}}}}'
                      f'{{{{< /blog-pic >}}}}')
        parts.insert(min(image_at, len(parts)), figure)
    if gallery_names:
        parts.append('{{< picture-slider dir="gallery" height="250px" >}}')
    return f"# {title}\n\n" + "\n\n".join(parts) + "\n"


def convert(doc_path, loose_images, out_dir):
    """Build a page bundle in out_dir. Raises ConversionError if it cannot."""
    import shutil
    import tempfile

    warnings = []
    work = tempfile.mkdtemp(prefix="medien-")
    try:
        if doc_path.lower().endswith(".docx"):
            text = docx_to_markdown(doc_path, work)
            media = os.path.join(work, "media")
            doc_images = ([os.path.join(media, n) for n in sorted(os.listdir(media))]
                          if os.path.isdir(media) else [])
            bold_aware = True
        else:
            text = pdf_to_text(doc_path)
            doc_images = pdf_images(doc_path, work)
            bold_aware = False
            warnings.append(
                "PDF input: a PDF carries no bold, so there are no sub-headings and no "
                "lead paragraph. Upload the .docx to get those.")

        title, blocks, caption, image_at = shape_document(text, bold_aware=bold_aware)
        teaser_src, gallery_src = select_images(doc_images, loose_images)

        teaser_name = None
        if teaser_src:
            teaser_name = "teaser" + os.path.splitext(teaser_src)[1].lower()
            shutil.copy2(teaser_src, os.path.join(out_dir, teaser_name))

        gallery_names = []
        if gallery_src:
            os.makedirs(os.path.join(out_dir, "gallery"), exist_ok=True)
            for src in gallery_src:
                name = os.path.basename(src)
                shutil.copy2(src, os.path.join(out_dir, "gallery", name))
                gallery_names.append(name)

        if teaser_name is None:
            warnings.append(
                "no usable image: the page will render without a teaser and Hugo will "
                "warn at build time.")

        body = assemble_body(title, blocks, caption, image_at, teaser_name, gallery_names)
        return Bundle(title, document_author(doc_path), body,
                      teaser_name, gallery_names, warnings)
    finally:
        shutil.rmtree(work, ignore_errors=True)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 scripts/test-medien-convert.py`
Expected: every check `ok`. Needs `pandoc`, `pdftotext`, `pdfimages` and `pdfinfo` on `PATH`.

- [ ] **Step 5: Commit**

```bash
git add scripts/medien_convert.py scripts/test-medien-convert.py
git commit -m "Medien convert: PDF input, document metadata and bundle assembly"
```

---

### Task 6: The CLI — folder grammar, meta.yaml, front matter

**Files:**
- Create: `data/medienmitteilungen.yaml`
- Create: `scripts/apply-medien-sync.py`
- Create: `scripts/test-apply-medien-sync.py`

**Interfaces:**
- Consumes: `medien_convert.convert`, `blog_mirror.apply`.
- Produces: the CLI `apply-medien-sync.py --staging DIR [--content content/blog] [--sites data/sites.yaml] [--aliases data/medienmitteilungen.yaml] [--prefix Medienmitteilungen] [--dry-run] [--allow-empty]`.

- [ ] **Step 1: Create the alias map**

```bash
cat > data/medienmitteilungen.yaml <<'YAML'
# Folder-name tokens for Medienmitteilungen/ that are not themselves keys in
# data/sites.yaml.
#
# A press-release folder is named  YYYY-MM-DD_<location>[_<topic>]…  and <location>
# sets the page's Site. Tokens that already match a key in data/sites.yaml
# (sonnhalde, hagmatt, bifang-säli, verein) need no entry here.
#
# A token that resolves to nothing is reported and the folder is left unpublished:
# adding a site stays a deliberate repository change, as it is for job ads.
aliases:
  hort: bifang-säli
YAML
```

- [ ] **Step 2: Write the failing test**

Create `scripts/test-apply-medien-sync.py`:

```python
#!/usr/bin/env python3
"""End-to-end tests for apply-medien-sync.py, run as a subprocess.

Run with:  python3 scripts/test-apply-medien-sync.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APPLY = os.path.join(HERE, "apply-medien-sync.py")
FIXTURES = os.path.join(HERE, "fixtures", "medien")
DOCX = "20260904_MM_EröffnungHort.docx"

SITES = "sonnhalde:\n  Name: Sonnhalde\nhagmatt:\n  Name: Hagmatt\nbifang-säli:\n  Name: Hort\nverein:\n  Name: Verein\n"
ALIASES = "aliases:\n  hort: bifang-säli\n"

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
        check("happy: Autor from the document", "Autor: Melanie von Arx" in text, text[:200])
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
        check("meta: TeaserTitle applied", "TeaserTitle: Eröffnung Hort" in text, text[:200])
        check("meta: Autor overridden", "Autor: F. Giori" in text, text[:200])

        # --- folder-name rejections ---
        for folder, why in (("hort", "no date"),
                            ("2026-13-45_hort", "impossible date"),
                            ("2026-09-04_kantine", "unknown location")):
            s, c, si, al = setup(tmp + "/r" + folder, {folder: [DOCX]})
            rc, out = run(s, c, si, al, "--allow-empty")
            check(f"reject: {why} -> rc 1", rc == 1, out)
            check(f"reject: {why} publishes nothing", os.listdir(c) == [], os.listdir(c))

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
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `python3 scripts/test-apply-medien-sync.py`
Expected: every check FAILs — `apply-medien-sync.py` does not exist.

- [ ] **Step 4: Write the minimal implementation**

Create `scripts/apply-medien-sync.py` (make it executable: `chmod +x`):

```python
#!/usr/bin/env python3
"""Publish press-release folders staged from OpenCloud into content/blog/.

Usage:
    apply-medien-sync.py --staging DIR [--content content/blog]
                         [--sites data/sites.yaml]
                         [--aliases data/medienmitteilungen.yaml]
                         [--prefix Medienmitteilungen] [--dry-run] [--allow-empty]

Each staged directory is  YYYY-MM-DD_<location>[_<topic>]…  and becomes one Hugo page
bundle. OpenCloud is the source of truth: the folder's contents are regenerated on
every run and a folder that disappears takes its page with it.

A REJECTED folder is inert -- never created, never updated, never deleted. Rejection
means "I cannot read this", which is not the same claim as "this was withdrawn", and
only an absent folder is a withdrawal. (apply-stellen-sync.py deletes what fails
validation; that is right for a job ad and wrong for a permanent URL.)

Exit status:
    0  applied cleanly
    1  applied, but at least one folder was rejected
    2  could not run -- the repository is untouched
    3  refused: the wipeout guard tripped
"""

import argparse
import datetime
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import blog_mirror          # noqa: E402
import medien_convert       # noqa: E402

FOLDER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
SITE_KEY_RE = re.compile(r"^([^\s#][^:]*):\s*$")
ALIAS_RE = re.compile(r"^\s{2,}([^\s#][^:]*):\s*(.+?)\s*$")
META_RE = re.compile(r"^(\w+):\s*(.*?)\s*$")
DOC_EXT = (".docx", ".pdf")
IMAGE_EXT = (".jpg", ".jpeg", ".png")
IGNORED = {"thumbs.db", "meta.yaml"}


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def read_sites(path):
    """Top-level keys of data/sites.yaml, in the repository's own spelling."""
    try:
        lines = open(path, encoding="utf-8").readlines()
    except OSError as exc:
        die(f"cannot read {path!r}: {exc}")
    sites = [SITE_KEY_RE.match(l).group(1).strip() for l in lines
             if not l.startswith(("#", " ", "\t")) and SITE_KEY_RE.match(l)]
    if not sites:
        die(f"no site keys found in {path!r}")
    return sites


def read_aliases(path):
    if not os.path.exists(path):
        return {}
    out, in_block = {}, False
    for line in open(path, encoding="utf-8"):
        if line.startswith("aliases:"):
            in_block = True
            continue
        if in_block:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            m = ALIAS_RE.match(line.rstrip("\n"))
            if m:
                out[m.group(1).strip().casefold()] = m.group(2).strip().strip("'\"")
    return out


def read_meta(folder):
    path = os.path.join(folder, "meta.yaml")
    if not os.path.isfile(path):
        return {}
    out = {}
    for line in open(path, encoding="utf-8"):
        if line.lstrip().startswith("#"):
            continue
        m = META_RE.match(line.rstrip("\n"))
        if m and m.group(2):
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def ignored(name):
    return name.startswith(".") or name.lower() in IGNORED


def parse_folder(name, sites, aliases):
    """(date, site, target directory name) -- or raise ValueError with the reason."""
    m = FOLDER_RE.match(name)
    if not m:
        raise ValueError("expected a folder named YYYY-MM-DD_<Ort>[_<Thema>]")
    try:
        date = datetime.date.fromisoformat(m.group(1))
    except ValueError:
        raise ValueError(f"{m.group(1)!r} is not a real date")
    tokens = m.group(2).split("_")
    key = tokens[0].casefold()
    known = {s.casefold(): s for s in sites}
    site = known.get(key) or known.get(aliases.get(key, "").casefold())
    if not site:
        raise ValueError(
            f"{tokens[0]!r} is not a site in data/sites.yaml and has no alias in "
            "data/medienmitteilungen.yaml")
    target = m.group(1) + "_" + "_".join(t[:1].upper() + t[1:] for t in tokens)
    return date, site, target


def inspect(folder):
    """(document path, sorted loose image paths) -- or raise ValueError."""
    docs, images, strays = [], [], []
    for name in sorted(os.listdir(folder)):
        if ignored(name):
            continue
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            strays.append(name + "/")
        elif name.lower().endswith(DOC_EXT):
            docs.append(path)
        elif name.lower().endswith(IMAGE_EXT):
            images.append(path)
        else:
            strays.append(name)
    if strays:
        raise ValueError("unexpected file(s): " + ", ".join(strays))
    if not docs:
        raise ValueError("no .docx or .pdf found")
    if len(docs) > 1:
        raise ValueError(
            "more than one document: " + ", ".join(os.path.basename(d) for d in docs))
    return docs[0], images


def quote(value):
    """YAML-safe scalar. A ':' in a title would otherwise break the front matter."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def front_matter(bundle, date, site, marker, meta):
    lines = ["---", f"Title: {quote(meta.get('Title', bundle.title))}"]
    if meta.get("TeaserTitle"):
        lines.append(f"TeaserTitle: {quote(meta['TeaserTitle'])}")
    author = meta.get("Autor") or bundle.author
    if author:
        lines.append(f"Autor: {quote(author)}")
    lines += [f"Date: {date.isoformat()}",
              f"Site: {meta.get('Site', site)}",
              f"SyncedFrom: {marker}",
              "---"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--staging", required=True)
    ap.add_argument("--content", default="content/blog")
    ap.add_argument("--sites", default="data/sites.yaml")
    ap.add_argument("--aliases", default="data/medienmitteilungen.yaml")
    ap.add_argument("--prefix", default="Medienmitteilungen")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-empty", action="store_true",
                    help="permit removing the last remaining page (overrides the guard)")
    args = ap.parse_args()

    if not os.path.isdir(args.staging):
        die(f"staging directory {args.staging!r} does not exist")
    if not os.path.isdir(args.content):
        die(f"content directory {args.content!r} does not exist")

    sites = read_sites(args.sites)
    aliases = read_aliases(args.aliases)

    work = tempfile.mkdtemp(prefix="medien-staging-")
    desired, protected, rejected, notes = {}, set(), [], []
    try:
        for name in sorted(os.listdir(args.staging)):
            folder = os.path.join(args.staging, name)
            # Files at the staging root are ignored rather than rejected, so author
            # instructions can live beside the folders in OpenCloud.
            if ignored(name) or not os.path.isdir(folder):
                continue

            target = None
            try:
                date, site, target = parse_folder(name, sites, aliases)
                doc, images = inspect(folder)
                out = os.path.join(work, target)
                os.makedirs(out)
                bundle = medien_convert.convert(doc, images, out)
            except (ValueError, medien_convert.ConversionError) as exc:
                rejected.append((name, str(exc)))
                if target:
                    protected.add(target)
                continue

            meta = read_meta(folder)
            marker = f"{args.prefix}/{name}"
            with open(os.path.join(out, "index.md"), "w", encoding="utf-8") as fh:
                fh.write(front_matter(bundle, date, site, marker, meta) + bundle.body)
            desired[target] = out
            notes.extend(f"note: {target}: {w}" for w in bundle.warnings)

        lines, status = blog_mirror.apply(
            desired, args.content, args.prefix, protected=protected,
            dry_run=args.dry_run, allow_empty=args.allow_empty)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for line in lines:
        print(line)
    for note in notes:
        print(note)
    if rejected:
        print(f"\n{len(rejected)} folder(s) could not be published:", file=sys.stderr)
        for name, why in rejected:
            published = " (page left as-is)" if name else ""
            print(f"  {name}/{published}\n      {why}", file=sys.stderr)
        print("\nFix them in OpenCloud. Nothing already published was removed.",
              file=sys.stderr)

    if status:
        return status
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `chmod +x scripts/apply-medien-sync.py && python3 scripts/test-apply-medien-sync.py`
Expected: every check `ok`, exit 0.

- [ ] **Step 6: Verify the real folder end to end against a scratch copy of the site**

```bash
rm -rf /scratch/zaucker/claude-tmp/e2e && mkdir -p /scratch/zaucker/claude-tmp/e2e/staging
cp -r /scratch/zaucker/2026-09-04_hort /scratch/zaucker/claude-tmp/e2e/staging/
python3 scripts/apply-medien-sync.py --staging /scratch/zaucker/claude-tmp/e2e/staging --dry-run
mise exec -- hugo build --quiet && echo "site builds"
```

Expected: `would add: 2026-09-04_Hort`, then a clean Hugo build.

- [ ] **Step 7: Commit**

```bash
git add data/medienmitteilungen.yaml scripts/apply-medien-sync.py scripts/test-apply-medien-sync.py
git commit -m "Medien sync: the CLI -- folder grammar, meta.yaml and front matter"
```

---

### Task 7: Workflows — sync, CI, and the shared concurrency group

**Files:**
- Create: `.github/workflows/sync-medienmitteilungen.yaml`
- Create: `.github/workflows/test-scripts.yaml`
- Modify: `.github/workflows/sync-stellen.yaml` (the `concurrency:` block only)

**Interfaces:**
- Consumes: `scripts/apply-medien-sync.py` from Task 6.
- Produces: nothing importable. Pinned values used by later tasks: `PANDOC_VERSION 3.11`, `PANDOC_SHA256 89d4c9d97818c62a97157f0072844e4602c6cee795bf84abd1aee7273abcda99`, `HUGO_VERSION 0.158.0`, `DART_SASS_VERSION 1.98.0`.

- [ ] **Step 1: Share one concurrency group between the two syncers**

The two syncers touch disjoint paths but push to the same branch, and the commit step has no fetch, rebase or retry — a non-fast-forward push fails the job and the deploy dispatch never runs. Edit `.github/workflows/sync-stellen.yaml`, replacing:

```yaml
concurrency:
  group: sync-stellen
  cancel-in-progress: false
```

with:

```yaml
# Shared with sync-medienmitteilungen.yaml, deliberately. The two syncers write to
# disjoint paths but push to the same branch, and the commit step below pushes with
# no fetch and no retry -- so a concurrent run would lose its push, fail the job, and
# skip the deploy dispatch, deferring publication up to 24 hours with only a red run
# to show for it. Serialising costs a few seconds.
concurrency:
  group: websync-sync
  cancel-in-progress: false
```

- [ ] **Step 2: Create the sync workflow**

Create `.github/workflows/sync-medienmitteilungen.yaml`. Start from `sync-stellen.yaml` and keep its "Check OpenCloud secrets are present", "Install rclone" and "Warn if the App Token is close to expiring" steps **verbatim** — they are instance facts, not job-ad specifics.

```yaml
name: Sync Medienmitteilungen from OpenCloud

# Mirrors press-release folders from the OpenCloud space into content/blog/.
# Design: docs/superpowers/specs/2026-09-06-opencloud-medienmitteilungen-sync-design.md
#
# The sibling of sync-stellen.yaml, kept as a separate file rather than factored into
# something shared: the two have the same SHAPE but not the same logic, and a shared
# workflow would couple a job-ad publish to a press-release bug.
on:
  schedule:
    - cron: '43 5 * * 1'   # UTC, Mondays. Off-round, and away from sync-stellen's :17.
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Fetch and validate only -- do not commit or push'
        type: boolean
        default: false
      allow_empty:
        description: 'Permit removing the last remaining page (overrides the wipeout guard)'
        type: boolean
        default: false

permissions:
  contents: write
  actions: write

# SHARED with sync-stellen.yaml. See the note there: both push to the same branch and
# neither rebases, so they must not run at the same time.
concurrency:
  group: websync-sync
  cancel-in-progress: false

jobs:
  sync:
    runs-on: ubuntu-latest
    env:
      PIN_RCLONE_VERSION: v1.75.0
      PIN_RCLONE_SHA256: aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa

      # Pandoc GENERATES the committed bytes, and the update pass detects change by
      # regenerating and comparing them. An unpinned pandoc means that the day the
      # runner image moves, every synced page compares unequal and one bot commit
      # rewrites the entire corpus, then deploys it. Pinning the tool that copies
      # bytes (rclone, above) while floating the tool that writes them would be
      # exactly backwards.
      PIN_PANDOC_VERSION: '3.11'
      PIN_PANDOC_SHA256: 89d4c9d97818c62a97157f0072844e4602c6cee795bf84abd1aee7273abcda99

      # For the pre-commit build check. Keep in step with deploy-hugo.yaml.
      HUGO_VERSION: 0.158.0
      DART_SASS_VERSION: 1.98.0

      OPENCLOUD_PATH: Medienmitteilungen

    steps:
      - name: Check OpenCloud secrets are present
        env:
          RCLONE_CONFIG_OC_URL: ${{ secrets.OPENCLOUD_WEBDAV_URL }}
          RCLONE_CONFIG_OC_USER: ${{ secrets.OPENCLOUD_USER }}
          OPENCLOUD_TOKEN: ${{ secrets.OPENCLOUD_TOKEN }}
        run: |
          set -euo pipefail
          for v in RCLONE_CONFIG_OC_URL RCLONE_CONFIG_OC_USER OPENCLOUD_TOKEN; do
            if [ -z "${!v:-}" ]; then
              echo "::error::secret behind $v is empty -- set it in Settings > Secrets and variables > Actions"
              exit 1
            fi
          done
          echo "all three OpenCloud secrets are set"

      - name: Checkout
        uses: actions/checkout@v4
        with:
          # assets/uikit is a submodule and the SCSS build needs it; the build check
          # below is the reason this differs from sync-stellen.yaml.
          submodules: recursive

      - name: Install rclone
        run: |
          set -euo pipefail
          dir="rclone-${PIN_RCLONE_VERSION}-linux-amd64"
          curl -fsSLO "https://downloads.rclone.org/${PIN_RCLONE_VERSION}/${dir}.zip"
          echo "${PIN_RCLONE_SHA256}  ${dir}.zip" | sha256sum -c -
          unzip -q "${dir}.zip"
          sudo install -m 0755 "${dir}/rclone" /usr/local/bin/rclone
          rm -rf "${dir}" "${dir}.zip"
          rclone version | head -1

      - name: Install pandoc, poppler and the imaging libraries
        run: |
          set -euo pipefail
          deb="pandoc-${PIN_PANDOC_VERSION}-1-amd64.deb"
          curl -fsSLO "https://github.com/jgm/pandoc/releases/download/${PIN_PANDOC_VERSION}/${deb}"
          echo "${PIN_PANDOC_SHA256}  ${deb}" | sha256sum -c -
          sudo dpkg -i "$deb"
          rm -f "$deb"
          # poppler stays unpinned: pdftotext output feeds the same parser, and drift
          # there surfaces as a rejected or visibly wrong page rather than a silent
          # corpus-wide rewrite. Pillow and numpy are for de-duplication only.
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends poppler-utils python3-pil python3-numpy
          pandoc --version | head -1
          pdftotext -v 2>&1 | head -1

      - name: Install Hugo
        run: |
          set -euo pipefail
          curl -fsSLJO "https://github.com/sass/dart-sass/releases/download/${DART_SASS_VERSION}/dart-sass-${DART_SASS_VERSION}-linux-x64.tar.gz"
          tar -xf "dart-sass-${DART_SASS_VERSION}-linux-x64.tar.gz"
          sudo cp -r dart-sass/* /usr/local/bin
          rm -rf dart-sass*
          curl -fsSLo hugo.deb "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-amd64.deb"
          sudo dpkg -i hugo.deb
          rm -f hugo.deb
          hugo version

      - name: Fetch press releases from OpenCloud
        env:
          RCLONE_CONFIG_OC_TYPE: webdav
          RCLONE_CONFIG_OC_VENDOR: infinitescale
          RCLONE_CONFIG_OC_URL: ${{ secrets.OPENCLOUD_WEBDAV_URL }}
          RCLONE_CONFIG_OC_USER: ${{ secrets.OPENCLOUD_USER }}
          OPENCLOUD_TOKEN: ${{ secrets.OPENCLOUD_TOKEN }}
        run: |
          set -euo pipefail
          mkdir -p staging
          RCLONE_CONFIG_OC_PASS="$(rclone obscure "$OPENCLOUD_TOKEN")"
          export RCLONE_CONFIG_OC_PASS
          rclone copy "OC:${OPENCLOUD_PATH}" staging --max-size 25M --transfers 4 --stats-one-line -v
          echo "--- fetched ---"
          find staging -type f -printf '%P\n' | sort

      - name: Warn if the App Token is close to expiring
        continue-on-error: true
        env:
          RCLONE_CONFIG_OC_URL: ${{ secrets.OPENCLOUD_WEBDAV_URL }}
          RCLONE_CONFIG_OC_USER: ${{ secrets.OPENCLOUD_USER }}
          OPENCLOUD_TOKEN: ${{ secrets.OPENCLOUD_TOKEN }}
          WARN_DAYS: '30'
        run: |
          # Copied verbatim from sync-stellen.yaml -- same token, same failure mode.
          # NOT set -e: this step must never fail the sync.
          set -uo pipefail
          base=$(printf '%s' "$RCLONE_CONFIG_OC_URL" | sed -E 's#^(https?://[^/]+).*#\1#')
          if [ -z "$base" ]; then
            echo "::warning::App Token expiry check skipped: could not derive the OpenCloud base URL"
            exit 0
          fi
          if ! resp=$(curl -fsS --max-time 20 -u "${RCLONE_CONFIG_OC_USER}:${OPENCLOUD_TOKEN}" \
                        "${base}/auth-app/tokens" 2>/dev/null); then
            echo "::warning::App Token expiry check skipped: /auth-app/tokens could not be read with the App Token (the sync itself succeeded, so the token is valid)."
            exit 0
          fi
          exp=$(printf '%s' "$resp" | jq -r --arg t "$OPENCLOUD_TOKEN" \
                  'map(select(.token == $t)) | .[0].expiration_date // empty' 2>/dev/null)
          if [ -z "${exp:-}" ]; then
            exp=$(printf '%s' "$resp" | jq -r \
                    '[.[].expiration_date] | map(select(. != null)) | sort | .[0] // empty' 2>/dev/null)
          fi
          [ -n "${exp:-}" ] || { echo "::warning::App Token expiry check skipped: no expiration_date in the response"; exit 0; }
          exp_s=$(date -u -d "$exp" +%s 2>/dev/null) || { echo "::warning::App Token expiry check skipped: could not parse '$exp'"; exit 0; }
          days=$(( (exp_s - $(date -u +%s)) / 86400 ))
          echo "App Token expires ${exp} (in ${days} days)"
          if [ "$days" -le "$WARN_DAYS" ]; then
            echo "::warning::The OpenCloud App Token expires in ${days} days (${exp}). Publishing stops when it does."
          fi
          exit 0

      - name: Apply to the repository
        id: apply
        env:
          DRY_RUN: ${{ inputs.dry_run || false }}
          ALLOW_EMPTY: ${{ inputs.allow_empty || false }}
        run: |
          set -euo pipefail
          flags=()
          if [ "$DRY_RUN" = "true" ]; then flags+=(--dry-run); fi
          if [ "$ALLOW_EMPTY" = "true" ]; then flags+=(--allow-empty); fi

          set +e
          python3 scripts/apply-medien-sync.py --staging staging "${flags[@]}" \
            | tee apply-report.txt
          rc=${PIPESTATUS[0]}
          set -e

          echo "rc=$rc" >> "$GITHUB_OUTPUT"
          # 0 clean, 1 applied with rejections (commit anyway, fail at the end),
          # 2 could not run, 3 wipeout guard. Stop now on 2/3 so nothing is committed.
          if [ "$rc" -ge 2 ]; then exit "$rc"; fi

      # This syncer GENERATES content rather than copying it, so the first thing to
      # evaluate the Markdown must not be the production deploy. Hugo evaluates
      # shortcodes in page content and this site sets goldmark unsafe:true, so a
      # document containing '{{<' or unexpected raw HTML could otherwise break every
      # deploy -- job ads included -- with an error naming content/blog/ rather than
      # the document it came from.
      - name: Check the site still builds
        run: |
          set -euo pipefail
          hugo build --quiet
          echo "site builds with the applied changes"

      - name: Commit and push
        id: commit
        if: ${{ inputs.dry_run != true }}
        run: |
          set -euo pipefail
          if [ -z "$(git status --porcelain content/blog)" ]; then
            echo "no changes to commit"
            echo "pushed=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          git config user.name  "kko-websyncer[bot]"
          git config user.email "websyncer@kinderkrippe-olten.ch"
          git add -A content/blog
          git commit -F - <<EOF
          Sync press releases from OpenCloud

          $(cat apply-report.txt)

          Applied automatically by .github/workflows/sync-medienmitteilungen.yaml
          EOF
          git push
          echo "pushed=true" >> "$GITHUB_OUTPUT"

      - name: Trigger the deploy, healing a stranded commit if needed
        if: ${{ inputs.dry_run != true }}
        env:
          GH_TOKEN: ${{ github.token }}
          PUSHED: ${{ steps.commit.outputs.pushed }}
        run: |
          set -euo pipefail
          head="$(git rev-parse HEAD)"
          if [ "$PUSHED" = "true" ]; then
            gh workflow run deploy-hugo.yaml --ref "${GITHUB_REF_NAME}"
            echo "deploy-hugo.yaml dispatched on ${GITHUB_REF_NAME} for ${head}"
            exit 0
          fi
          if [ "$(git log -1 --format='%an')" != "kko-websyncer[bot]" ]; then
            echo "no changes, and HEAD is not ours -- nothing to do"
            exit 0
          fi
          deployed="$(gh api \
            "repos/${GITHUB_REPOSITORY}/deployments?environment=github-pages&per_page=1" \
            --jq '.[0].sha // empty' 2>/dev/null || true)"
          if [ -z "$deployed" ]; then
            echo "could not determine the deployed commit -- skipping the heal check"
            exit 0
          fi
          if [ "$head" = "$deployed" ]; then echo "already deployed at ${head}"; exit 0; fi
          inflight="$(gh run list --workflow=deploy-hugo.yaml --json status \
            --jq '[.[] | select(.status == "queued" or .status == "in_progress")] | length' \
            2>/dev/null || echo 0)"
          if [ "$inflight" -gt 0 ]; then
            echo "a deploy is already queued or running -- letting it finish"
            exit 0
          fi
          echo "::warning::${head} was committed by an earlier run but never deployed -- dispatching now"
          gh workflow run deploy-hugo.yaml --ref "${GITHUB_REF_NAME}"

      - name: Report rejected folders
        if: ${{ steps.apply.outputs.rc == '1' }}
        run: |
          echo "::error::Some folders in the OpenCloud Medienmitteilungen folder could not be published."
          echo "Nothing already published was removed. See 'Apply to the repository' above"
          echo "for the folder names and what to correct."
          exit 1
```

- [ ] **Step 3: Create the CI workflow**

Nothing currently runs `scripts/test-*.py` — `.github/workflows/` holds only `deploy-hugo.yaml` and `sync-stellen.yaml`. That is tolerable for pure-Python job-ad scripts and not tolerable for a converter whose output depends on a pinned external binary.

Create `.github/workflows/test-scripts.yaml`:

```yaml
name: Test the sync scripts

# The fixture test in scripts/test-medien-convert.py is the only thing that would
# notice pandoc's Markdown output moving. It has to run somewhere, with the SAME
# pinned pandoc the sync workflow uses -- otherwise a pin bump passes here and
# rewrites the corpus there.
on:
  pull_request:
    paths: ['scripts/**', 'data/**', '.github/workflows/test-scripts.yaml']
  push:
    branches: [main]
    paths: ['scripts/**', 'data/**', '.github/workflows/test-scripts.yaml']
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      # Keep in step with sync-medienmitteilungen.yaml.
      PIN_PANDOC_VERSION: '3.11'
      PIN_PANDOC_SHA256: 89d4c9d97818c62a97157f0072844e4602c6cee795bf84abd1aee7273abcda99
    steps:
      - uses: actions/checkout@v4

      - name: Install pandoc, poppler and the imaging libraries
        run: |
          set -euo pipefail
          deb="pandoc-${PIN_PANDOC_VERSION}-1-amd64.deb"
          curl -fsSLO "https://github.com/jgm/pandoc/releases/download/${PIN_PANDOC_VERSION}/${deb}"
          echo "${PIN_PANDOC_SHA256}  ${deb}" | sha256sum -c -
          sudo dpkg -i "$deb"
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends poppler-utils python3-pil python3-numpy

      - name: Run every test script
        run: |
          set -euo pipefail
          status=0
          for t in scripts/test-*.py; do
            echo "== $t"
            python3 "$t" || status=1
          done
          exit "$status"
```

- [ ] **Step 4: Validate the workflow files parse**

Run:
```bash
python3 -c "
import yaml, glob
for f in sorted(glob.glob('.github/workflows/*.yaml')):
    yaml.safe_load(open(f)); print('ok', f)
"
grep -n 'group: websync-sync' .github/workflows/sync-stellen.yaml .github/workflows/sync-medienmitteilungen.yaml
```
Expected: `ok` for all four files, and the shared group present in both syncers.

- [ ] **Step 5: Run the whole test suite the way CI will**

Run: `for t in scripts/test-*.py; do echo "== $t"; python3 "$t" || break; done`
Expected: all five scripts pass.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/
git commit -m "Sync press releases from OpenCloud, and run the sync tests in CI"
```

---

### Task 8: Author-facing instructions

**Files:**
- Create: `docs/medienmitteilungen-anleitung.md`

**Interfaces:**
- Consumes: the folder grammar and `meta.yaml` keys from Task 6.
- Produces: nothing importable.

The mirror regenerates `index.md` on every change, so a `TeaserTitle` typed into the repository by hand survives only until the next dispatch. `meta.yaml` is the sole durable place for it, and the authors need to know that on day one rather than discover it. Written in German, for non-technical authors.

- [ ] **Step 1: Write the document**

Create `docs/medienmitteilungen-anleitung.md`:

```markdown
# Medienmitteilungen veröffentlichen

Eine Medienmitteilung kommt auf die Website, indem sie in OpenCloud im Space
**WebSync** im Ordner **Medienmitteilungen** abgelegt wird. Ein paar Minuten
später steht sie unter «Geschichten» auf kinderkrippe-olten.ch.

## Ordner anlegen

Pro Mitteilung ein Ordner, benannt nach diesem Muster:

    2026-09-04_Hort
    JJJJ-MM-TT_<Ort>[_<Thema>]

* **Datum** – erscheint auf der Website als Datum der Mitteilung.
* **Ort** – `Sonnhalde`, `Hagmatt`, `Hort` (= Bifang-Säli) oder `Verein`.
* **Thema** – freiwillig, z. B. `2026-09-04_Hort_Eroeffnung`. Nötig nur, wenn am
  selben Tag zwei Mitteilungen zum selben Ort erscheinen.

## In den Ordner gehören

* **Genau ein** Dokument: `.docx` oder `.pdf`.
  Das `.docx` ist die bessere Wahl – daraus entstehen Zwischentitel und ein
  fetter Lead-Absatz. Ein PDF kennt kein Fett, dort wird alles Fliesstext.
* **Fotos** als einzelne Bilddateien (`.jpg`, `.jpeg`, `.png`), so viele wie
  gewünscht. Sie werden zur Bildergalerie am Ende der Seite.
* Sonst nichts. Ein zusätzliches ZIP oder eine zweite Datei führt dazu, dass der
  Ordner nicht verarbeitet wird.

## Aufbau des Dokuments

Die Website übernimmt die Struktur des Dokuments:

| Im Dokument | Auf der Website |
|---|---|
| `MEDIENMITTEILUNG` zuoberst | wird weggelassen |
| erste Zeile danach | Titel der Seite |
| fetter Absatz | Lead |
| fette Einzelzeile | Zwischentitel |
| eingebettetes Bild | Titelbild der Seite |
| `Bildlegende: …` | Bildunterschrift |
| Adressblock am Schluss | wird weggelassen |

Der Adressblock wird an der Postleitzahl erkannt und **absichtlich entfernt** –
auf der Website steht die Adresse ohnehin schon.

Ist das Bild im Dokument dasselbe wie eines der losen Fotos, wird es **nicht
doppelt** angezeigt. Es genügt also, das Foto ganz normal ins Dokument
einzufügen und zusätzlich beizulegen.

## `meta.yaml` – für Kurztitel und Autorin

Der Titel einer Medienmitteilung ist oft lang, die Kachel auf der Startseite ist
schmal. Für einen kürzeren Kacheltitel eine Datei `meta.yaml` in den Ordner
legen:

```yaml
TeaserTitle: Eröffnung Hort
Autor: Melanie von Arx
```

Alle Angaben sind freiwillig. Ohne `TeaserTitle` steht der volle Titel auf der
Kachel; ohne `Autor` wird die Autorin aus den Dokumenteigenschaften übernommen.

**Wichtig:** `meta.yaml` ist der *einzige* Ort, an dem diese Angaben dauerhaft
bestehen bleiben. Die Seite wird bei jeder Änderung neu erzeugt – was direkt auf
der Website geändert wird, geht dabei verloren.

## Ändern und Zurückziehen

* **Ändern** – Dokument oder Fotos in OpenCloud ersetzen. Die Seite wird neu
  erzeugt.
* **Zurückziehen** – den Ordner in OpenCloud löschen. Die Seite verschwindet von
  der Website. Sie bleibt in der Versionsgeschichte erhalten und lässt sich
  wiederherstellen.
* Wird ein Ordner **nicht verarbeitet** (falscher Name, zwei Dokumente, fremde
  Datei), bleibt eine bereits veröffentlichte Seite unverändert stehen. Es geht
  also nichts verloren, solange der Fehler behoben wird.

Dateien, die direkt im Ordner `Medienmitteilungen` liegen – etwa diese Anleitung
– werden ignoriert.
```

- [ ] **Step 2: Check it renders and the facts match the code**

Run:
```bash
grep -o 'TeaserTitle\|Autor\|Site' docs/medienmitteilungen-anleitung.md | sort -u
grep -n 'TeaserTitle\|Autor' scripts/apply-medien-sync.py | head
```
Expected: the keys named in the document are exactly the ones `read_meta`/`front_matter` honour.

- [ ] **Step 3: Commit**

```bash
git add docs/medienmitteilungen-anleitung.md
git commit -m "Anleitung: how to publish a press release through OpenCloud"
```

---

## Done when

- `for t in scripts/test-*.py; do python3 "$t" || break; done` passes.
- `python3 scripts/apply-medien-sync.py --staging <copy of the real folder> --dry-run` reports `would add: 2026-09-04_Hort`.
- `mise exec -- hugo build` succeeds with the page applied.
- A `workflow_dispatch` of `sync-medienmitteilungen.yaml` with `dry_run` ticked is green.
- Then the companion plan: `docs/superpowers/plans/2026-09-06-medien-dispatcher.md`.
