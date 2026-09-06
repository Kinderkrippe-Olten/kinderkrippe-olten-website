#!/usr/bin/env python3
"""Turn a press-release .docx or .pdf, plus the photos beside it, into a Hugo page body.

Pure with respect to the repository: it reads a document and a list of image paths and
writes into a destination directory. It knows nothing about git, content/blog/ or
OpenCloud.

Conversion must be DETERMINISTIC -- the mirror detects change by regenerating and
comparing bytes. That is why the workflow pins pandoc by version and checksum.
"""

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


def docx_to_markdown(path, media_dir):
    """Pandoc's Markdown for a .docx, with body images extracted into media_dir.

    markdown-smart, not markdown: the plain writer turns the document's en-dash into
    '--', and every other post on this site carries a real en-dash.
    """
    return subprocess.run(
        ["pandoc", "-f", "docx", "-t", "markdown-smart", "--wrap=none",
         f"--extract-media={media_dir}", path],
        capture_output=True, text=True, check=True,
    ).stdout


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
