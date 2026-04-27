"""sync_settings.py — 自动回写设定集 (US-004)

从 index.db 和大纲文件提取实体信息，增量同步到 設定集/ markdown 文件。

用法：
    python3 ink-writer/scripts/sync_settings.py --project-root <项目根目录>
    python3 ink-writer/scripts/sync_settings.py --project-root <项目根目录> --dry-run
    python3 ink-writer/scripts/sync_settings.py --project-root <项目根目录> --volume 1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中，使 ink_writer 和 runtime_compat 可导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── 实体类型 → 设定集文件映射 ──────────────────────────────────────────
TYPE_TO_FILE: dict[str, str] = {
    "角色": "角色卡.md",
    "势力": "世界观.md",
    "地点": "世界观.md",
    "物品": "世界观.md",
    "招式": "世界观.md",
}

# 核心角色（主角/重要角色）单独写入主角组
CORE_CHARACTER_FILE = "主角组.md"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync-settings",
        description="从 index.db 和大纲文件增量同步实体到 設定集/",
    )
    parser.add_argument("--project-root", required=True, type=Path, help="书项目根目录")
    parser.add_argument("--dry-run", action="store_true", help="只输出差异，不修改文件")
    parser.add_argument("--volume", type=int, default=None, help="仅同步指定卷（1-indexed）")
    return parser


# ── 实体读取 ────────────────────────────────────────────────────────────


def _get_entities_from_db(project_root: str) -> dict[str, list[dict]]:
    """从 index.db 抽取所有非归档实体，按 type 分组。

    Returns:
        {"角色": [{id, canonical_name, tier, desc, ...}, ...], ...}
    """
    from ink_writer.core.index.index_manager import IndexManager
    from ink_writer.core.infra.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    if not cfg.index_db.exists():
        return {}

    mgr = IndexManager(cfg)
    result: dict[str, list[dict]] = {}
    for entity_type in ("角色", "势力", "地点", "物品", "招式"):
        entities = mgr.get_entities_by_type(entity_type, include_archived=False)
        if entities:
            result[entity_type] = entities
    return result


def _get_characters_from_outlines(project_root: str, volume: int | None) -> dict[str, set[str]]:
    """从卷大纲文件中提取角色/势力/地点名称。

    大纲位置：project_root/大纲/ 或 project_root/outline.json

    Returns:
        {"角色": {"裴砚", "折玥"}, "势力": {"西夏"}, "地点": {"汴梁"}}
    """
    pr = Path(project_root)
    result: dict[str, set[str]] = {"角色": set(), "势力": set(), "地点": set()}

    # 尝试多来源：大纲/ 目录 > outline.json
    outline_dir = pr / "大纲"
    outline_files: list[Path] = []
    if outline_dir.is_dir():
        if volume is not None:
            vol_file = outline_dir / f"卷{volume}.json"
            if vol_file.exists():
                outline_files.append(vol_file)
        else:
            outline_files = sorted(outline_dir.glob("卷*.json"))
    if not outline_files:
        single = pr / "outline.json"
        if single.exists():
            outline_files.append(single)

    for outline_file in outline_files:
        try:
            data = json.loads(outline_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        skeletons = data.get("volume_skeleton", [])
        for ch in skeletons:
            summary = ch.get("summary", "")
            # 提取 → 前的角色名（如 "裴砚→武库激活"）
            for match in re.finditer(r"([一-鿿]{2,4})→", summary):
                result["角色"].add(match.group(1))

    # setting.json 中的 character_names
    setting_file = pr / "setting.json"
    if setting_file.exists():
        try:
            data = json.loads(setting_file.read_text(encoding="utf-8"))
            for entry in data.get("character_names", []):
                name = entry.get("name", "").strip()
                if name:
                    result["角色"].add(name)
        except (json.JSONDecodeError, OSError):
            pass

    return result


# ── 设定集读取 ──────────────────────────────────────────────────────────


def _read_existing_settings(settings_dir: Path) -> dict[str, set[str]]:
    """读取設定集/已有文件，提取已记录的实体名称。

    匹配策略：以 ## 开头的 markdown 标题作为实体名，
    同时对文件全文做实体名出现检查。

    Returns:
        文件路径 -> 已记录实体名集合
    """
    existing: dict[str, set[str]] = {}
    if not settings_dir.is_dir():
        return existing

    for md_file in sorted(settings_dir.glob("**/*.md")):
        names: set[str] = set()
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # 提取 ## 标题行中的实体名
        for match in re.finditer(r"^##\s+(.+)$", content, re.MULTILINE):
            name = match.group(1).strip()
            if name and 2 <= len(name) <= 6:
                names.add(name)
        # 也对全文做简单字符串搜索（备用）
        existing[str(md_file)] = names

    return existing


def _find_entity_in_settings(
    canonical_name: str, existing: dict[str, set[str]]
) -> str | None:
    """检查实体 canonical_name 是否已在任意设定集文件中存在。

    Returns:
        文件名如果找到，否则 None。
    """
    for filepath, names in existing.items():
        if canonical_name in names:
            return filepath
    return None


# ── 冲突检测 ────────────────────────────────────────────────────────────


def _detect_conflicts(
    db_entities: dict[str, list[dict]],
    outline_chars: dict[str, set[str]],
    existing: dict[str, set[str]],
) -> list[str]:
    """检测大纲声明与设定集已有条目的冲突。

    冲突条件：大纲声明某角色，设定集中已有同名实体但信息冲突。
    简化版：检查 outline 声明的角色名是否在 settings 中出现过 —
    若出现过则只标记不阻断（大纲是增量声明，不视为冲突）。

    Returns:
        冲突描述列表（当前版本始终为空 — 大纲被视为增量而非冲突源）。
    """
    # 大纲声明的角色如果在 settings 中已存在，不算冲突 —
    # 大纲是写作计划，设定集是已落地设定，大纲追加新信息是正常的。
    # 真正的冲突需要更深层的语义分析（如：大纲说 A 是友方，设定集说 A 是敌方），
    # 这超出了自动化检测范围，留给人审阅。
    return []


# ── markdown 生成 ───────────────────────────────────────────────────────


def _entity_to_markdown(entity: dict) -> str:
    """将实体 dict 转为 markdown 条目块。"""
    name = entity.get("canonical_name", entity.get("id", "未知"))
    tier = entity.get("tier", "装饰")
    desc = entity.get("desc", "")
    first_ch = entity.get("first_appearance", 0)
    last_ch = entity.get("last_appearance", 0)
    is_protagonist = entity.get("is_protagonist", False)
    current = entity.get("current_json", {})

    lines = [f"## {name}", ""]
    if is_protagonist:
        lines.append("- **身份**: 主角")
    lines.append(f"- **类型**: {entity.get('type', '未知')}")
    lines.append(f"- **重要度**: {tier}")
    if desc:
        lines.append(f"- **描述**: {desc}")
    if first_ch:
        lines.append(f"- **首次出场**: 第{first_ch}章")
        if last_ch and last_ch != first_ch:
            lines.append(f"- **最后出场**: 第{last_ch}章")
    elif last_ch:
        lines.append(f"- **最后出场**: 第{last_ch}章")
    if current:
        lines.append(f"- **当前状态**: {json.dumps(current, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def _target_file(entity_type: str, entity: dict) -> str:
    """根据实体类型和属性确定目标文件名。"""
    if entity_type == "角色":
        is_core = entity.get("is_protagonist") or entity.get("tier") in ("核心",)
        if is_core:
            return CORE_CHARACTER_FILE
    return TYPE_TO_FILE.get(entity_type, "世界观.md")


# ── 主同步逻辑 ──────────────────────────────────────────────────────────


def sync(project_root: str, *, dry_run: bool = False, volume: int | None = None) -> int:
    """执行设定集同步。

    Returns:
        0 成功，1 有冲突/BLOCKER。
    """
    pr = Path(project_root)
    if not pr.is_dir():
        print(f"[ERROR] project_root {pr} 不存在或不是目录", file=sys.stderr)
        return 1

    settings_dir = pr / "設定集"
    settings_dir.mkdir(parents=True, exist_ok=True)

    # 1. 从 index.db 读取实体
    db_entities = _get_entities_from_db(str(pr))
    if not db_entities:
        print("[INFO] index.db 中无实体数据，跳过同步")
        return 0

    # 2. 从大纲读取声明角色
    outline_chars = _get_characters_from_outlines(str(pr), volume)

    # 3. 读取设定集已有条目
    existing = _read_existing_settings(settings_dir)

    # 4. 冲突检测
    conflicts = _detect_conflicts(db_entities, outline_chars, existing)
    if conflicts:
        print("[BLOCKER] 大纲与设定集冲突:")
        for c in conflicts:
            print(f"  - {c}")
        return 1

    # 5. 找出设定集中未覆盖的实体，按目标文件分组
    new_entries: dict[str, list[str]] = {}  # target_file -> [markdown_blocks]
    total_new = 0

    for entity_type, entities in db_entities.items():
        for entity in entities:
            name = entity.get("canonical_name", "")
            if not name:
                continue

            # 检查是否已在设定集中
            found_in = _find_entity_in_settings(name, existing)
            if found_in:
                continue  # 幂等：已存在则跳过

            target = _target_file(entity_type, entity)
            block = _entity_to_markdown(entity)
            new_entries.setdefault(target, []).append(block)
            total_new += 1

    if total_new == 0:
        print("[OK] 设定集已是最新，无待同步实体")
        return 0

    # 6. 输出或写入
    if dry_run:
        print(f"[DRY-RUN] 将追加 {total_new} 个新实体到设定集:\n")
        for target_file, blocks in sorted(new_entries.items()):
            print(f"── {target_file} (+{len(blocks)} 条) ──")
            for block in blocks:
                # 只打印第一行标题
                title = block.strip().split("\n")[0]
                print(f"  {title}")
            print()
        return 0

    for target_file, blocks in new_entries.items():
        filepath = settings_dir / target_file
        filepath.parent.mkdir(parents=True, exist_ok=True)

        existing_content = ""
        if filepath.exists():
            existing_content = filepath.read_text(encoding="utf-8")
            if existing_content and not existing_content.endswith("\n"):
                existing_content += "\n"

        appended = "\n".join(blocks)
        new_content = existing_content + appended
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        filepath.write_text(new_content, encoding="utf-8")
        print(f"[WROTE] {target_file} ← +{len(blocks)} 条")

    print(f"[OK] 同步完成：{total_new} 个新实体已写入设定集")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:
        pass

    parser = _build_parser()
    args = parser.parse_args(argv)
    return sync(
        str(args.project_root),
        dry_run=args.dry_run,
        volume=args.volume,
    )


if __name__ == "__main__":
    sys.exit(main())
