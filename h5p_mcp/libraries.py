from __future__ import annotations

from typing import Any

from h5p_mcp.models.quiz_models import QuizType


LibrarySpec = tuple[str, int, int]

# Single source of truth for the H5P libraries this project emits.
#
# The version pinned here must match a library installed on the target platform
# (Moodle, Lumi, ...). Packages produced by this project are content-only: they
# do not bundle library folders, so the platform supplies them.
LIBRARIES: dict[QuizType, LibrarySpec] = {
    QuizType.mcq: ("H5P.MultiChoice", 1, 16),
    QuizType.truefalse: ("H5P.TrueFalse", 1, 8),
    QuizType.blanks: ("H5P.Blanks", 1, 14),
    QuizType.questionset: ("H5P.QuestionSet", 1, 20),
    QuizType.interactivevideo: ("H5P.InteractiveVideo", 1, 28),
}

# Human-readable names H5P shows for embedded sub-content.
CONTENT_TYPE_NAMES: dict[QuizType, str] = {
    QuizType.mcq: "Multiple Choice",
    QuizType.truefalse: "True/False Question",
    QuizType.blanks: "Fill in the Blanks",
    QuizType.questionset: "Question Set",
    QuizType.interactivevideo: "Interactive Video",
}

# Interactive Video declares "iframe" in its own library.json; the flat question
# types render fine inline.
_IFRAME_TYPES = {QuizType.interactivevideo}


def library_spec(qtype: QuizType) -> LibrarySpec:
    try:
        return LIBRARIES[qtype]
    except KeyError:
        raise ValueError(f"Unsupported QuizType: {qtype}") from None


def library_string(qtype: QuizType) -> str:
    """Return the "machineName major.minor" form used inside content.json."""
    name, major, minor = library_spec(qtype)
    return f"{name} {major}.{minor}"


def dependency_entry(qtype: QuizType) -> dict[str, Any]:
    """Return one h5p.json preloadedDependencies entry."""
    name, major, minor = library_spec(qtype)
    return {"machineName": name, "majorVersion": major, "minorVersion": minor}


def embed_types(qtype: QuizType) -> list[str]:
    return ["iframe"] if qtype in _IFRAME_TYPES else ["div"]


def subcontent_metadata(qtype: QuizType, title: str) -> dict[str, Any]:
    """
    Metadata block H5P writes alongside every embedded sub-content instance.

    H5P's own editor emits this; without it some hosts fall back to a generic
    label for the embedded item.
    """
    return {
        "contentType": CONTENT_TYPE_NAMES[qtype],
        "license": "U",
        "title": title,
        "authors": [],
        "changes": [],
    }
