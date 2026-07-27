import fcntl
import os
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pydantic import ValidationError

from callrhino.annotation.models import (
    Adjudication,
    AnnotationRecord,
    ReviewerSubmission,
    SourceMeeting,
)


class AnnotationRepositoryError(RuntimeError):
    pass


class AnnotationNotFoundError(AnnotationRepositoryError):
    pass


class DuplicateMeetingError(AnnotationRepositoryError):
    pass


class DuplicateReviewerError(AnnotationRepositoryError):
    pass


class ReviewerLimitError(AnnotationRepositoryError):
    pass


class DuplicateAdjudicationError(AnnotationRepositoryError):
    pass


RecordResult = TypeVar("RecordResult")


class JsonAnnotationRepository:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def create(self, source: SourceMeeting) -> AnnotationRecord:
        with self._meeting_lock(source.id):
            path = self._record_path(source.id)
            if path.exists():
                raise DuplicateMeetingError(f'annotation meeting "{source.id}" already exists')
            record = AnnotationRecord(source=source)
            self._atomic_write(path, record)
            return record

    def get(self, meeting_id: str) -> AnnotationRecord:
        path = self._record_path(meeting_id)
        if not path.exists():
            raise AnnotationNotFoundError(f'annotation meeting "{meeting_id}" was not found')
        return AnnotationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_records(self) -> list[AnnotationRecord]:
        records = []
        for path in sorted(self._root.glob("*.json")):
            try:
                records.append(
                    AnnotationRecord.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValidationError) as exc:
                raise AnnotationRepositoryError(
                    f'Could not load annotation record "{path}": {exc}'
                ) from exc
        return records

    def delete(self, meeting_id: str) -> None:
        with self._meeting_lock(meeting_id):
            path = self._record_path(meeting_id)
            if not path.exists():
                raise AnnotationNotFoundError(
                    f'annotation meeting "{meeting_id}" was not found'
                )
            path.unlink()
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    def add_submission(
        self,
        meeting_id: str,
        submission: ReviewerSubmission,
    ) -> AnnotationRecord:
        def append(record: AnnotationRecord) -> AnnotationRecord:
            reviewer_key = submission.reviewer_id.casefold()
            if any(
                existing.reviewer_id.casefold() == reviewer_key
                for existing in record.submissions
            ):
                raise DuplicateReviewerError(
                    f'reviewer "{submission.reviewer_id}" already submitted'
                )
            if len(record.submissions) >= 2:
                raise ReviewerLimitError("a meeting accepts exactly two reviewer submissions")
            return record.model_copy(
                update={"submissions": [*record.submissions, submission]}
            )

        return self._mutate(meeting_id, append)

    def set_adjudication(
        self,
        meeting_id: str,
        adjudication: Adjudication,
    ) -> AnnotationRecord:
        def set_once(record: AnnotationRecord) -> AnnotationRecord:
            if record.adjudication is not None:
                raise DuplicateAdjudicationError("the gold case has already been adjudicated")
            return record.model_copy(update={"adjudication": adjudication})

        return self._mutate(meeting_id, set_once)

    def _mutate(
        self,
        meeting_id: str,
        operation: Callable[[AnnotationRecord], AnnotationRecord],
    ) -> AnnotationRecord:
        with self._meeting_lock(meeting_id):
            record = self.get(meeting_id)
            updated = AnnotationRecord.model_validate(operation(record))
            self._atomic_write(self._record_path(meeting_id), updated)
            return updated

    def _record_path(self, meeting_id: str) -> Path:
        if (
            not meeting_id
            or meeting_id in {".", ".."}
            or Path(meeting_id).name != meeting_id
        ):
            raise ValueError("meeting ID is not a safe file name")
        return self._root / f"{meeting_id}.json"

    @contextmanager
    def _meeting_lock(self, meeting_id: str):
        lock_path = self._record_path(meeting_id).with_suffix(".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _atomic_write(self, path: Path, record: AnnotationRecord) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(record.model_dump_json(indent=2))
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
