from callrhino.services.exports import brief_to_json, brief_to_markdown


def test_markdown_export_contains_approved_work(valid_brief) -> None:
    result = brief_to_markdown(
        valid_brief,
        title="Launch review",
        series_name="Weekly Product Review",
    )

    assert result.startswith("# Launch review")
    assert "Owner: Rohan" in result
    assert "Evidence: seg_0003" in result


def test_json_export_is_unicode_safe(valid_brief) -> None:
    result = brief_to_json(valid_brief)

    assert '"action_items"' in result
    assert "\\u" not in result

