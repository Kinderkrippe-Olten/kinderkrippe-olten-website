#!/usr/bin/env python3
"""Tests for medien_convert.py.  Run with:  python3 scripts/test-medien-convert.py"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "medien")
DOCX = os.path.join(FIXTURES, "20260904_MM_EröffnungHort.docx")
PDF = os.path.join(FIXTURES, "20260904_MM_EröffnungHort.pdf")
# The same press release printed to PDF by LibreOffice Writer rather than by LaTeX:
# ragged-right, and with a title whose own line spacing exceeds the body pitch.
PDF_WRITER = os.path.join(FIXTURES, "20260904_MM_EröffnungHort_writer.pdf")
# The bytes the .docx and its 13 loose photos must keep producing. See "THE GOLDEN
# FILE" below for why, and for how to regenerate it on purpose.
GOLDEN = os.path.join(FIXTURES, "golden-body.md")
sys.path.insert(0, HERE)
import medien_convert  # noqa: E402

failures = []
_TEMPS = []


def mkdtemp(prefix="medien-test-"):
    """A scratch directory this run cleans up.

    Bare tempfile.mkdtemp() left one behind per call, and this suite makes about
    twenty -- on a CI runner that is invisible, on a developer's machine it is a
    slow accumulation of extracted media and gallery copies.
    """
    d = tempfile.mkdtemp(prefix=prefix)
    _TEMPS.append(d)
    return d


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

    # --- _is_address must match a whole address line, not merely an opening ---
    # One matching LINE drops the whole paragraph it sits in, so a rule that
    # matches an opening deletes prose: a founding year, a donation figure, a time,
    # a list of milestones. The Anleitung warns only about postcodes, so an author
    # cannot anticipate any of it.
    for prose in ("1990 Wurde der Verein gegründet und wuchs stetig.",
                  "5000 Franken wurden gespendet, herzlichen Dank an alle.",
                  "1830 Uhr beginnt die Feier.",
                  "2024 Eröffnung der Kita",
                  "2026 Eröffnung des Horts"):
        _, b, _, _ = medien_convert.shape_document("**Titel**\n\n" + prose + "\n")
        check(f"address: prose survives -- {prose[:28]}", b == [prose], b)
    # the same three lines as one hand-broken paragraph, which is what Shift+Enter
    # in Word produces
    _, b, _, _ = medien_convert.shape_document(
        "**Titel**\n\nMeilensteine:\\\n2024 Eröffnung der Kita\\\n"
        "2026 Eröffnung des Horts\n")
    check("address: a hand-broken list of years survives whole",
          b and "Meilensteine" in b[0] and "2026" in b[0], b)
    # and a real address line still goes, town names of several words included
    for addr in ("4600 Olten", "8000 Zürich", "2300 La Chaux-de-Fonds"):
        _, b, _, _ = medien_convert.shape_document(
            "**Titel**\n\nHort Bifang-Säli\\\nReiserstrasse 91\\\n" + addr + "\n")
        check(f"address: {addr} still takes its block", b == [], b)
    # --- the Anleitung's promise about number lines, pinned in both directions ---
    # A line of four digits followed by one to four capitalised words IS taken for
    # an address today, milestone or not. Pinned so that narrowing ADDRESS_RE stays
    # a deliberate decision rather than an accident.
    for gone in ("2024 Umbau Sonnhalde", "2026 Start Hort",
                 "2025 Jubiläum Verein Kinderkrippe Olten"):
        _, b, _, _ = medien_convert.shape_document("**Titel**\n\n" + gone + "\n")
        check(f"address: article-less milestone goes -- {gone}", b == [], b)
    # and every line the Anleitung names as surviving must keep surviving
    for kept in ("1990 Wurde der Verein gegründet",
                 "5000 Franken wurden gespendet",
                 "2024 Eröffnung der Kita",
                 "2024 Umbau der Sonnhalde",
                 "Die Feier findet im Stadthaus, 4600 Olten, statt"):
        _, b, _, _ = medien_convert.shape_document("**Titel**\n\n" + kept + "\n")
        check(f"address: the Anleitung's survivor survives -- {kept[:28]}",
              b == [kept], b)

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

    # --- a leading image must never become the title ---
    # A press release on letterhead opens with the logo, and the markup carries the
    # per-run --extract-media path: as the title it would put an absolute
    # build-runner path into a committed file and change on every run.
    t, b, c, i = medien_convert.shape_document(
        '![](/tmp/medien-abc123/media/rId20.png){width="5.83in" height="2.33in"}\n\n'
        "**MEDIENMITTEILUNG**\n\n"
        "**Schülerhort startet erfolgreich**\n\n"
        "Ein Absatz mit Text.\n")
    check("leading image: the text is the title, not the image",
          t == "Schülerhort startet erfolgreich", t)
    check("leading image: the label is still dropped",
          not any("MEDIENMITTEILUNG" in x for x in b), b)
    check("leading image: the real title is not demoted to a sub-heading",
          not any(x.startswith("## ") for x in b), b)
    check("leading image: no extract-media path anywhere",
          "/tmp/medien-" not in t and not any("/tmp/medien-" in x for x in b), (t, b))
    check("leading image: its position is still recorded", i == 0, i)

    # a document that is nothing but images -- a scanned press release -- has no
    # title to find, and the Anleitung already tells the author it is rejected
    try:
        medien_convert.shape_document("![](/tmp/medien-abc123/xml/doc-1_1.jpg)\n")
        check("image-only document rejected", False, "no exception")
    except medien_convert.ConversionError as e:
        check("image-only document rejected", "no text" in str(e), str(e))

    # an image set INSIDE a paragraph loses its markup but not the prose around it,
    # and does not leave a double space behind
    t, b, _, _ = medien_convert.shape_document(
        "**Titel**\n\nEin Absatz ![](/tmp/medien-abc123/media/rId7.png) mit Bild.\n")
    check("inline image: the path does not reach the body",
          b == ["Ein Absatz mit Bild."], b)

    # the real document, through pandoc
    _media = mkdtemp()
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
    tmp = mkdtemp()
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
    swap_dir = mkdtemp()
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

    # --- a file the author named teaser.* settles the cover ---
    # The convention the Geschichten folders already use: the cover photo is copied
    # beside the others under the name teaser.jpg. It has to beat both the fallback
    # (first loose file alphabetically) and the document's own image, or an author
    # who names the cover does not get it.
    # Built from three DIFFERENT photos, not three rescalings of one: rescalings are
    # perceptual twins, and the twin rules would decide these cases for reasons that
    # have nothing to do with the name.
    named_dir = mkdtemp()

    def _named(name, source):
        path = os.path.join(named_dir, name)
        Image.open(source).save(path)
        return path

    doc_img = _named("doc.jpeg", loose[2])
    photo_a = _named("AAA_first.jpeg", loose[0])   # would win the fallback: sorts first
    photo_b = _named("ZZZ_last.jpeg", loose[1])
    cover = os.path.join(named_dir, "teaser.jpg")
    shutil.copyfile(photo_a, cover)             # a byte-identical copy, as in the example

    t_named, g_named = medien_convert.select_images([], [photo_a, photo_b, cover])
    check("teaser.jpg wins the cover slot over the alphabetical fallback",
          os.path.basename(t_named) == "teaser.jpg", t_named)
    check("the named cover is not itself a gallery entry",
          cover not in g_named, [os.path.basename(g) for g in g_named])
    check("a byte-twin of the named cover stays in the gallery",
          sorted(os.path.basename(g) for g in g_named) == ["AAA_first.jpeg",
                                                           "ZZZ_last.jpeg"],
          [os.path.basename(g) for g in g_named])

    t_over, g_over = medien_convert.select_images([doc_img], [photo_a, cover])
    check("teaser.jpg wins the cover slot over the document's own image",
          os.path.basename(t_over) == "teaser.jpg", t_over)
    check("the document's own image falls back to the gallery",
          any(os.path.basename(g) == "doc.jpeg" for g in g_over),
          [os.path.basename(g) for g in g_over])

    # Two named files cannot both be the cover. Whichever loses stays an ordinary
    # gallery photo, and which one loses may not depend on iteration order.
    cover_png = _named("teaser.png", photo_b)
    t_two_fwd, g_two_fwd = medien_convert.select_images([], [cover, cover_png, photo_b])
    t_two_rev, _ = medien_convert.select_images([], [cover_png, cover, photo_b])
    check("two teaser.* files resolve to the same cover in either order",
          os.path.basename(t_two_fwd) == os.path.basename(t_two_rev) == "teaser.jpg",
          (t_two_fwd, t_two_rev))
    check("the teaser.* that lost is still shown in the gallery",
          any(os.path.basename(g) == "teaser.png" for g in g_two_fwd),
          [os.path.basename(g) for g in g_two_fwd])

    shutil.rmtree(named_dir, ignore_errors=True)

    # nothing at all
    check("no images at all is allowed", medien_convert.select_images([], []) == (None, []))

    shutil.rmtree(tmp, ignore_errors=True)

    # --- full bundle assembly from the real document ---
    out = mkdtemp()
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

    # --- THE GOLDEN FILE: the only assertion that can see pandoc move ---
    # Every other assertion here is structural -- startswith, a count of '## ', a
    # word that must not appear. A pandoc that starts escaping the German
    # guillemets changes 1,492 characters of the published corpus, puts visible
    # backslashes on the page, and passes all of them. That is the exact drift the
    # version-and-checksum pin exists to prevent, and without a byte comparison the
    # pin guards nothing.
    #
    # Regenerate deliberately, never to make the test green:
    #   python3 -c "import sys; sys.path.insert(0,'scripts'); import glob, medien_convert as m; \
    #     print(m.convert('scripts/fixtures/medien/20260904_MM_EröffnungHort.docx', \
    #       sorted(glob.glob('scripts/fixtures/medien/IMG_*.jpeg')), OUT).body, end='')" > \
    #     scripts/fixtures/medien/golden-body.md
    # and read the diff: it is the diff the whole corpus is about to take.
    #
    # No path normalisation is needed. Nothing carrying the --extract-media
    # directory reaches the body any more -- see shape_document -- which is what
    # makes an equality assertion possible at all.
    with open(GOLDEN, encoding="utf-8") as fh:
        golden = fh.read()
    check("golden: the generated body is byte for byte the committed one",
          b.body == golden,
          next((f"line {i + 1}: {x!r} != {y!r}" for i, (x, y) in
                enumerate(zip(b.body.splitlines(), golden.splitlines())) if x != y),
               f"length {len(b.body)} != {len(golden)}"))
    check("golden: it carries the guillemets unescaped, as pandoc 3.11 writes them",
          "«Der Hort bietet" in golden and "\\«" not in golden, golden[:0])
    shutil.rmtree(out, ignore_errors=True)

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
    evil_dir = mkdtemp()
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
    out = mkdtemp()
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
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(evil_dir, ignore_errors=True)

    # --- a real letterhead document, and the determinism that hangs on it ---
    # A press release on letterhead opens with the logo. Converted twice from two
    # DIFFERENT temp directories the bundle must come out byte for byte the same:
    # the mirror detects change by regenerating and comparing, so a title carrying
    # the mkdtemp path is a bot commit and a deploy every single Monday.
    import hashlib
    head_dir = mkdtemp()
    from PIL import Image as _Im
    _Im.new("RGB", (500, 200), "white").save(os.path.join(head_dir, "logo.png"))
    head_md = os.path.join(head_dir, "head.md")
    with open(head_md, "w", encoding="utf-8") as fh:
        fh.write("![](logo.png)\n\n**MEDIENMITTEILUNG**\n\n"
                 "**Schülerhort startet erfolgreich**\n\nEin Absatz mit Text.\n")
    head_docx = os.path.join(head_dir, "letterhead.docx")
    subprocess.run(["pandoc", "-f", "markdown", "-o", head_docx, head_md],
                   cwd=head_dir, check=True)

    def _convert_under(tmpdir):
        """convert() with tempfile pointed somewhere else, digested."""
        os.makedirs(tmpdir, exist_ok=True)
        was, tempfile.tempdir = tempfile.tempdir, tmpdir
        try:
            dest = os.path.join(head_dir, os.path.basename(tmpdir) + "-out")
            os.makedirs(dest)
            bundle = medien_convert.convert(head_docx, [], dest)
            files = {}
            for root, _, names in os.walk(dest):
                for n in sorted(names):
                    p = os.path.join(root, n)
                    files[os.path.relpath(p, dest)] = hashlib.sha256(
                        open(p, "rb").read()).hexdigest()
            return bundle.title, bundle.body, files
        finally:
            tempfile.tempdir = was

    run_a = _convert_under(os.path.join(head_dir, "tmpA"))
    run_b = _convert_under(os.path.join(head_dir, "tmpB"))
    check("letterhead: the logo does not become the title",
          run_a[0] == "Schülerhort startet erfolgreich", run_a[0])
    check("letterhead: the label is dropped and the title is the H1",
          run_a[1].startswith("# Schülerhort startet erfolgreich")
          and "MEDIENMITTEILUNG" not in run_a[1], run_a[1][:200])
    check("letterhead: no absolute temp path reaches the page",
          "medien-" not in run_a[1] and head_dir not in run_a[1], run_a[1])
    check("determinism: two runs from two temp directories are byte-identical",
          run_a == run_b, (run_a[0], run_b[0]))
    shutil.rmtree(head_dir, ignore_errors=True)

    # --- a document the tools cannot read is a ConversionError, not a crash ---
    # Task 6 catches ConversionError to reject one folder; anything else it does not
    # catch would take the whole sync run down with it.
    for name in ("bad.docx", "bad.pdf"):
        bad_dir = mkdtemp()
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
        shutil.rmtree(bad_dir, ignore_errors=True)

    # --- PDF input ---
    # A committed fixture rather than a PDF rendered during the test: rendering one
    # needs a LaTeX engine, which the CI runner does not have. The task report records
    # the command that produced it.
    out = mkdtemp()
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
    upload = mkdtemp()
    shutil.copy2(PDF, os.path.join(upload, "mm.pdf"))
    out2 = mkdtemp()
    medien_convert.convert(os.path.join(upload, "mm.pdf"), [], out2)
    check("pdf: the folder the document came from is left untouched",
          os.listdir(upload) == ["mm.pdf"], os.listdir(upload))
    shutil.rmtree(upload, ignore_errors=True)
    shutil.rmtree(out2, ignore_errors=True)
    check("pdf: a relative document path still resolves",
          "<pdf2xml" in medien_convert.pdf_xml(os.path.relpath(PDF), mkdtemp()))
    check("pdf: the obsolete 'no bold' warning is gone",
          not any("no bold" in w for w in b.warnings), b.warnings)
    shutil.rmtree(out, ignore_errors=True)

    # --- a PDF from a WORD PROCESSOR, not from LaTeX ---
    # The LaTeX fixture is justified, single-spaced throughout and sets its title in
    # the body size, so it cannot exercise the geometry the calibration actually has
    # to survive. This one is the SAME .docx, printed by LibreOffice Writer
    # (soffice --headless --convert-to pdf) -- ragged-right, and with a title set
    # large enough that its own line spacing (26) exceeds the body pitch (20) and
    # lands among the paragraph gaps as a single outlier against eight real ones of
    # 41. Taking the SMALLEST of those broke the title in half.
    out = mkdtemp()
    bw = medien_convert.convert(PDF_WRITER, [], out)
    check("writer pdf: the title survives its own larger line spacing",
          bw.title == "Schülerhort Bifang-Säli startet erfolgreich – freie Plätze "
                      "verfügbar", bw.title)
    check("writer pdf: the lead is the lead, not a sub-heading",
          bw.body.split("\n\n")[1].startswith("**Seit Anfang August"),
          bw.body[:400])
    check("writer pdf: three sub-headings", bw.body.count("\n## ") == 3,
          [x for x in bw.body.splitlines() if x.startswith("## ")])
    check("writer pdf: label, address and telephone all gone",
          "MEDIENMITTEILUNG" not in bw.body and "Reiserstrasse" not in bw.body
          and "062 526" not in bw.body, bw.body)
    check("writer pdf: caption recovered without its prefix",
          "Die Verantwortlichen eröffnen den Hort" in bw.body
          and "Bildlegende" not in bw.body, bw.body)
    check("writer pdf: page numbers dropped",
          not any(x.strip().isdigit() for x in bw.body.splitlines()), bw.body)
    check("writer pdf: the embedded photo becomes the teaser",
          bw.teaser == "teaser.jpg" and os.path.isfile(os.path.join(out, "teaser.jpg")),
          bw.teaser)
    check("writer pdf: author read from the PDF metadata",
          bw.author == "Melanie von Arx", bw.author)
    # A word processor keeps the space it broke the line at inside the line's own
    # text run. Injecting a join space on top of it put 26 double spaces per page
    # into the committed bytes.
    check("writer pdf: no double spaces in the committed body",
          "  " not in bw.body, [x for x in bw.body.split() if not x])
    shutil.rmtree(out, ignore_errors=True)

    # deferred 158, now that it can be asserted: the two input formats produce the
    # SAME page. Only the teaser's file extension differs (Word embeds a .jpeg,
    # pdfimages writes a .jpg) and Word's non-breaking spaces.
    def _plain_body(path):
        d = mkdtemp()
        try:
            return (medien_convert.convert(path, [], d).body
                    .replace('src="teaser.jpeg"', 'src="teaser.X"')
                    .replace('src="teaser.jpg"', 'src="teaser.X"')
                    .replace(" ", " "))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    body_docx, body_tex, body_writer = (_plain_body(DOCX), _plain_body(PDF),
                                        _plain_body(PDF_WRITER))
    check("158: the LaTeX PDF gives the same body as the .docx",
          body_docx == body_tex,
          next((f"{a!r} != {b_!r}" for a, b_ in
                zip(body_docx.splitlines(), body_tex.splitlines()) if a != b_), ""))
    check("158: the Writer PDF gives the same body as the .docx",
          body_docx == body_writer,
          next((f"{a!r} != {b_!r}" for a, b_ in
                zip(body_docx.splitlines(), body_writer.splitlines()) if a != b_), ""))

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

    # --- the realised margins on the fixture, on BOTH sides ---
    # A threshold that clears the line spacing but sits a fraction of a unit under the
    # real paragraph gap is one rounding step away from losing every paragraph break
    # in the document -- the single-block collapse the PDF path exists to avoid. Pin
    # both walls so a regenerated fixture cannot walk into either one unnoticed.
    #
    # Both fixtures, because they realise different geometry: the LaTeX one is
    # single-spaced with paragraph gaps of 26-28, the Writer one has a 20 pitch and
    # 41 gaps plus the title's 26 sitting between them.
    def _geometry(path):
        pgs = medien_convert._pdf_items(
            medien_convert.pdf_xml(path, mkdtemp()))
        pitch = medien_convert._line_pitch(pgs)
        merged = [medien_convert._merge_lines(p, pitch) for p in pgs]
        return pitch, medien_convert._paragraph_gap(merged, pitch), \
            medien_convert._line_gaps(merged)

    for label, path in (("latex", PDF), ("writer", PDF_WRITER)):
        fx_pitch, fx_thr, fx_gaps = _geometry(path)
        spacing = max(g for g in fx_gaps if g <= fx_thr)
        apart = min(g for g in fx_gaps if g > fx_thr)
        check(f"margins ({label}): the paragraph threshold clears the line spacing",
              fx_thr - spacing >= 3, (fx_pitch, fx_thr, spacing))
        check(f"margins ({label}): the threshold stays under the smallest real break",
              apart - fx_thr >= 3, (fx_thr, apart))

    # The exact numbers, so a re-derivation cannot quietly move them. The Writer
    # PDF's 30.5 is what the modal rule buys: min() over the same gaps gives 23.0,
    # which puts a paragraph break inside the title.
    check("margins: the LaTeX fixture's geometry is unchanged by the modal rule",
          _geometry(PDF)[:2] == (18, 22.0), _geometry(PDF)[:2])
    check("margins: the Writer fixture clears its title's own line spacing",
          _geometry(PDF_WRITER)[:2] == (20, 30.5), _geometry(PDF_WRITER)[:2])

    # A single line set in a larger font must not be able to move the wall the whole
    # document is measured against: pitch 20, one gap of 26, eight real breaks at 41.
    outlier = [[{"kind": "text", "top": t, "left": 0, "right": 400, "runs": []}
                for t in ([0, 20, 46] + [46 + 41 * (i + 1) for i in range(8)])]]
    check("margins: one outlier gap does not drag the threshold down to it",
          medien_convert._paragraph_gap(outlier, 20) == 30.5,
          medien_convert._paragraph_gap(outlier, 20))

    # A one-paragraph document has no larger gap to find, and must not invent one.
    check("margins: nothing to separate leaves every line in one paragraph",
          medien_convert._paragraph_gap(
              [[{"kind": "text", "top": t, "left": 0, "right": 400, "runs": []}
                for t in (100, 118, 136)]], 18) == float("inf"))

    # --- the hard-break floor, pinned from both sides ---
    # The fixture is justified LaTeX, so every wrapped line in it is full-measure and
    # the floor could sit almost anywhere. A Word export is ragged-right: a wrapped
    # line at 0.8 of the measure is ordinary and must still be joined, while an
    # author-ended line at 0.35 must still break.
    def _seam(width_second):
        return medien_convert.pdf_xml_to_markdown(
            '<?xml version="1.0" encoding="UTF-8"?>\n<pdf2xml>\n'
            '<page number="1" top="0" left="0" height="1188" width="918">\n'
            '<text top="100" left="100" width="400" height="13">Erste Zeile mit</text>\n'
            f'<text top="118" left="100" width="{width_second}" height="13">viel Text</text>\n'
            '<text top="136" left="100" width="400" height="13">und dritte Zeile</text>\n'
            '</page>\n</pdf2xml>\n')

    check("floor: a ragged-right line at 0.8 of the measure is still wrapped text",
          "\\" not in _seam(320), _seam(320))
    check("floor: a line at 0.35 of the measure is a hand-broken one",
          "viel Text\\\n" in _seam(140), _seam(140))

    # --- same-baseline fragments ---
    # pdftohtml splits a line at a stretched space, but also mid-word on a kerning
    # pair. Only the first of those may gain a space.
    def _fragments(second_left):
        return medien_convert.pdf_xml_to_markdown(
            '<?xml version="1.0" encoding="UTF-8"?>\n<pdf2xml>\n'
            '<page number="1" top="0" left="0" height="1188" width="918">\n'
            '<text top="100" left="100" width="100" height="13">Kinder</text>\n'
            f'<text top="100" left="{second_left}" width="100" height="13">krippe</text>\n'
            '</page>\n</pdf2xml>\n')

    check("fragments: a kerning split mid-word does not gain a space",
          _fragments(200) == "Kinderkrippe", _fragments(200))
    check("fragments: a split at a stretched space keeps the space",
          _fragments(230) == "Kinder krippe", _fragments(230))

    # --- joining two wrapped lines ---
    # A word processor keeps the space it broke the line at inside the line's own
    # text run; a typesetter does not. The join has to look before it adds one.
    def _join(first):
        return medien_convert.pdf_xml_to_markdown(
            '<?xml version="1.0" encoding="UTF-8"?>\n<pdf2xml>\n'
            '<page number="1" top="0" left="0" height="1188" width="918">\n'
            f'<text top="100" left="100" width="400" height="13">{first}</text>\n'
            '<text top="118" left="100" width="380" height="13">Stadtseite</text>\n'
            '</page>\n</pdf2xml>\n')

    check("join: a line that already ends in a space does not gain a second one",
          _join("auf der rechten ") == "auf der rechten Stadtseite",
          _join("auf der rechten "))
    check("join: a line that does not still gains one",
          _join("auf der rechten") == "auf der rechten Stadtseite",
          _join("auf der rechten"))

    # --- the pitch and the threshold are measured over ONE population ---
    # _line_pitch runs before _merge_lines (which needs it) and _paragraph_gap runs
    # after, so the two saw slightly different sets. Same rule now: skip repeated
    # tops, reset at an image, never cross a page.
    split_line = [[{"kind": "text", "top": 100, "left": 0, "right": 200, "runs": []},
                   {"kind": "text", "top": 100, "left": 210, "right": 400, "runs": []},
                   {"kind": "text", "top": 118, "left": 0, "right": 400, "runs": []},
                   {"kind": "image", "top": 200, "left": 0, "src": "x.jpg"},
                   {"kind": "text", "top": 400, "left": 0, "right": 400, "runs": []}]]
    check("population: a line split into fragments counts once, and no gap "
          "crosses an image",
          medien_convert._line_gaps(split_line) == [18],
          medien_convert._line_gaps(split_line))
    check("population: the pitch is the mode of exactly those gaps",
          medien_convert._line_pitch(split_line) == 18,
          medien_convert._line_pitch(split_line))

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        for d in _TEMPS:
            shutil.rmtree(d, ignore_errors=True)
    sys.exit(code)
