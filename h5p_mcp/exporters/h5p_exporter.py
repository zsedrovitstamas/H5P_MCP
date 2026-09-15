from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from h5p_mcp.generators.blanks_generator import BlanksGenerator
from h5p_mcp.generators.interactivebook_generator import InteractiveBookGenerator
from h5p_mcp.generators.interactivevideo_generator import InteractiveVideoGenerator
from h5p_mcp.generators.mcq_generator import MCQGenerator
from h5p_mcp.generators.questionset_generator import QuestionSetGenerator
from h5p_mcp.generators.truefalse_generator import TrueFalseGenerator
from h5p_mcp.libraries import (
    ADVANCED_TEXT,
    COLUMN,
    LibrarySpec,
    dependency_entry_for_spec,
    embed_types,
    library_spec,
)
from h5p_mcp.models.quiz_models import (
    FillBlanksQuiz,
    InteractiveBookQuiz,
    InteractiveVideoQuiz,
    MCQQuiz,
    QuestionSetQuiz,
    QuizModel,
    QuizType,
    TextSection,
    TrueFalseQuiz,
)
from h5p_mcp.utils.file_utils import resolve_export_dir, safe_filename, temp_workdir, write_json
from h5p_mcp.utils.zip_utils import zip_dir


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    h5p_json: dict[str, Any]
    content_json: dict[str, Any]


class H5PExporter:
    """
    Export canonical quiz models into .h5p (zip) packages.

    The resulting .h5p includes:
    - h5p.json
    - content/content.json
    """

    def __init__(self, *, export_dir: str | None = None, templates_dir: str | None = None) -> None:
        self._export_dir = resolve_export_dir(export_dir)
        self._templates_dir = Path(templates_dir) if templates_dir else Path(
            __file__).resolve().parents[1] / "templates"

        self._mcq = MCQGenerator(self._templates_dir / "mcq" / "content.json")
        self._tf = TrueFalseGenerator(
            self._templates_dir / "truefalse" / "content.json")
        self._blanks = BlanksGenerator(
            self._templates_dir / "blanks" / "content.json")
        self._qs = QuestionSetGenerator(
            template_path=self._templates_dir / "questionset" / "content.json",
            templates_dir=self._templates_dir,
        )
        self._iv = InteractiveVideoGenerator(
            template_path=self._templates_dir / "interactivevideo" / "content.json",
            templates_dir=self._templates_dir,
        )
        self._ib = InteractiveBookGenerator(
            template_path=self._templates_dir / "interactivebook" / "content.json",
            templates_dir=self._templates_dir,
        )

    def export(self, quiz: QuizModel, *, output_name: str) -> ExportResult:
        out_stem = safe_filename(output_name)
        out_path = self._export_dir / f"{out_stem}.h5p"

        content_json = self._generate_content_json(quiz)
        h5p_json = self._build_h5p_manifest(quiz)
        content_json = self._ensure_content_metadata(
            content_json, title=quiz.title)

        logger.info("Exporting quiz type=%s title=%s -> %s",
                    quiz.type.value, quiz.title, out_path)

        with temp_workdir(prefix="h5p_mcp_export_") as wd:
            root = wd
            content_dir = root / "content"
            content_dir.mkdir(parents=True, exist_ok=True)

            write_json(root / "h5p.json", h5p_json)
            write_json(content_dir / "content.json", content_json)

            tmp_zip = root / f"{out_stem}.zip"
            zip_dir(root, tmp_zip)

            # Move into place as .h5p
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.exists():
                out_path.unlink()
            tmp_zip.replace(out_path)

        return ExportResult(output_path=out_path, h5p_json=h5p_json, content_json=content_json)

    def _generate_content_json(self, quiz: QuizModel) -> dict[str, Any]:
        if isinstance(quiz, MCQQuiz):
            return self._mcq.generate_content_json(quiz)
        if isinstance(quiz, TrueFalseQuiz):
            return self._tf.generate_content_json(quiz)
        if isinstance(quiz, FillBlanksQuiz):
            return self._blanks.generate_content_json(quiz)
        if isinstance(quiz, QuestionSetQuiz):
            return self._qs.generate_content_json(quiz)
        if isinstance(quiz, InteractiveVideoQuiz):
            return self._iv.generate_content_json(quiz)
        if isinstance(quiz, InteractiveBookQuiz):
            return self._ib.generate_content_json(quiz)
        raise ValueError(f"Unsupported quiz model: {type(quiz).__name__}")

    def _build_h5p_manifest(self, quiz: QuizModel) -> dict[str, Any]:
        main_library, _major, _minor = library_spec(quiz.type)
        # Keep this minimal. Some validators reject unknown or mis-typed keys.
        return {
            "title": quiz.title,
            "language": "en",
            "mainLibrary": main_library,
            "embedTypes": embed_types(quiz.type),
            "preloadedDependencies": [
                dependency_entry_for_spec(spec) for spec in _collect_libraries(quiz)
            ],
        }

    def _ensure_content_metadata(self, content_json: dict[str, Any], *, title: str) -> dict[str, Any]:
        """
        Ensure content.json includes a spec-friendly metadata block.

        Many platforms expect metadata on content, not in h5p.json.
        """
        if not isinstance(content_json, dict):
            raise ValueError("content_json must be a dict")

        meta = content_json.get("metadata")
        if not isinstance(meta, dict):
            meta = {}

        meta.setdefault("title", title)
        meta.setdefault("license", "U")
        meta.setdefault("defaultLanguage", "en")
        meta.setdefault("authors", [])
        meta.setdefault("changes", [])
        meta.setdefault("extraTitle", title)

        content_json["metadata"] = meta
        return content_json


def _collect_libraries(quiz: QuizModel) -> list[LibrarySpec]:
    """
    List every library the content instantiates, main library first.

    Container types embed other content types by name inside content.json, and
    H5P expects each of those to be declared in h5p.json. Declaring only the
    main library leaves a host free to drop the embedded content instead of
    reporting a missing library.

    Interactive Book reaches two levels deep: the book instantiates a Column
    per chapter, and each Column instantiates its sections.
    """
    found: list[LibrarySpec] = [library_spec(quiz.type)]

    if isinstance(quiz, QuestionSetQuiz):
        found.extend(library_spec(q.type) for q in quiz.questions)
    elif isinstance(quiz, InteractiveVideoQuiz):
        found.extend(library_spec(item.question.type) for item in quiz.interactions)
    elif isinstance(quiz, InteractiveBookQuiz):
        found.append(COLUMN)
        for chapter in quiz.chapters:
            for section in chapter.sections:
                if isinstance(section, TextSection):
                    found.append(ADVANCED_TEXT)
                else:
                    found.append(library_spec(section.type))

    # Preserve first-seen order so the main library stays first.
    return list(dict.fromkeys(found))
