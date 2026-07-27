import json
from pathlib import Path

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
