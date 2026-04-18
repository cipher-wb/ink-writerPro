"""Read/write .ink/propagation_debt.json (FIX-17 P4a)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from ink_writer.propagation.models import PropagationDebtFile, PropagationDebtItem

DEFAULT_REL_PATH = Path(".ink/propagation_debt.json")


class DebtStore:
    """轻量 JSON store：仅负责 load/save/roundtrip，业务逻辑交给 detector/consumer。"""

    def __init__(self, path: Union[str, Path, None] = None, project_root: Optional[Path] = None):
        if path is not None:
            self.path = Path(path)
        else:
            root = project_root or Path.cwd()
            self.path = root / DEFAULT_REL_PATH

    def load(self) -> PropagationDebtFile:
        if not self.path.exists():
            return PropagationDebtFile()
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return PropagationDebtFile()
        data = json.loads(raw)
        return PropagationDebtFile.model_validate(data)

    def save(self, file: PropagationDebtFile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = file.model_dump(mode="json")
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def append(self, item: PropagationDebtItem) -> PropagationDebtFile:
        file = self.load()
        file.upsert(item)
        self.save(file)
        return file
