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

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
