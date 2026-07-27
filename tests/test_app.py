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
