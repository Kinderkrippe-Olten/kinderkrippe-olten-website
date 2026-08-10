#!/usr/bin/env python3
"""Validate job-ad PDFs staged from OpenCloud before they are copied into the repo.

Usage:
    validate-stellen-filenames.py [--sites data/stellen.yaml] [--print0] STAGING_DIR

STAGING_DIR is laid out as <site>/<file>, mirroring content/docs/stellen/.

Writes the relative path of every publishable file to stdout, and a human-readable
report of every rejected one to stderr.

Exit status:
    0  nothing was rejected
    1  at least one file or directory was rejected
    2  usage error, or the site list could not be read

The workflow consumes stdout even when the exit status is 1: valid ads are published
and the run is then marked failed, so one colleague's typo cannot hold up someone
else's ad.

The filename convention is also enforced at build time in
layouts/_shortcodes/stellen.html. That duplication is deliberate -- this script is
the primary gate, the shortcode is the backstop for a PDF committed directly to git.
Keep the two in step.
"""

import argparse
import os
import re
import sys

# A site directory name, then a separator, an 8-digit posting date, another
# separator, and a non-empty link text. The site prefix is checked separately so
# it can be compared case-insensitively against the containing directory.
SEPARATORS = " -_"
DATE_RE = re.compile(r"^[0-9]{8}$")

# data/stellen.yaml is a block-style list of "- dir: <name>" / "  title: <name>".
# Parsed with a regex rather than PyYAML to keep this script dependency-free; if the
# file ever moves to flow style ({dir: x}), this needs revisiting.
DIR_RE = re.compile(r"^\s*-\s*dir:\s*(.+?)\s*$")

IGNORED_NAMES = {"thumbs.db"}


def die(message):
    """Exit 2 -- could not run at all.

    Distinct from exit 1 (ran fine, some files rejected) on purpose. The workflow
    publishes the valid files on 1 but must not touch the repository on 2: an
    unreadable site list or a missing staging directory would otherwise look
    identical to "every ad is invalid" and could empty the page.
    """
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def read_sites(path):
    """Return the ordered list of site directory names from data/stellen.yaml."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        die(f"cannot read site list {path!r}: {exc}")

    sites = []
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        m = DIR_RE.match(line)
        if m:
            sites.append(m.group(1).strip().strip("'\""))

    if not sites:
        die(f"no '- dir:' entries found in {path!r}")
    return sites


def is_ignored(name):
    """Dot-files cover .DS_Store and OpenCloud's own metadata."""
    return name.startswith(".") or name.lower() in IGNORED_NAMES


def check_file(site, name):
    """Return None if the file is publishable, else the reason it is not."""
    stem, ext = os.path.splitext(name)

    if ext.lower() != ".pdf":
        return f"not a PDF (job ads must be uploaded as .pdf, found {ext or 'no extension'!r})"

    # Case-insensitive prefix match. casefold() rather than lower() so that the
    # umlaut in e.g. "Bifang-Säli" folds correctly regardless of locale.
    if stem.casefold()[: len(site)] != site.casefold():
        return f"must start with {site!r} (case-insensitive)"

    rest = stem[len(site):]
    if not rest or rest[0] not in SEPARATORS:
        return f"{site!r} must be followed by a space, '-' or '_'"

    rest = rest[1:]
    date, sep, text = rest[:8], rest[8:9], rest[9:]

    if not DATE_RE.match(date):
        return f"expected an 8-digit date YYYYMMDD after {site!r}, found {date!r}"
    if sep not in SEPARATORS:
        return "the date must be followed by a space, '-' or '_'"
    if not text.strip():
        return "no link text after the date"

    return None


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("staging_dir")
    ap.add_argument("--sites", default="data/stellen.yaml")
    ap.add_argument(
        "--print0",
        action="store_true",
        help="NUL-separate the paths on stdout (filenames contain spaces)",
    )
    args = ap.parse_args()

    root = args.staging_dir
    if not os.path.isdir(root):
        die(f"{root!r} is not a directory")

    sites = read_sites(args.sites)
    known = {s.casefold(): s for s in sites}

    valid, errors = [], []

    for entry in sorted(os.listdir(root)):
        if is_ignored(entry):
            continue
        path = os.path.join(root, entry)

        if not os.path.isdir(path):
            errors.append((entry, "unexpected file at the top level; job ads belong in a site folder"))
            continue
        if entry.casefold() not in known:
            errors.append((entry + "/", f"not a site listed in {args.sites}"))
            continue

        # Use the repository's spelling, not OpenCloud's, so that a folder created
        # as "Hagmatt" still lands in content/docs/stellen/hagmatt/.
        site = known[entry.casefold()]

        for name in sorted(os.listdir(path)):
            if is_ignored(name):
                continue
            rel = os.path.join(entry, name)
            if os.path.isdir(os.path.join(path, name)):
                errors.append((rel + "/", "subdirectories inside a site folder are not supported"))
                continue
            reason = check_file(site, name)
            if reason:
                errors.append((rel, reason))
            else:
                valid.append((site, name, rel))

    for _, _, rel in valid:
        sys.stdout.write(rel + ("\0" if args.print0 else "\n"))

    if errors:
        print(
            f"\n{len(errors)} file(s) could not be published "
            f"-- expected <site><sep><YYYYMMDD><sep><link text>.pdf:\n",
            file=sys.stderr,
        )
        for rel, reason in errors:
            print(f"  {rel}\n      {reason}", file=sys.stderr)
        print(
            "\nRename them in OpenCloud, e.g. "
            "'sonnhalde 20260728 Koch oder Köchin (10%) per 1.9.2026.pdf'.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
