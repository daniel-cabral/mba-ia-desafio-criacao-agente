import re

from aurora.config import DADOS_DIR

_CHAPTER_HEADING = re.compile(r"^## Capítulo ([IVX]+): (.+)$", re.MULTILINE)


def _parse(text: str) -> dict[str, dict]:
    headings = list(_CHAPTER_HEADING.finditer(text))
    chapters = {}
    for position, heading in enumerate(headings):
        end = headings[position + 1].start() if position + 1 < len(headings) else len(text)
        chapters[heading.group(1)] = {
            "titulo": heading.group(2).strip(),
            "texto": text[heading.end() : end].strip(),
        }
    return chapters


CHAPTERS: dict[str, dict] = _parse((DADOS_DIR / "regulamento.md").read_text(encoding="utf-8"))


def chapter_index() -> str:
    return "\n".join(f"{chapter_id}: {chapter['titulo']}" for chapter_id, chapter in CHAPTERS.items())


def get_chapter(chapter_id: str) -> dict | None:
    return CHAPTERS.get(chapter_id)
