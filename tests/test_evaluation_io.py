from pathlib import Path

import pytest

from callrhino.evaluation.io import require_distinct_paths


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
