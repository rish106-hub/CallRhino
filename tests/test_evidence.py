from callrhino.domain.transcript import segment_transcript
from callrhino.services.evidence import complete_evidence_context


def _complete(payload: dict, transcript: str) -> dict:
    complete_evidence_context(payload, segment_transcript(transcript))
    return payload


def test_reversal_includes_previous_state_and_intervening_reason() -> None:
    payload = {
        "decisions": [
            {
                "status": "reversed",
                "evidence_segment_ids": ["seg_0003"],
            }
        ]
    }

    _complete(
        payload,
        "Neha: We had decided beta goes live on 30 July.\n"
        "Arjun: Payment callback is still failing.\n"
        "Neha: Cancel the 30 July launch.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
        "seg_0003",
    ]


def test_reversal_fills_a_gap_between_existing_evidence_segments() -> None:
    payload = {
        "decisions": [
            {
                "text": "Cancel the 30 July beta launch.",
                "status": "reversed",
                "evidence_segment_ids": ["seg_0001", "seg_0003"],
            }
        ]
    }

    _complete(
        payload,
        "Neha: We had decided beta goes live on 30 July.\n"
        "Arjun: Payment callback is still failing.\n"
        "Neha: Cancel the 30 July launch.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
        "seg_0003",
    ]


def test_deferred_decision_includes_condition_context() -> None:
    payload = {
        "decisions": [
            {
                "status": "deferred",
                "evidence_segment_ids": ["seg_0003"],
            }
        ]
    }

    _complete(
        payload,
        "Karthik: Payment screen is crashing.\n"
        "Divya: I will share the crash logs today.\n"
        "Karthik: We will decide after the logs arrive.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
        "seg_0003",
    ]


def test_terse_approval_includes_the_proposal() -> None:
    payload = {
        "decisions": [
            {
                "status": "confirmed",
                "evidence_segment_ids": ["seg_0002"],
            }
        ]
    }

    _complete(
        payload,
        "Ishita: The quote is ₹1.8 lakh excluding GST.\n"
        "Vikram: Approved, with a ₹2 lakh total cap.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
    ]


def test_complete_agreement_statement_does_not_add_context() -> None:
    payload = {
        "decisions": [
            {
                "text": "Campaign launch will be on Friday.",
                "status": "confirmed",
                "evidence_segment_ids": ["seg_0002"],
            }
        ]
    }

    _complete(
        payload,
        "Rohan: I will send the revised copy Wednesday.\n"
        "Aditi: Theek hai, campaign launch Friday ko karenge.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == ["seg_0002"]


def test_complete_decision_removes_non_contributing_previous_evidence() -> None:
    payload = {
        "decisions": [
            {
                "text": "Campaign launch will occur on Friday.",
                "status": "confirmed",
                "evidence_segment_ids": ["seg_0001", "seg_0002"],
            }
        ]
    }

    _complete(
        payload,
        "Rohan: I will send the revised copy Wednesday.\n"
        "Aditi: Theek hai, campaign launch Friday ko karenge.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == ["seg_0002"]


def test_non_agreement_decision_keeps_model_supplied_context() -> None:
    payload = {
        "decisions": [
            {
                "text": "Campaign launch will occur on Friday.",
                "status": "confirmed",
                "evidence_segment_ids": ["seg_0001", "seg_0002"],
            }
        ]
    }

    _complete(
        payload,
        "Rohan: The copy dependency is resolved.\n"
        "Aditi: Campaign launch Friday ko karenge.",
    )

    assert payload["decisions"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
    ]


def test_requested_action_includes_refusal_and_owner_state() -> None:
    payload = {
        "action_items": [
            {
                "commitment_status": "requested",
                "owner_basis": "unassigned",
                "evidence_segment_ids": ["seg_0001"],
            }
        ]
    }

    _complete(
        payload,
        "Meera: Kunal, send the updated PO by EOD.\n"
        "Kunal: I cannot commit before finance approval.\n"
        "Meera: Keep the owner open until approval.",
    )

    assert payload["action_items"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
        "seg_0003",
    ]


def test_group_commitment_includes_the_requested_object() -> None:
    payload = {
        "action_items": [
            {
                "commitment_status": "committed",
                "owner_basis": "group_commitment",
                "evidence_segment_ids": ["seg_0002"],
            }
        ]
    }

    _complete(
        payload,
        "Client: When will we get the Hindi dashboard?\n"
        "Priya: Hum jaldi share kar denge.",
    )

    assert payload["action_items"][0]["evidence_segment_ids"] == [
        "seg_0001",
        "seg_0002",
    ]


def test_independent_self_commitment_does_not_add_context() -> None:
    payload = {
        "action_items": [
            {
                "commitment_status": "committed",
                "owner_basis": "self_commitment",
                "evidence_segment_ids": ["seg_0002"],
            }
        ]
    }

    _complete(
        payload,
        "Aditi: The dashboard is ready.\n"
        "Rohan: I will send the final report by Friday.",
    )

    assert payload["action_items"][0]["evidence_segment_ids"] == ["seg_0002"]


def test_unknown_evidence_id_is_preserved_for_validation() -> None:
    payload = {
        "action_items": [
            {
                "commitment_status": "committed",
                "owner_basis": "self_commitment",
                "evidence_segment_ids": ["seg_9999"],
            }
        ]
    }

    _complete(payload, "Rohan: I will send the report.")

    assert payload["action_items"][0]["evidence_segment_ids"] == ["seg_9999"]
