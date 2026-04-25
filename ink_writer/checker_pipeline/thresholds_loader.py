"""M3 阈值加载器：读 config/checker-thresholds.yaml。

ink-write 启动时调一次 load_thresholds()，把 dict 透传给 rewrite_loop / 各 checker。
M3 期间不做热更新；修改 yaml 后需重启 writer。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "checker-thresholds.yaml"
)


class ThresholdsConfigError(RuntimeError):
    """阈值配置加载失败（缺文件 / yaml 解析失败）。"""


def load_thresholds(path: Path | str | None = None) -> dict[str, Any]:
    """加载 M3 阈值 yaml；缺文件或解析失败 raise ThresholdsConfigError。"""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        raise ThresholdsConfigError(
            f"checker-thresholds.yaml not found: {path}"
        )

    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ThresholdsConfigError(
            f"failed to parse checker-thresholds.yaml: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ThresholdsConfigError(
            f"checker-thresholds.yaml must be a mapping at top level, got {type(raw).__name__}"
        )

    return raw
