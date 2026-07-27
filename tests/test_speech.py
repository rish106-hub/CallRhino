from pathlib import Path

import httpx
import pytest
import respx

from callrhino.config import Settings
from callrhino.services.sarvam import SarvamError
from callrhino.services.speech import SarvamSpeechClient


@respx.mock
def test_sarvam_speech_posts_documented_multipart_fields(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFFtest")
    route = respx.post("https://api.sarvam.ai/speech-to-text").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": "request-1",
                "transcript": "नमस्ते team",
                "language_code": "hi-IN",
                "language_probability": 0.98,
            },
        )
    )
    settings = Settings(SARVAM_API_KEY="test-key", _env_file=None)

    with SarvamSpeechClient(settings) as client:
        result = client.transcribe(audio_path, mode="codemix")

    assert route.called
    request = route.calls[0].request
    assert request.headers["api-subscription-key"] == "test-key"
    assert b'name="model"' in request.content
    assert b"saaras:v3" in request.content
    assert b'name="mode"' in request.content
    assert b"codemix" in request.content
    assert result.transcript == "नमस्ते team"


@respx.mock
def test_sarvam_batch_transcribes_diarized_meeting(tmp_path: Path) -> None:
    audio_path = tmp_path / "meeting.mp3"
    audio_path.write_bytes(b"meeting-audio")
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1").mock(
        return_value=httpx.Response(
            200,
            json={"job_id": "job-1", "job_state": "Accepted"},
        )
    )
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1/upload-files").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "job_state": "Accepted",
                "upload_urls": {
                    "meeting.mp3": {"file_url": "https://blob.example/upload"}
                },
                "storage_container_type": "Azure",
            },
        )
    )
    upload = respx.put("https://blob.example/upload").mock(
        return_value=httpx.Response(201)
    )
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1/job-1/start").mock(
        return_value=httpx.Response(200, json={"job_id": "job-1", "job_state": "Running"})
    )
    respx.get("https://api.sarvam.ai/speech-to-text/job/v1/job-1/status").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "job_state": "Completed",
                "job_details": [
                    {
                        "state": "Success",
                        "inputs": [{"file_name": "meeting.mp3"}],
                        "outputs": [{"file_name": "0.json"}],
                    }
                ],
            },
        )
    )
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1/download-files").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "job_state": "Completed",
                "download_urls": {"0.json": {"file_url": "https://blob.example/result"}},
                "storage_container_type": "Azure",
            },
        )
    )
    respx.get("https://blob.example/result").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": "request-2",
                "language_code": "hi-IN",
                "transcript": "fallback text",
                "diarized_transcript": {
                    "entries": [
                        {
                            "speaker_id": "0",
                            "start_time_seconds": 1.4,
                            "transcript": "नमस्ते team",
                        },
                        {
                            "speaker_id": "1",
                            "start_time_seconds": 4.2,
                            "transcript": "Main report bhej dunga.",
                        },
                    ]
                },
            },
        )
    )
    settings = Settings(
        SARVAM_API_KEY="test-key",
        SARVAM_BATCH_POLL_SECONDS=0.01,
        _env_file=None,
    )

    with SarvamSpeechClient(settings, sleep=lambda _: None) as client:
        result = client.transcribe_meeting(audio_path)

    assert upload.called
    assert upload.calls[0].request.headers["x-ms-blob-type"] == "BlockBlob"
    initiation = respx.calls[0].request
    assert b'"mode":"codemix"' in initiation.content
    assert b'"with_diarization":true' in initiation.content
    assert result.job_id == "job-1"
    assert result.diarized is True
    assert result.transcript == (
        "[00:00:01] Speaker 0: नमस्ते team\n"
        "[00:00:04] Speaker 1: Main report bhej dunga."
    )


@respx.mock
def test_sarvam_batch_surfaces_failed_job(tmp_path: Path) -> None:
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"audio")
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1").mock(
        return_value=httpx.Response(200, json={"job_id": "job-2", "job_state": "Accepted"})
    )
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1/upload-files").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload_urls": {
                    "meeting.wav": {"file_url": "https://blob.example/upload-failed"}
                }
            },
        )
    )
    respx.put("https://blob.example/upload-failed").mock(
        return_value=httpx.Response(201)
    )
    respx.post("https://api.sarvam.ai/speech-to-text/job/v1/job-2/start").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": "job-2",
                "job_state": "Failed",
                "error_message": "Unsupported audio",
            },
        )
    )
    settings = Settings(SARVAM_API_KEY="test-key", _env_file=None)

    with (
        SarvamSpeechClient(settings) as client,
        pytest.raises(SarvamError, match="Unsupported audio"),
    ):
        client.transcribe_meeting(audio_path)
