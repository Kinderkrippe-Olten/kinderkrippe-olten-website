#!/usr/bin/env python3
"""Tests for medien_convert.py.  Run with:  python3 scripts/test-medien-convert.py"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "medien")
DOCX = os.path.join(FIXTURES, "20260904_MM_EröffnungHort.docx")
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

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
