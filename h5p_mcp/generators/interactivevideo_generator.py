from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from h5p_mcp.generators.blanks_generator import BlanksGenerator
from h5p_mcp.generators.mcq_generator import MCQGenerator
from h5p_mcp.generators.truefalse_generator import TrueFalseGenerator
from h5p_mcp.libraries import CONTENT_TYPE_NAMES, library_string, subcontent_metadata
from h5p_mcp.models.quiz_models import (
    FillBlanksQuiz,
    InteractiveVideoQuiz,
    MCQQuiz,
    QuestionModel,
    TrueFalseQuiz,
    VideoInteraction,
)
from h5p_mcp.utils.html_utils import as_paragraph


# Where an interaction sits on the video, as percentages of the player area.
# Buttons are small and centred; posters take most of the frame.
_BUTTON_POSITION = {"x": 45.0, "y": 45.0}
_POSTER_POSITION = {"x": 10.0, "y": 10.0, "width": 80.0, "height": 70.0}


def mime_for_url(url: str) -> str:
    """
    Map a video URL to the mime type H5P.Video expects.

    YouTube is a distinct pseudo-mime in H5P; everything else is matched on the
    file extension, defaulting to mp4 for extensionless streaming URLs.
    """
    lowered = url.lower()
    if re.search(r"://([\w-]+\.)*(youtube\.com|youtube-nocookie\.com|youtu\.be)(/|$)", lowered):
        return "video/YouTube"
    if lowered.endswith(".webm"):
        return "video/webm"
    if lowered.endswith((".ogv", ".ogg")):
        return "video/ogg"
    return "video/mp4"


class InteractiveVideoGenerator:
    """
    Convert an InteractiveVideoQuiz into H5P.InteractiveVideo content.json.

    The heavy lifting is delegated: each timed question is rendered by the same
    generator used for the standalone content type, then wrapped in the
    interaction envelope (timecode, position, sub-content identity) that
    Interactive Video expects.
    """

    def __init__(self, *, template_path: Path, templates_dir: Path) -> None:
        self._template_path = template_path
        self._templates_dir = templates_dir

        self._mcq = MCQGenerator(templates_dir / "mcq" / "content.json")
        self._tf = TrueFalseGenerator(templates_dir / "truefalse" / "content.json")
        self._blanks = BlanksGenerator(templates_dir / "blanks" / "content.json")

    def generate_content_json(self, quiz: InteractiveVideoQuiz) -> dict[str, Any]:
        template: dict[str, Any] = json.loads(self._template_path.read_text(encoding="utf-8"))

        video = template["interactiveVideo"]["video"]
        video["files"] = [
            {
                "path": quiz.video_url,
                "mime": mime_for_url(quiz.video_url),
                "copyright": {"license": "U"},
            }
        ]

        start_screen = video["startScreenOptions"]
        start_screen["title"] = quiz.title
        if quiz.summary.strip():
            start_screen["shortStartDescription"] = quiz.summary.strip()

        template["interactiveVideo"]["assets"]["interactions"] = [
            self._to_interaction(item) for item in quiz.interactions
        ]
        template["override"]["startVideoAt"] = quiz.start_video_at

        return template

    def _to_interaction(self, item: VideoInteraction) -> dict[str, Any]:
        question = item.question
        position = dict(_POSTER_POSITION if item.display == "poster" else _BUTTON_POSITION)
        title = question.title

        interaction: dict[str, Any] = {
            **position,
            "duration": {"from": item.time, "to": item.time + item.duration},
            "pause": item.pause,
            "displayType": item.display,
            "buttonOnMobile": False,
            "label": as_paragraph(item.label) if item.label else "",
            "libraryTitle": CONTENT_TYPE_NAMES[question.type],
            "action": {
                "library": library_string(question.type),
                "params": self._params_for(question),
                "subContentId": str(uuid.uuid4()),
                "metadata": subcontent_metadata(question.type, title),
            },
            "adaptivity": {
                "correct": {"allowOptOut": False, "message": ""},
                "wrong": {"allowOptOut": False, "message": ""},
                "requireCompletion": False,
            },
            "visuals": {"backgroundColor": "rgb(255, 255, 255)", "boxShadow": True},
        }
        return interaction

    def _params_for(self, question: QuestionModel) -> dict[str, Any]:
        if isinstance(question, MCQQuiz):
            return self._mcq.generate_content_json(question)
        if isinstance(question, TrueFalseQuiz):
            return self._tf.generate_content_json(question)
        if isinstance(question, FillBlanksQuiz):
            return self._blanks.generate_content_json(question)
        raise ValueError(f"Unsupported question type in Interactive Video: {type(question).__name__}")
