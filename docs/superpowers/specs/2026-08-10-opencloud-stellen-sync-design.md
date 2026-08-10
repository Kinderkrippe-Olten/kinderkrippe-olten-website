# OpenCloud → GitHub sync for job-ad PDFs

Date: 2026-08-10

Builds on [2026-08-10-stellen-auto-generation-design.md](2026-08-10-stellen-auto-generation-design.md),
which made the Stellen page a function of the files in `content/docs/stellen/`.

## Problem

Publishing a job ad currently means using the GitHub web UI. That works, but it asks
a non-technical author to operate a developer tool, and a mistyped filename fails the
deploy with the explanation buried in a build log they will never open.

Goal: the author drops a PDF into an OpenCloud folder and the ad appears on the site.

## Solution overview

A scheduled GitHub Actions workflow pulls the folder over WebDAV with rclone,
validates the filenames, and commits the result. Nothing runs on OpenCloud — no
custom service, no NATS consumer, no OpenCloud extension.

OpenCloud's real event hook (a custom `POSTPROCESSING_STEPS` step consuming NATS
events) was rejected: it must be written and hosted, it couples us to OpenCloud
internals, and because postprocessing blocks until the custom step replies, an
outage would leave uploads stuck mid-finalisation. Too much blast radius for
publishing job ads.

## Folder mapping

OpenCloud holds three subfolders whose names match the repository's site
directories, so the mapping is identity:

```
OpenCloud space                     repository
  bifang-säli/   ───────────────▶     content/docs/stellen/bifang-säli/
  hagmatt/       ───────────────▶     content/docs/stellen/hagmatt/
  sonnhalde/     ───────────────▶     content/docs/stellen/sonnhalde/
```

The authoritative list of sites remains `data/stellen.yaml`. A folder in OpenCloud
that is not listed there is reported and ignored — adding a site stays a deliberate
repository change, because it also needs a heading and a position on the page.

## Direction and authority

OpenCloud is the source of truth for `content/docs/stellen/`. The sync is a one-way
mirror: deleting a PDF in OpenCloud takes the ad off the site, and a PDF added
directly through the GitHub web UI is reverted at the next run. One place to manage
ads, no ambiguity about which side wins.

Git history still retains every removed PDF, so nothing is lost.

## Workflow

`.github/workflows/sync-stellen.yaml`, triggered by `schedule` and by
`workflow_dispatch` for an immediate run.

The cron is `*/15 6-18 * * 1-5`. GitHub cron is always UTC, which is 07:00–19:00
local in winter and 08:00–20:00 in summer; the window is deliberately wide enough
that the shift does not matter. GitHub's scheduled runs are also queued rather than
punctual, so 15 minutes can become considerably more under load — acceptable for job
ads, and `workflow_dispatch` covers the case where someone wants it live now.

1. Check out the repository.
2. Install rclone.
3. `rclone sync` the OpenCloud space into a **staging directory**, not into the
   repository.
4. Run `scripts/validate-stellen-filenames.sh` over the staging directory.
5. Copy only the valid PDFs into `content/docs/stellen/<site>/`, and delete
   repository PDFs that are not in the valid set.
6. Re-create `.gitkeep` in every site directory.
7. If the working tree is unchanged, finish without committing.
8. Otherwise commit and push over SSH using the deploy key.
9. If any file was rejected, fail the job, listing each offender and the reason.

Step 3 is why staging exists. `rclone sync` mirrors everything it finds, including
files that violate the convention; validation has to sit between the mirror and the
repository so that one bad file cannot block everyone else's ads.

Step 6 matters because `.gitkeep` exists only in the repository. A naive mirror
would delete it, and a site whose folder is empty would then vanish from git — which
the Hugo shortcode treats as a hard error, not as "no open positions".

Step 9 runs last on purpose. The valid ads are already committed, pushed and
deploying by then; the red run is a notification, not a rollback.

## Why the push uses a deploy key

A push made with the workflow's `GITHUB_TOKEN` does not trigger other workflows —
GitHub suppresses it to prevent recursion. The site would sync but never rebuild.

Pushes authenticated with an SSH deploy key are not suppressed, so the existing
`deploy-hugo.yaml` (which already fires on `push: branches: ['**']`) runs
automatically with no modification.

A deploy key is preferred over a personal access token because it is scoped to this
one repository rather than to an entire GitHub account.

A useful consequence: the workflow's own `GITHUB_TOKEN` needs only
`permissions: contents: read`, since it never writes.

## Validation

`scripts/validate-stellen-filenames.py` takes a directory laid out as
`<site>/<file>` and reports every file that is not publishable. It is standalone,
with no GitHub or rclone dependencies, so it can be run and tested locally.

Python rather than shell, and stdlib-only rather than PyYAML. Matching
`Bifang-Säli` against `bifang-säli` case-insensitively needs locale-aware case
folding, which bash gets wrong under the `C` locale a runner may well have;
Python's `str.casefold()` is correct regardless.

Interface:

| | |
|---|---|
| stdout | relative path of each publishable file, one per line (`--print0` to NUL-separate, since filenames contain spaces) |
| stderr | each rejected file with the reason, and an example of a correct name |
| exit 0 | nothing rejected |
| exit 1 | ran fine, at least one file rejected |
| exit 2 | could not run at all — bad usage, unreadable site list, missing staging directory |

The 1/2 split is load-bearing. On 1 the workflow publishes the files on stdout and
then fails the run; on 2 it must not touch the repository at all. Collapsing them
would make "I could not read anything" indistinguishable from "every ad is
invalid", which is precisely the situation the wipeout guard exists to prevent.

A file is valid when all of the following hold:

- it sits directly in a site directory listed in `data/stellen.yaml`
- its extension is `.pdf`, compared case-insensitively
- its name matches `<site><sep><YYYYMMDD><sep><text>.pdf`, where `<site>` equals the
  containing directory name compared case-insensitively, `<sep>` is a single space,
  `-` or `_`, `<YYYYMMDD>` is exactly 8 digits, and `<text>` is non-empty

Reported as errors:

- a non-PDF file (most likely an ad uploaded in the wrong format)
- a PDF whose name does not match the convention
- a subdirectory inside a site directory
- a top-level folder not listed in `data/stellen.yaml`

Ignored silently:

- dot-files, which covers `.DS_Store` and OpenCloud's own metadata
- `Thumbs.db`

The convention is now expressed in two places: this script and
`layouts/_shortcodes/stellen.html`. That duplication is deliberate. The script is
the primary gate; the shortcode's build-time error remains as a backstop for a PDF
added directly to git, during the window before the next sync reverts it. Each file
carries a comment pointing at the other.

## Wipeout guard

If OpenCloud returns an empty or partial listing — an expired token, a WebDAV
outage, someone renaming the space — a naive mirror would delete every job ad from
the live site.

Two safeguards:

- `rclone sync --max-delete` bounds how much a single run may remove from staging.
- The repository update step refuses to run if the validated set is empty while the
  repository currently holds PDFs. Taking the last ad down is then a
  `workflow_dispatch` run with an explicit override input.

Removing several ads at once is rare; silently emptying the page is unacceptable.

## Secrets

| Secret | Purpose |
|---|---|
| `OPENCLOUD_WEBDAV_URL` | space URL, `https://<host>/remote.php/dav/spaces/<space-id>/` |
| `OPENCLOUD_USER` | account the App Token belongs to |
| `OPENCLOUD_TOKEN` | OpenCloud App Token, passed to rclone via `RCLONE_WEBDAV_PASS` (obscured) |
| `SYNC_DEPLOY_KEY` | private half of the repository deploy key, write access enabled |

The OpenCloud account should be dedicated to this job and have access only to the
job-ad space, so a leaked token exposes one folder rather than a person's whole
account.

## Testing

The WebDAV leg cannot be exercised from the development machine, so the two halves
are tested differently.

`scripts/test-validate-stellen-filenames.py` builds fixture directories in a temp
dir and runs the validator as a subprocess, so it exercises the real command-line
contract rather than importing internals. Run it with
`python3 scripts/test-validate-stellen-filenames.py`.

It covers: a valid set spanning all three separators, uppercase `.PDF`, an uppercase
umlauted site prefix, and names containing an en-dash and `%`; the reject paths for
wrong site prefix, missing/short/non-digit date, missing separator, empty link text,
non-PDF, and no extension; the structural rejects for a subdirectory, an unlisted
top-level folder and a stray top-level file; silent handling of dot-files and
`Thumbs.db`; partial success, where valid files are still emitted alongside exit 1;
an empty staging directory as success rather than error; `--print0` framing; and
both exit-2 paths.

One test is a drift guard: the validator is run against the repository's own
`content/docs/stellen/` and must accept every committed ad. Everything there already
builds under `layouts/_shortcodes/stellen.html`, so a disagreement means the two
implementations of the convention have diverged — the risk the duplication
introduces.

The workflow is first run manually via `workflow_dispatch` with a dry-run input that
performs the sync and validation but neither commits nor pushes, so the WebDAV URL,
credentials and folder layout are confirmed before anything reaches the repository.

## Out of scope

- Two-way sync. OpenCloud is authoritative; the repository never writes back.
- Notifying the author in OpenCloud or Mattermost. A failed Actions run is the
  notification for now; a richer channel can be added once the sync is proven.
- Syncing anything other than `content/docs/stellen/`.
