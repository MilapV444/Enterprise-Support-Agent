"""M1-10: structure-aware parent-child chunking (KR-D4)."""

from knowledge.ingest.chunker import CHILD_WORDS, PARENT_MAX_WORDS, blocks, chunk

CODE = "```bash\n" + "\n".join(f"step_{i} --flag value" for i in range(80)) + "\n```"
TABLE = "| plan | limit |\n| --- | --- |\n| Pro | 100 req/min |\n| Free | 10 req/min |"


def article(sections=4, paragraph_words=90, paragraphs=5):
    parts = []
    for s in range(sections):
        parts.append(f"## Section {s}")
        for p in range(paragraphs):
            parts.append(" ".join(f"w{s}_{p}_{i}." if i % 15 == 14 else f"w{s}_{p}_{i}"
                                  for i in range(paragraph_words)))
    return "\n\n".join(parts)


def test_code_blocks_and_tables_stay_whole():
    doc = f"# Setup\n\nInstall it.\n\n{CODE}\n\n{TABLE}\n\nDone."
    found = [text for _, text in blocks(doc)]
    assert CODE in found and TABLE in found
    children = [text for _, _, _, kids in chunk("d1", doc) for _, text in kids]
    assert any("step_0" in c and "step_79" in c for c in children)  # one child holds the whole code block


def test_parents_and_children_respect_their_sizes_and_keep_every_word():
    doc = article()
    parents = chunk("d2", doc)
    source_words = doc.replace("## ", "").split()
    for _, _, parent_text, children in parents:
        assert len(parent_text.split()) <= PARENT_MAX_WORDS
        assert all(len(text.split()) <= CHILD_WORDS for _, text in children)
        assert " ".join(text for _, text in children).split() == parent_text.split()
    kept = [w for _, _, text, _ in parents for w in text.split()]
    assert kept == [w for w in source_words if not w.startswith("Section") and not w.isdigit()]


def test_parents_start_at_headings_once_big_enough():
    parents = chunk("d3", article(sections=3, paragraphs=4))  # 360 words per section
    assert [heading for _, heading, _, _ in parents] == ["Section 0", "Section 1", "Section 2"]
    assert parents[0][0] == "d3#p0" and parents[0][3][0][0] == "d3#p0c0"
