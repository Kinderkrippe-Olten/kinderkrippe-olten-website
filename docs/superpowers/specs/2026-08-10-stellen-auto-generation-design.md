# Auto-generated "Offene Stellen" page

Date: 2026-08-10

## Problem

`content/blocks/stellen.md` hand-maintained a markdown list of job-posting links.
Every link duplicated a filename in `content/docs/stellen/`. The two drifted: at the
time of writing the directory held 10 PDFs of which only 4 were linked; the other 6
were expired postings nobody removed.

Goal: the rendered page is derived from the files present in the directory, so adding
a PDF adds an entry and deleting a PDF removes one. This must work identically in a
local checkout and in the GitHub Actions build.

## Solution overview

A Hugo shortcode reads the job-posting directories at build time and renders the list.
No external scripts, no generated files committed to the repo, no change to
`.github/workflows/deploy-hugo.yaml`.

Three moving parts:

1. **Directory layout** — one directory per site, holding that site's PDFs.
2. **`data/stellen.yaml`** — declares which sites exist, their heading, and their order.
3. **`layouts/_shortcodes/stellen.html`** — reads the directories and emits the HTML.

## Directory layout

```
content/docs/stellen/
  bifang-säli/
    .gitkeep
    bifang-säli 20260617 Aushilfe (kein Fixpensum) per 1.8.2026.pdf
    bifang-säli 20260805 Pädagogische Fachperson (30 – 50%) per 1.9.2026.pdf
  hagmatt/
    .gitkeep
    hagmatt 20260423 Aushilfe per sofort.pdf
  sonnhalde/
    .gitkeep
    sonnhalde 20260728 Koch oder Köchin (10% und Ferienvertretung) per 1.9.2026.pdf
```

`.gitkeep` exists so a site directory with no open positions survives in git. Git does
not track empty directories, and without the placeholder a job-free site would vanish
from the repository — and therefore from the page — instead of showing "Zur Zeit keine
offenen Stellen."

### No archive directory

Taking a posting down means deleting the PDF. There is no `archiv/` folder, because
git history already retains every deleted PDF permanently — `git log --diff-filter=D`
finds them and `git show <rev>:<path>` restores one. A second copy inside the working
tree would add a folder to maintain without adding any recoverability.

This also keeps the author's workflow inside the GitHub web UI, which is the point:
GitHub's web editor cannot rename or move binary files (the edit pencil is disabled for
PDFs), so "move to archive" is not a gesture available in the browser. Deleting is.

The six expired PDFs that were in the directory were removed in this change and remain
recoverable from the commit that removed them.

## Filename convention

```
<site><sep><YYYYMMDD><sep><link text>.pdf
```

- `<site>` — the containing directory's name, compared **case-insensitively**.
  `Bifang-Säli 20260617 ….pdf` and `bifang-säli 20260617 ….pdf` are both accepted.
- `<sep>` — a single space, `-`, or `_`.
- `<YYYYMMDD>` — exactly 8 digits. This is the *posting* date and drives sort order.
  It is deliberately not the start date; the start date belongs in the link text, where
  it can be phrased freely ("per 1.9.2026", "per sofort").
- `<link text>` — everything up to `.pdf`, used verbatim as the anchor text. Spaces,
  parentheses, `%`, en-dashes and umlauts are all permitted.

Example:

```
sonnhalde 20260728 Koch oder Köchin (10% und Ferienvertretung) per 1.9.2026.pdf
```

renders as

```html
<li><a href="…">Koch oder Köchin (10% und Ferienvertretung) per 1.9.2026</a></li>
```

The site prefix is redundant with the directory as far as rendering goes. It is
required anyway because it makes a file self-describing wherever it ends up — in a
download folder, in an e-mail attachment, in a git diff — and because it lets the
shortcode catch a PDF dropped into the wrong site directory.

### Parsing

For each `*.pdf` in a site directory, in this order:

1. Strip the `.pdf` extension.
2. Case-insensitively match the directory name as a prefix.
3. Expect exactly one separator character.
4. Expect the next 8 characters to be digits.
5. Expect one more separator character.
6. The remainder is the link text, which must be non-empty.

Non-`.pdf` files (notably `.gitkeep`) are ignored silently.

Any other file **fails the build** via `errorf`, with a message naming the file and
what was expected. This is deliberate. The person managing the job ads works through
the GitHub web UI and never reads a build log, so a warning would be invisible and a
mistyped filename would simply mean the ad never appears. A failed Actions run is
visible: it shows a red ❌ on the commit and sends an e-mail.

The cost is that one bad filename blocks the whole deploy until it is corrected. That
is the intended trade: a blocked deploy gets fixed, a silently missing job ad does not.

## `data/stellen.yaml`

```yaml
- dir: bifang-säli
  title: Hort Bifang-Säli
- dir: hagmatt
  title: Kita Hagmatt
- dir: sonnhalde
  title: Kita Sonnhalde
```

This file, not the directory listing, is the source of truth for which sections appear
and in what order. Three reasons it cannot be derived:

- A site with no open positions has no files to discover, but must still render its
  heading and the "keine offenen Stellen" line.
- The headings ("Kita Hagmatt", "Kita Sonnhalde") do not match the `Name` values in
  `data/sites.yaml` ("Hagmatt", "Sonnhalde").
- The page's section order (Hort, Hagmatt, Sonnhalde) differs from the order in
  `data/sites.yaml`.

Adding a fourth site means adding one entry here and one directory containing a
`.gitkeep`. A directory listed here but missing from disk fails the build.

## `layouts/_shortcodes/stellen.html`

For each entry in `hugo.Data.stellen`, in file order:

1. Emit `<h2 id="{{ .title | anchorize }}">{{ .title }}</h2>`. Goldmark's auto heading
   IDs previously produced `<h2 id="hort-bifang-säli">`; `anchorize` reproduces that
   string exactly (verified), so the headings come out unchanged.
2. `os.ReadDir` the directory `content/docs/stellen/<dir>`, guarded by `os.FileExists`
   — `os.ReadDir` on a missing path is a hard build error, not an empty result.
3. Keep `.pdf` files and parse each per the rules above.
4. Sort by `"<date> <link text>"` descending — newest posting first within each site,
   with the link text as a tiebreaker so the output is deterministic.
5. If the result is empty, emit `<p>Zur Zeit keine offenen Stellen.</p>`. Otherwise emit
   a `<ul>` with one `<li>` per posting, containing an `<a>` with the link text and
   nothing else.

`hugo.Data` is used rather than `site.Data`, which is deprecated as of Hugo v0.156.0.
The CI workflow pins Hugo 0.158.0, so `hugo.Data` is available there.

Earlier versions appended a constant `<br>oder nach Vereinbarung` to every entry,
matching the four hand-written entries this generator replaced. Removed on the
customer's request (2026-08-14): anything of the sort now belongs in the link text,
where the filename controls it per ad.

Offsets are computed with `strings.RuneCount`, not `len`. Hugo's `substr` is rune-based
while `len` returns bytes, and `bifang-säli` is 11 runes but 12 bytes.

### href construction

`/docs/stellen/<dir>/<filename>`, with `<dir>` and `<filename>` each encoded as:

```
replace (urlquery $segment) "+" "%20"
```

`urlquery` is Go's query escaper, which percent-encodes UTF-8 correctly but renders
spaces as `+`. Since a literal `+` in a filename is already escaped to `%2B` by that
point, replacing the remaining `+` with `%20` is unambiguous.

Verified output for the worst-case filename:

```
Pädagogische Fachperson (30 – 50%) per 1.9.2026.pdf
→ P%C3%A4dagogische%20Fachperson%20%2830%20%E2%80%93%2050%25%29%20per%201.9.2026.pdf
```

This matches the encoding Goldmark already applied to the previous link
(`Hort-P%C3%A4dagogische-Fachperson-20260805.pdf`), and leaves pure-ASCII names such as
`Hort-Aushilfe-20260617.pdf` untouched.

The assembled markup is emitted through `safeHTML` so the already-encoded href is not
escaped a second time.

## `content/blocks/stellen.md`

Shrinks to:

```markdown
---
Title: Freie Stellen
---
<h1><a name="stellen" style="color: inherit; text-decoration: inherit">Offene Stellen</a></h1>

{{< stellen >}}
```

The `<h1>` and its `name="stellen"` anchor stay hand-written: `data/menu.yaml` links to
`/angebot#stellen`.

The shortcode is called with `{{< >}}` (not `{{% %}}`) and emits HTML directly, so its
output is not re-processed by Goldmark.

## Local and CI equivalence

`os.ReadDir` is a Hugo built-in resolved against the project root. The GitHub Actions
workflow runs `hugo` against a fresh checkout of the same tree, so it sees exactly the
same files. Nothing is generated ahead of time, nothing is committed that could go
stale, and `.github/workflows/deploy-hugo.yaml` is untouched.

### Known limitation: `hugo server` does not live-reload the list

Adding or deleting a PDF while `hugo server` is running does **not** update the page.
The server notices the file (`Source changed …`) and rebuilds, but the rendered list is
unchanged, because `os.ReadDir` is not registered as a template dependency and Hugo
therefore never re-renders the page that calls it. Touching `content/blocks/stellen.md`
or `content/angebot.md` does not help either. **Restart `hugo server`.**

This affects local preview only. A fresh `hugo build` — which is what CI runs — is
always correct.

The obvious alternative was tried and rejected: making `content/docs/stellen/` a branch
bundle and enumerating `.Resources`, which Hugo does track. Hugo's own `.RelPermalink`
fails outright on these filenames:

```
error calling RelPermalink: parse "/docs/stellen/bifang-säli/bifang-säli 20260805
Pädagogische Fachperson (30 – 50%) per 1.9.2026.pdf": invalid URL escape "%) "
```

The `urlquery`-based encoding used here handles filenames that Hugo's built-in
permalink cannot, so `os.ReadDir` stays and the restart is accepted as the cost.

## Intended deviations from the previous output

Everything in the rendered block is unchanged except:

- Hort entries are now newest-first.
- `</br>` became `<br>`. The previous output contained the invalid closing tag
  literally, because the markdown source did and `unsafe: true` passed it through.
- The three commented-out `<!-- Zur Zeit keine offenen Stellen. -->` placeholders are
  gone; the shortcode emits the real line when a site is empty.
- The four hrefs point at the new per-site paths.

The `<h2 id="…">` elements are byte-identical.

## Verification performed

1. Built before and after; inspected the rendered block and confirmed only the
   deviations listed above.
2. Confirmed all four generated hrefs resolve to files actually published under
   `public/docs/stellen/`, including the name containing `%`, an umlaut and an en-dash.
3. Deleted a PDF, rebuilt, confirmed its entry disappeared.
4. Emptied a site directory down to its `.gitkeep`, rebuilt, confirmed the heading
   remained and "Zur Zeit keine offenen Stellen." appeared.
5. Added a PDF with a wrong site prefix and one with no date; confirmed each fails the
   build with a message naming the file (exit status 1).
6. Confirmed the clean tree builds with exit status 0 and no `stellen:` diagnostics.
7. Confirmed no references to the old `/docs/stellen/<Site>-<Role>-<date>.pdf` paths
   remain anywhere in the built site.

## Out of scope

- Expiring postings automatically by date. Taking a posting down stays a manual delete.
- Any change to how other `content/docs/` subdirectories are linked.
- A GitHub Action that moves deleted PDFs into an archive folder. Considered and
  rejected along with the archive folder itself; see "No archive directory".
