# OpenCloud → GitHub sync for press releases (Medienmitteilungen)

Date: 2026-09-06

Second syncer against the same OpenCloud space as
[2026-08-10-opencloud-stellen-sync-design.md](2026-08-10-opencloud-stellen-sync-design.md),
triggered by the listener from
[2026-08-11-stellen-sync-trigger-design.md](2026-08-11-stellen-sync-trigger-design.md).

Read those two first. This spec records only what differs, and the differences are
substantial: the unit of sync is a folder rather than a file, the payload is
converted rather than copied, and the destination is a directory the syncer does
**not** own outright.

## Problem

Publishing a press release means hand-building a Hugo page bundle: transcribing the
`.docx` into Markdown, lifting the embedded photo out into `teaser.jpg`, dropping the
loose photos into `gallery/`, and writing front matter. It is half an hour of
mechanical work, it is done by whoever knows git, and it happens days after the press
release actually went out.

Goal: the author drops the folder they already assembled into OpenCloud, and the page
appears on the site.

## Solution overview

A second GitHub Actions workflow, `sync-medienmitteilungen.yaml`, built to the same
shape as `sync-stellen.yaml`: pull the folder over WebDAV with rclone into a staging
directory, apply it to the repository with a Python script, commit, dispatch the
deploy. Same space, same secrets, same App Token expiry warning, same stranded-commit
heal.

A second Helm release of the existing `stellen-dispatcher` chart watches the new
folder and dispatches the new workflow. No chart logic changes.

## Folder mapping

```
OpenCloud space (WebSync)                    repository
  .space/                     (ignored)
  Stellenanzeigen/            (the other syncer's; untouched here)
  Geschichten/                (a future syncer's; untouched here)
  Medienmitteilungen/
    2026-09-04_hort/  ──────────────────▶    content/blog/2026-09-04_Hort/
      20260904_MM_EröffnungHort.docx           index.md
        └ word/media/image1.jpeg               teaser.jpg
      IMG_0083.jpeg … (13 files)               gallery/IMG_0083.jpeg …
      meta.yaml         (optional)
```

`OPENCLOUD_PATH: Medienmitteilungen` in the workflow, so the layout stays visible in
review rather than baked into the URL secret — same reasoning as for `Stellenanzeigen`.

### Folder name grammar

```
YYYY-MM-DD _ <location> [ _ <topic> ]…
```

- The date becomes `Date:` in the front matter. It must parse as a real calendar date.
- `<location>` resolves, case-insensitively, against the site keys in `data/sites.yaml`
  plus an alias map in a new `data/medienmitteilungen.yaml` (`hort: bifang-säli`). It
  becomes `Site:`. A location that resolves to nothing is a rejection, not a guess —
  adding a site stays a deliberate repository change, as it is for job ads.

  ```yaml
  # data/medienmitteilungen.yaml
  # Folder-name tokens that are not themselves keys in data/sites.yaml.
  aliases:
    hort: bifang-säli
  ```
- Further `_`-separated tokens are free text. They do not affect the front matter; they
  exist so two releases on the same day do not collide and so the URL can say what the
  page is about.

The destination directory is the folder name with each token after the date
title-cased: `2026-09-04_hort` → `content/blog/2026-09-04_Hort`, which is the
convention the hand-made bundles already follow (`2026-06-25_Hagmatt_Bauernhof`).
Nothing depends on being able to reverse that transformation — see the marker below.

### Folder contents

| Found | Treatment |
|---|---|
| Exactly one `.docx` **or** one `.pdf` | The document. Required. |
| `.jpg` / `.jpeg` / `.png` at the top level | Copied verbatim into `gallery/`. |
| `meta.yaml` | Optional front-matter overrides. |
| Dot-files, `Thumbs.db` | Ignored, as in the job-ad validator. |
| Anything else | The folder is rejected. |

Zero or several documents is a rejection. A stray file of an unexpected type is
usually a mistake — a `.doc` saved in the wrong format, a `.zip` nobody unpacked — and
silently ignoring it publishes a page that is missing something.

Subdirectories are rejected. The gallery is built from the top-level images; a
`gallery/` folder in OpenCloud would be a second, conflicting way to say the same
thing.

## What the syncer owns

This is the part that has no counterpart in the job-ad syncer, and it is the reason
this spec exists rather than a copy of that one with the paths changed.

`content/docs/stellen/<site>/` belongs to the job-ad syncer wholesale. Every file in it
came from OpenCloud, so "delete what OpenCloud no longer has" is safe by construction.

`content/blog/` does not work that way. It holds nineteen hand-made page bundles —
`2024-03-18_Osterprojekt`, `Impressionen_Sonnhalde`, and so on — that predate this
syncer and will outlive it. A mirror applied naively to that directory deletes every
one of them on its first run.

So each generated bundle carries an ownership marker in its front matter, naming the
OpenCloud folder it came from:

```yaml
SyncedFrom: Medienmitteilungen/2026-09-04_hort
```

The update and delete passes consider **only** bundles carrying a `SyncedFrom` under
this syncer's own prefix. So does the wipeout guard.

**Scoped by prefix, not merely present.** A third syncer is planned for
`WebSync/Geschichten/`, writing into this same `content/blog/`. If the test were "has a
`SyncedFrom`", the Medienmitteilungen run would find a Geschichten post's marker
matching nothing in its staging set and delete it — and the Geschichten run would do
the same in reverse, so the two would take turns deleting each other's work on every
dispatch. The prefix check costs one string comparison and is the reason that cannot
happen. It is load-bearing now, not a provision for later.

Front matter rather than a side-car manifest because Hugo ignores unknown params, the
marker travels with the thing it describes, it is visible in review and in `git log`,
and there is no second file to drift out of step with the tree.

Two rules follow from the marker, and both are worth having:

**A target directory that exists without a matching marker is never touched.** It is
reported as "exists, not owned" and skipped. A hand-made post cannot be eaten by a path
collision, and the first run of this syncer cannot damage anything.

**Deleting the marker line detaches the bundle.** The syncer stops touching it and will
never delete it. This is the escape hatch a mirror otherwise lacks. Generated prose
sometimes needs a human fix — a link, a hyphen, a name spelled properly — and without
detachment that fix is silently reverted on the next dispatch, which is a bad thing to
learn by watching it happen. The cost is that the page and the OpenCloud folder then
diverge permanently, which is exactly what was asked for.

## Document conversion

The conversion is deterministic and stateless: same bytes in, same Markdown out. The
mirror below depends on that, because it detects changes by regenerating and comparing.

### `.docx`

```
pandoc -f docx -t markdown-smart --wrap=none --extract-media=<tmp> <file>
```

`markdown-smart` rather than plain `markdown`: the plain writer renders the document's
en-dash as `--`, and the site's other posts contain real `–`.

Against the resulting block sequence:

1. A leading `MEDIENMITTEILUNG` marker line is dropped. It is a label on the paper
   document, not part of the text.
2. The first remaining block is the **title**. It becomes both `Title:` in the front
   matter and the `#` heading, matching every hand-made post.
3. The next block, if bold, is the **lead paragraph** and stays bold — the house style,
   as in `2025-12-04_Hort`.
4. Later blocks that are entirely bold become `##` sub-headings.
5. The **address block is dropped**. `--wrap=none` puts each paragraph on one line and
   renders in-paragraph hard breaks as a trailing `\`, so the address arrives as a single
   block of backslash-separated lines. It is identified by one of those lines matching a
   Swiss postcode and town — `^\d{4}\s+[A-ZÄÖÜ]`, spelled out rather than `\p{Lu}`,
   which Python's `re` does not support — and only that block is removed. Deliberately
   not "everything from the address to the end of the document": in the sample the image
   and its caption follow the address, and a drop-to-end rule would silently lose the
   photo. Splitting on the hard breaks rather than searching the whole block also keeps
   a body sentence that happens to mention `4600 Olten` from being mistaken for it.
6. The embedded image becomes `teaser.<ext>`, emitted at the position it occupied in
   the document as `{{< blog-pic src="teaser.jpeg" … >}}` — the `src` naming whatever
   extension the image actually has.
7. A paragraph beginning `Bildlegende:` is that caption, with the prefix stripped and
   the remainder as the shortcode's inner text. With no such paragraph the shortcode is
   emitted with an explicit `alt` set to the title instead, because `blog-pic.html`
   otherwise derives `alt` from its inner text and would produce an empty one.
8. Loose images become `gallery/`, and
   `{{< picture-slider dir="gallery" height="250px" >}}` is appended, as in
   `2026-06-25_Hagmatt_Bauernhof`.
9. **If the document embeds no image**, the alphabetically first gallery image is
   copied to `teaser.<ext>` as well, and no `blog-pic` shortcode is emitted. Not a
   detail: `render-blog-section.html` warns at build time when a post has no
   `teaser.*`, and the blog card renders with an empty media area. A folder with
   neither an embedded image nor a loose one is still accepted — it produces exactly
   that warning, which is the correct outcome for a release that genuinely has no
   photo.

The extension is preserved rather than forced to `.jpg`. This is a deliberate
departure from the original brief, which said `teaser.jpg`: Hugo matches `teaser.*`
(`render-blog-section.html` and the sample bundle `2026-04-23_GV` already carry a
`teaser.jpeg`), and naming a PNG `.jpg` would be a lie told to every tool that reads the
file afterwards.

More than one embedded image is a rejection. Picking the first and discarding the rest
would drop content silently, and the author cannot tell from the website that it
happened.

### `.pdf`

`pdftotext -layout` for the text, `pdfimages` for the embedded image. A PDF carries no
bold, so steps 3 and 4 above cannot run: the output is a title plus flat paragraphs.
That is a real degradation and the run log says so on every PDF, naming the `.docx`
path as the one that produces sub-headings and a lead paragraph.

Supporting PDF at all is a requirement, not a preference — some releases only ever
exist as PDF. It is supported honestly rather than by pretending the structure can be
recovered from font metrics.

## `meta.yaml`

Optional, and flat:

```yaml
TeaserTitle: Eröffnung Hort
Autor: Melanie von Arx
Site: bifang-säli
```

All three keys are optional and all three override what would otherwise be derived.
`Site` overrides the folder-name mapping for the case a release genuinely belongs to a
site the folder name does not name.

Defaults when it is absent: `Autor` from the document's own metadata (`dc:creator` in
`docProps/core.xml`, `/Author` in a PDF), and `TeaserTitle` omitted entirely — Hugo's
`render-blog-section.html` already falls back to `Title`.

**`meta.yaml` is the only durable place for these.** `index.md` is regenerated on every
change, so a `TeaserTitle` typed into it by hand survives exactly until the next
dispatch. That matters more than it sounds: press-release titles run long, and the blog
card is 400px wide, so `TeaserTitle` is the field most likely to be wanted. The
author-facing documentation has to lead with this.

Parsed with a small `^(\w+):\s*(.*)$` reader rather than PyYAML, keeping the scripts
dependency-free as the job-ad scripts deliberately are. If `meta.yaml` ever needs
nested values, that decision gets revisited rather than worked around.

## Mirror semantics

OpenCloud is the source of truth, as it is for job ads.

**Create.** No target directory → generate the bundle.

**Update.** Regenerate the whole bundle into a temporary directory and compare
file-by-file against the target, copying only what differs and removing generated files
that no longer exist. Conversion is deterministic and images are copied verbatim, so a
byte comparison is exact — there is no stored hash or timestamp to go stale, and the
comparison answers "is the repository what the source implies" rather than "has
something been touched".

`index.md`, `teaser.*` and the entire contents of `gallery/` are generated, so all
three are mirrored — including deleting gallery images removed in OpenCloud.

**Delete.** The OpenCloud folder is gone and a marked bundle remains → remove the
bundle. Git history retains it, exactly as it does a withdrawn job ad.

**Wipeout guard.** An empty validated set while marked bundles still exist is refused,
because that is what an expired token or a WebDAV outage looks like. `--allow-empty`
overrides, exposed as the workflow's `allow_empty` input. The guard counts marked
bundles only; the nineteen hand-made posts are not a safety net and must not be
mistaken for one.

### Exit status

Unchanged from `apply-stellen-sync.py`, because the workflow logic that consumes it is
the same:

| | |
|---|---|
| 0 | applied cleanly |
| 1 | applied, but at least one folder was rejected — commit, then fail the run |
| 2 | could not run; the repository is untouched |
| 3 | refused: the wipeout guard tripped |

One malformed folder must not hold up everybody else's release, which is why 1 commits.

## Code layout

Three modules, split where the seams actually are:

`scripts/medien_convert.py`
: Document → Markdown plus extracted images. Pure: takes bytes and a destination
  directory, knows nothing about git, the repository layout or OpenCloud. All the
  heuristics above live here, and so does all the risk, which is why it is the piece
  that can be tested exhaustively against the real `.docx` without a repository tree.

`scripts/blog_mirror.py`
: The create/update/delete pass over `content/blog/`: marker reading and writing,
  prefix scoping, byte comparison, the wipeout guard, the report. Knows nothing about
  Word, PDF or press releases.

`scripts/apply-medien-sync.py`
: Thin glue and the CLI: walk the staging tree, validate folder names against
  `data/sites.yaml` and the alias map, call the converter, hand the result to the
  mirror.

The split between the first two is where the planned `WebSync/Geschichten/` syncer
comes in: it is expected to reuse `blog_mirror.py` unchanged and supply its own
converter. That is the extent of the provision made for it. No plugin registry, no
converter dispatch table, no abstract base class — its input format is not yet known,
and a framework designed against one example and one guess would be wrong in ways that
are expensive to undo. When it arrives it gets its own spec.

## Workflow

`.github/workflows/sync-medienmitteilungen.yaml`, cloned from `sync-stellen.yaml`:

- `OPENCLOUD_PATH: Medienmitteilungen`.
- An added step installing `pandoc` and `poppler-utils` from apt, rather than relying
  on what happens to be in the runner image.
- `content/blog` in place of `content/docs/stellen` in the commit paths.
- Everything else kept: the secret-presence pre-check, the pinned checksum-verified
  rclone, the App Token expiry warning, the `dry_run` and `allow_empty` inputs, the
  deploy dispatch and the stranded-commit heal.

Its own `concurrency` group. The two syncers touch disjoint paths and must not queue
behind each other.

The `schedule` stays as the same weak third net it is for job ads, with the same caveat
recorded there: GitHub disables scheduled workflows in public repositories after 60
days of inactivity, so it is a visible-failure backstop and not a mechanism to rely on.

Kept deliberately identical rather than factored into a reusable workflow. The two
share their shape but not their logic, and a shared workflow would couple a job-ad
publish to a press-release bug.

## Dispatcher (`oep-k8s`)

A **second Helm release of the existing chart**, not a change to it. `watch.path`,
`github.workflow` and `nats.durable` are already values, and the ApplicationSet
resolves `customers/<customer>/services/<name>/values.yaml` by convention.

1. `customers/kko/services/medien-dispatcher/values.yaml` — `watch.path:
   Medienmitteilungen`, `github.workflow: sync-medienmitteilungen.yaml`,
   `nats.durable: medien-dispatcher`; same `nats.url`, `watch.spaceId`, repo, ref and
   `existingSecret`.
2. `customers/kko/customer.yaml` — a service entry alongside `stellen-dispatcher`,
   `releaseName: kko-medien-dispatcher`, cross-referencing this spec.
3. `clusters/talos-volki-01/cluster_config/monitoring/medien-dispatcher-alerts.yaml` —
   a sibling of the existing three rules, against the new deployment and CronJob names.

**The `nats.durable` override is load-bearing.** Two releases sharing one durable
consumer would not each see the stream; JetStream would *split* it between them,
delivering each message to exactly one pod. Press-release events would land at random
in the job-ad dispatcher and be dropped, and job-ad events in the press-release
dispatcher — intermittently, in proportion to how many pods are up, which is the
hardest possible failure to reproduce. Separate durables give each release its own
independent view of `main-queue`.

Both releases mount the same `stellen-dispatcher-github` sealed Secret. It is sealed
`--scope strict` to name and namespace, both unchanged, and the PAT already carries
`Actions: write` on the one repository that holds both workflows. Nothing to reseal.

`stellen-dispatcher` itself is not touched: no consumer rename, so no ack-floor reset
and no replay of up to seven days of retained events. This is why a second release
beats extending the existing one into a two-prefix watcher, which was the first
proposal — that would have needed changes to `filter.jq`, to `test-filter.sh`, and to
the debounce and rate-limit logic, all in code that is currently correct.

The one change to the shared chart is cosmetic: `files/listen.sh` hardcodes the
dispatch reason as `"job-ad change under $WATCH_PATH"`, which is wrong in the log of
every press-release dispatch. It becomes `"change under $WATCH_PATH"`.

The cost of a second pod is 10m CPU and 32Mi, plus a fourteenth durable consumer on a
stream that already carries thirteen.

## Testing

Plain self-checking scripts run as `python3 scripts/test-<name>.py`, matching the
existing pair. No pytest, no dependencies.

`scripts/test-medien-convert.py`
: Against a fixture built from the real `20260904_MM_EröffnungHort.docx`, committed
  under `scripts/fixtures/`, plus synthetic cases: no embedded image; two embedded
  images (rejected); no address block; no `Bildlegende`; a PDF; an en-dash in the
  title; a document that is nothing but a title.

`scripts/test-apply-medien-sync.py`
: A staging tree and a fake `content/blog/` in a temp directory, the script run as a
  subprocess. Covers create, update, no-op re-run, delete, the wipeout guard and its
  override, folder-name rejections, alias resolution, an unowned target directory, a
  detached bundle, and — the case the prefix scoping exists for — a bundle marked
  `SyncedFrom: Geschichten/…` surviving a Medienmitteilungen run untouched.

The no-op re-run is the one that matters most in practice: it is what proves conversion
is deterministic, and a regression there produces a commit on every dispatch forever.

## What this deliberately does not do

- **No image processing.** Photos are copied at whatever size they arrive; Hugo already
  resizes at build time in `blog-pic.html` and `picture-slider.html`.
- **No LLM in the pipeline.** The conventions above are mechanical, testable and free.
  A model in the loop would make the output non-deterministic, which the byte-comparison
  update pass depends on not being.
- **No editing back to OpenCloud.** One direction only, as with job ads.
- **No `Group:` in the front matter.** The blog cards support a group icon below the
  site; press releases are institutional and belong to a site, not a group.
