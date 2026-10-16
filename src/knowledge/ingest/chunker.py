"""Structure-aware parent-child chunking (KR-ADP-02 KR-D4).

Markdown is read as headings and blocks (paragraphs, list items, tables, fenced code). Tables and code
blocks are never split. Parent sections hold about 300-800 words and start at a heading when they can; child
chunks of about 120 words are what gets embedded and matched, and a hit expands to its parent section.
"""

import re

CHILD_WORDS = 120
PARENT_MIN_WORDS, PARENT_MAX_WORDS = 300, 800
HEADING = re.compile(r"^(#{1,6})\s+(.*)")


def blocks(markdown):
    """(heading, text) pairs; a fenced code block or a table stays one block."""
    heading, out, current, fenced = "", [], [], False

    def flush():
        if current:
            out.append((heading, "\n".join(current).strip()))
            current.clear()

    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            current.append(line)
            if fenced:
                flush()
            fenced = not fenced
            continue
        if fenced:
            current.append(line)
            continue
        match = HEADING.match(line)
        if match:
            flush()
            heading = match.group(2).strip()
        elif not line.strip():
            flush()
        elif line.lstrip().startswith("|") and current and not current[-1].lstrip().startswith("|"):
            flush()  # a table starts a block of its own
            current.append(line)
        else:
            current.append(line)
    flush()
    return [(h, text) for h, text in out if text]


def words(text):
    return len(text.split())


def split_long(text, limit):
    """A prose block over `limit` words split at sentence ends; code and tables are returned whole."""
    if text.startswith("```") or text.lstrip().startswith("|") or words(text) <= limit:
        return [text]
    pieces, current = [], []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and words(" ".join([*current, sentence])) > limit:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    return pieces + [" ".join(current)] if current else pieces


def chunk(doc_id, markdown):
    """[(parent_id, heading, parent_text, [(child_id, child_text), ...]), ...]"""
    parents, current, heading = [], [], ""
    for block_heading, text in blocks(markdown):
        starts_section = block_heading != heading and words("\n\n".join(current)) >= PARENT_MIN_WORDS
        too_big = words("\n\n".join([*current, text])) > PARENT_MAX_WORDS
        if current and (starts_section or too_big):
            parents.append((heading, current))
            current = []
        if not current:
            heading = block_heading
        current.extend(split_long(text, PARENT_MAX_WORDS))
    if current:
        parents.append((heading, current))

    result = []
    for p_index, (title, parent_blocks) in enumerate(parents):
        parent_id = f"{doc_id}#p{p_index}"
        children, piece = [], []
        for block in (part for b in parent_blocks for part in split_long(b, CHILD_WORDS)):
            if piece and words(" ".join([*piece, block])) > CHILD_WORDS:
                children.append(" ".join(piece))
                piece = []
            piece.append(block)
        if piece:
            children.append(" ".join(piece))
        result.append((parent_id, title, "\n\n".join(parent_blocks),
                       [(f"{parent_id}c{c_index}", text) for c_index, text in enumerate(children)]))
    return result
