import mimetypes
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from callrhino.config import Settings
from callrhino.services.sarvam import SarvamConfigurationError, SarvamError

SpeechMode = Literal["transcribe", "translate", "verbatim", "translit", "codemix"]


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    language_code: str | None
    language_probability: float | None
    request_id: str | None
    model: str
    mode: SpeechMode
    job_id: str | None = None
    diarized: bool = False


class SarvamSpeechClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not settings.sarvam_api_key:
            raise SarvamConfigurationError(
                "SARVAM_API_KEY is missing. Add it to .env before transcribing audio."
            )
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.sarvam_timeout_seconds)
        self._owns_client = client is None
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SarvamSpeechClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str = "saaras:v3",
        mode: SpeechMode = "codemix",
        language_code: str = "unknown",
    ) -> TranscriptionResult:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        try:
            with audio_path.open("rb") as audio_file:
                response = self._client.post(
                    f"{self._settings.sarvam_base_url.rstrip('/')}/speech-to-text",
                    headers={"api-subscription-key": self._settings.sarvam_api_key},
                    files={"file": (audio_path.name, audio_file, content_type)},
                    data={
                        "model": model,
                        "mode": mode,
                        "language_code": language_code,
                    },
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SarvamError("Sarvam speech-to-text timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise SarvamError(
                f"Sarvam speech-to-text returned HTTP {exc.response.status_code}: "
                f"{_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SarvamError("Could not reach Sarvam speech-to-text.") from exc

        body = response.json()
        transcript = body.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            raise SarvamError("Sarvam speech-to-text returned an empty transcript.")
        probability = body.get("language_probability")
        return TranscriptionResult(
            transcript=transcript.strip(),
            language_code=body.get("language_code"),
            language_probability=float(probability) if probability is not None else None,
            request_id=body.get("request_id"),
            model=model,
            mode=mode,
        )

    def transcribe_meeting(
        self,
        audio_path: Path,
        *,
        model: str = "saaras:v3",
        mode: SpeechMode = "codemix",
        language_code: str = "unknown",
        num_speakers: int | None = None,
    ) -> TranscriptionResult:
        """Transcribe long-form audio through Sarvam's asynchronous batch API."""
        file_name = audio_path.name
        job_parameters: dict[str, Any] = {
            "model": model,
            "mode": mode,
            "language_code": language_code,
            "with_timestamps": True,
            "with_diarization": True,
        }
        if num_speakers is not None:
            job_parameters["num_speakers"] = num_speakers

        initiated = self._api_request(
            "POST",
            "/speech-to-text/job/v1",
            json={"job_parameters": job_parameters},
        )
        job_id = _required_string(initiated, "job_id", "job initiation")

        upload_response = self._api_request(
            "POST",
            "/speech-to-text/job/v1/upload-files",
            json={"job_id": job_id, "files": [file_name]},
        )
        upload_url = _signed_url(upload_response, "upload_urls", file_name)
        self._upload_audio(audio_path, upload_url)

        status = self._api_request(
            "POST",
            f"/speech-to-text/job/v1/{job_id}/start",
            json={},
        )
        status = self._wait_for_job(job_id, initial_status=status)
        output_name = _successful_output_name(status)

        download_response = self._api_request(
            "POST",
            "/speech-to-text/job/v1/download-files",
            json={"job_id": job_id, "files": [output_name]},
        )
        download_url = _signed_url(download_response, "download_urls", output_name)
        output = self._download_json(download_url)
        transcript, diarized = _meeting_transcript(output)

        return TranscriptionResult(
            transcript=transcript,
            language_code=_optional_string(output.get("language_code")),
            language_probability=None,
            request_id=_optional_string(output.get("request_id")),
            model=model,
            mode=mode,
            job_id=job_id,
            diarized=diarized,
        )

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                f"{self._settings.sarvam_base_url.rstrip('/')}{path}",
                headers={"api-subscription-key": self._settings.sarvam_api_key},
                json=json,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise SarvamError("Sarvam batch speech-to-text timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise SarvamError(
                f"Sarvam batch speech-to-text returned HTTP {exc.response.status_code}: "
                f"{_error_detail(exc.response)}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise SarvamError("Could not read Sarvam batch speech-to-text response.") from exc
        if not isinstance(body, dict):
            raise SarvamError("Sarvam batch speech-to-text returned an invalid response.")
        return body

    def _upload_audio(self, audio_path: Path, upload_url: str) -> None:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        try:
            with audio_path.open("rb") as audio_file:
                response = self._client.put(
                    upload_url,
                    content=audio_file,
                    headers={
                        "x-ms-blob-type": "BlockBlob",
                        "Content-Type": content_type,
                    },
                    timeout=self._settings.sarvam_batch_timeout_seconds,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SarvamError("The meeting audio upload timed out.") from exc
        except httpx.HTTPError as exc:
            raise SarvamError("Could not upload meeting audio to Sarvam.") from exc

    def _wait_for_job(
        self,
        job_id: str,
        *,
        initial_status: dict[str, Any],
    ) -> dict[str, Any]:
        status = initial_status
        started_at = time.monotonic()
        while True:
            state = str(status.get("job_state", "")).casefold()
            if state in {"completed", "partiallycompleted"}:
                return status
            if state == "failed":
                detail = status.get("error_message") or "The transcription job failed."
                raise SarvamError(f"Sarvam transcription failed: {detail}")
            if time.monotonic() - started_at >= self._settings.sarvam_batch_timeout_seconds:
                raise SarvamError(
                    "Sarvam transcription did not finish before the local timeout."
                )
            self._sleep(self._settings.sarvam_batch_poll_seconds)
            status = self._api_request(
                "GET",
                f"/speech-to-text/job/v1/{job_id}/status",
            )

    def _download_json(self, download_url: str) -> dict[str, Any]:
        try:
            response = self._client.get(
                download_url,
                timeout=self._settings.sarvam_batch_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise SarvamError("Downloading the meeting transcript timed out.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise SarvamError("Could not download the completed meeting transcript.") from exc
        if not isinstance(body, dict):
            raise SarvamError("The completed meeting transcript was invalid.")
        return body


def _required_string(body: dict[str, Any], key: str, context: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise SarvamError(f"Sarvam {context} response omitted {key}.")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _signed_url(body: dict[str, Any], collection: str, file_name: str) -> str:
    links = body.get(collection)
    details = links.get(file_name) if isinstance(links, dict) else None
    if not isinstance(details, dict):
        raise SarvamError(f"Sarvam did not return a signed URL for {file_name}.")
    return _required_string(details, "file_url", "signed URL")


def _successful_output_name(status: dict[str, Any]) -> str:
    details = status.get("job_details")
    if not isinstance(details, list):
        raise SarvamError("Sarvam completed the job without file details.")
    errors: list[str] = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        if detail.get("state") != "Success":
            if detail.get("error_message"):
                errors.append(str(detail["error_message"]))
            continue
        outputs = detail.get("outputs")
        if isinstance(outputs, list) and outputs and isinstance(outputs[0], dict):
            output_name = outputs[0].get("file_name")
            if isinstance(output_name, str) and output_name:
                return output_name
    suffix = f": {'; '.join(errors)}" if errors else ""
    raise SarvamError(f"Sarvam did not produce a usable transcript file{suffix}.")


def _meeting_transcript(output: dict[str, Any]) -> tuple[str, bool]:
    diarized = output.get("diarized_transcript")
    entries = diarized.get("entries") if isinstance(diarized, dict) else None
    if isinstance(entries, list):
        lines = [_diarized_line(entry) for entry in entries if isinstance(entry, dict)]
        lines = [line for line in lines if line]
        if lines:
            return "\n".join(lines), True

    transcript = output.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip(), False
    raise SarvamError("Sarvam speech-to-text returned an empty transcript.")


def _diarized_line(entry: dict[str, Any]) -> str | None:
    transcript = entry.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        return None
    raw_speaker = str(entry.get("speaker_id", "Unknown"))
    speaker = f"Speaker {raw_speaker}"
    start = entry.get("start_time_seconds")
    if isinstance(start, int | float) and start >= 0:
        return f"[{_format_timestamp(float(start))}] {speaker}: {transcript.strip()}"
    return f"{speaker}: {transcript.strip()}"


def _format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or "Unknown provider error"
    if isinstance(body, dict):
        return str(body.get("error") or body.get("detail") or body.get("message") or body)[:300]
    return str(body)[:300]
