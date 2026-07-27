from datetime import date

from callrhino.annotation.table import parse_action_rows, parse_decision_rows


def test_annotation_table_parses_structured_items() -> None:
    decisions = parse_decision_rows(
        [
            {
                "item_id": "decision_launch",
                "text": "Launch Friday.",
                "status": "confirmed",
                "decision_maker_text": "Aditi",
                "effective_date": "2026-07-31",
                "effective_date_text": "Friday",
                "date_precision": "resolved_relative",
                "evidence_segment_ids": "seg_0001, seg_0002",
            },
            {"item_id": ""},
        ]
    )
    actions = parse_action_rows(
        [
            {
                "item_id": "action_deck",
                "task": "Send the launch deck.",
                "commitment_status": "committed",
                "owner_text": "Rohan",
                "suggested_owner_text": "",
                "due_date": "2026-07-30",
                "due_text": "Thursday",
                "deadline_precision": "resolved_relative",
                "evidence_segment_ids": "seg_0003",
            }
        ]
    )

    assert decisions[0].effective_date == date(2026, 7, 31)
    assert decisions[0].evidence_segment_ids == ["seg_0001", "seg_0002"]
    assert actions[0].owner_text == "Rohan"
    assert actions[0].suggested_owner_text is None
    assert actions[0].evidence_segment_ids == ["seg_0003"]


def test_annotation_table_rejects_invalid_date() -> None:
    try:
        parse_action_rows(
            [
                {
                    "item_id": "action_deck",
                    "task": "Send the deck.",
                    "commitment_status": "committed",
                    "owner_text": "Rohan",
                    "suggested_owner_text": "",
                    "due_date": "31/07/2026",
                    "due_text": "Friday",
                    "deadline_precision": "resolved_relative",
                    "evidence_segment_ids": "seg_0001",
                }
            ]
        )
    except ValueError as exc:
        assert "Invalid isoformat" in str(exc)
    else:
        raise AssertionError("invalid table date should fail")


def test_annotation_table_rejects_populated_row_without_item_id() -> None:
    try:
        parse_decision_rows(
            [
                {
                    "item_id": "",
                    "text": "Launch Friday.",
                    "status": "confirmed",
                    "date_precision": "absent",
                }
            ]
        )
    except ValueError as exc:
        assert "Decision item ID is required" in str(exc)
    else:
        raise AssertionError("populated row without item ID should fail")


def test_annotation_table_treats_nan_cells_as_empty() -> None:
    actions = parse_action_rows(
        [
            {
                "item_id": "action_deck",
                "task": "Send the deck.",
                "commitment_status": "committed",
                "owner_text": float("nan"),
                "suggested_owner_text": float("nan"),
                "due_date": float("nan"),
                "due_text": float("nan"),
                "deadline_precision": "absent",
                "evidence_segment_ids": "seg_0001",
            }
        ]
    )

    assert actions[0].owner_text is None
    assert actions[0].due_date is None
