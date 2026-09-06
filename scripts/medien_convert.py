#!/usr/bin/env python3
"""Turn a press-release .docx or .pdf, plus the photos beside it, into a Hugo page body.

Pure with respect to the repository: it reads a document and a list of image paths and
writes into a destination directory. It knows nothing about git, content/blog/ or
OpenCloud.

Conversion must be DETERMINISTIC -- the mirror detects change by regenerating and
comparing bytes. That is why the workflow pins pandoc by version and checksum.
"""

import collections
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


def _run(cmd):
    """Run a converter, reporting its failure as something the author can act on.

    Every external tool here is reached through convert(), and convert()'s caller
    rejects one folder on ConversionError. A bare CalledProcessError would escape
    that and take the whole sync run down over one unreadable document.
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise ConversionError(
            f"{cmd[0]} is not installed on the machine running the sync") from None
    except subprocess.CalledProcessError as e:
        last = [x for x in (e.stderr or "").strip().splitlines() if x.strip()]
        raise ConversionError(
            f"{cmd[0]} could not read the document"
            + (f": {last[-1].strip()}" if last else "")) from e


def docx_to_markdown(path, media_dir):
    """Pandoc's Markdown for a .docx, with body images extracted into media_dir.

    markdown-smart, not markdown: the plain writer turns the document's en-dash into
    '--', and every other post on this site carries a real en-dash.
    """
    return _run(
        ["pandoc", "-f", "docx", "-t", "markdown-smart", "--wrap=none",
         f"--extract-media={media_dir}", path]).stdout


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


def shape_document(text):
    """(title, body blocks, caption, index in blocks where the image sat)."""
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
        inner = _bold_inner(block)
        if inner is None:
            body.append(_escape(block))
        elif not body:
            body.append("**" + _escape(inner) + "**")   # the lead paragraph
        else:
            body.append("## " + _escape(inner))          # a sub-heading
    return title, body, caption, image_at


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
    text and the one the Bildlegende describes. Where a loose file is the same photo
    as the document's own image, the higher-resolution copy becomes the teaser; where
    a loose file duplicates one of the document's *other* images, the loose copy is
    dropped and the document's own copy stands in the gallery unconditionally.
    """
    docs = [p for p in doc_images if _pixels(p) >= min_pixels]
    loose = [p for p in loose_images if _pixels(p) >= min_pixels]
    sigs = {p: signature(p) for p in docs + loose}

    teaser = docs[0] if docs else None
    gallery = []
    teaser_twins = [teaser] if teaser is not None else []
    for p in loose:
        twin = next((d for d in docs if distance(sigs[p], sigs[d]) < threshold), None)
        if twin is None:
            gallery.append(p)
        elif twin == teaser:
            teaser_twins.append(p)      # a rescaling of the teaser photo: competes below
        # else: a duplicate of some other document image (docs[1:]) -- dropped. That
        # document image already stands in the gallery via the extend() below.
    if teaser_twins:
        # Resolved after the loop, from every twin found, rather than swapped in as
        # each loose file is seen -- so the winner is the sharpest copy of the photo
        # and does not depend on the order loose_images happened to arrive in.
        # (Comparing to the *original* docs[0] mid-loop, once a swap had already
        # happened, silently stopped later swaps from ever being considered.)
        # The basename is a third, stable key: two loose twins can tie on pixel
        # count without either being docs[0], and without it max() would fall
        # back to first-occurrence, reopening the same order-dependence.
        teaser = max(teaser_twins,
                     key=lambda p: (_pixels(p), p == docs[0], os.path.basename(p)))
    gallery.extend(d for d in docs[1:] if d != teaser)

    gallery.sort(key=os.path.basename)
    if teaser is None and gallery:
        teaser = gallery.pop(0)
    return teaser, gallery


# --- PDF ------------------------------------------------------------------
#
# pdftotext cannot be used here. Measured on the sample release it emits no blank
# line between paragraphs -- with -layout, without it, and on a source typeset with
# parskip -- so _blocks() sees one single block, shape_document takes the whole
# document as the title, and the page comes out empty under a page-long heading.
#
# pdftohtml -xml keeps the two things pdftotext throws away: the vertical position
# of every typeset line, and <b> markup. From those the text can be rebuilt in the
# shape pandoc already gives a .docx -- paragraphs separated by blank lines, a
# wholly-bold paragraph wrapped in ** -- and handed to the same shape_document. So
# a PDF does carry bold, and the label drop, title, lead, sub-headings, address
# removal and Bildlegende extraction all work for PDF with no second implementation.

# pdftohtml reports the top of each line's box, and that moves by a unit or two with
# the tallest glyph on the line: the sample's single line spacing arrives as both 17
# and 18. A gap within this much of the pitch is still ordinary line spacing.
LINE_JITTER = 1.1
# A line that stops well short of the widest line in the document was not wrapped by
# the typesetter -- the author ended it, as in the address block. Emitting a Markdown
# hard break there is what pandoc does for a Word line break, and it is what lets
# _is_address() see the postcode on a line of its own.
#
# Set well below the midpoint the sample suggests (its shortest wrapped line is 0.99
# of the measure, its longest hand-broken one 0.27). The sample is justified LaTeX,
# where every wrapped line is full; a real upload is a Word export, which is
# ragged-right, and there a German compound routinely leaves a wrapped line at 0.7-0.8
# of the measure. The two errors are not equal, so the bias is deliberate: reading a
# WRAPPED line as hand-broken puts a break inside running prose and -- if the next
# line opens with a postcode -- makes _is_address() drop that whole paragraph from the
# page, silently. Reading a HAND-BROKEN line as wrapped only leaves an address block
# visible where it should have been dropped.
FULL_MEASURE = 0.6


def pdf_xml(path, work_dir):
    """pdftohtml's XML for a PDF: one element per typeset line, plus <image>.

    Written to a named output in work_dir rather than read from -stdout: pdftohtml
    always writes out the images it finds beside its output, and with -stdout that
    is beside the PDF -- which here is the author's own upload folder, where the
    next run would pick the leftovers up as loose photos. They are not used at all
    (pdf_images does that job, with pdfimages) and go with the work directory.
    """
    out = os.path.join(work_dir, "doc")
    _run(["pdftohtml", "-xml", path, out])
    with open(out + ".xml", encoding="utf-8") as fh:
        return fh.read()


def _pdf_runs(elem, bold=False):
    """The (bold, text) runs of one <text> element, flattening its markup."""
    runs = []
    if elem.text:
        runs.append((bold, elem.text))
    for child in elem:
        runs.extend(_pdf_runs(child, bold or child.tag == "b"))
        if child.tail:
            runs.append((bold, child.tail))
    return runs


def _pdf_items(xml_text):
    """Per page, its text lines and images in reading order.

    ElementTree resolves the XML entities pdftohtml writes (&amp;, &#160;), so the
    text arrives as the characters the document actually holds.
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ConversionError(f"the PDF's text could not be read: {e}") from e
    pages = []
    for page in root.iter("page"):
        items = []
        for el in page:
            top, left = int(el.get("top", 0)), int(el.get("left", 0))
            if el.tag == "text":
                items.append({"kind": "text", "top": top, "left": left,
                              "right": left + int(el.get("width", 0)),
                              "runs": _pdf_runs(el)})
            elif el.tag == "image":
                items.append({"kind": "image", "top": top, "left": left,
                              "src": el.get("src", "")})
        items.sort(key=lambda it: (it["top"], it["left"]))
        pages.append(items)
    return pages


def _line_pitch(pages):
    """The body line pitch: the most common gap between consecutive text lines.

    Derived from the document rather than fixed, so it holds for any point size.
    Ties break on the smaller gap, because conversion must be deterministic.
    """
    gaps = collections.Counter()
    for items in pages:
        tops = sorted({it["top"] for it in items if it["kind"] == "text"})
        for a, b in zip(tops, tops[1:]):
            gaps[b - a] += 1
    return min(gaps, key=lambda g: (-gaps[g], g)) if gaps else 0


def _line_gaps(pages):
    """The vertical gaps between consecutive text lines, as the paragraph loop sees
    them: never across a page boundary, never across an image."""
    gaps = []
    for items in pages:
        prev = None
        for it in items:
            if it["kind"] != "text":
                prev = None
                continue
            if prev is not None:
                gaps.append(it["top"] - prev["top"])
            prev = it
    return gaps


def _paragraph_gap(pages, pitch):
    """The vertical gap above which a line starts a new paragraph.

    Placed midway between the two clusters the document itself reveals -- its line
    spacing, and the smallest gap materially larger than that -- rather than at a
    fixed multiple of the pitch. Measured on the sample, a fixed 1.4x pitch landed
    7.2 units above the line spacing but only 0.8 units below the real paragraph gap
    of 26. One unit of rounding in the pitch, from a slightly larger point size, and
    every paragraph break in the document would have been missed -- the single-block
    collapse this whole code path exists to avoid. Derived, the sample's margin is
    4.0 units on each side.
    """
    gaps = _line_gaps(pages)
    spacing = [g for g in gaps if g <= pitch * LINE_JITTER]
    apart = [g for g in gaps if g > pitch * LINE_JITTER]
    if not apart:
        return float("inf")     # one paragraph, or one line: nothing to separate
    return (max(spacing, default=pitch) + min(apart)) / 2


def _merge_lines(items, pitch):
    """One line per baseline: a line broken into several <text> elements is one line.

    pdftohtml splits a line wherever the PDF's text-showing operators do, so a single
    typeset line can arrive as two elements. Left unmerged, the first of them looks
    like a short line and would be taken for a hand-broken one.
    """
    merged = []
    for it in items:
        prev = merged[-1] if merged else None
        if (it["kind"] == "text" and prev and prev["kind"] == "text"
                and it["top"] - prev["top"] < max(pitch // 2, 1)):
            # A space only where the fragments really are set apart. pdftohtml splits
            # a line at a stretched space, but it also splits mid-word on a kerning
            # pair, and there an injected space would publish 'Kinder krippe'.
            tail = prev["runs"][-1][1] if prev["runs"] else ""
            head = it["runs"][0][1] if it["runs"] else ""
            if (it["left"] - prev["right"] > 0
                    and not tail[-1:].isspace() and not head[:1].isspace()):
                prev["runs"].append((False, " "))
            prev["runs"].extend(it["runs"])
            prev["right"] = max(prev["right"], it["right"])
        else:
            merged.append(dict(it, runs=list(it.get("runs", []))))
    return merged


def _bold_markup(text):
    """'**text**', with any surrounding whitespace kept outside the markers."""
    core = text.strip()
    if not core:
        return text
    return (text[:len(text) - len(text.lstrip())] + "**" + core + "**"
            + text[len(text.rstrip()):])


def _pdf_paragraph(lines):
    """One paragraph as Markdown, in the shape pandoc gives a .docx."""
    runs = []
    for i, (hard, line_runs) in enumerate(lines):
        if i:
            runs.append([None, "\\\n"] if hard else [False, " "])
        runs.extend([bold, text] for bold, text in line_runs)
    # The space that joins two bold lines belongs inside the bold: otherwise a
    # wholly-bold paragraph arrives as '**a** **b**', which _bold_inner rejects, and
    # the title, the lead and the sub-headings all stop being recognised.
    for i in range(1, len(runs) - 1):
        if runs[i] == [False, " "] and runs[i - 1][0] and runs[i + 1][0]:
            runs[i][0] = True
    joined = []
    for bold, text in runs:
        if joined and joined[-1][0] == bold:
            joined[-1][1] += text
        else:
            joined.append([bold, text])
    return "".join(_bold_markup(t) if b else t for b, t in joined).strip()


def pdf_xml_to_markdown(xml_text):
    """Rebuild pandoc-shaped Markdown from pdftohtml -xml output."""
    pages = _pdf_items(xml_text)
    pitch = _line_pitch(pages)
    pages = [_merge_lines(items, pitch) for items in pages]
    threshold = _paragraph_gap(pages, pitch)
    measure = max((it["right"] - it["left"] for items in pages for it in items
                   if it["kind"] == "text"), default=0)

    paragraphs, current = [], []

    def flush():
        plain = "".join(t for _, runs in current for _, t in runs).strip()
        # A paragraph that is nothing but digits is the page number.
        if plain and not plain.isdigit():
            paragraphs.append(_pdf_paragraph(current))
        current.clear()

    for items in pages:
        prev = None            # the previous line on THIS page: geometry does not
        for it in items:       # carry across a page break
            if it["kind"] == "image":
                flush()
                paragraphs.append(f"![]({it['src']})")
                prev = None
                continue
            if prev is None:
                current.append((False, it["runs"]))
            elif it["top"] - prev["top"] > threshold:
                flush()
                current.append((False, it["runs"]))
            else:
                hard = (prev["right"] - prev["left"]) < measure * FULL_MEASURE
                current.append((hard, it["runs"]))
            prev = it
        flush()
    return "\n\n".join(p for p in paragraphs if p)


def pdf_images(path, out_dir):
    """Extract only the real photographs from a PDF, in page order.

    `pdfimages -list` reports every image XObject, and a single visible photo is
    routinely more than one of them: a JPEG with transparency is stored as the image
    PLUS its soft mask, and large images are split into bands. The `type` column
    distinguishes 'image' from 'smask' and 'stencil' exactly -- a pixel-area floor
    cannot, because a mask has the same dimensions as the image it belongs to.
    """
    listing = _run(["pdfimages", "-list", path]).stdout
    keep = set()
    for line in listing.splitlines()[2:]:
        fields = line.split()
        if len(fields) > 2 and fields[2] == "image":
            keep.add(int(fields[1]))
    root = os.path.join(out_dir, "pdfimg")
    _run(["pdfimages", "-all", path, root])
    found = []
    for name in sorted(os.listdir(out_dir)):
        m = re.match(r"pdfimg-(\d+)\.", name)
        if m and int(m.group(1)) in keep:
            found.append(os.path.join(out_dir, name))
    return found


# --- metadata -------------------------------------------------------------

def _pdfinfo_author(info):
    """The Author field of pdfinfo output, or None.

    [ \\t] rather than \\s: \\s matches a newline, so with re.M an 'Author:' with
    nothing after it swallows the line break and reports the NEXT field's value as
    the author. A PDF with no author still prints 'Author:' followed by padding, so
    the empty match has to become None rather than a string of spaces -- otherwise
    the page's front matter carries  Autor: " " .
    """
    m = re.search(r"^Author:[ \t]*(.*?)[ \t]*$", info, re.M)
    return (m.group(1).strip() or None) if m else None


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
    return _pdfinfo_author(_run(["pdfinfo", path]).stdout)


# --- assembly -------------------------------------------------------------

Bundle = collections.namedtuple(
    "Bundle", "title author body teaser gallery warnings")


def assemble_body(title, blocks, caption, image_at, teaser_name, gallery_names):
    """The Markdown body: heading, prose, the teaser figure, then the slider.

    The title and the caption are escaped HERE rather than in shape_document, which
    returns them raw. The same title is what the front matter carries, and Hugo does
    not evaluate shortcodes there but does HTML-escape {{ .Title }} when it renders
    -- so an escaped title stored in front matter would surface as a visible
    '&#123;&#123;'. Front matter keeps the true text; page content is escaped.
    """
    safe_title = _escape(title)
    parts = list(blocks)
    if teaser_name and image_at is not None:
        if caption:
            figure = (f'{{{{< blog-pic src="{teaser_name}" >}}}}\n'
                      f'{_escape(caption)}\n'
                      f'{{{{< /blog-pic >}}}}')
        else:
            # blog-pic.html derives alt from its inner text; with no Bildlegende that
            # would be empty, so name the alt explicitly. A double quote in the title
            # would end the attribute, so it goes in as an entity.
            alt = safe_title.replace('"', "&quot;")
            figure = (f'{{{{< blog-pic src="{teaser_name}" alt="{alt}" >}}}}'
                      f'{{{{< /blog-pic >}}}}')
        parts.insert(min(image_at, len(parts)), figure)
    if gallery_names:
        parts.append('{{< picture-slider dir="gallery" height="250px" >}}')
    return f"# {safe_title}\n\n" + "\n\n".join(parts) + "\n"


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
        else:
            # Each tool gets its own directory: pdftohtml drops page images beside
            # its output, and pdf_images must not pick those up.
            xml_dir = os.path.join(work, "xml")
            img_dir = os.path.join(work, "img")
            os.makedirs(xml_dir)
            os.makedirs(img_dir)
            text = pdf_xml_to_markdown(pdf_xml(doc_path, xml_dir))
            doc_images = pdf_images(doc_path, img_dir)
            warnings.append(
                "PDF input: the paragraphs, sub-headings and the Bildlegende are "
                "recovered from the page layout, and the photos are the copies the "
                "PDF embeds rather than the originals. Upload the .docx if anything "
                "looks wrong.")

        title, blocks, caption, image_at = shape_document(text)
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
