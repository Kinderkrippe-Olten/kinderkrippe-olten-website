#!/usr/bin/env python3
"""Publish folders staged from OpenCloud into content/blog/.

Serves both syncers: --prefix names the OpenCloud folder a run owns, and a run owns
nothing else. Medienmitteilungen/ and Geschichten/ write into this one section, and
neither may touch the other's pages or the hand-made ones -- see blog_mirror.owned().
The two differ in their source folder and their schedule, not in their logic; when
that stops being true, this is the seam to split, not to parameterise further.

Usage:
    apply-blog-sync.py --staging DIR [--content content/blog]
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
    1  applied, but at least one folder was rejected or skipped
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
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import blog_mirror          # noqa: E402
import medien_convert       # noqa: E402

FOLDER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
# A folder-name token. Letters and digits (Unicode, so "säli" is fine) joined by
# hyphens -- deliberately narrow, because the folder name goes into the front matter
# unquoted as the SyncedFrom marker. A ':' or a '#' there would be invalid YAML and
# Hugo would fail the WHOLE site build, naming content/blog/ rather than the folder.
TOKEN_RE = re.compile(r"^[^\W_]+(?:-[^\W_]+)*$")
SITE_KEY_RE = re.compile(r"^([^\s#][^:]*):\s*$")
# Under a site: 'Groups:' opens the block of that site's groups, and any other
# two-space key -- 'Name:', 'Color:' -- closes it again. The group keys themselves
# sit one level deeper, and their own contents ('Icon:', 'Name:') deeper still.
GROUP_BLOCK_RE = re.compile(r"^\s{2}([^\s#][^:]*):")
GROUP_KEY_RE = re.compile(r"^\s{4}([^\s#][^:]*):\s*$")
ALIAS_RE = re.compile(r"^\s{2,}([^\s#][^:]*):\s*(.+?)\s*$")
META_RE = re.compile(r"^(\w+):\s*(.*?)\s*$")
# Pandoc escapes ASCII punctuation on its way out of the .docx, so a title reads
# 'Titel mit {{\< … \>}}'. Markdown renders that correctly in the body; front matter
# is not Markdown, so the backslashes would be visible on the page.
MD_ESCAPE_RE = re.compile(r"\\([!-/:-@\[-`{-~])")
DOC_EXT = (".docx", ".pdf")
IMAGE_EXT = (".jpg", ".jpeg", ".png")
IGNORED = {"thumbs.db", "meta.yaml"}
# Deliberately no "Title". assemble_body has already baked the document's own
# title into the page's '#' heading, so honouring one here produced a page whose
# browser tab, blog card and sitemap said one thing while the heading said
# another. TeaserTitle serves the documented need -- a short title for the card --
# and giving the page a SECOND title authority would mean teaching assemble_body
# about it too. Left out of META_KEYS, 'Title:' is now reported as an unknown key,
# which is what the note below exists for.
META_KEYS = ("TeaserTitle", "Autor", "Site", "Group")
SKIPPED = "exists, not owned -- skipped: "


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def read_sites(path):
    """({site key: [group keys]}) from data/sites.yaml, in its own spelling.

    Both levels stay spelled as the repository spells them: these values go into
    front matter, where Hugo looks them up in this same file.
    """
    try:
        lines = open(path, encoding="utf-8").readlines()
    except OSError as exc:
        die(f"cannot read {path!r}: {exc}")
    sites, site, in_groups = {}, None, False
    for line in lines:
        line = line.rstrip("\n")
        if line.startswith(("#", " ", "\t")):
            if site is None:
                continue
            # 'Groups:' opens the block; any other two-space key closes it. Group
            # keys sit one level deeper, and nothing below THEM is a group.
            m = GROUP_BLOCK_RE.match(line)
            if m:
                in_groups = m.group(1) == "Groups"
                continue
            m = GROUP_KEY_RE.match(line)
            if in_groups and m:
                sites[site].append(m.group(1).strip())
            continue
        m = SITE_KEY_RE.match(line)
        site, in_groups = (m.group(1).strip(), False) if m else (None, False)
        if site is not None:
            sites[site] = []
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
                out[nfc(m.group(1).strip()).casefold()] = m.group(2).strip().strip("'\"")
    return out


def read_meta(folder):
    """(recognised keys, unrecognised keys) from the folder's meta.yaml."""
    path = os.path.join(folder, "meta.yaml")
    if not os.path.isfile(path):
        return {}, []
    out, unknown = {}, []
    for line in open(path, encoding="utf-8"):
        if line.lstrip().startswith("#"):
            continue
        m = META_RE.match(line.rstrip("\n"))
        if m and m.group(2):
            if m.group(1) in META_KEYS:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
            else:
                unknown.append(m.group(1))
    return out, unknown


def nfc(text):
    """Unicode composed form.

    macOS and iOS clients hand out folder names in NFD, where 'ä' is a plain 'a'
    followed by a combining diaeresis. TOKEN_RE's [^\\W_] does not match a
    combining mark and casefold() does not equate NFD to the NFC keys in
    data/sites.yaml -- so an exactly correct '2026-09-04_Bifang-Säli' was quoted
    back to its author as "unusable", with nothing on screen to show what differed.
    The Anleitung teaches that very name and expressly expects iPhone users.
    """
    return unicodedata.normalize("NFC", text)


def ignored(name):
    return name.startswith(".") or name.lower() in IGNORED


def unescape_markdown(text):
    """Undo pandoc's backslash escaping, for text leaving Markdown behind."""
    return MD_ESCAPE_RE.sub(r"\1", text)


def resolve_group(token, site, site_groups):
    """A group key in data/sites.yaml's own spelling -- or raise ValueError.

    A group belongs to ONE site, so it is checked against the site the page ends up
    with, not against every group in the file: 'frosch' on a Sonnhalde page would
    render a group badge the Sonnhalde does not have.
    """
    groups = site_groups.get(site, [])
    if not groups:
        raise ValueError(f"meta.yaml sets Group: {token} -- but the site {site} has "
                         "no groups in data/sites.yaml")
    key = nfc(token).casefold()
    for g in groups:
        if nfc(g).casefold() == key:
            return g
    raise ValueError(f"meta.yaml sets Group: {token} -- not a group of {site}, whose "
                     f"groups are {', '.join(groups)}")


def resolve_site(token, known_sites, aliases):
    """A site key in data/sites.yaml's own spelling, or None.

    The one place a location token becomes a Site: the folder name and meta.yaml's
    Site: both go through it, so 'hort' means the same thing in both.
    """
    key = nfc(token).casefold()
    return known_sites.get(key) or known_sites.get(nfc(aliases.get(key, "")).casefold())


def parse_folder(name, known_sites, aliases):
    """(date, site, target directory name) -- or raise ValueError with the reason."""
    # Before anything looks at the letters: the grammar and the site lookup both
    # compare them, and NFD would fail both.
    name = nfc(name)
    m = FOLDER_RE.match(name)
    if not m:
        raise ValueError("expected a folder named YYYY-MM-DD_<Ort>[_<Thema>]")
    try:
        date = datetime.date.fromisoformat(m.group(1))
    except ValueError:
        raise ValueError(f"{m.group(1)!r} is not a real date")
    tokens = m.group(2).split("_")
    bad = [t for t in tokens if not TOKEN_RE.match(t)]
    if bad:
        raise ValueError(
            "only letters, digits and '-' are allowed between the '_' separators; "
            "unusable: " + ", ".join(repr(t) for t in bad))
    site = resolve_site(tokens[0], known_sites, aliases)
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
    lines = ["---",
             f"Title: {quote(unescape_markdown(bundle.title))}"]
    if meta.get("TeaserTitle"):
        lines.append(f"TeaserTitle: {quote(meta['TeaserTitle'])}")
    # meta.yaml only, never the document's docProps: dc:creator is whatever account
    # last saved the file ("Hagmatt Leitung Stv"), and a name printed under a story
    # has to be one a person chose to put there.
    if meta.get("Autor"):
        lines.append(f"Autor: {quote(meta['Autor'])}")
    # Date, Site, Group and SyncedFrom stay unquoted: they are validated against
    # data/sites.yaml or built here, and blog_mirror reads the marker with a regex
    # and compares it to the source prefix -- quotes there would make every page
    # look like someone else's.
    lines += [f"Date: {date.isoformat()}",
              f"Site: {meta.get('Site', site)}"]
    if meta.get("Group"):
        lines.append(f"Group: {meta['Group']}")
    lines += [f"SyncedFrom: {marker}",
              "---"]
    return "\n".join(lines) + "\n"


def collisions(parsed):
    """{folder name: reason} for folders that would fight over one page name.

    Two folders can differ and still produce one target -- '..._hort' and '..._Hort'.
    Publishing either one of them is a coin toss the author cannot see, so both are
    rejected and any page already there is left alone.
    """
    by_target = {}
    for name, (_, _, target) in parsed.items():
        by_target.setdefault(target, []).append(name)
    out = {}
    for target, names in by_target.items():
        if len(names) > 1:
            for name in names:
                others = ", ".join(n + "/" for n in sorted(names) if n != name)
                out[name] = (f"would become the same page {target!r} as {others} -- "
                             "rename one of them")
    return out


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

    site_groups = read_sites(args.sites)
    # The KEY is normalised, never the value: the value goes into the page's
    # front matter and must stay in data/sites.yaml's own spelling.
    known_sites = {nfc(s).casefold(): s for s in site_groups}
    aliases = read_aliases(args.aliases)

    # Files at the staging root are ignored rather than rejected, so author
    # instructions can live beside the folders in OpenCloud.
    folders = [n for n in sorted(os.listdir(args.staging))
               if not ignored(n) and os.path.isdir(os.path.join(args.staging, n))]

    # rejected: (folder name, target or None, reason). The target is None when the
    # folder name itself is unusable, and then no page of that name can exist.
    parsed, rejected = {}, []
    for name in folders:
        try:
            parsed[name] = parse_folder(name, known_sites, aliases)
        except ValueError as exc:
            rejected.append((name, None, str(exc)))

    for name, why in sorted(collisions(parsed).items()):
        rejected.append((name, parsed.pop(name)[2], why))

    work = tempfile.mkdtemp(prefix="medien-staging-")
    desired, source_of, notes = {}, {}, []
    try:
        for name in sorted(parsed):
            folder = os.path.join(args.staging, name)
            date, site, target = parsed[name]
            try:
                doc, images = inspect(folder)
                meta, unknown = read_meta(folder)
                if meta.get("Site"):
                    # Through the same alias map as the folder name, so that the
                    # 'hort' the Anleitung teaches means one thing in both places.
                    chosen = resolve_site(meta["Site"], known_sites, aliases)
                    if not chosen:
                        raise ValueError(
                            f"meta.yaml sets Site: {meta['Site']} -- not a site in "
                            "data/sites.yaml and no alias in "
                            "data/medienmitteilungen.yaml")
                    meta["Site"] = chosen
                if meta.get("Group"):
                    # After the Site override, not before: meta.yaml can move the
                    # page to another site, and the group has to belong to the site
                    # the page actually ends up on.
                    meta["Group"] = resolve_group(
                        meta["Group"], meta.get("Site", site), site_groups)
                out = os.path.join(work, target)
                os.makedirs(out)
                bundle = medien_convert.convert(doc, images, out)
            # OSError too: an author's image that Pillow cannot open reaches
            # select_images as PIL.UnidentifiedImageError, which is an OSError. One
            # truncated file -- what a half-finished WebDAV sync leaves behind -- must
            # cost its own folder and no one else's.
            except (ValueError, OSError, medien_convert.ConversionError) as exc:
                rejected.append((name, target, str(exc)))
                continue

            # Normalised, so a client that switches between NFC and NFD does not
            # rewrite every marker -- and with it every index.md -- on the next run.
            marker = f"{args.prefix}/{nfc(name)}"
            with open(os.path.join(out, "index.md"), "w", encoding="utf-8") as fh:
                fh.write(front_matter(bundle, date, site, marker, meta) + bundle.body)
            desired[target] = out
            source_of[target] = name
            notes.extend(f"note: {target}: {w}" for w in bundle.warnings)
            for key in unknown:
                notes.append(f"note: {target}: meta.yaml key {key!r} is not one of "
                             f"{', '.join(META_KEYS)} and was ignored")

        # A rejected folder's page is protected from deletion -- but say so in the
        # report only when there really is such a page, and it really is ours.
        protected = {t for _, t, _ in rejected if t}
        ours = {n for n in os.listdir(args.content)
                if blog_mirror.owned(os.path.join(args.content, n), args.prefix)}
        left_alone = protected & ours

        # The wipeout guard exists to stop a mass deletion after an outage. When the
        # only reason nothing is being published is that every page we own is held
        # back by a rejection, there is no deletion to guard, and tripping the guard
        # would hide the author's real problem behind an outage warning.
        allow_empty = args.allow_empty or not (ours - protected)

        lines, status = blog_mirror.apply(
            desired, args.content, args.prefix, protected=protected,
            dry_run=args.dry_run, allow_empty=allow_empty)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for line in lines:
        print(line)
    for note in notes:
        print(note)

    if rejected:
        print(f"\n{len(rejected)} folder(s) could not be published:", file=sys.stderr)
        for name, target, why in sorted(rejected, key=lambda r: r[0]):
            kept = " (page left as-is)" if target in left_alone else ""
            print(f"  {name}/{kept}\n      {why}", file=sys.stderr)
        print("\nFix them in OpenCloud. No page belonging to a rejected folder was "
              "removed.", file=sys.stderr)

    # A target name that is already taken by a hand-made post is a silent
    # publication failure otherwise: nothing is written and the author sees a
    # green run. blog_mirror keeps its 0/3 contract; the exit code is ours.
    skipped = [l[len(SKIPPED):] for l in lines if l.startswith(SKIPPED)]
    if skipped:
        print(f"\n{len(skipped)} folder(s) were not published because the page name "
              "is not owned by this syncer:", file=sys.stderr)
        for target in skipped:
            print(f"  {source_of[target]}/\n      "
                  f"{os.path.join(args.content, target)} exists without this "
                  "syncer's SyncedFrom marker and was left untouched",
                  file=sys.stderr)

    if status:
        return status
    return 1 if rejected or skipped else 0


if __name__ == "__main__":
    sys.exit(main())
