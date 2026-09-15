from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from h5p_mcp.generators.blanks_generator import BlanksGenerator
from h5p_mcp.generators.mcq_generator import MCQGenerator
from h5p_mcp.generators.truefalse_generator import TrueFalseGenerator
from h5p_mcp.libraries import (
    ADVANCED_TEXT,
    COLUMN,
    library_string,
    spec_metadata,
    spec_string,
    subcontent_metadata,
)
from h5p_mcp.models.quiz_models import (
    BookChapter,
    BookSection,
    FillBlanksQuiz,
    InteractiveBookQuiz,
    MCQQuiz,
    TextSection,
    TrueFalseQuiz,
)
from h5p_mcp.utils.html_utils import escape_html


def render_text_section(section: TextSection) -> str:
    """
    Render a prose section as the HTML string H5P.AdvancedText expects.

    Input is plain text, so everything is escaped: an optional heading becomes
    an <h2> and blank-line-separated blocks become paragraphs. Single newlines
    inside a block are soft wraps and become <br>.
    """
    parts: list[str] = []
    if section.heading.strip():
        parts.append(f"<h2>{escape_html(section.heading.strip())}</h2>")

    for block in section.body.split("\n\n"):
        lines = [escape_html(line.strip()) for line in block.split("\n") if line.strip()]
        if lines:
            parts.append(f"<p>{'<br>'.join(lines)}</p>")

    return "".join(parts)


class InteractiveBookGenerator:
    """
    Convert an InteractiveBookQuiz into H5P.InteractiveBook content.json.

    A book is a list of chapters, and each chapter is an H5P.Column wrapping
    that page's sections. Two shapes here are load-bearing and easy to get
    wrong, both confirmed against the runtime in h5p-interactive-book:

    - `chapters` is a flat list of library objects, not a list of wrappers.
      The runtime hands each entry straight to H5P.newRunnable
      (pagecontent.js), so a {"chapter": ...} envelope would break it.
    - the chapter title is read from the chapter's *metadata*, not its
      params, so metadata is required rather than decorative.
    """

    def __init__(self, *, template_path: Path, templates_dir: Path) -> None:
        self._template_path = template_path
        self._templates_dir = templates_dir

        self._mcq = MCQGenerator(templates_dir / "mcq" / "content.json")
        self._tf = TrueFalseGenerator(templates_dir / "truefalse" / "content.json")
        self._blanks = BlanksGenerator(templates_dir / "blanks" / "content.json")

    def generate_content_json(self, quiz: InteractiveBookQuiz) -> dict[str, Any]:
        template: dict[str, Any] = json.loads(self._template_path.read_text(encoding="utf-8"))

        template["showCoverPage"] = quiz.show_cover
        template["bookCover"] = {
            "coverDescription": f"<p>{escape_html(quiz.cover_description.strip())}</p>"
            if quiz.cover_description.strip()
            else ""
        }

        template.setdefault("behaviour", {})
        template["behaviour"]["baseColor"] = quiz.base_color
        template["behaviour"]["displaySummary"] = quiz.display_summary

        template["chapters"] = [self._to_chapter(chapter) for chapter in quiz.chapters]
        return template

    def _to_chapter(self, chapter: BookChapter) -> dict[str, Any]:
        return {
            "library": spec_string(COLUMN),
            "params": {
                "content": [self._to_column_item(section) for section in chapter.sections]
            },
            "subContentId": str(uuid.uuid4()),
            # The table of contents reads the chapter name from here.
            "metadata": spec_metadata(COLUMN, chapter.title),
        }

    def _to_column_item(self, section: BookSection) -> dict[str, Any]:
        return {"content": self._to_content(section), "useSeparator": "auto"}

    def _to_content(self, section: BookSection) -> dict[str, Any]:
        if isinstance(section, TextSection):
            title = section.heading.strip() or "Text"
            return {
                "library": spec_string(ADVANCED_TEXT),
                "params": {"text": render_text_section(section)},
                "subContentId": str(uuid.uuid4()),
                "metadata": spec_metadata(ADVANCED_TEXT, title),
            }

        if isinstance(section, MCQQuiz):
            params = self._mcq.generate_content_json(section)
        elif isinstance(section, TrueFalseQuiz):
            params = self._tf.generate_content_json(section)
        elif isinstance(section, FillBlanksQuiz):
            params = self._blanks.generate_content_json(section)
        else:
            raise ValueError(f"Unsupported section type in Interactive Book: {type(section).__name__}")

        return {
            "library": library_string(section.type),
            "params": params,
            "subContentId": str(uuid.uuid4()),
            "metadata": subcontent_metadata(section.type, section.title),
        }
