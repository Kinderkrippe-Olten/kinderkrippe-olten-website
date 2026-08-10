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

## Connection details

The space URL has the form

```
https://cloud.kinderkrippe-olten.ch/dav/spaces/<storage-id>$<space-id>
```

Two properties of it constrain the implementation:

- The path is `/dav/spaces/…`, not the older `/remote.php/dav/spaces/…`.
- The space ID contains a literal `$`, separating storage ID from space ID. It must
  never be interpolated into a double-quoted shell string, where `$faf2…` would
  expand to nothing and yield a silently wrong URL. The value is passed only through
  environment variables, never spliced into a command line.

The endpoint answers an unauthenticated `PROPFIND` with `401` and offers both
`Bearer` and `Basic` challenges, so rclone authenticates with Basic using the
username and an App Token.

`--webdav-vendor` must be **`infinitescale`**. There is no `opencloud` vendor;
OpenCloud is a fork of ownCloud Infinite Scale, and `owncloud` refers to the older
PHP implementation. `infinitescale` is absent from older rclone builds (1.68.1, for
instance), so the workflow installs a current rclone rather than relying on the
runner's packaged version.

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
2. Install rclone — pinned to `v1.75.0` and checksum-verified, rather than piping
   an install script into a root shell.
3. `rclone copy` the OpenCloud space into a **staging directory**, not into the
   repository.
4. Run `scripts/apply-stellen-sync.py`, which validates the staged files and makes
   `content/docs/stellen/` match the validated set.
5. If the working tree is unchanged, finish without committing.
6. Otherwise commit, push, and dispatch `deploy-hugo.yaml`.
7. If any file was rejected, fail the job.

Staging exists because rclone fetches everything it finds, including files that
violate the convention. Validation has to sit between the fetch and the repository
so that one bad file cannot block everyone else's ads.

The workflow itself stays thin: three shell steps plus a commit. The decisions live
in `apply-stellen-sync.py` and `validate-stellen-filenames.py`, which run and are
tested locally — the only way to get real coverage, since the WebDAV leg is
unreachable from a development machine.

Step 7 runs last on purpose. The valid ads are already committed, pushed and
deploying by then; the red run is a notification, not a rollback.

## Repository update

`scripts/apply-stellen-sync.py` owns the mirror. It invokes the validator as a
subprocess, maps each staged path onto the repository's spelling of its site
directory (so a folder created in OpenCloud as `Hagmatt/` still lands in
`hagmatt/`), then copies added and changed PDFs, removes those no longer present,
and ensures every site directory still has its `.gitkeep`.

`.gitkeep` needs restoring explicitly because it exists only in the repository —
OpenCloud has no reason to carry it. A naive mirror would delete it, the now-empty
site directory would vanish from git, and the Hugo shortcode treats a missing site
directory as a hard error rather than as "no open positions".

Its exit codes extend the validator's: 0 clean, 1 applied with rejections, 2 could
not run, 3 wipeout guard tripped. The workflow commits on 0 and 1 and stops on 2
and 3.

## How the deploy is triggered

A push made with the workflow's `GITHUB_TOKEN` does not trigger other workflows —
GitHub suppresses it to prevent recursion. Left alone, the ads would be committed
and the site would never rebuild.

The original plan was an SSH deploy key, whose pushes are not suppressed. That is
not available: deploy keys are disabled org-wide on `Kinderkrippe-Olten`, and
registering one fails with `HTTP 422`.

Instead the workflow uses the documented exception to the suppression rule:
`workflow_dispatch` and `repository_dispatch` *can* be triggered by `GITHUB_TOKEN`.
So the sync pushes with the built-in token and then runs
`gh workflow run deploy-hugo.yaml --ref "$GITHUB_REF_NAME"`.

This is better than the deploy key it replaces. No long-lived credential exists at
all, so there is nothing to leak, rotate, or silently expire — the token is
ephemeral and scoped to the run. The cost is one extra line and a
`workflow_dispatch` trigger on `deploy-hugo.yaml`, which also gives a manual Deploy
button.

It requires `permissions: contents: write` (to commit) and `actions: write` (to
dispatch) on the sync workflow.

### Two changes to deploy-hugo.yaml

`workflow_dispatch:` is added as a trigger, and the `deploy` job's condition gains
`|| github.event_name == 'workflow_dispatch'`.

The second is not cosmetic. That job was gated on `push` or `pull_request` only, so
a dispatched run would have built the site and skipped publishing it — the sync
would report success, and the site would never change. The `build` job needed no
change: it already passes on `github.ref == 'refs/heads/main'`, and `check-pr`
gates its logic at step level rather than job level, so it does not block a
dispatched run.

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

The guard lives in `apply-stellen-sync.py`, which refuses to proceed when the
validated set is empty while the repository still holds ads, and exits 3. Taking the
genuinely last ad down is then a `workflow_dispatch` run with `allow_empty` ticked.

It deliberately does *not* live in rclone. `rclone sync --max-delete` would be
useless here: the runner is ephemeral, so staging starts empty every run and sync's
deletion pass has nothing to act on. For the same reason the workflow uses
`rclone copy` rather than `sync` — the mirror's deletions happen in the repository,
where the guard can actually see them.

The guard is narrow on purpose: only the total-wipe case. Bounding deletions to "no
more than N per run" was considered and dropped — with only a handful of ads live at
any time, such a bound would trip on legitimate cleanups while adding nothing
against the failure it is meant to catch, which is an empty listing from an expired
token or a WebDAV outage.

## Secrets

| Secret | Purpose |
|---|---|
| `OPENCLOUD_WEBDAV_URL` | space URL, `https://<host>/dav/spaces/<storage-id>$<space-id>` |
| `OPENCLOUD_USER` | account the App Token belongs to |
| `OPENCLOUD_TOKEN` | OpenCloud App Token, in plain text; the workflow runs `rclone obscure` on it at runtime, since rclone expects an obscured password in config |

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
