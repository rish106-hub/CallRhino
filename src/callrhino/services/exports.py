import json

from callrhino.domain.models import MeetingBrief


def brief_to_json(brief: MeetingBrief) -> str:
    return json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False)


def brief_to_markdown(brief: MeetingBrief, *, title: str, series_name: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"**Series:** {series_name}",
        "",
        "## Summary",
        "",
        brief.summary.short,
        "",
        "## Decisions",
        "",
    ]
    lines.extend(
        _numbered_lines(
            [
                f"{item.text}{_owner_suffix(item.owner_text)} "
                f"`Evidence: {', '.join(item.evidence_segment_ids)}`"
                for item in brief.decisions
            ]
        )
    )
    lines.extend(["", "## Action items", ""])
    lines.extend(
        _checkbox_lines(
            [
                (
                    f"{item.task}{_owner_suffix(item.owner_text)}"
                    f"{_deadline_suffix(item.due_text, item.due_date)}"
                )
                for item in brief.action_items
            ]
        )
    )
    lines.extend(["", "## Open questions", ""])
    lines.extend(_bullet_lines([item.text for item in brief.open_questions]))
    lines.extend(["", "## Risks", ""])
    lines.extend(_bullet_lines([item.text for item in brief.risks]))
    return "\n".join(lines).rstrip() + "\n"


def _owner_suffix(owner: str | None) -> str:
    return f" | Owner: {owner}" if owner else " | Owner: unassigned"


def _deadline_suffix(due_text: str | None, due_date: object | None) -> str:
    value = due_text or (str(due_date) if due_date else None)
    return f" | Due: {value}" if value else " | Due: not set"


def _numbered_lines(items: list[str]) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)] or [
        "No decisions recorded."
    ]


def _checkbox_lines(items: list[str]) -> list[str]:
    return [f"- [ ] {item}" for item in items] or ["No action items recorded."]


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["None recorded."]

