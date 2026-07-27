from pathlib import Path

import pytest

from callrhino.evaluation.io import require_distinct_paths, write_private_json


def test_evaluation_paths_reject_input_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.json"

    with pytest.raises(ValueError, match="must not overwrite"):
        require_distinct_paths(
            inputs={"--cases": source},
            outputs={"--output": source},
        )


def test_evaluation_paths_reject_duplicate_outputs(tmp_path: Path) -> None:
    output = tmp_path / "output.json"

    with pytest.raises(ValueError, match="must use different paths"):
        require_distinct_paths(
            inputs={},
            outputs={
                "--public-output": output,
                "--gold-output": output,
            },
        )


def test_private_json_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "private" / "gold.json"

    write_private_json(path, {"secret": "labels"})

    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text(encoding="utf-8").endswith("\n")
