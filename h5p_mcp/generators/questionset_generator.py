from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from h5p_mcp.generators.blanks_generator import BlanksGenerator
from h5p_mcp.generators.mcq_generator import MCQGenerator
from h5p_mcp.generators.truefalse_generator import TrueFalseGenerator
from h5p_mcp.libraries import library_string, subcontent_metadata
from h5p_mcp.models.quiz_models import FillBlanksQuiz, MCQQuiz, QuestionSetQuiz, TrueFalseQuiz
from h5p_mcp.utils.html_utils import as_paragraph


class QuestionSetGenerator:
    """
    Convert a QuestionSetQuiz into H5P.QuestionSet content.json.

    QuestionSet embeds a list of question instances with:
    - library: "H5P.MultiChoice x.y"
    - params: the library's parameters object
    - subContentId: UUID
    """

    def __init__(self, *, template_path: Path, templates_dir: Path) -> None:
        self._template_path = template_path
        self._templates_dir = templates_dir

        self._mcq = MCQGenerator(self._templates_dir / "mcq" / "content.json")
        self._tf = TrueFalseGenerator(self._templates_dir / "truefalse" / "content.json")
        self._blanks = BlanksGenerator(self._templates_dir / "blanks" / "content.json")

    def generate_content_json(self, quiz: QuestionSetQuiz) -> dict[str, Any]:
        template: dict[str, Any] = json.loads(self._template_path.read_text(encoding="utf-8"))

        template["title"] = quiz.title
        template.setdefault("introPage", {})
        template["introPage"].setdefault("showIntroPage", True)
        template["introPage"].setdefault("title", quiz.title)
        if quiz.intro.strip():
            template["introPage"]["introduction"] = as_paragraph(quiz.intro.strip())

        template["passPercentage"] = quiz.pass_percentage

        questions: list[dict[str, Any]] = []
        for q in quiz.questions:
            questions.append(self._to_question_instance(q))

        template["questions"] = questions
        return template

    def _to_question_instance(self, q: MCQQuiz | TrueFalseQuiz | FillBlanksQuiz) -> dict[str, Any]:
        if isinstance(q, MCQQuiz):
            params = self._mcq.generate_content_json(q)
        elif isinstance(q, TrueFalseQuiz):
            params = self._tf.generate_content_json(q)
        elif isinstance(q, FillBlanksQuiz):
            params = self._blanks.generate_content_json(q)
        else:
            raise ValueError(f"Unsupported question type in QuestionSet: {type(q).__name__}")

        return {
            "library": library_string(q.type),
            "params": params,
            "subContentId": str(uuid.uuid4()),
            "metadata": subcontent_metadata(q.type, q.title),
        }

