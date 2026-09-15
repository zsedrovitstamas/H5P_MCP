"""
Regression tests for H5P.Blanks field mapping and HTML escaping.

The generator previously wrote the quiz title into the task description and
passed author text through unescaped, so any <, & or quote in the source landed
raw in content.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from h5p_mcp.exporters.h5p_exporter import H5PExporter  # noqa: E402
from h5p_mcp.generators.blanks_generator import escape_preserving_blanks  # noqa: E402
from h5p_mcp.models.quiz_models import FillBlanksQuiz, extract_asterisk_answers, split_blanks  # noqa: E402


@pytest.fixture(scope="module")
def exporter(tmp_path_factory):
    return H5PExporter(export_dir=str(tmp_path_factory.mktemp("blanks_exports")))


def _content(path: Path) -> dict:
    with ZipFile(path, "r") as z:
        return json.loads(z.read("content/content.json").decode("utf-8"))


class TestSplitBlanks:
    def test_alternates_prose_and_answer(self):
        assert split_blanks("A *cat* sits") == [(False, "A "), (True, "cat"), (False, " sits")]

    def test_plain_text_is_one_prose_segment(self):
        assert split_blanks("no gaps here") == [(False, "no gaps here")]

    def test_unclosed_gap_stays_prose(self):
        # An asterisk that never closes is a literal asterisk, not a gap.
        assert split_blanks("unclosed *gap") == [(False, "unclosed "), (False, "*gap")]

    def test_empty_segments_are_dropped(self):
        assert split_blanks("**") == []


class TestEscapePreservingBlanks:
    def test_escapes_prose(self):
        assert escape_preserving_blanks("a <b> & c") == "a &lt;b&gt; &amp; c"

    def test_escapes_inside_the_gap_too(self):
        # The gap content is author text as well, so it cannot go through raw.
        assert escape_preserving_blanks("use *<* here") == "use *&lt;* here"

    def test_keeps_markers_for_plain_answers(self):
        assert escape_preserving_blanks("A *cat* sits") == "A *cat* sits"

    def test_escapes_quotes(self):
        assert escape_preserving_blanks('say "hi"') == "say &quot;hi&quot;"

    @pytest.mark.parametrize(
        "text",
        [
            "A *cat* and a *dog*.",
            'The "lt" operator is *<* and *&* joins.',
            "2 * 3 < 7 and *x* wins",
            "unclosed *gap with <tag>",
            "no gaps at all",
        ],
    )
    def test_escaping_agrees_with_extraction(self, text):
        """
        Every answer the model validates must survive into the rendered string
        as a marked gap. If the two parsers ever diverge, a package validates
        but renders the wrong blanks.
        """
        rendered = escape_preserving_blanks(text)
        for answer in extract_asterisk_answers(text):
            escaped = (
                answer.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
            )
            assert escaped in rendered


class TestBlanksFieldMapping:
    def test_title_is_the_quiz_title(self, exporter):
        quiz = FillBlanksQuiz(title="Capitals of Europe", text="France is *Paris*.", answers=["Paris"])
        content = _content(exporter.export(quiz, output_name="blanks_title").output_path)
        assert content["title"] == "Capitals of Europe"

    def test_text_holds_the_instruction_not_the_title(self, exporter):
        quiz = FillBlanksQuiz(title="Capitals of Europe", text="France is *Paris*.", answers=["Paris"])
        content = _content(exporter.export(quiz, output_name="blanks_text").output_path)
        assert content["text"] == "<p>Fill in the missing words.</p>"
        assert "Capitals of Europe" not in content["text"]

    def test_custom_instructions(self, exporter):
        quiz = FillBlanksQuiz(
            title="Operators",
            instructions="Complete each line with the correct operator.",
            text="A block ends with *}*.",
            answers=["}"],
            )
        content = _content(exporter.export(quiz, output_name="blanks_instructions").output_path)
        assert content["text"] == "<p>Complete each line with the correct operator.</p>"

    def test_questions_are_wrapped_paragraphs(self, exporter):
        quiz = FillBlanksQuiz(title="Two lines", text="One is *a*.\nTwo is *b*.", answers=["a", "b"])
        content = _content(exporter.export(quiz, output_name="blanks_lines").output_path)
        assert content["questions"] == ["<p>One is *a*.</p>", "<p>Two is *b*.</p>"]

    def test_blank_lines_are_dropped(self, exporter):
        quiz = FillBlanksQuiz(title="Gaps", text="One is *a*.\n\n\nTwo is *b*.", answers=["a", "b"])
        content = _content(exporter.export(quiz, output_name="blanks_blank_lines").output_path)
        assert len(content["questions"]) == 2

    def test_source_html_is_escaped_in_output(self, exporter):
        quiz = FillBlanksQuiz(
            title="Markup",
            text='AT&T wrote <b>bold</b> and used *<*.',
            answers=["<"],
        )
        content = _content(exporter.export(quiz, output_name="blanks_escaped").output_path)
        rendered = content["questions"][0]
        assert "<b>" not in rendered
        assert "&amp;" in rendered and "&lt;b&gt;" in rendered
        # The gap marker survives, with its contents escaped.
        assert "*&lt;*" in rendered

    def test_instructions_are_escaped(self, exporter):
        quiz = FillBlanksQuiz(
            title="Markup",
            instructions="Use <b> tags & such",
            text="A is *a*.",
            answers=["a"],
        )
        content = _content(exporter.export(quiz, output_name="blanks_instr_escaped").output_path)
        assert content["text"] == "<p>Use &lt;b&gt; tags &amp; such</p>"
