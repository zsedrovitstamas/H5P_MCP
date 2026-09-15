from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _decode_unicode_escapes(text: str) -> str:
    """
    Decode literal \\uXXXX sequences that were not resolved by the JSON parser.

    This happens when JSON is double-encoded (e.g. the string contains the 6
    characters backslash-u-0-0-e-9 instead of the actual é character).  We
    normalise them here so that validators and generators always work with
    real Unicode text.
    """
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)


class QuizType(str, Enum):
    mcq = "mcq"
    truefalse = "truefalse"
    blanks = "blanks"
    questionset = "questionset"
    interactivevideo = "interactivevideo"


class QuizBase(BaseModel):
    """
    Canonical, AI-friendly quiz schema used by MCP tools.

    Generators convert these models into H5P content JSON structures.
    """

    type: QuizType
    title: str = Field(min_length=1, max_length=200)


class MCQQuiz(QuizBase):
    type: Literal[QuizType.mcq] = QuizType.mcq
    question: str = Field(min_length=1, max_length=2000)
    choices: list[str] = Field(min_length=2, max_length=12)
    correct_answer: str = Field(min_length=1, max_length=500)
    explanation: str = Field(default="", max_length=4000)

    @field_validator("choices")
    @classmethod
    def _normalize_choices(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c.strip()]
        if len(cleaned) < 2:
            raise ValueError("choices must contain at least 2 non-empty items")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("choices must not contain duplicates")
        return cleaned

    @model_validator(mode="after")
    def _correct_in_choices(self) -> "MCQQuiz":
        if self.correct_answer.strip() not in self.choices:
            raise ValueError("correct_answer must match one of the choices exactly")
        return self


class TrueFalseQuiz(QuizBase):
    type: Literal[QuizType.truefalse] = QuizType.truefalse
    question: str = Field(min_length=1, max_length=2000)
    correct_answer: bool
    explanation: str = Field(default="", max_length=4000)


class FillBlanksQuiz(QuizBase):
    type: Literal[QuizType.blanks] = QuizType.blanks
    text: str = Field(
        min_length=1,
        max_length=8000,
        description="Text containing H5P.Blanks asterisk-wrapped answers, e.g. 'The capital is *Paris*.'",
    )
    answers: list[str] = Field(min_length=1, max_length=50)
    instructions: str = Field(
        default="Fill in the missing words.",
        min_length=1,
        max_length=500,
        description="Task description shown above the exercise",
    )

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_text(cls, v: str) -> str:
        """Decode literal \\uXXXX escapes so comparisons always use real characters."""
        return _decode_unicode_escapes(v) if isinstance(v, str) else v

    @field_validator("answers")
    @classmethod
    def _normalize_answers(cls, v: list[str]) -> list[str]:
        cleaned = [_decode_unicode_escapes(a).strip() for a in v if a.strip()]
        if not cleaned:
            raise ValueError("answers must contain at least 1 non-empty item")
        return cleaned

    @model_validator(mode="after")
    def _answers_match_text(self) -> "FillBlanksQuiz":
        extracted = extract_asterisk_answers(self.text)
        if not extracted:
            raise ValueError("text must contain at least one *answer* (asterisk-wrapped)")
        missing = [a for a in self.answers if a not in extracted]
        if missing:
            raise ValueError(
                "answers must be present in text as *answer* tokens. Missing: " + ", ".join(missing)
            )
        return self


class QuestionSetQuiz(QuizBase):
    """
    A mixed quiz container exported as H5P.QuestionSet.

    This enables packaging multiple question *types* into a single .h5p.
    """

    type: Literal[QuizType.questionset] = QuizType.questionset
    intro: str = Field(default="", max_length=4000)
    questions: list[MCQQuiz | TrueFalseQuiz | FillBlanksQuiz] = Field(min_length=1, max_length=50)
    pass_percentage: int = Field(default=50, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_nested(self) -> "QuestionSetQuiz":
        # Ensure nested items are not themselves containers.
        for q in self.questions:
            if getattr(q, "type", None) == QuizType.questionset:
                raise ValueError("Nested questionset is not supported")
        return self


QuestionModel = MCQQuiz | TrueFalseQuiz | FillBlanksQuiz


class VideoInteraction(BaseModel):
    """
    One question pinned to a point on a video's timeline.

    `time` is when the interaction appears and `duration` how long it stays
    visible; H5P stores these as an absolute from/to pair.
    """

    time: float = Field(ge=0, description="Seconds into the video where the interaction appears")
    duration: float = Field(default=10.0, gt=0, le=3600, description="How many seconds it stays visible")
    pause: bool = Field(default=True, description="Pause the video when the interaction appears")
    display: Literal["button", "poster"] = "button"
    label: str = Field(default="", max_length=200)
    question: QuestionModel

    @model_validator(mode="after")
    def _no_container_questions(self) -> "VideoInteraction":
        if getattr(self.question, "type", None) in (QuizType.questionset, QuizType.interactivevideo):
            raise ValueError("Video interactions take a single question, not a container")
        return self


class InteractiveVideoQuiz(QuizBase):
    """
    A video with questions overlaid at timecodes, exported as H5P.InteractiveVideo.

    The video itself is referenced by URL and never copied into the package:
    embedding media would blow past typical LMS upload limits, and H5P resolves
    external sources (YouTube or a direct file URL) at playback time.
    """

    type: Literal[QuizType.interactivevideo] = QuizType.interactivevideo
    video_url: str = Field(min_length=1, max_length=2000)
    interactions: list[VideoInteraction] = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=4000, description="Short description on the start screen")
    start_video_at: int = Field(default=0, ge=0)

    @field_validator("video_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        url = v.strip()
        if not re.match(r"^https?://", url, re.IGNORECASE):
            raise ValueError("video_url must be an http(s) URL")
        return url

    @model_validator(mode="after")
    def _sort_interactions(self) -> "InteractiveVideoQuiz":
        # H5P renders in list order; keeping them sorted makes the exported
        # timeline match the order an author reads.
        self.interactions.sort(key=lambda i: i.time)
        return self


QuizModel = MCQQuiz | TrueFalseQuiz | FillBlanksQuiz | QuestionSetQuiz | InteractiveVideoQuiz


class ExportRequest(BaseModel):
    quiz_data: dict[str, Any]
    output_name: str = Field(min_length=1, max_length=120)


def split_blanks(text: str) -> list[tuple[bool, str]]:
    """
    Split H5P.Blanks text into (is_answer, chunk) segments.

    Asterisks toggle between prose and answer, so "A *cat* sits" yields
    [(False, "A "), (True, "cat"), (False, " sits")]. A trailing asterisk that
    never closes leaves its remainder as prose, matching how an unterminated
    gap is simply not a gap.

    This is the single source of truth for asterisk parsing: both answer
    extraction and HTML escaping read the text through it, so what gets
    validated as an answer is exactly what gets rendered as one.
    """
    segments: list[tuple[bool, str]] = []
    buf: list[str] = []
    in_answer = False

    for ch in text:
        if ch == "*":
            segments.append((in_answer, "".join(buf)))
            buf = []
            in_answer = not in_answer
            continue
        buf.append(ch)

    tail = "".join(buf)
    if in_answer:
        # Unclosed gap: the opening asterisk was literal after all.
        segments.append((False, "*" + tail))
    else:
        segments.append((False, tail))

    return [(is_answer, chunk) for is_answer, chunk in segments if chunk != ""]


def extract_asterisk_answers(text: str) -> list[str]:
    """
    Extract asterisk-wrapped answers from H5P.Blanks text.

    Example: "A *cat* and a *dog*." -> ["cat", "dog"]
    """
    return [
        stripped
        for is_answer, chunk in split_blanks(text)
        if is_answer and (stripped := chunk.strip())
    ]

