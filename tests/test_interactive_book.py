"""
Tests for the Interactive Book content type.

Two shapes here are load-bearing and were confirmed against the runtime in
h5p-interactive-book rather than inferred from semantics.json:

- `chapters` is a flat list of library objects. pagecontent.js hands each entry
  straight to H5P.newRunnable, so a {"chapter": ...} wrapper would break it.
- the chapter title is read from chapter metadata, not params.

Both have explicit tests below, because a wrong guess produces a package that
validates cleanly and then renders an empty book.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from h5p_mcp.exporters.h5p_exporter import H5PExporter  # noqa: E402
from h5p_mcp.generators.interactivebook_generator import render_text_section  # noqa: E402
from h5p_mcp.models.quiz_models import (  # noqa: E402
    BookChapter,
    FillBlanksQuiz,
    InteractiveBookQuiz,
    MCQQuiz,
    TextSection,
    TrueFalseQuiz,
)
from h5p_mcp.validators.quiz_validator import validate_h5p_package, validate_quiz_data  # noqa: E402


@pytest.fixture(scope="module")
def exporter(tmp_path_factory):
    return H5PExporter(export_dir=str(tmp_path_factory.mktemp("book_exports")))


def _mcq(title: str = "Check") -> MCQQuiz:
    return MCQQuiz(
        title=title,
        question="Where does photosynthesis happen?",
        choices=["Chloroplast", "Nucleus", "Ribosome"],
        correct_answer="Chloroplast",
    )


def _book(**overrides) -> InteractiveBookQuiz:
    params = dict(
        title="Photosynthesis",
        cover_description="How plants make food.",
        chapters=[
            BookChapter(
                title="The basics",
                sections=[
                    TextSection(heading="Overview", body="Plants convert light into sugar."),
                    _mcq(),
                ],
            ),
            BookChapter(
                title="Why it matters",
                sections=[TextSection(body="Food chains start here.")],
            ),
        ],
    )
    params.update(overrides)
    return InteractiveBookQuiz(**params)


def _content(path: Path) -> dict:
    with ZipFile(path, "r") as z:
        return json.loads(z.read("content/content.json").decode("utf-8"))


def _h5p(path: Path) -> dict:
    with ZipFile(path, "r") as z:
        return json.loads(z.read("h5p.json").decode("utf-8"))


class TestBookModel:
    def test_valid_book(self):
        book = _book()
        assert book.type.value == "interactivebook"
        assert len(book.chapters) == 2

    def test_rejects_no_chapters(self):
        with pytest.raises(ValidationError):
            _book(chapters=[])

    def test_rejects_chapter_with_no_sections(self):
        with pytest.raises(ValidationError):
            BookChapter(title="Empty", sections=[])

    def test_rejects_untitled_chapter(self):
        with pytest.raises(ValidationError):
            BookChapter(title="", sections=[TextSection(body="text")])

    def test_rejects_blank_body(self):
        with pytest.raises(ValidationError):
            TextSection(body="   ")

    @pytest.mark.parametrize("colour", ["red", "#ABC", "1768c4", "#12345g"])
    def test_rejects_bad_base_color(self, colour):
        with pytest.raises(ValidationError):
            _book(base_color=colour)

    def test_accepts_hex_base_color(self):
        assert _book(base_color="#AA00FF").base_color == "#AA00FF"

    def test_sections_discriminate_by_type(self):
        chapter = BookChapter.model_validate(
            {
                "title": "Mixed",
                "sections": [
                    {"type": "text", "body": "prose"},
                    {"type": "mcq", "title": "Q", "question": "2+2?", "choices": ["3", "4"], "correct_answer": "4"},
                    {"type": "truefalse", "title": "T", "question": "Sky is blue.", "correct_answer": True},
                ],
            }
        )
        assert [type(s).__name__ for s in chapter.sections] == ["TextSection", "MCQQuiz", "TrueFalseQuiz"]

    def test_round_trip_through_validate_quiz_data(self):
        restored = validate_quiz_data(_book().model_dump())
        assert isinstance(restored, InteractiveBookQuiz)
        assert restored.chapters[0].title == "The basics"


class TestRenderTextSection:
    def test_heading_becomes_h2(self):
        html = render_text_section(TextSection(heading="Intro", body="Body."))
        assert html.startswith("<h2>Intro</h2>")

    def test_no_heading_means_no_h2(self):
        assert "<h2>" not in render_text_section(TextSection(body="Body."))

    def test_blank_lines_split_paragraphs(self):
        html = render_text_section(TextSection(body="One.\n\nTwo."))
        assert html == "<p>One.</p><p>Two.</p>"

    def test_single_newline_is_a_soft_wrap(self):
        html = render_text_section(TextSection(body="One.\nStill one."))
        assert html == "<p>One.<br>Still one.</p>"

    def test_author_markup_is_escaped(self):
        html = render_text_section(TextSection(heading="A <b>x</b>", body="5 < 6 & 7 > 2"))
        assert "<b>" not in html
        assert "&lt;b&gt;" in html
        assert "5 &lt; 6 &amp; 7 &gt; 2" in html


class TestBookExport:
    def test_package_is_structurally_valid(self, exporter):
        result = exporter.export(_book(), output_name="book_basic")
        report = validate_h5p_package(result.output_path)
        assert report.ok, report.errors

    def test_main_library_and_embed_type(self, exporter):
        h5p = _h5p(exporter.export(_book(), output_name="book_manifest").output_path)
        assert h5p["mainLibrary"] == "H5P.InteractiveBook"
        assert h5p["embedTypes"] == ["iframe"]

    def test_declares_two_levels_of_embedded_libraries(self, exporter):
        h5p = _h5p(exporter.export(_book(), output_name="book_deps").output_path)
        names = [d["machineName"] for d in h5p["preloadedDependencies"]]
        assert names[0] == "H5P.InteractiveBook"
        # The book instantiates a Column per chapter; each Column its sections.
        assert "H5P.Column" in names
        assert "H5P.AdvancedText" in names
        assert "H5P.MultiChoice" in names

    def test_dependencies_are_deduplicated(self, exporter):
        book = _book(
            chapters=[
                BookChapter(title="One", sections=[TextSection(body="a"), TextSection(body="b")]),
                BookChapter(title="Two", sections=[TextSection(body="c")]),
            ]
        )
        h5p = _h5p(exporter.export(book, output_name="book_dedupe").output_path)
        names = [d["machineName"] for d in h5p["preloadedDependencies"]]
        assert names == ["H5P.InteractiveBook", "H5P.Column", "H5P.AdvancedText"]

    def test_chapters_are_flat_library_objects(self, exporter):
        """
        The runtime passes each chapter straight to H5P.newRunnable, so entries
        must be library objects, not {"chapter": ...} wrappers.
        """
        content = _content(exporter.export(_book(), output_name="book_flat").output_path)
        chapter = content["chapters"][0]
        assert "chapter" not in chapter
        assert chapter["library"] == "H5P.Column 1.22"
        assert set(chapter) == {"library", "params", "subContentId", "metadata"}

    def test_chapter_title_lives_in_metadata(self, exporter):
        """The table of contents reads config.chapters[i].metadata.title."""
        content = _content(exporter.export(_book(), output_name="book_toc").output_path)
        titles = [c["metadata"]["title"] for c in content["chapters"]]
        assert titles == ["The basics", "Why it matters"]

    def test_column_items_wrap_content_with_separator(self, exporter):
        content = _content(exporter.export(_book(), output_name="book_items").output_path)
        items = content["chapters"][0]["params"]["content"]
        assert len(items) == 2
        assert set(items[0]) == {"content", "useSeparator"}
        assert items[0]["useSeparator"] == "auto"

    def test_section_libraries(self, exporter):
        content = _content(exporter.export(_book(), output_name="book_sections").output_path)
        items = content["chapters"][0]["params"]["content"]
        assert items[0]["content"]["library"] == "H5P.AdvancedText 1.1"
        assert items[1]["content"]["library"] == "H5P.MultiChoice 1.16"

    def test_every_subcontent_id_is_unique(self, exporter):
        content = _content(exporter.export(_book(), output_name="book_subids").output_path)
        ids = []
        for chapter in content["chapters"]:
            ids.append(chapter["subContentId"])
            ids.extend(item["content"]["subContentId"] for item in chapter["params"]["content"])
        assert len(ids) == len(set(ids))
        assert all(len(i) == 36 for i in ids)

    def test_cover_and_behaviour(self, exporter):
        book = _book(base_color="#AA00FF", display_summary=False, show_cover=True)
        content = _content(exporter.export(book, output_name="book_cover").output_path)
        assert content["showCoverPage"] is True
        assert content["bookCover"]["coverDescription"] == "<p>How plants make food.</p>"
        assert content["behaviour"]["baseColor"] == "#AA00FF"
        assert content["behaviour"]["displaySummary"] is False

    def test_empty_cover_description_stays_empty(self, exporter):
        content = _content(exporter.export(_book(cover_description=""), output_name="book_nocover").output_path)
        assert content["bookCover"]["coverDescription"] == ""

    def test_l10n_defaults_are_present(self, exporter):
        content = _content(exporter.export(_book(), output_name="book_l10n").output_path)
        # Pulled from the official semantics.json defaults.
        assert content["read"] == "Read"
        assert content["behaviour"]["progressIndicators"] is True

    def test_blanks_section_is_supported(self, exporter):
        book = _book(
            chapters=[
                BookChapter(
                    title="Gaps",
                    sections=[FillBlanksQuiz(title="Fill", text="France is *Paris*.", answers=["Paris"])],
                )
            ]
        )
        h5p = _h5p(exporter.export(book, output_name="book_blanks").output_path)
        assert "H5P.Blanks" in [d["machineName"] for d in h5p["preloadedDependencies"]]

    def test_nothing_but_json_is_bundled(self, exporter):
        result = exporter.export(_book(), output_name="book_files")
        with ZipFile(result.output_path, "r") as z:
            assert z.namelist() == ["content/content.json", "h5p.json"]
