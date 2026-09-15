from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from h5p_mcp.models.quiz_models import FillBlanksQuiz, split_blanks
from h5p_mcp.utils.html_utils import escape_html


def escape_preserving_blanks(text: str) -> str:
    """
    Escape HTML in blanks text while keeping the *answer* markers intact.

    Everything the author wrote is untrusted prose, including what sits inside
    a gap, so both halves are escaped; only the asterisk delimiters are written
    back literally. Segmentation comes from the same scanner the model uses to
    validate answers, so escaping can never disagree with extraction.
    """
    out: list[str] = []
    for is_answer, chunk in split_blanks(text):
        escaped = escape_html(chunk)
        out.append(f"*{escaped}*" if is_answer else escaped)
    return "".join(out)


class BlanksGenerator:
    """
    Convert a FillBlanksQuiz into H5P.Blanks content.json.

    H5P.Blanks splits the two halves of the task: `text` holds the instruction
    shown above the exercise, and `questions` holds the sentences carrying the
    gaps — one html string per line.
    """

    def __init__(self, template_path: Path) -> None:
        self._template_path = template_path

    def generate_content_json(self, quiz: FillBlanksQuiz) -> dict[str, Any]:
        template = json.loads(self._template_path.read_text(encoding="utf-8"))

        template["title"] = quiz.title
        template["text"] = f"<p>{escape_html(quiz.instructions)}</p>"

        # One entry per line, escaped but with the *answer* markers preserved.
        template["questions"] = [
            f"<p>{escape_preserving_blanks(line)}</p>"
            for line in quiz.text.split("\n")
            if line.strip()
        ]

        # Better UX defaults for language learning / practice questions.
        template.setdefault("behaviour", {})
        template["behaviour"].setdefault("caseSensitive", False)
        template["behaviour"].setdefault("enableSolutionsButton", True)

        return template
