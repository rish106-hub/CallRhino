import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


def load_model[ModelT: BaseModel](path: Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: BaseModel | dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_private_json(path: Path, value: BaseModel | dict | list) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def require_distinct_paths(
    *,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
) -> None:
    resolved_inputs = {name: path.resolve() for name, path in inputs.items()}
    resolved_outputs = {name: path.resolve() for name, path in outputs.items()}
    all_outputs = list(resolved_outputs.items())

    for output_name, output_path in all_outputs:
        for input_name, input_path in resolved_inputs.items():
            if output_path == input_path:
                raise ValueError(
                    f"{output_name} must not overwrite {input_name}: {output_path}"
                )

    for index, (first_name, first_path) in enumerate(all_outputs):
        for second_name, second_path in all_outputs[index + 1 :]:
            if first_path == second_path:
                raise ValueError(
                    f"{first_name} and {second_name} must use different paths: "
                    f"{first_path}"
                )
