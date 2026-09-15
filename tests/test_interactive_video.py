"""
Tests for the Interactive Video content type.

Unlike the older suite these write their .h5p files to a pytest tmp directory
rather than into the repository tree, so running them leaves git clean.
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
from h5p_mcp.generators.interactivevideo_generator import mime_for_url  # noqa: E402
from h5p_mcp.models.quiz_models import (  # noqa: E402
    FillBlanksQuiz,
    InteractiveVideoQuiz,
    MCQQuiz,
    QuestionSetQuiz,
    TrueFalseQuiz,
    VideoInteraction,
)
from h5p_mcp.validators.quiz_validator import validate_h5p_package, validate_quiz_data  # noqa: E402


MP4 = "https://cdn.example.org/lessons/photosynthesis.mp4"


@pytest.fixture(scope="module")
def exporter(tmp_path_factory):
    return H5PExporter(export_dir=str(tmp_path_factory.mktemp("iv_exports")))


def _mcq(title: str = "Checkpoint") -> MCQQuiz:
    return MCQQuiz(
        title=title,
        question="Which pigment drives photosynthesis?",
        choices=["Chlorophyll", "Keratin", "Haemoglobin"],
        correct_answer="Chlorophyll",
        explanation="Chlorophyll absorbs light to power the reaction.",
    )


def _tf(title: str = "Quick check") -> TrueFalseQuiz:
    return TrueFalseQuiz(
        title=title,
        question="Photosynthesis releases oxygen.",
        correct_answer=True,
    )


def _video(**overrides) -> InteractiveVideoQuiz:
    params = dict(
        title="Photosynthesis explained",
        video_url=MP4,
        summary="Watch the clip and answer as you go.",
        interactions=[
            VideoInteraction(time=45, question=_mcq()),
            VideoInteraction(time=90, duration=20, pause=False, display="poster", question=_tf()),
        ],
    )
    params.update(overrides)
    return InteractiveVideoQuiz(**params)


def _read(path: Path, name: str) -> dict:
    with ZipFile(path, "r") as z:
        return json.loads(z.read(name).decode("utf-8"))


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------

class TestInteractiveVideoModel:
    def test_valid_video(self):
        quiz = _video()
        assert quiz.type.value == "interactivevideo"
        assert len(quiz.interactions) == 2

    def test_rejects_non_http_url(self):
        with pytest.raises(ValidationError):
            _video(video_url="/local/file.mp4")

    def test_rejects_empty_interactions(self):
        with pytest.raises(ValidationError):
            _video(interactions=[])

    def test_rejects_negative_time(self):
        with pytest.raises(ValidationError):
            VideoInteraction(time=-1, question=_mcq())

    def test_rejects_zero_duration(self):
        with pytest.raises(ValidationError):
            VideoInteraction(time=10, duration=0, question=_mcq())

    def test_rejects_nested_container(self):
        nested = QuestionSetQuiz(title="Inner", questions=[_mcq()])
        with pytest.raises(ValidationError):
            VideoInteraction(time=5, question=nested)

    def test_interactions_are_sorted_by_time(self):
        quiz = _video(
            interactions=[
                VideoInteraction(time=120, question=_mcq("Third")),
                VideoInteraction(time=10, question=_mcq("First")),
                VideoInteraction(time=60, question=_mcq("Second")),
            ]
        )
        assert [i.time for i in quiz.interactions] == [10, 60, 120]

    def test_round_trip_through_validate_quiz_data(self):
        restored = validate_quiz_data(_video().model_dump())
        assert isinstance(restored, InteractiveVideoQuiz)
        assert restored.video_url == MP4


# ---------------------------------------------------------------------------
# URL -> mime mapping
# ---------------------------------------------------------------------------

class TestMimeForUrl:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.youtube.com/watch?v=abc123", "video/YouTube"),
            ("https://youtu.be/abc123", "video/YouTube"),
            ("https://www.youtube-nocookie.com/embed/abc", "video/YouTube"),
            ("https://cdn.example.org/a.mp4", "video/mp4"),
            ("https://cdn.example.org/a.webm", "video/webm"),
            ("https://cdn.example.org/a.ogv", "video/ogg"),
            ("https://cdn.example.org/stream/manifest", "video/mp4"),
            # A path that merely mentions youtube must not be treated as one.
            ("https://cdn.example.org/youtube.com/clip.mp4", "video/mp4"),
        ],
    )
    def test_mime(self, url, expected):
        assert mime_for_url(url) == expected


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestInteractiveVideoExport:
    def test_package_is_structurally_valid(self, exporter):
        result = exporter.export(_video(), output_name="iv_basic")
        assert result.output_path.exists()
        report = validate_h5p_package(result.output_path)
        assert report.ok, report.errors

    def test_main_library_and_embed_type(self, exporter):
        result = exporter.export(_video(), output_name="iv_manifest")
        h5p = _read(result.output_path, "h5p.json")
        assert h5p["mainLibrary"] == "H5P.InteractiveVideo"
        # Interactive Video declares iframe in its own library.json.
        assert h5p["embedTypes"] == ["iframe"]

    def test_declares_every_embedded_library(self, exporter):
        result = exporter.export(_video(), output_name="iv_deps")
        h5p = _read(result.output_path, "h5p.json")
        names = [d["machineName"] for d in h5p["preloadedDependencies"]]
        assert names[0] == "H5P.InteractiveVideo"
        assert "H5P.MultiChoice" in names
        assert "H5P.TrueFalse" in names

    def test_dependencies_are_deduplicated(self, exporter):
        quiz = _video(
            interactions=[
                VideoInteraction(time=10, question=_mcq("One")),
                VideoInteraction(time=20, question=_mcq("Two")),
            ]
        )
        result = exporter.export(quiz, output_name="iv_dedupe")
        h5p = _read(result.output_path, "h5p.json")
        names = [d["machineName"] for d in h5p["preloadedDependencies"]]
        assert names == ["H5P.InteractiveVideo", "H5P.MultiChoice"]

    def test_video_is_referenced_by_url_not_bundled(self, exporter):
        result = exporter.export(_video(), output_name="iv_url")
        with ZipFile(result.output_path, "r") as z:
            assert z.namelist() == ["content/content.json", "h5p.json"]
        content = _read(result.output_path, "content/content.json")
        files = content["interactiveVideo"]["video"]["files"]
        assert files[0]["path"] == MP4
        assert files[0]["mime"] == "video/mp4"

    def test_start_screen_carries_title_and_summary(self, exporter):
        result = exporter.export(_video(), output_name="iv_startscreen")
        content = _read(result.output_path, "content/content.json")
        options = content["interactiveVideo"]["video"]["startScreenOptions"]
        assert options["title"] == "Photosynthesis explained"
        assert options["shortStartDescription"] == "Watch the clip and answer as you go."

    def test_interaction_timecodes(self, exporter):
        result = exporter.export(_video(), output_name="iv_timecodes")
        content = _read(result.output_path, "content/content.json")
        interactions = content["interactiveVideo"]["assets"]["interactions"]
        assert len(interactions) == 2
        assert interactions[0]["duration"] == {"from": 45, "to": 55}
        assert interactions[1]["duration"] == {"from": 90, "to": 110}

    def test_interaction_action_shape(self, exporter):
        result = exporter.export(_video(), output_name="iv_action")
        content = _read(result.output_path, "content/content.json")
        action = content["interactiveVideo"]["assets"]["interactions"][0]["action"]
        assert action["library"] == "H5P.MultiChoice 1.16"
        assert action["metadata"]["contentType"] == "Multiple Choice"
        assert action["params"]["answers"]
        # Every embedded instance needs its own identifier.
        assert len(action["subContentId"]) == 36

    def test_subcontent_ids_are_unique(self, exporter):
        result = exporter.export(_video(), output_name="iv_subids")
        content = _read(result.output_path, "content/content.json")
        ids = [i["action"]["subContentId"] for i in content["interactiveVideo"]["assets"]["interactions"]]
        assert len(set(ids)) == len(ids)

    def test_display_type_controls_geometry(self, exporter):
        result = exporter.export(_video(), output_name="iv_display")
        content = _read(result.output_path, "content/content.json")
        button, poster = content["interactiveVideo"]["assets"]["interactions"]
        assert button["displayType"] == "button"
        assert button["pause"] is True
        assert "width" not in button
        assert poster["displayType"] == "poster"
        assert poster["pause"] is False
        assert poster["width"] == 80.0

    def test_youtube_source_gets_youtube_mime(self, exporter):
        quiz = _video(video_url="https://www.youtube.com/watch?v=abc123")
        result = exporter.export(quiz, output_name="iv_youtube")
        content = _read(result.output_path, "content/content.json")
        assert content["interactiveVideo"]["video"]["files"][0]["mime"] == "video/YouTube"

    def test_start_video_at_is_applied(self, exporter):
        result = exporter.export(_video(start_video_at=30), output_name="iv_startat")
        content = _read(result.output_path, "content/content.json")
        assert content["override"]["startVideoAt"] == 30

    def test_l10n_defaults_are_present(self, exporter):
        result = exporter.export(_video(), output_name="iv_l10n")
        content = _read(result.output_path, "content/content.json")
        # Pulled from the official semantics.json defaults.
        assert content["l10n"]["play"] == "Play"
        assert "endcardSubmitButton" in content["l10n"]

    def test_blanks_question_is_supported(self, exporter):
        quiz = _video(
            interactions=[
                VideoInteraction(
                    time=15,
                    question=FillBlanksQuiz(
                        title="Gap fill",
                        text="Plants convert light into *glucose*.",
                        answers=["glucose"],
                    ),
                )
            ]
        )
        result = exporter.export(quiz, output_name="iv_blanks")
        h5p = _read(result.output_path, "h5p.json")
        assert "H5P.Blanks" in [d["machineName"] for d in h5p["preloadedDependencies"]]


# ---------------------------------------------------------------------------
# Regressions the Interactive Video work also fixes
# ---------------------------------------------------------------------------

class TestManifestRegressions:
    def test_extra_title_is_the_title_not_an_id(self, exporter):
        result = exporter.export(_video(), output_name="iv_extratitle")
        content = _read(result.output_path, "content/content.json")
        assert content["metadata"]["extraTitle"] == "Photosynthesis explained"

    def test_questionset_declares_its_embedded_libraries(self, exporter):
        quiz = QuestionSetQuiz(
            title="Mixed set",
            intro="Answer all questions.",
            questions=[_mcq(), _tf()],
        )
        result = exporter.export(quiz, output_name="qs_deps")
        h5p = _read(result.output_path, "h5p.json")
        names = [d["machineName"] for d in h5p["preloadedDependencies"]]
        assert names == ["H5P.QuestionSet", "H5P.MultiChoice", "H5P.TrueFalse"]

    def test_flat_type_declares_only_itself(self, exporter):
        result = exporter.export(_mcq("Standalone"), output_name="mcq_deps")
        h5p = _read(result.output_path, "h5p.json")
        assert [d["machineName"] for d in h5p["preloadedDependencies"]] == ["H5P.MultiChoice"]
        assert h5p["embedTypes"] == ["div"]
