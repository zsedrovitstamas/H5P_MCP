from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from h5p_mcp.exporters.h5p_exporter import H5PExporter
from h5p_mcp.models.quiz_models import (
    BookChapter,
    FillBlanksQuiz,
    InteractiveBookQuiz,
    InteractiveVideoQuiz,
    MCQQuiz,
    QuestionSetQuiz,
    QuizModel,
    TextSection,
    TrueFalseQuiz,
    VideoInteraction,
)
from h5p_mcp.utils.markdown_utils import parse_markdown_quizzes
from h5p_mcp.validators.quiz_validator import H5PValidationResult, validate_h5p_package, validate_quiz_data


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    # Ensure UTF-8 output on Windows terminals where possible.
    try:
        import sys

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


mcp = FastMCP("h5p-quiz-generator")


@mcp.tool()
def create_mcq_quiz(
    title: str,
    question: str,
    choices: list[str],
    correct_answer: str,
    explanation: str = "",
) -> dict[str, Any]:
    """
    Create a validated canonical MCQ quiz object.
    """
    quiz = MCQQuiz(
        title=title,
        question=question,
        choices=choices,
        correct_answer=correct_answer,
        explanation=explanation,
    )
    return quiz.model_dump()


@mcp.tool()
def create_true_false_quiz(
    title: str,
    question: str,
    correct_answer: bool,
    explanation: str = "",
) -> dict[str, Any]:
    """
    Create a validated canonical True/False quiz object.
    """
    quiz = TrueFalseQuiz(
        title=title,
        question=question,
        correct_answer=correct_answer,
        explanation=explanation,
    )
    return quiz.model_dump()


@mcp.tool()
def create_fill_blanks_quiz(
    title: str,
    text: str,
    answers: list[str],
) -> dict[str, Any]:
    """
    Create a validated canonical Fill in the Blanks quiz object.

    The text must contain asterisk-wrapped answers: "The capital is *Paris*."
    """
    quiz = FillBlanksQuiz(title=title, text=text, answers=answers)
    return quiz.model_dump()


@mcp.tool()
def create_questionset_quiz(
    title: str,
    intro: str,
    questions: list[dict[str, Any]],
    pass_percentage: int = 50,
) -> dict[str, Any]:
    """
    Create a validated canonical QuestionSet quiz object.

    `questions` is a list of canonical quiz dicts (mcq/truefalse/blanks).
    """
    validated_questions = [validate_quiz_data(q) for q in questions]
    quiz = QuestionSetQuiz(title=title, intro=intro, questions=validated_questions, pass_percentage=pass_percentage)
    return quiz.model_dump()

@mcp.tool()
def create_interactive_video(
    title: str,
    video_url: str,
    interactions: list[dict[str, Any]],
    summary: str = "",
    start_video_at: int = 0,
) -> dict[str, Any]:
    """
    Create a validated canonical Interactive Video object.

    The video stays external and is referenced by URL (YouTube or a direct
    .mp4/.webm/.ogv link) — it is never copied into the .h5p package.

    Each entry in `interactions` is:
      time      seconds into the video where the question appears (required)
      question  a canonical quiz dict (mcq/truefalse/blanks) (required)
      duration  seconds it stays visible (default 10)
      pause     pause the video when it appears (default true)
      display   "button" (click to open) or "poster" (shown over the video)
      label     optional caption shown next to the button
    """
    parsed = [VideoInteraction.model_validate(item) for item in interactions]
    quiz = InteractiveVideoQuiz(
        title=title,
        video_url=video_url,
        interactions=parsed,
        summary=summary,
        start_video_at=start_video_at,
    )
    return quiz.model_dump()


@mcp.tool()
def create_interactive_book(
    title: str,
    chapters: list[dict[str, Any]],
    cover_description: str = "",
    show_cover: bool = True,
    base_color: str = "#1768c4",
    display_summary: bool = True,
) -> dict[str, Any]:
    """
    Create a validated canonical Interactive Book object.

    Each entry in `chapters` is one page of the book:
      title     the chapter name, shown in the table of contents (required)
      sections  an ordered list of blocks on that page (required)

    A section is either a prose block:
      {"type": "text", "heading": "optional", "body": "plain text"}
    or a canonical quiz dict (mcq/truefalse/blanks), which becomes a graded
    activity embedded in the page.

    Section `body` is plain text, not HTML. Blank lines separate paragraphs and
    single newlines are soft wraps; any markup typed in is escaped and shows up
    literally.
    """
    parsed = [BookChapter.model_validate(chapter) for chapter in chapters]
    book = InteractiveBookQuiz(
        title=title,
        chapters=parsed,
        cover_description=cover_description,
        show_cover=show_cover,
        base_color=base_color,
        display_summary=display_summary,
    )
    return book.model_dump()


@mcp.tool()
def export_h5p(quiz_data: dict[str, Any], output_name: str) -> dict[str, Any]:
    """
    Export a canonical quiz object to a .h5p file.

    Returns the output path and the generated manifests.
    """
    quiz: QuizModel = validate_quiz_data(quiz_data)
    exporter = H5PExporter()
    result = exporter.export(quiz, output_name=output_name)
    return {
        "output_path": str(result.output_path),
        "h5p_json": result.h5p_json,
        "content_json": result.content_json,
    }


@mcp.tool()
def validate_h5p(path: str) -> dict[str, Any]:
    """
    Validate a generated (or external) .h5p package.
    """
    res: H5PValidationResult = validate_h5p_package(path)
    return {"ok": res.ok, "errors": res.errors, "warnings": res.warnings}


@mcp.tool()
def export_h5p_batch(quizzes: list[dict[str, Any]], name_prefix: str = "quiz") -> dict[str, Any]:
    """
    Bonus: export many quizzes in one call.

    Each quiz is validated (Pydantic) before export. Returns per-item results.
    """
    exporter = H5PExporter()
    results: list[dict[str, Any]] = []
    for idx, quiz_data in enumerate(quizzes):
        quiz: QuizModel = validate_quiz_data(quiz_data)
        output_name = f"{name_prefix}_{idx+1:03d}"
        exported = exporter.export(quiz, output_name=output_name)
        results.append({"output_name": output_name, "output_path": str(exported.output_path)})
    return {"count": len(results), "results": results}


@mcp.tool()
def markdown_to_quizzes(markdown: str) -> dict[str, Any]:
    """
    Bonus: parse a simple markdown format into canonical quiz objects.
    """
    quizzes = parse_markdown_quizzes(markdown)
    # Validate here so the calling agent gets immediate, structured failures.
    validated = [validate_quiz_data(q).model_dump() for q in quizzes]
    return {"count": len(validated), "quizzes": validated}


@mcp.tool()
def h5p_prompt_helpers() -> dict[str, Any]:
    """
    Bonus: return concise, AI-ready guidance for generating robust quiz inputs.
    """
    return {
        "mcq": {
            "notes": [
                "choices must be unique strings; correct_answer must match one choice exactly",
                "explanation is optional and will be mapped to feedback where supported",
            ],
            "example": {
                "title": "Basic Math",
                "question": "What is 2 + 2?",
                "choices": ["3", "4", "5"],
                "correct_answer": "4",
                "explanation": "2 + 2 equals 4.",
            },
        },
        "truefalse": {
            "notes": ["correct_answer must be boolean true/false"],
            "example": {
                "title": "Astronomy",
                "question": "The Earth orbits the Sun.",
                "correct_answer": True,
                "explanation": "It takes about one year.",
            },
        },
        "blanks": {
            "notes": [
                "text must contain asterisk-wrapped answers, e.g. 'The capital is *Paris*.'",
                "answers list must appear inside text as *answer* tokens",
            ],
            "example": {
                "title": "Capitals",
                "text": "The capital of France is *Paris*.",
                "answers": ["Paris"],
            },
        },
        "interactive_book": {
            "notes": [
                "a book is a list of chapters; each chapter is one page with an ordered list of sections",
                "a section is either {'type': 'text', 'heading': ..., 'body': ...} or a quiz dict",
                "section body is plain text: blank lines separate paragraphs, markup is escaped",
                "the chapter title is what the reader sees in the table of contents",
            ],
            "example": {
                "title": "Photosynthesis",
                "cover_description": "How plants make food.",
                "chapters": [
                    {
                        "title": "The basics",
                        "sections": [
                            {
                                "type": "text",
                                "heading": "Overview",
                                "body": "Plants convert light into sugar.\n\nOxygen is released as a by-product.",
                            },
                            {
                                "type": "truefalse",
                                "title": "Check",
                                "question": "Photosynthesis releases oxygen.",
                                "correct_answer": True,
                            },
                        ],
                    }
                ],
            },
        },
        "interactive_video": {
            "notes": [
                "video_url must be an http(s) URL; the video is never bundled into the package",
                "YouTube links are detected automatically, as are .mp4/.webm/.ogv files",
                "each interaction needs a time (seconds) and a canonical question dict",
                "interactions are sorted by time on validation, so order does not matter",
            ],
            "example": {
                "title": "Photosynthesis explained",
                "video_url": "https://www.youtube.com/watch?v=example",
                "summary": "Watch the clip and answer as you go.",
                "interactions": [
                    {
                        "time": 45,
                        "duration": 15,
                        "pause": True,
                        "question": {
                            "type": "truefalse",
                            "title": "Checkpoint",
                            "question": "Chlorophyll absorbs green light most strongly.",
                            "correct_answer": False,
                            "explanation": "Green is largely reflected, which is why leaves look green.",
                        },
                    }
                ],
            },
        },
    }


def _generate_samples() -> list[Path]:
    exporter = H5PExporter()

    outputs: list[Path] = []

    # MCQ samples (single correct)
    outputs.append(
        exporter.export(
            MCQQuiz(
                title="MCQ - Basic Math",
                question="What is 2 + 2?",
                choices=["3", "4", "5"],
                correct_answer="4",
                explanation="2 + 2 equals 4.",
            ),
            output_name="sample_mcq_basic_math",
        ).output_path
    )
    outputs.append(
        exporter.export(
            MCQQuiz(
                title="MCQ - Geography",
                question="Which country has the capital city 'Lisbon'?",
                choices=["Spain", "Portugal", "Brazil", "Italy"],
                correct_answer="Portugal",
                explanation="Lisbon is the capital of Portugal.",
            ),
            output_name="sample_mcq_geography",
        ).output_path
    )

    # True/False samples
    outputs.append(
        exporter.export(
            TrueFalseQuiz(
                title="True/False - Astronomy",
                question="The Earth orbits the Sun.",
                correct_answer=True,
                explanation="It takes about one year.",
            ),
            output_name="sample_truefalse_astronomy",
        ).output_path
    )
    outputs.append(
        exporter.export(
            TrueFalseQuiz(
                title="True/False - Biology",
                question="Humans can breathe underwater unaided.",
                correct_answer=False,
                explanation="Humans need equipment (like scuba gear) to breathe underwater.",
            ),
            output_name="sample_truefalse_biology",
        ).output_path
    )

    # Fill in the blanks samples
    outputs.append(
        exporter.export(
            FillBlanksQuiz(
                title="Blanks - Capitals",
                text="The capital of France is *Paris* and the capital of Italy is *Rome*.",
                answers=["Paris", "Rome"],
            ),
            output_name="sample_blanks_capitals",
        ).output_path
    )
    outputs.append(
        exporter.export(
            FillBlanksQuiz(
                title="Blanks - Python",
                text="In Python, a list is written with square brackets like *[1, 2, 3]*.",
                answers=["[1, 2, 3]"],
            ),
            output_name="sample_blanks_python",
        ).output_path
    )

    # Interactive Video sample (timed questions over an external video)
    outputs.append(
        exporter.export(
            InteractiveVideoQuiz(
                title="Interactive Video - Water Cycle",
                video_url="https://www.youtube.com/watch?v=al-do-HGuIk",
                summary="Watch the clip and answer the questions as they appear.",
                interactions=[
                    VideoInteraction(
                        time=30,
                        question=TrueFalseQuiz(
                            title="Evaporation",
                            question="Evaporation turns liquid water into vapour.",
                            correct_answer=True,
                            explanation="Heat gives water molecules enough energy to escape as vapour.",
                        ),
                    ),
                    VideoInteraction(
                        time=75,
                        duration=20,
                        display="poster",
                        question=MCQQuiz(
                            title="Condensation",
                            question="What forms when water vapour cools and condenses?",
                            choices=["Clouds", "Lava", "Sand"],
                            correct_answer="Clouds",
                            explanation="Cooling vapour condenses onto particles and forms clouds.",
                        ),
                    ),
                ],
            ),
            output_name="sample_interactivevideo_water_cycle",
        ).output_path
    )

    # Interactive Book sample (prose and questions across chapters)
    outputs.append(
        exporter.export(
            InteractiveBookQuiz(
                title="Interactive Book - Photosynthesis",
                cover_description="A short book on how plants turn light into food.",
                chapters=[
                    BookChapter(
                        title="What photosynthesis is",
                        sections=[
                            TextSection(
                                heading="Overview",
                                body=(
                                    "Plants use light energy to turn carbon dioxide and water into sugar.\n"
                                    "The reaction happens inside chloroplasts.\n\n"
                                    "Oxygen is released as a by-product, which is why the process matters "
                                    "far beyond the plant itself."
                                ),
                            ),
                            MCQQuiz(
                                title="Where it happens",
                                question="Which part of the cell carries out photosynthesis?",
                                choices=["The chloroplast", "The nucleus", "The ribosome"],
                                correct_answer="The chloroplast",
                                explanation="Chloroplasts hold the chlorophyll that absorbs light.",
                            ),
                        ],
                    ),
                    BookChapter(
                        title="Why it matters",
                        sections=[
                            TextSection(
                                body=(
                                    "Almost every food chain starts with a photosynthesising organism, "
                                    "and the oxygen in the atmosphere is largely their doing."
                                ),
                            ),
                            TrueFalseQuiz(
                                title="Food chains",
                                question="Most food chains begin with an organism that photosynthesises.",
                                correct_answer=True,
                                explanation="Producers capture the energy every later link depends on.",
                            ),
                        ],
                    ),
                ],
            ),
            output_name="sample_interactivebook_photosynthesis",
        ).output_path
    )

    # QuestionSet sample (mixed types in one .h5p)
    outputs.append(
        exporter.export(
            QuestionSetQuiz(
                title="Question Set - Mixed Quiz",
                intro="This quiz mixes multiple question types in one activity.",
                pass_percentage=60,
                questions=[
                    MCQQuiz(
                        title="MCQ - Safety",
                        question="Which of these is a strong password practice?",
                        choices=[
                            "Use 'password123' everywhere",
                            "Reuse the same password for convenience",
                            "Use a password manager and unique passwords",
                            "Share passwords over email",
                        ],
                        correct_answer="Use a password manager and unique passwords",
                        explanation="Unique passwords + a password manager is the standard best practice.",
                    ),
                    TrueFalseQuiz(
                        title="True/False - Web",
                        question="HTTPS helps protect data in transit between browser and server.",
                        correct_answer=True,
                        explanation="HTTPS encrypts traffic and reduces tampering risk.",
                    ),
                    FillBlanksQuiz(
                        title="Blanks - Geography",
                        text="The capital of Japan is *Tokyo*.",
                        answers=["Tokyo"],
                    ),
                ],
            ),
            output_name="sample_questionset_mixed",
        ).output_path
    )

    return outputs


def main() -> None:
    _configure_logging()

    parser = argparse.ArgumentParser(description="H5P Quiz Generator MCP Server")
    parser.add_argument("--generate-samples", action="store_true", help="Generate sample .h5p files and exit")
    args = parser.parse_args()

    if args.generate_samples:
        paths = _generate_samples()
        for p in paths:
            res = validate_h5p_package(p)
            status = "OK" if res.ok else "FAIL"
            print(f"{status}: {p}")
            if res.errors:
                print("  errors:", res.errors)
            if res.warnings:
                print("  warnings:", res.warnings)
        return

    # MCP stdio server
    mcp.run()


if __name__ == "__main__":
    main()

