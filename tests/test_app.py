import pytest
from streamlit.testing.v1 import AppTest


def test_app_renders_primary_pages_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file("app.py", default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "Turn talk into a record."
    assert "Sarvam: add SARVAM_API_KEY" in app.sidebar.markdown[-1].value
    assert "OpenAI:" in app.sidebar.markdown[-1].value
    assert "Storage: local SQLite" in app.sidebar.markdown[-1].value

    app.radio[0].set_value("Meeting audio").run()

    assert not app.exception
    assert app.file_uploader[0].label == "Meeting audio"
    assert "Audio is sent to Sarvam" in app.caption[-1].value

    app.sidebar.radio[0].set_value("Series register").run()

    assert not app.exception
    assert app.title[0].value == "The series register."
    assert app.info[0].value == "Approve the first meeting to create a register."


def test_text_ingestion_stops_at_transcript_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file("app.py", default_timeout=10).run()

    app.button[0].click().run()
    review_button = next(
        button for button in app.button if button.label == "Review transcript"
    )
    review_button.click().run()

    assert not app.exception
    assert app.subheader[0].value == "Review transcript before extraction"
    assert "Extraction has not started" in app.caption[0].value
    assert app.text_area[0].label == "Transcript"
    assert app.text_area[0].value.startswith("[00:00] Aditi:")
    assert any(markdown.value == "### Detected speakers" for markdown in app.markdown)
    assert [text_input.label for text_input in app.text_input] == [
        'Rename "Aditi"',
        'Rename "Rohan"',
        'Rename "Meera"',
    ]
    assert any(
        button.label == "Confirm transcript and extract brief" for button in app.button
    )
    assert "pending_transcript" in app.session_state
    assert "draft_brief" not in app.session_state


def test_review_stage_refreshes_detected_speakers_after_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "")
    app = AppTest.from_file("app.py", default_timeout=10).run()

    app.button[0].click().run()
    next(button for button in app.button if button.label == "Review transcript").click().run()
    reviewed_text = (
        "[00:00] Speaker 0: We need to move the launch because the upload is still broken.\n"
        "[00:05] Speaker 1: I will own the fix and send the pull request by Wednesday."
    )
    app.text_area[0].set_value(reviewed_text).run()

    assert not app.exception
    assert [text_input.label for text_input in app.text_input] == [
        'Rename "Speaker 0"',
        'Rename "Speaker 1"',
    ]
    assert "draft_brief" not in app.session_state
