import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from callrhino.domain.models import ApprovedMeeting, MeetingBrief, TranscriptSegment

SCHEMA_VERSION = 2


class SQLiteMeetingRepository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meeting_series (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY,
                    series_id TEXT NOT NULL REFERENCES meeting_series(id),
                    title TEXT NOT NULL,
                    meeting_date TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    transcript_text TEXT NOT NULL,
                    segments_json TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS meetings_series_date_idx
                ON meetings(series_id, meeting_date DESC);
                """
            )

    def approve_meeting(
        self,
        *,
        series_name: str,
        title: str,
        meeting_date: date,
        source_type: str,
        transcript_text: str,
        segments: list[TranscriptSegment],
        brief: MeetingBrief,
    ) -> str:
        meeting_id = str(uuid4())
        approved_at = datetime.now(UTC)

        with self._connect() as connection:
            series_row = connection.execute(
                "SELECT id FROM meeting_series WHERE name = ? COLLATE NOCASE",
                (series_name.strip(),),
            ).fetchone()
            if series_row:
                series_id = str(series_row["id"])
            else:
                series_id = str(uuid4())
                connection.execute(
                    "INSERT INTO meeting_series(id, name, created_at) VALUES (?, ?, ?)",
                    (series_id, series_name.strip(), approved_at.isoformat()),
                )

            connection.execute(
                """
                INSERT INTO meetings(
                    id, series_id, title, meeting_date, source_type, transcript_text,
                    segments_json, brief_json, approved_at, schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meeting_id,
                    series_id,
                    title.strip(),
                    meeting_date.isoformat(),
                    source_type,
                    transcript_text,
                    json.dumps(
                        [segment.model_dump(mode="json") for segment in segments],
                        ensure_ascii=False,
                    ),
                    brief.model_dump_json(),
                    approved_at.isoformat(),
                    SCHEMA_VERSION,
                ),
            )
        return meeting_id

    def list_meetings(self, *, series_name: str | None = None) -> list[ApprovedMeeting]:
        query = """
            SELECT m.*, s.name AS series_name
            FROM meetings m
            JOIN meeting_series s ON s.id = m.series_id
        """
        parameters: tuple[str, ...] = ()
        if series_name:
            query += " WHERE s.name = ? COLLATE NOCASE"
            parameters = (series_name,)
        query += " ORDER BY m.meeting_date DESC, m.approved_at DESC"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [
            ApprovedMeeting(
                id=str(row["id"]),
                series_name=str(row["series_name"]),
                title=str(row["title"]),
                meeting_date=date.fromisoformat(str(row["meeting_date"])),
                source_type=str(row["source_type"]),
                transcript_text=str(row["transcript_text"]),
                segments=[
                    TranscriptSegment.model_validate(item)
                    for item in json.loads(str(row["segments_json"]))
                ],
                brief=MeetingBrief.model_validate_json(str(row["brief_json"])),
                approved_at=datetime.fromisoformat(str(row["approved_at"])),
            )
            for row in rows
        ]

    def list_series(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM meeting_series ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [str(row["name"]) for row in rows]
