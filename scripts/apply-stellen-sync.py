#!/usr/bin/env python3
"""Mirror validated job-ad PDFs from a staging directory into the repository.

Usage:
    apply-stellen-sync.py --staging DIR [--content content/docs/stellen]
                          [--sites data/stellen.yaml] [--dry-run] [--allow-empty]

Runs validate-stellen-filenames.py over the staging directory, then makes
content/docs/stellen/ match the validated set: copies added and changed PDFs,
deletes the ones no longer present, and keeps each site's .gitkeep alive.

OpenCloud is the source of truth, so this is a one-way mirror. A PDF added
directly to git is removed here.

Exit status:
    0  applied cleanly, nothing rejected
    1  applied, but the validator rejected at least one file
    2  could not run -- bad usage, unreadable inputs, validator could not run
    3  refused: the wipeout guard tripped (see below)

The caller commits on 0 and 1, and must not commit on 2 or 3. On 1 the valid ads
are published and the run is then marked failed, so one bad filename cannot hold up
everyone else's ad.

Wipeout guard
-------------
If OpenCloud returns nothing -- expired token, WebDAV outage, a renamed space --
a plain mirror would delete every job ad from the live site. So an empty validated
set is refused while the repository still holds ads, unless --allow-empty says the
last ad really is being taken down.
"""

import argparse
import filecmp
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATOR = os.path.join(HERE, "validate-stellen-filenames.py")

GITKEEP = ".gitkeep"


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def read_sites(path):
    """Site directory names, in the repository's own spelling."""
    import re
    dir_re = re.compile(r"^\s*-\s*dir:\s*(.+?)\s*$")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        die(f"cannot read site list {path!r}: {exc}")
    sites = [
        dir_re.match(l).group(1).strip().strip("'\"")
        for l in lines
        if not l.lstrip().startswith("#") and dir_re.match(l)
    ]
    if not sites:
        die(f"no '- dir:' entries found in {path!r}")
    return sites


def run_validator(staging, sites_path):
    """Return (staging-relative valid paths, had_rejections)."""
    p = subprocess.run(
        [sys.executable, VALIDATOR, "--sites", sites_path, "--print0", staging],
        capture_output=True,
    )
    if p.stderr:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
    if p.returncode == 2:
        die("validator could not run; leaving the repository untouched")
    paths = [x for x in p.stdout.decode("utf-8").split("\0") if x]
    return paths, p.returncode == 1


def current_pdfs(content, sites):
    """Map canonical site -> set of filenames currently committed."""
    out = {}
    for site in sites:
        d = os.path.join(content, site)
        names = set()
        if os.path.isdir(d):
            names = {
                n for n in os.listdir(d)
                if not n.startswith(".") and os.path.isfile(os.path.join(d, n))
            }
        out[site] = names
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--staging", required=True)
    ap.add_argument("--content", default="content/docs/stellen")
    ap.add_argument("--sites", default="data/stellen.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--allow-empty",
        action="store_true",
        help="permit removing the last remaining ads (overrides the wipeout guard)",
    )
    args = ap.parse_args()

    if not os.path.isdir(args.staging):
        die(f"staging directory {args.staging!r} does not exist")
    if not os.path.isdir(args.content):
        die(f"content directory {args.content!r} does not exist")

    sites = read_sites(args.sites)
    canonical = {s.casefold(): s for s in sites}

    valid, had_rejections = run_validator(args.staging, args.sites)

    # Map each staging path onto the repository's spelling of its site.
    desired = {s: {} for s in sites}
    for rel in valid:
        folder, name = rel.split(os.sep, 1)
        site = canonical[folder.casefold()]
        desired[site][name] = os.path.join(args.staging, rel)

    current = current_pdfs(args.content, sites)

    n_desired = sum(len(v) for v in desired.values())
    n_current = sum(len(v) for v in current.values())

    if n_desired == 0 and n_current > 0 and not args.allow_empty:
        print(
            f"refusing to remove all {n_current} job ad(s): the validated set is empty.\n"
            "This is what an expired token or a WebDAV outage looks like. If the last\n"
            "ad really is being taken down, re-run with --allow-empty.",
            file=sys.stderr,
        )
        return 3

    added, updated, removed = [], [], []

    for site in sites:
        d = os.path.join(args.content, site)
        if not os.path.isdir(d) and not args.dry_run:
            os.makedirs(d, exist_ok=True)

        for name, src in sorted(desired[site].items()):
            dst = os.path.join(d, name)
            if name not in current[site]:
                added.append(f"{site}/{name}")
            elif not filecmp.cmp(src, dst, shallow=False):
                updated.append(f"{site}/{name}")
            else:
                continue
            if not args.dry_run:
                shutil.copy2(src, dst)

        for name in sorted(current[site] - set(desired[site])):
            removed.append(f"{site}/{name}")
            if not args.dry_run:
                os.remove(os.path.join(d, name))

        # .gitkeep exists only in the repository -- OpenCloud has no reason to carry
        # it. Without it a site with no open positions vanishes from git, and the
        # Hugo shortcode treats a missing site directory as a hard error rather than
        # as "no open positions".
        keep = os.path.join(d, GITKEEP)
        if not os.path.exists(keep) and not args.dry_run:
            open(keep, "a").close()

    prefix = "would " if args.dry_run else ""
    for label, items in (("add", added), ("update", updated), ("remove", removed)):
        for item in items:
            print(f"{prefix}{label}: {item}")
    if not (added or updated or removed):
        print("no changes")

    return 1 if had_rejections else 0


if __name__ == "__main__":
    sys.exit(main())
