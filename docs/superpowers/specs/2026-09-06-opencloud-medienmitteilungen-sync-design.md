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

**Only directories at that level are considered. A file sitting directly in
`Medienmitteilungen/` is ignored, not rejected** — so the authors' own instructions can
live beside the release folders where they will actually be found. This differs from
the job-ad validator, which reports a top-level file as "unexpected file at the top
level; job ads belong in a site folder". There the flat layout means a stray file is
almost certainly a misplaced ad; here the folders are the unit and a loose file at the
root is deliberate. Rejecting it would make the one obvious place to put an Anleitung
the one place that breaks the sync.

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
| `.jpg` / `.jpeg` / `.png` at the top level | Pooled with the document's own images; see "Images". |
| `meta.yaml` | Optional front-matter overrides. |
| Dot-files, `Thumbs.db` | Ignored, as in the job-ad validator. |
| Anything else | The folder is rejected. |

Zero or several documents is a rejection. A stray file of an unexpected type is
usually a mistake — a `.doc` saved in the wrong format, a `.zip` nobody unpacked — and
silently ignoring it publishes a page that is missing something.

Subdirectories are rejected. The gallery is built from the top-level images; a
`gallery/` folder in OpenCloud would be a second, conflicting way to say the same
thing.

**Rejection is inert.** A rejected folder is never created, never updated and — this
is the part that matters — **never deleted**. Any bundle already published from it
stays exactly as it is, and the report says so in as many words:
`rejected (page left as-is): 2026-09-04_hort — 2 documents`.

This diverges from the job-ad syncer, deliberately. There, `desired` is built only
from the validator's `valid` list and `removed` is `current - desired`
(`scripts/apply-stellen-sync.py`), so a PDF that exists in OpenCloud but fails
validation is deleted from the repository. For a job ad that is defensible: a
mis-named ad is not publishable and the page is regenerated from OpenCloud anyway.

Applied to `content/blog/` the same rule means somebody drags a stray file into a
folder and **a published press release disappears from the website** — a permanent URL
that has been linked to, taken down by an edit that had nothing to do with it, with a
red tick in the Actions tab as the only signal. Rejection means "I cannot read this",
which is not the same claim as "this was withdrawn". Only an absent folder is a
withdrawal. This also makes a partial rclone fetch safe for free.

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
6. A paragraph beginning `Bildlegende:` is the photo caption, with the prefix
   stripped. It becomes the inner text of the `blog-pic` shortcode that renders the
   teaser. With no such paragraph the shortcode carries an explicit `alt` set to the
   title instead, because `blog-pic.html` otherwise derives `alt` from its inner text
   and would produce an empty one.
7. `{{` in body text is escaped to `&#123;&#123;`. See "Generated content is not
   trusted markup" below — Hugo evaluates shortcodes in page content, so an
   unescaped `{{<` in a press release fails the whole site build.
8. Images are handled as described in "Images" below, and the page ends with the
   teaser's `blog-pic` at the position the document placed it, followed by
   `{{< picture-slider dir="gallery" height="250px" >}}` when the gallery is
   non-empty — as in `2026-06-25_Hagmatt_Bauernhof`.


### `.pdf`

`pdftotext -layout` for the text, `pdfimages` for the images. A PDF carries no
bold, so steps 3 and 4 above cannot run: the output is a title plus flat paragraphs.
That is a real degradation and the run log says so on every PDF, naming the `.docx`
path as the one that produces sub-headings and a lead paragraph.

Supporting PDF at all is a requirement, not a preference — some releases only ever
exist as PDF. It is supported honestly rather than by pretending the structure can be
recovered from font metrics.

## Images

Every image in the folder is a candidate, from both sources: the ones embedded in the
document and the ones sitting loose beside it. They are pooled, filtered,
de-duplicated, and then split into one teaser and a gallery.

### Extraction

`.docx`
: Pandoc's `--extract-media` output, which is the document *body*. Header and footer
  parts are not included, so a letterhead never reaches the pool.

`.pdf`
: `pdfimages -list`, then extract only the rows whose `type` is `image`. **The
  `smask` and `stencil` rows are transparency masks and stencils, not photographs.**
  A mask has the same dimensions as the image it belongs to, so a pixel-area floor
  does not remove it — the type column is the exact discriminator and a size filter
  is not a substitute for it.

Both are then filtered by a minimum pixel area, which is what removes logos, bullets
and rules. PDFs also split large images into horizontal bands; the floor removes thin
bands, and any that survive are caught by the de-duplication below or, failing that,
are visible in the run log's inventory.

### De-duplication is perceptual, and must stay that way

The document's image is usually *also* one of the loose files, because the author put
it in the document from the same camera roll. Word and PDF both re-encode and rescale
it on the way in, so **the duplicate is not byte-identical and exact comparison cannot
find it.** Measured on the sample folder:

| | dimensions | MD5 |
|---|---|---|
| `word/media/image1.jpeg` | 1385×931 | `5800d062…` |
| `IMG_0090.jpeg` | 1280×860 | `120b34a0…` |

Different bytes, different dimensions — and the same photograph. A normalised
16×16 luminance signature separates them unambiguously: `IMG_0090` scores **0.0083**
against the embedded image, and the next-nearest of the other twelve scores **0.9187**.
A 110× margin is not a threshold anyone has to tune.

This is recorded at length because the obvious "simplification" — hash the files,
drop the collisions — is provably wrong on the only real folder we have, and would
silently ship the same photo twice on every page. When duplicates are found the larger
copy by pixel count is kept.

Comparison uses Pillow and numpy, installed from apt alongside pandoc. It is the one
place these scripts take a dependency, and it buys a result no dependency-free rule
reaches.

### Teaser and gallery

The **teaser** is the document's own image — the one the author chose to place next to
the text, and the one the `Bildlegende` describes. If de-duplication matched it to a
loose file, the surviving larger copy is the teaser and the loose file does not also
appear in the gallery. If the document embeds no image at all, the alphabetically
first pooled image becomes the teaser and no `blog-pic` shortcode is emitted.

The **gallery** is everything else, in filename order.

The extension is preserved rather than forced to `.jpg`. This is a deliberate
departure from the original brief, which said `teaser.jpg`: Hugo matches `teaser.*`
(`render-blog-section.html` and the sample bundle `2026-04-23_GV` already carry a
`teaser.jpeg`), and naming a PNG `.jpg` would be a lie told to every tool that reads
the file afterwards.

A folder with no images at all is still accepted. It produces the build-time warning
`render-blog-section.html` already emits for a post with no `teaser.*`, which is the
correct outcome for a release that genuinely has no photo.

On the sample folder this yields exactly one right answer, and it is the fixture
test's acceptance criterion: **teaser = the Hort photo, gallery = 12 files, no
duplicate.**

## Generated content is not trusted markup

The workflow's order is fetch → apply → commit → push → dispatch the deploy, so
without a check the first thing to evaluate the generated Markdown would be the
production build. The job-ad syncer can afford that because it copies PDFs, which
cannot break a build. This one *generates* content, and three dialect mismatches
follow from that.

**Hugo evaluates shortcodes in page content.** A release whose text contains `{{<` —
a mail-merge remnant, or someone writing about the site itself — fails the build with
"unterminated shortcode". That does not merely lose the press release: `deploy-hugo.yaml`
fails, so the site stops updating entirely, job ads included, and the error names
`content/blog/…` rather than the document it came from. Hence the `{{` escaping in the
conversion steps.

**`config.yaml` sets `markup.goldmark.renderer.unsafe: true`.** Raw HTML that pandoc
emits for constructs Markdown cannot express — text boxes, some tables, attributed
`<div>`/`<span>` — is rendered rather than stripped. The WebSync space is
staff-writable, so this is a trusted boundary rather than an open upload form; it is
still an uninspected path from a Word file to live HTML.

**Pandoc's attribute syntax is not Goldmark's.** The sample's own output carries
`{width="6.295833333333333in" height="4.2340277777777775in"}` after the image. The
image line is replaced by a shortcode, so that instance is handled — but an attribute
pandoc emits anywhere else renders as literal junk on the page.

So the sync workflow **runs `hugo build` over the working tree after applying and
before committing.** A failure rejects the offending folder — inert, per the rejection
rule above — and the run reports it. This validates against the renderer that will
actually consume the output rather than against a list of failure modes someone
thought of in advance, and it catches malformed generated front matter for free.
`deploy-hugo.yaml` already carries the mise / Hugo-extended / dart-sass recipe to
copy.

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

Parsed with a small `^(\w+):\s*(.*)$` reader rather than PyYAML. The job-ad scripts
are deliberately dependency-free; these are not quite — de-duplication needs Pillow and
numpy — but that is one dependency bought for one result that nothing else reaches, and
it is not a reason to start adding more. If `meta.yaml` ever needs nested values, that
decision gets revisited rather than worked around.

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

**Delete.** The OpenCloud folder is **absent** and a marked bundle remains → remove
the bundle. Git history retains it, exactly as it does a withdrawn job ad. A folder
that is present but rejected is not absent; see "Rejection is inert" above.

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
- **Pandoc pinned by version and SHA-256**, installed from its GitHub release the
  way rclone already is — not from apt. `poppler-utils`, Pillow and numpy do come
  from apt.
- A `hugo build` step after applying and before committing, per "Generated content is
  not trusted markup".
- `content/blog` in place of `content/docs/stellen` in the commit paths.
- Everything else kept: the secret-presence pre-check, the pinned checksum-verified
  rclone, the App Token expiry warning, the `dry_run` and `allow_empty` inputs, the
  deploy dispatch and the stranded-commit heal.

### Pandoc must be pinned

The update pass rests on one claim — same bytes in, same Markdown out — and that is
true only for a fixed pandoc. The markdown writer's escaping, attribute emission and
list markers all move between releases. An unpinned `apt-get install pandoc` therefore
means that the day GitHub moves the `ubuntu-latest` image, every marked bundle compares
unequal and the syncer emits **one bot commit rewriting every press release on the
site**, then deploys it — a diff indistinguishable from real content changes, and if
the shift is a degradation it ships unreviewed.

`sync-stellen.yaml` already pins rclone to a version *and* a SHA-256. Pinning the tool
that copies bytes while floating the tool that generates them would be exactly
backwards. Bumping the pin then becomes a deliberate act, and the fixture diff in that
pull request is the review of what changed.

`poppler-utils` stays on apt: `pdftotext -layout` output feeds the same parser, and
drift there surfaces as a rejected or visibly wrong page rather than a silent
corpus-wide rewrite.

### One concurrency group across both syncers

`concurrency: group: websync-sync`, **shared with `sync-stellen.yaml`**, not a group of
its own.

The two syncers touch disjoint paths but they do not have disjoint branches, and
`sync-stellen.yaml`'s commit step pushes with no fetch, no rebase and no retry. Under
`set -euo pipefail` a non-fast-forward push fails the step, fails the job, and the
deploy-dispatch step never runs because it requires success — so that run's content is
not published at all until the next event or the daily heartbeat, up to 24 hours later,
with a red run nobody reads as the only trace.

That collision is the default rather than a rarity: a new dispatcher release cloned
from the existing values file inherits `heartbeat.schedule: "23 4 * * *"`, so both
dispatchers would fire in the same second every day. Serialising is the right
primitive here; the second run checks out the first's commit and proceeds normally,
and a press-release sync waiting seconds behind a job-ad sync costs nothing.

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
   `nats.durable: medien-dispatcher`, **`heartbeat.schedule: "53 4 * * *"`**; same
   `nats.url`, `watch.spaceId`, repo, ref and `existingSecret`.

   The heartbeat stagger is not cosmetic. The base chart's `"23 4 * * *"` would
   otherwise be inherited verbatim and both dispatchers would fire in the same second
   every night. The shared `concurrency` group above makes that safe rather than
   destructive, but two syncs queueing behind each other daily makes the Actions log
   harder to read than it needs to be, and the fix is one line.
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
existing pair. No pytest.

**They run in CI.** `.github/workflows/test-scripts.yaml` executes every
`scripts/test-*.py` on pull requests and pushes, using the same pinned pandoc as the
sync workflow. Today nothing runs the existing job-ad tests at all — `.github/workflows/`
holds only `deploy-hugo.yaml` and `sync-stellen.yaml` — which is tolerable for pure
Python with no external dependency and is not tolerable here: `medien_convert.py`'s
output depends on a binary that can change underneath it, and the fixture test is the
only thing that would notice. The existing job-ad tests come along for free.

`scripts/test-medien-convert.py`
: Against a fixture built from the real `20260904_MM_EröffnungHort.docx`, committed
  under `scripts/fixtures/`, asserting the acceptance criterion from "Images": teaser
  is the Hort photo, gallery is 12 files, `IMG_0090.jpeg` appears once and not twice.
  Plus synthetic cases: no images at all; a document image with no loose twin; a
  letterhead logo below the area floor; a PDF whose `pdfimages -list` includes an
  `smask` row; no address block; no `Bildlegende`; an en-dash in the title; body text
  containing `{{<`; a document that is nothing but a title.

`scripts/test-apply-medien-sync.py`
: A staging tree and a fake `content/blog/` in a temp directory, the script run as a
  subprocess. Covers create, update, no-op re-run, delete, the wipeout guard and its
  override, folder-name rejections, alias resolution, an unowned target directory, a
  detached bundle, and — the case the prefix scoping exists for — a bundle marked
  `SyncedFrom: Geschichten/…` surviving a Medienmitteilungen run untouched.

The no-op re-run is the one that matters most in practice: it is what proves conversion
is deterministic, and a regression there produces a commit on every dispatch forever.

## What this deliberately does not do

- **No image *re-encoding*.** Photos are copied to the repository byte-for-byte at
  whatever size they arrive; Hugo resizes at build time in `blog-pic.html` and
  `picture-slider.html`. Images are decoded during the run, but only to compute the
  de-duplication signature — nothing decoded is ever written out.
- **No LLM in the pipeline.** The conventions above are mechanical, testable and free.
  A model in the loop would make the output non-deterministic, which the byte-comparison
  update pass depends on not being.
- **No editing back to OpenCloud.** One direction only, as with job ads.
- **No `Group:` in the front matter.** The blog cards support a group icon below the
  site; press releases are institutional and belong to a site, not a group.
