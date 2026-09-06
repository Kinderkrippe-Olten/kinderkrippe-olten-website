#!/usr/bin/env python3
"""Tests for medien_convert.py.  Run with:  python3 scripts/test-medien-convert.py"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "medien")
DOCX = os.path.join(FIXTURES, "20260904_MM_EröffnungHort.docx")
PDF = os.path.join(FIXTURES, "20260904_MM_EröffnungHort.pdf")
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
    # Four body entries accumulate before the image is reached: the bold lead,
    # "An der Eröffnung ...", "## Erfolgreicher Start" and "Der Betrieb ...".
    # The address block in between is dropped without occupying an index.
    check("image position recorded", image_at == 4, (image_at, blocks))
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

    # --- the teaser swap must not depend on iteration order ---
    # In the committed fixtures the embedded image is already the larger copy, so
    # that comparison is never exercised above. Build genuine perceptual twins by
    # rescaling one real photo to three sizes -- all safely above the 40,000px
    # MIN_PIXELS floor -- so the swap branch, and its order-independence, are
    # actually tested rather than merely present in the code.
    import shutil
    swap_dir = tempfile.mkdtemp()
    src = Image.open(loose[0])
    w0, h0 = src.size

    def _rescaled(name, width):
        path = os.path.join(swap_dir, name)
        src.resize((width, round(h0 * width / w0)), Image.LANCZOS).save(path)
        return path

    doc_copy = _rescaled("doc.jpeg", 300)   # ~300x201: the document's own copy
    mid_copy = _rescaled("mid.jpeg", 400)   # ~400x268: a smaller loose rescan
    big_copy = _rescaled("big.jpeg", 500)   # ~500x335: the largest loose rescan

    teaser_fwd, gallery_fwd = medien_convert.select_images([doc_copy], [mid_copy, big_copy])
    check("largest twin wins the teaser slot (the swap branch)",
          os.path.basename(teaser_fwd) == "big.jpeg", teaser_fwd)
    check("no twin of the teaser reaches the gallery (forward order)",
          not any(os.path.basename(g) in ("mid.jpeg", "big.jpeg") for g in gallery_fwd),
          gallery_fwd)

    teaser_rev, gallery_rev = medien_convert.select_images([doc_copy], [big_copy, mid_copy])
    check("teaser choice does not depend on loose_images order",
          os.path.basename(teaser_rev) == "big.jpeg", teaser_rev)
    check("no twin of the teaser reaches the gallery (reverse order)",
          not any(os.path.basename(g) in ("mid.jpeg", "big.jpeg") for g in gallery_rev),
          gallery_rev)

    # two loose twins tied on pixel count, neither the document's own copy: the
    # resolution key alone cannot break this tie, so it must fall to a stable key
    # (basename) rather than to which twin happened to be seen first.
    tie_a = _rescaled("tieA.jpeg", 450)
    tie_b = _rescaled("tieB.jpeg", 450)   # identical dimensions to tie_a

    teaser_tie_fwd, _ = medien_convert.select_images([doc_copy], [tie_a, tie_b])
    teaser_tie_rev, _ = medien_convert.select_images([doc_copy], [tie_b, tie_a])
    check("equal-pixel loose twins break the tie the same way in both orderings",
          os.path.basename(teaser_tie_fwd) == os.path.basename(teaser_tie_rev),
          (teaser_tie_fwd, teaser_tie_rev))

    shutil.rmtree(swap_dir, ignore_errors=True)

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
    check("bundle: a complete document warns about nothing", b.warnings == [], b.warnings)
    _sh.rmtree(out, ignore_errors=True)

    # no caption -> explicit alt, never an empty one
    body = medien_convert.assemble_body("Titel", ["Ein Absatz."], None, 0, "teaser.jpg", [])
    check("no caption: alt falls back to the title",
          'alt="Titel"' in body, body)

    # a double quote in the title would otherwise end the alt= attribute
    body = medien_convert.assemble_body('Ein "zitierter" Titel', ["Ein Absatz."],
                                        None, 0, "teaser.jpg", [])
    check("alt= is quote-safe",
          'alt="Ein &quot;zitierter&quot; Titel"' in body, body)

    # no images at all: no shortcodes
    body = medien_convert.assemble_body("Titel", ["Ein Absatz."], None, None, None, [])
    check("no images: no blog-pic", "blog-pic" not in body, body)
    check("no images: no slider", "picture-slider" not in body, body)

    # --- shortcode delimiters in the title and in the Bildlegende ---
    # shape_document escapes body blocks only; the title and the caption are escaped
    # where they enter page content, which is assemble_body. Unescaped, either one
    # fails the whole site build, not just this page.
    evil_dir = tempfile.mkdtemp()
    shutil.copy2(loose[0], os.path.join(evil_dir, "foto.jpeg"))
    evil_md = os.path.join(evil_dir, "evil.md")
    with open(evil_md, "w", encoding="utf-8") as fh:
        fh.write("**MEDIENMITTEILUNG**\n\n"
                 "**Titel mit {{< stellen >}} darin**\n\n"
                 "Ein Absatz.\n\n"
                 "![](foto.jpeg)\n\n"
                 "Bildlegende: Legende mit {{< stellen >}} darin\n")
    evil_docx = os.path.join(evil_dir, "evil.docx")
    subprocess.run(["pandoc", "-f", "markdown", "-o", evil_docx, evil_md],
                   cwd=evil_dir, check=True)
    out = tempfile.mkdtemp()
    b = medien_convert.convert(evil_docx, [], out)
    check("escape: Bundle.title keeps its raw '{{', so front matter stays truthful",
          "{{" in b.title and "&#123;" not in b.title, b.title)
    check("escape: the heading carries the escaped title",
          b.body.startswith("# Titel mit &#123;&#123;"), b.body[:80])
    check("escape: the caption is escaped inside the shortcode",
          "&#123;&#123;" in b.body.split("blog-pic")[1], b.body)
    check("escape: title and caption are both escaped",
          b.body.count("&#123;&#123;") == 2, b.body)
    check("escape: the only '{{' left are the shortcodes assemble_body emits",
          b.body.count("{{") == 2, b.body)
    _sh.rmtree(out, ignore_errors=True)
    _sh.rmtree(evil_dir, ignore_errors=True)

    # --- a document the tools cannot read is a ConversionError, not a crash ---
    # Task 6 catches ConversionError to reject one folder; anything else it does not
    # catch would take the whole sync run down with it.
    for name in ("bad.docx", "bad.pdf"):
        bad_dir = tempfile.mkdtemp()
        bad = os.path.join(bad_dir, name)
        with open(bad, "wb") as fh:
            fh.write(b"this is not a document")
        try:
            medien_convert.convert(bad, [], bad_dir)
            check(f"{name}: rejected with ConversionError", False, "no exception")
        except medien_convert.ConversionError as e:
            check(f"{name}: rejected with ConversionError", True, str(e))
        except Exception as e:
            check(f"{name}: rejected with ConversionError", False, repr(e))
        _sh.rmtree(bad_dir, ignore_errors=True)

    # --- PDF input ---
    # A committed fixture rather than a PDF rendered during the test: rendering one
    # needs a LaTeX engine, which the CI runner does not have. The task report records
    # the command that produced it.
    out = tempfile.mkdtemp()
    b = medien_convert.convert(PDF, [], out)
    check("pdf: title is exactly the press-release title",
          b.title == "Schülerhort Bifang-Säli startet erfolgreich – freie Plätze verfügbar",
          b.title)
    check("pdf: the title matches the one the .docx yields", b.title == title,
          (b.title, title))
    check("pdf: a body sentence is in the body, and not swallowed by the title",
          "freut sich Vereinspräsident Franco Giori" in b.body
          and "Franco Giori" not in b.title, (b.title, b.body[:300]))
    check("pdf: the body is many paragraphs, not one",
          b.body.count("\n\n") >= 8, b.body.count("\n\n"))
    check("pdf: three sub-headings, so bold survived",
          b.body.count("\n## ") == 3,
          [x for x in b.body.splitlines() if x.startswith("## ")])
    check("pdf: the lead paragraph is one bold run across four typeset lines",
          "**Seit Anfang August bietet der Verein Kinderkrippe Olten auf der rechten "
          "Stadtseite mit dem Hort Bifang-Säli ein Betreuungsangebot für Kindergarten- "
          "und Schulkinder an. Am 4. September fand die offizielle Eröffnung statt.**"
          in b.body, b.body[:600])
    check("pdf: MEDIENMITTEILUNG label dropped",
          "MEDIENMITTEILUNG" not in b.body, b.body[:200])
    check("pdf: address gone",
          "Reiserstrasse" not in b.body and "062 526" not in b.body, b.body)
    check("pdf: page numbers dropped",
          not any(x.strip().isdigit() for x in b.body.splitlines()), b.body)
    check("pdf: caption recovered without its prefix",
          "Die Verantwortlichen eröffnen den Hort feierlich" in b.body
          and "Bildlegende" not in b.body, b.body)
    check("pdf: the caption's XML entity is unescaped",
          "(Foto & Text: Melanie von Arx)" in b.body, b.body[-400:])
    check("pdf: the embedded photo becomes the teaser",
          b.teaser == "teaser.jpg" and os.path.isfile(os.path.join(out, "teaser.jpg")),
          b.teaser)
    check("pdf: the teaser is placed where the photo sat",
          '{{< blog-pic src="teaser.jpg" >}}' in b.body, b.body[-400:])
    check("pdf: a blank pdfinfo Author is None, not a space",
          medien_convert.document_author(PDF) is None,
          repr(medien_convert.document_author(PDF)))
    # The fixture has no author, so pin both halves of the field on pdfinfo's own
    # layout: an empty Author must not swallow the next line, a real one must arrive.
    check("pdfinfo: an empty Author is None, not the next field",
          medien_convert._pdfinfo_author(
              "Author:          \nCreator:         LaTeX via pandoc\n") is None,
          medien_convert._pdfinfo_author(
              "Author:          \nCreator:         LaTeX via pandoc\n"))
    check("pdfinfo: a real Author is read",
          medien_convert._pdfinfo_author(
              "Title:           MM\nAuthor:          Melanie von Arx\nPages:  2\n")
          == "Melanie von Arx")
    # pdftohtml drops the images it finds beside its output. Pointed at the upload
    # folder they would be read back as loose photos on the next run, so the folder
    # the document came from must come out of a conversion untouched.
    upload = tempfile.mkdtemp()
    shutil.copy2(PDF, os.path.join(upload, "mm.pdf"))
    out2 = tempfile.mkdtemp()
    medien_convert.convert(os.path.join(upload, "mm.pdf"), [], out2)
    check("pdf: the folder the document came from is left untouched",
          os.listdir(upload) == ["mm.pdf"], os.listdir(upload))
    _sh.rmtree(upload, ignore_errors=True)
    _sh.rmtree(out2, ignore_errors=True)
    check("pdf: a relative document path still resolves",
          "<pdf2xml" in medien_convert.pdf_xml(os.path.relpath(PDF), tempfile.mkdtemp()))
    check("pdf: the obsolete 'no bold' warning is gone",
          not any("no bold" in w for w in b.warnings), b.warnings)
    _sh.rmtree(out, ignore_errors=True)

    # --- the XML -> Markdown seam, on geometry chosen to pin both rules ---
    # Line pitch 18, paragraph gap 40, widest line 400 units. The address block is a
    # run of short lines the author broke by hand; the sentence above it is a wrapped
    # paragraph that merely mentions a postcode and must survive.
    XML = """<?xml version="1.0" encoding="UTF-8"?>
<pdf2xml producer="poppler" version="24.02.0">
<page number="1" position="absolute" top="0" left="0" height="1188" width="918">
<text top="100" left="100" width="400" height="13" font="0"><b>Titel der Mitteilung</b></text>
<text top="140" left="100" width="400" height="13" font="1">Der Hort liegt in 4600 Olten und ist gut</text>
<text top="158" left="100" width="120" height="13" font="1">erreichbar.</text>
<text top="198" left="100" width="120" height="13" font="0"><b>Hort Bifang-S&#228;li</b></text>
<text top="216" left="100" width="110" height="13" font="1">Reiserstrasse 91</text>
<text top="234" left="100" width="80" height="13" font="1">4600 Olten</text>
<text top="274" left="100" width="10" height="13" font="1">1</text>
</page>
</pdf2xml>
"""
    md = medien_convert.pdf_xml_to_markdown(XML)
    check("xml seam: wrapped lines join into running prose",
          "Der Hort liegt in 4600 Olten und ist gut erreichbar." in md, md)
    check("xml seam: hand-broken lines keep a Markdown hard break",
          "Reiserstrasse 91\\\n4600 Olten" in md, md)
    check("xml seam: the page number is dropped", "\n\n1" not in md, md)
    t2, b2, c2, i2 = medien_convert.shape_document(md)
    check("xml seam: title recovered", t2 == "Titel der Mitteilung", t2)
    check("xml seam: postcode inside a sentence survives",
          any("4600 Olten und ist gut erreichbar" in x for x in b2), b2)
    check("xml seam: the address block is dropped",
          not any("Reiserstrasse" in x for x in b2), b2)

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
