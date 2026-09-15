"""
Comprehensive test suite for h5p_mcp – covers every quiz type supported by
the server and exports each one as a real .h5p file that is then validated.
"""
from __future__ import annotations
from h5p_mcp.validators.quiz_validator import validate_h5p_package, validate_quiz_data
from h5p_mcp.models.quiz_models import (
    FillBlanksQuiz,
    MCQQuiz,
    QuestionSetQuiz,
    TrueFalseQuiz,
)
from h5p_mcp.exporters.h5p_exporter import H5PExporter

import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

# Make sure the workspace root is on sys.path so imports work without install.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXPORT_DIR = ROOT / "h5p_mcp" / "exports" / "test_outputs"


@pytest.fixture(scope="session")
def exporter(tmp_path_factory):
    """One exporter that writes all test .h5p files to a dedicated directory."""
    out = EXPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    return H5PExporter(export_dir=str(out))


def _assert_valid_h5p(path: Path) -> None:
    """Convenience: assert the .h5p file passes structural validation."""
    result = validate_h5p_package(path)
    assert result.ok, f"H5P validation failed for {path.name}: {result.errors}"


def _read_content_json(path: Path) -> dict:
    with ZipFile(path, "r") as z:
        return json.loads(z.read("content/content.json").decode("utf-8"))


def _read_h5p_json(path: Path) -> dict:
    with ZipFile(path, "r") as z:
        return json.loads(z.read("h5p.json").decode("utf-8"))


# ===========================================================================
# 1. MODEL UNIT TESTS
# ===========================================================================


class TestMCQModel:
    def test_valid_mcq(self):
        q = MCQQuiz(
            title="Math",
            question="What is 2+2?",
            choices=["3", "4", "5"],
            correct_answer="4",
        )
        assert q.type.value == "mcq"
        assert q.correct_answer == "4"

    def test_correct_answer_not_in_choices_raises(self):
        with pytest.raises(Exception):
            MCQQuiz(
                title="Bad",
                question="Q?",
                choices=["A", "B"],
                correct_answer="C",
            )

    def test_duplicate_choices_raises(self):
        with pytest.raises(Exception):
            MCQQuiz(
                title="Bad",
                question="Q?",
                choices=["A", "A"],
                correct_answer="A",
            )

    def test_too_few_choices_raises(self):
        with pytest.raises(Exception):
            MCQQuiz(
                title="Bad",
                question="Q?",
                choices=["Only one"],
                correct_answer="Only one",
            )

    def test_model_dump_round_trip(self):
        q = MCQQuiz(
            title="RT",
            question="Q?",
            choices=["Yes", "No"],
            correct_answer="Yes",
        )
        data = q.model_dump()
        restored = validate_quiz_data(data)
        assert restored.title == "RT"


class TestTrueFalseModel:
    def test_valid_true(self):
        q = TrueFalseQuiz(
            title="T", question="Earth orbits the Sun.", correct_answer=True)
        assert q.correct_answer is True

    def test_valid_false(self):
        q = TrueFalseQuiz(
            title="F", question="Humans breathe underwater.", correct_answer=False)
        assert q.correct_answer is False

    def test_model_dump_round_trip(self):
        q = TrueFalseQuiz(title="RT", question="Q?", correct_answer=True)
        data = q.model_dump()
        restored = validate_quiz_data(data)
        assert restored.correct_answer is True


class TestFillBlanksModel:
    def test_valid_blanks(self):
        q = FillBlanksQuiz(
            title="Caps",
            text="The capital of France is *Paris*.",
            answers=["Paris"],
        )
        assert q.answers == ["Paris"]

    def test_missing_asterisks_raises(self):
        with pytest.raises(Exception):
            FillBlanksQuiz(title="Bad", text="No blanks here.",
                           answers=["Paris"])

    def test_answer_not_in_text_raises(self):
        with pytest.raises(Exception):
            FillBlanksQuiz(
                title="Bad",
                text="Capital is *London*.",
                answers=["Paris"],
            )

    def test_multiple_blanks(self):
        q = FillBlanksQuiz(
            title="Multi",
            text="*Python* is a language and *Rust* is another.",
            answers=["Python", "Rust"],
        )
        assert len(q.answers) == 2

    def test_model_dump_round_trip(self):
        q = FillBlanksQuiz(title="RT", text="Answer is *42*.", answers=["42"])
        data = q.model_dump()
        restored = validate_quiz_data(data)
        assert restored.answers == ["42"]


class TestQuestionSetModel:
    def _make_qs(self) -> QuestionSetQuiz:
        return QuestionSetQuiz(
            title="Mixed",
            intro="Test intro.",
            pass_percentage=70,
            questions=[
                MCQQuiz(title="MCQ", question="Q?", choices=[
                        "A", "B"], correct_answer="A"),
                TrueFalseQuiz(title="TF", question="True?",
                              correct_answer=True),
                FillBlanksQuiz(
                    title="Blanks", text="Fill *this*.", answers=["this"]),
            ],
        )

    def test_valid_questionset(self):
        qs = self._make_qs()
        assert qs.pass_percentage == 70
        assert len(qs.questions) == 3

    def test_nested_questionset_raises(self):
        inner = self._make_qs()
        with pytest.raises(Exception):
            QuestionSetQuiz(
                title="Outer",
                intro="",
                questions=[inner],
            )

    def test_model_dump_round_trip(self):
        qs = self._make_qs()
        data = qs.model_dump()
        restored = validate_quiz_data(data)
        assert restored.title == "Mixed"


# ===========================================================================
# 2. SERVER TOOL FUNCTION TESTS  (calling the same logic the MCP tools use)
# ===========================================================================


class TestServerToolFunctions:
    """
    Import the tool functions directly and exercise them in the same way
    the MCP runtime would – they just return plain dicts.
    """

    def test_create_mcq_quiz_tool(self):
        from h5p_mcp.server import create_mcq_quiz

        result = create_mcq_quiz(
            title="Tool MCQ",
            question="What is 3+3?",
            choices=["5", "6", "7"],
            correct_answer="6",
            explanation="3+3=6",
        )
        assert result["type"] == "mcq"
        assert result["correct_answer"] == "6"

    def test_create_true_false_quiz_tool(self):
        from h5p_mcp.server import create_true_false_quiz

        result = create_true_false_quiz(
            title="Tool TF",
            question="The sky is blue.",
            correct_answer=True,
        )
        assert result["type"] == "truefalse"
        assert result["correct_answer"] is True

    def test_create_fill_blanks_quiz_tool(self):
        from h5p_mcp.server import create_fill_blanks_quiz

        result = create_fill_blanks_quiz(
            title="Tool Blanks",
            text="The answer is *42*.",
            answers=["42"],
        )
        assert result["type"] == "blanks"
        assert "42" in result["answers"]

    def test_create_questionset_quiz_tool(self):
        from h5p_mcp.server import create_mcq_quiz, create_questionset_quiz, create_true_false_quiz

        q1 = create_mcq_quiz("MCQ1", "Q1?", ["A", "B"], "A")
        q2 = create_true_false_quiz("TF1", "True?", False)

        result = create_questionset_quiz(
            title="Tool QS",
            intro="Mixed set.",
            questions=[q1, q2],
            pass_percentage=60,
        )
        assert result["type"] == "questionset"
        assert len(result["questions"]) == 2

    def test_h5p_prompt_helpers_tool(self):
        from h5p_mcp.server import h5p_prompt_helpers

        helpers = h5p_prompt_helpers()
        assert "mcq" in helpers
        assert "truefalse" in helpers
        assert "blanks" in helpers

    def test_markdown_to_quizzes_tool(self):
        from h5p_mcp.server import markdown_to_quizzes

        md = (
            "### MCQ: Basic Math\n"
            "Q: What is 2 + 2?\n"
            "- [ ] 3\n"
            "- [x] 4\n"
            "- [ ] 5\n"
            "Explanation: 2+2=4.\n\n"
            "### TF: Astronomy\n"
            "Q: The Earth orbits the Sun.\n"
            "A: true\n"
            "Explanation: Yes.\n\n"
            "### Blanks: Capitals\n"
            "Text: The capital of France is *Paris*.\n"
            "Answers: Paris\n"
        )
        result = markdown_to_quizzes(md)
        assert result["count"] == 3

    def test_validate_h5p_tool_nonexistent(self):
        from h5p_mcp.server import validate_h5p

        result = validate_h5p("does_not_exist.h5p")
        assert result["ok"] is False
        assert result["errors"]


# ===========================================================================
# 3. EXPORT TESTS – each quiz type → .h5p file → structural validation
# ===========================================================================


class TestMCQExport:
    def test_export_basic_math(self, exporter):
        quiz = MCQQuiz(
            title="MCQ – Basic Math",
            question="What is 2 + 2?",
            choices=["3", "4", "5"],
            correct_answer="4",
            explanation="2+2 equals 4.",
        )
        result = exporter.export(quiz, output_name="test_mcq_basic_math")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_export_geography(self, exporter):
        quiz = MCQQuiz(
            title="MCQ – Geography",
            question="Which country has the capital 'Lisbon'?",
            choices=["Spain", "Portugal", "Brazil", "Italy"],
            correct_answer="Portugal",
            explanation="Lisbon is the capital of Portugal.",
        )
        result = exporter.export(quiz, output_name="test_mcq_geography")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_export_science(self, exporter):
        quiz = MCQQuiz(
            title="MCQ – Science",
            question="What is the chemical symbol for water?",
            choices=["HO", "H2O", "CO2", "O2"],
            correct_answer="H2O",
            explanation="Water is H2O.",
        )
        result = exporter.export(quiz, output_name="test_mcq_science")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_h5p_json_main_library(self, exporter):
        quiz = MCQQuiz(
            title="MCQ – Library Check",
            question="Q?",
            choices=["A", "B"],
            correct_answer="A",
        )
        result = exporter.export(quiz, output_name="test_mcq_library_check")
        h5p = _read_h5p_json(result.output_path)
        assert h5p["mainLibrary"] == "H5P.MultiChoice"

    def test_content_json_has_metadata(self, exporter):
        quiz = MCQQuiz(
            title="MCQ – Meta",
            question="Q?",
            choices=["X", "Y"],
            correct_answer="X",
        )
        result = exporter.export(quiz, output_name="test_mcq_meta")
        content = _read_content_json(result.output_path)
        assert "metadata" in content
        assert content["metadata"]["title"] == "MCQ – Meta"


class TestTrueFalseExport:
    def test_export_astronomy_true(self, exporter):
        quiz = TrueFalseQuiz(
            title="TF – Astronomy",
            question="The Earth orbits the Sun.",
            correct_answer=True,
            explanation="It takes ~1 year.",
        )
        result = exporter.export(quiz, output_name="test_tf_astronomy")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_export_biology_false(self, exporter):
        quiz = TrueFalseQuiz(
            title="TF – Biology",
            question="Humans can breathe underwater unaided.",
            correct_answer=False,
            explanation="Scuba gear is needed.",
        )
        result = exporter.export(quiz, output_name="test_tf_biology")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_export_history(self, exporter):
        quiz = TrueFalseQuiz(
            title="TF – History",
            question="World War II ended in 1945.",
            correct_answer=True,
        )
        result = exporter.export(quiz, output_name="test_tf_history")
        _assert_valid_h5p(result.output_path)

    def test_h5p_json_main_library(self, exporter):
        quiz = TrueFalseQuiz(
            title="TF Lib", question="Q?", correct_answer=True)
        result = exporter.export(quiz, output_name="test_tf_library_check")
        h5p = _read_h5p_json(result.output_path)
        assert h5p["mainLibrary"] == "H5P.TrueFalse"


class TestFillBlanksExport:
    def test_export_capitals(self, exporter):
        quiz = FillBlanksQuiz(
            title="Blanks – Capitals",
            text="The capital of France is *Paris* and of Italy is *Rome*.",
            answers=["Paris", "Rome"],
        )
        result = exporter.export(quiz, output_name="test_blanks_capitals")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_export_python(self, exporter):
        quiz = FillBlanksQuiz(
            title="Blanks – Python",
            text="In Python a list uses *square brackets*.",
            answers=["square brackets"],
        )
        result = exporter.export(quiz, output_name="test_blanks_python")
        _assert_valid_h5p(result.output_path)

    def test_export_single_blank(self, exporter):
        quiz = FillBlanksQuiz(
            title="Blanks – Single",
            text="The answer is *42*.",
            answers=["42"],
        )
        result = exporter.export(quiz, output_name="test_blanks_single")
        _assert_valid_h5p(result.output_path)

    def test_h5p_json_main_library(self, exporter):
        quiz = FillBlanksQuiz(title="Blanks Lib",
                              text="Fill *this*.", answers=["this"])
        result = exporter.export(quiz, output_name="test_blanks_library_check")
        h5p = _read_h5p_json(result.output_path)
        assert h5p["mainLibrary"] == "H5P.Blanks"

    def test_blanks_text_is_in_questions_field(self, exporter):
        quiz = FillBlanksQuiz(
            title="Blanks Field Mapping",
            text="The capital of France is *Paris*.",
            answers=["Paris"],
        )
        result = exporter.export(
            quiz, output_name="test_blanks_question_field")
        content = _read_content_json(result.output_path)
        assert "questions" in content
        assert content["questions"]
        # H5P.Blanks semantics defines `questions` as a list of html text
        # fields, so each entry is a plain string, not a wrapper object.
        assert isinstance(content["questions"][0], str)
        assert "*Paris*" in content["questions"][0]


class TestQuestionSetExport:
    def _mixed_qs(self) -> QuestionSetQuiz:
        return QuestionSetQuiz(
            title="QS – Mixed",
            intro="A mixed-type question set.",
            pass_percentage=60,
            questions=[
                MCQQuiz(
                    title="MCQ – Security",
                    question="Which is a strong password practice?",
                    choices=[
                        "Use 'password123'",
                        "Reuse the same password",
                        "Use a password manager",
                        "Share over email",
                    ],
                    correct_answer="Use a password manager",
                    explanation="Password managers are best practice.",
                ),
                TrueFalseQuiz(
                    title="TF – Web",
                    question="HTTPS encrypts traffic between browser and server.",
                    correct_answer=True,
                    explanation="HTTPS protects data in transit.",
                ),
                FillBlanksQuiz(
                    title="Blanks – Geography",
                    text="The capital of Japan is *Tokyo*.",
                    answers=["Tokyo"],
                ),
            ],
        )

    def test_export_mixed(self, exporter):
        result = exporter.export(self._mixed_qs(), output_name="test_qs_mixed")
        assert result.output_path.exists()
        _assert_valid_h5p(result.output_path)

    def test_h5p_json_main_library(self, exporter):
        result = exporter.export(
            self._mixed_qs(), output_name="test_qs_library_check")
        h5p = _read_h5p_json(result.output_path)
        assert h5p["mainLibrary"] == "H5P.QuestionSet"

    def test_export_mcq_only_qs(self, exporter):
        qs = QuestionSetQuiz(
            title="QS – MCQ Only",
            intro="Only MCQ questions.",
            questions=[
                MCQQuiz(title="Q1", question="1+1?",
                        choices=["1", "2", "3"], correct_answer="2"),
                MCQQuiz(title="Q2", question="2+2?",
                        choices=["3", "4", "5"], correct_answer="4"),
            ],
        )
        result = exporter.export(qs, output_name="test_qs_mcq_only")
        _assert_valid_h5p(result.output_path)

    def test_export_tf_only_qs(self, exporter):
        qs = QuestionSetQuiz(
            title="QS – TF Only",
            intro="Only True/False questions.",
            questions=[
                TrueFalseQuiz(title="TF1", question="Sky is blue.",
                              correct_answer=True),
                TrueFalseQuiz(title="TF2", question="Ice is hot.",
                              correct_answer=False),
            ],
        )
        result = exporter.export(qs, output_name="test_qs_tf_only")
        _assert_valid_h5p(result.output_path)


# ===========================================================================
# 4. BATCH EXPORT TOOL TEST
# ===========================================================================


class TestBatchExport:
    def test_export_h5p_batch_tool(self, tmp_path):
        """export_h5p_batch should export multiple quizzes and return paths."""
        from h5p_mcp.server import export_h5p_batch

        quizzes = [
            MCQQuiz(title="Batch MCQ", question="Q?", choices=[
                    "A", "B"], correct_answer="A").model_dump(),
            TrueFalseQuiz(title="Batch TF", question="True?",
                          correct_answer=False).model_dump(),
            FillBlanksQuiz(title="Batch Blanks", text="Fill *blank*.",
                           answers=["blank"]).model_dump(),
        ]
        result = export_h5p_batch(quizzes, name_prefix="batch_test")
        assert result["count"] == 3
        for item in result["results"]:
            path = Path(item["output_path"])
            assert path.exists(), f"Expected exported file: {path}"
            _assert_valid_h5p(path)


# ===========================================================================
# 5. EXPORT_H5P TOOL (single export via server tool function)
# ===========================================================================


class TestExportH5PTool:
    def _run(self, quiz_dict: dict, name: str) -> Path:
        from h5p_mcp.server import export_h5p

        result = export_h5p(quiz_dict, name)
        path = Path(result["output_path"])
        assert path.exists()
        return path

    def test_export_mcq_via_tool(self):
        quiz = MCQQuiz(title="Tool Export MCQ", question="Q?", choices=[
                       "A", "B"], correct_answer="B").model_dump()
        path = self._run(quiz, "tool_export_mcq")
        _assert_valid_h5p(path)

    def test_export_tf_via_tool(self):
        quiz = TrueFalseQuiz(title="Tool Export TF",
                             question="True?", correct_answer=True).model_dump()
        path = self._run(quiz, "tool_export_tf")
        _assert_valid_h5p(path)

    def test_export_blanks_via_tool(self):
        quiz = FillBlanksQuiz(title="Tool Export Blanks",
                              text="Fill *me*.", answers=["me"]).model_dump()
        path = self._run(quiz, "tool_export_blanks")
        _assert_valid_h5p(path)

    def test_export_questionset_via_tool(self):
        qs = QuestionSetQuiz(
            title="Tool Export QS",
            intro="Intro.",
            questions=[
                MCQQuiz(title="Q", question="Q?", choices=[
                        "A", "B"], correct_answer="A"),
            ],
        ).model_dump()
        path = self._run(qs, "tool_export_qs")
        _assert_valid_h5p(path)


# ===========================================================================
# 6. VALIDATE_H5P TOOL
# ===========================================================================


class TestValidateH5PTool:
    def test_validates_generated_mcq(self, exporter):
        quiz = MCQQuiz(title="Val MCQ", question="Q?",
                       choices=["A", "B"], correct_answer="A")
        result = exporter.export(quiz, output_name="test_validate_mcq")
        from h5p_mcp.server import validate_h5p

        val = validate_h5p(str(result.output_path))
        assert val["ok"] is True
        assert val["errors"] == []

    def test_validates_generated_tf(self, exporter):
        quiz = TrueFalseQuiz(
            title="Val TF", question="Q?", correct_answer=True)
        result = exporter.export(quiz, output_name="test_validate_tf")
        from h5p_mcp.server import validate_h5p

        val = validate_h5p(str(result.output_path))
        assert val["ok"] is True

    def test_validates_generated_blanks(self, exporter):
        quiz = FillBlanksQuiz(title="Val Blanks",
                              text="Fill *X*.", answers=["X"])
        result = exporter.export(quiz, output_name="test_validate_blanks")
        from h5p_mcp.server import validate_h5p

        val = validate_h5p(str(result.output_path))
        assert val["ok"] is True

    def test_validates_generated_questionset(self, exporter):
        quiz = QuestionSetQuiz(
            title="Val QS",
            intro="",
            questions=[TrueFalseQuiz(
                title="TF", question="Q?", correct_answer=False)],
        )
        result = exporter.export(quiz, output_name="test_validate_qs")
        from h5p_mcp.server import validate_h5p

        val = validate_h5p(str(result.output_path))
        assert val["ok"] is True
