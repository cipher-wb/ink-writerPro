from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_JSON_PATH = ROOT / "ink-writer" / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON_PATH = ROOT / ".claude-plugin" / "marketplace.json"
GEMINI_EXTENSION_PATH = ROOT / "gemini-extension.json"
SCRIPTS_INIT_PATH = ROOT / "ink-writer" / "scripts" / "__init__.py"
PACKAGE_JSON_PATH = ROOT / "ink-writer" / "dashboard" / "frontend" / "package.json"
PACKAGE_LOCK_PATH = ROOT / "ink-writer" / "dashboard" / "frontend" / "package-lock.json"
README_PATH = ROOT / "README.md"
PLUGIN_NAME = "ink-writer"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
README_BADGE_PATTERN = re.compile(
    r"(\[!\[Version\]\(https://img\.shields\.io/badge/Version-)"
    r"[\d.]+"
    r"(-green\.svg\)\])"
)
README_ROW_PATTERN = re.compile(
    r"^\| \*\*v(?P<version>[^\s*]+)(?P<current> \(当前\))?\*\* \| (?P<notes>.*) \|$"
)
README_HEADER = "| 版本 | 说明 |"
README_SEPARATOR = "|------|------|"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def get_marketplace_plugin(payload: dict[str, Any]) -> dict[str, Any]:
    plugins = payload.get("plugins", [])
    for plugin in plugins:
        if plugin.get("name") == PLUGIN_NAME:
            return plugin
    raise ValueError(f"Plugin {PLUGIN_NAME} not found in marketplace.json")


def parse_readme_rows(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = README_ROW_PATTERN.match(line.strip())
        if not match:
            continue
        rows.append(
            {
                "index": index,
                "version": match.group("version"),
                "notes": match.group("notes"),
                "is_current": bool(match.group("current")),
            }
        )
    return rows


def format_readme_row(version: str, notes: str, is_current: bool) -> str:
    marker = " (当前)" if is_current else ""
    return f"| **v{version}{marker}** | {notes.strip()} |"


def get_readme_current_version(content: str) -> str:
    rows = parse_readme_rows(content.splitlines())
    current_rows = [row for row in rows if row["is_current"]]
    if len(current_rows) != 1:
        raise ValueError("README.md must contain exactly one current release row")
    return str(current_rows[0]["version"])


def update_readme_release(content: str, version: str, release_notes: str | None) -> str:
    lines = content.splitlines()

    try:
        header_index = next(index for index, line in enumerate(lines) if line.strip() == README_HEADER)
    except StopIteration as error:
        raise ValueError("README.md release table header not found") from error

    separator_index = header_index + 1
    if separator_index >= len(lines) or lines[separator_index].strip() != README_SEPARATOR:
        raise ValueError("README.md release table separator not found")

    rows = parse_readme_rows(lines)
    target_row = next((row for row in rows if row["version"] == version), None)

    for row in rows:
        is_target = row["version"] == version
        notes = release_notes if is_target and release_notes is not None else row["notes"]
        lines[row["index"]] = format_readme_row(row["version"], notes, is_target)

    if target_row is None:
        if not release_notes:
            raise ValueError(
                "Release notes are required when the target version does not exist in README.md"
            )
        lines.insert(separator_index + 1, format_readme_row(version, release_notes, True))

    return "\n".join(lines) + "\n"


def sync_versions(version: str | None = None, release_notes: str | None = None) -> tuple[str, str, bool]:
    plugin_payload = load_json(PLUGIN_JSON_PATH)
    marketplace_payload = load_json(MARKETPLACE_JSON_PATH)
    gemini_payload = load_json(GEMINI_EXTENSION_PATH) if GEMINI_EXTENSION_PATH.exists() else None
    readme_content = load_text(README_PATH)
    marketplace_plugin = get_marketplace_plugin(marketplace_payload)

    previous_version = str(plugin_payload.get("version", ""))
    target_version = version or previous_version
    changed = False

    if plugin_payload.get("version") != target_version:
        plugin_payload["version"] = target_version
        changed = True

    if marketplace_plugin.get("version") != target_version:
        marketplace_plugin["version"] = target_version
        changed = True

    if gemini_payload is not None and gemini_payload.get("version") != target_version:
        gemini_payload["version"] = target_version
        changed = True

    # scripts/__init__.py __version__
    if SCRIPTS_INIT_PATH.exists():
        init_text = SCRIPTS_INIT_PATH.read_text(encoding="utf-8")
        new_init = re.sub(
            r'^__version__\s*=\s*["\'].*?["\']',
            f'__version__ = "{target_version}"',
            init_text,
            count=1,
            flags=re.MULTILINE,
        )
        if new_init != init_text:
            save_text(SCRIPTS_INIT_PATH, new_init)
            changed = True

    # dashboard frontend package.json & package-lock.json
    if PACKAGE_JSON_PATH.exists():
        pkg_payload = load_json(PACKAGE_JSON_PATH)
        if pkg_payload.get("version") != target_version:
            pkg_payload["version"] = target_version
            save_json(PACKAGE_JSON_PATH, pkg_payload)
            changed = True

    if PACKAGE_LOCK_PATH.exists():
        lock_payload = load_json(PACKAGE_LOCK_PATH)
        lock_changed = False
        if lock_payload.get("version") != target_version:
            lock_payload["version"] = target_version
            lock_changed = True
        # Also update the root entry in "packages"
        root_pkg = lock_payload.get("packages", {}).get("")
        if root_pkg and root_pkg.get("version") != target_version:
            root_pkg["version"] = target_version
            lock_changed = True
        if lock_changed:
            save_json(PACKAGE_LOCK_PATH, lock_payload)
            changed = True

    updated_readme = update_readme_release(readme_content, target_version, release_notes)
    updated_readme = README_BADGE_PATTERN.sub(rf"\g<1>{target_version}\g<2>", updated_readme)
    if updated_readme != readme_content:
        save_text(README_PATH, updated_readme)
        changed = True

    if changed:
        save_json(PLUGIN_JSON_PATH, plugin_payload)
        save_json(MARKETPLACE_JSON_PATH, marketplace_payload)
        if gemini_payload is not None:
            save_json(GEMINI_EXTENSION_PATH, gemini_payload)

    return previous_version, target_version, changed


def _get_schema_versions() -> dict[str, str]:
    """收集 state.json 和 index_manager 的 schema 版本号"""
    versions: dict[str, str] = {}
    # state.json schema_version (来自 state_schema.py 的默认值)
    try:
        import sys, importlib.util
        schema_path = ROOT / "ink-writer" / "scripts" / "state_schema.py"
        if schema_path.exists():
            spec = importlib.util.spec_from_file_location("state_schema", schema_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["state_schema"] = mod
            spec.loader.exec_module(mod)
            versions["state_schema"] = str(getattr(mod.StateModel.model_fields["schema_version"], "default", "?"))
    except Exception:
        pass
    # index.db SCHEMA_VERSION (来自 index_manager.py 的类属性)
    try:
        idx_path = ROOT / "ink-writer" / "scripts" / "data_modules" / "index_manager.py"
        if idx_path.exists():
            for line in idx_path.read_text().splitlines():
                if "SCHEMA_VERSION" in line and "=" in line and "class" not in line.lower():
                    versions["index_schema"] = line.split("=")[1].strip()
                    break
    except Exception:
        pass
    return versions


def check_versions(expected_version: str | None = None) -> int:
    plugin_payload = load_json(PLUGIN_JSON_PATH)
    marketplace_payload = load_json(MARKETPLACE_JSON_PATH)
    gemini_payload = load_json(GEMINI_EXTENSION_PATH) if GEMINI_EXTENSION_PATH.exists() else None
    readme_content = load_text(README_PATH)
    marketplace_plugin = get_marketplace_plugin(marketplace_payload)

    plugin_version = str(plugin_payload.get("version", ""))
    marketplace_version = str(marketplace_plugin.get("version", ""))
    gemini_version = str(gemini_payload.get("version", "")) if gemini_payload else plugin_version
    readme_version = get_readme_current_version(readme_content)

    # scripts/__init__.py __version__
    scripts_init_version = plugin_version  # default match
    if SCRIPTS_INIT_PATH.exists():
        for line in SCRIPTS_INIT_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                scripts_init_version = line.split("=")[1].strip().strip('"').strip("'")
                break

    # README badge version
    badge_match = README_BADGE_PATTERN.search(readme_content)
    badge_version = ""
    if badge_match:
        badge_version = readme_content[badge_match.start(0):badge_match.end(0)]
        badge_version = re.search(r"Version-(\d+\.\d+\.\d+)-", badge_version)
        badge_version = badge_version.group(1) if badge_version else ""

    mismatches: list[str] = []
    if badge_version and plugin_version != badge_version:
        mismatches.append(
            f"plugin.json={plugin_version}, README badge={badge_version}"
        )
    if plugin_version != marketplace_version:
        mismatches.append(
            f"plugin.json={plugin_version}, marketplace.json={marketplace_version}"
        )
    if plugin_version != gemini_version:
        mismatches.append(
            f"plugin.json={plugin_version}, gemini-extension.json={gemini_version}"
        )
    if plugin_version != readme_version:
        mismatches.append(f"plugin.json={plugin_version}, README.md={readme_version}")
    if plugin_version != scripts_init_version:
        mismatches.append(
            f"plugin.json={plugin_version}, scripts/__init__.py={scripts_init_version}"
        )
    # dashboard frontend package.json & package-lock.json
    if PACKAGE_JSON_PATH.exists():
        pkg_version = str(load_json(PACKAGE_JSON_PATH).get("version", ""))
        if plugin_version != pkg_version:
            mismatches.append(
                f"plugin.json={plugin_version}, package.json={pkg_version}"
            )
    if PACKAGE_LOCK_PATH.exists():
        lock_version = str(load_json(PACKAGE_LOCK_PATH).get("version", ""))
        if plugin_version != lock_version:
            mismatches.append(
                f"plugin.json={plugin_version}, package-lock.json={lock_version}"
            )

    if expected_version and plugin_version != expected_version:
        mismatches.append(
            f"expected={expected_version}, current release metadata={plugin_version}"
        )

    if mismatches:
        print("Version mismatch detected:")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return 1

    # 报告 schema 版本（仅信息性，不阻断）
    schema_vers = _get_schema_versions()
    schema_info = ", ".join(f"{k}={v}" for k, v in schema_vers.items()) if schema_vers else "N/A"
    print(f"Versions are in sync: {plugin_version} (schema: {schema_info})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Claude plugin release metadata")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether plugin metadata and README release info are in sync",
    )
    parser.add_argument(
        "--version",
        help="Update release metadata to the given semantic version",
    )
    parser.add_argument(
        "--expected-version",
        help="When used with --check, require the current release metadata to match this version",
    )
    parser.add_argument(
        "--release-notes",
        help="Release notes used for the README current release row",
    )
    args = parser.parse_args()

    if args.version and not VERSION_PATTERN.fullmatch(args.version):
        parser.error("--version must look like X.Y.Z")
    if args.expected_version and not VERSION_PATTERN.fullmatch(args.expected_version):
        parser.error("--expected-version must look like X.Y.Z")
    if args.expected_version and not args.check:
        parser.error("--expected-version can only be used together with --check")

    try:
        if args.check:
            return check_versions(expected_version=args.expected_version)

        previous_version, target_version, changed = sync_versions(
            version=args.version,
            release_notes=args.release_notes,
        )
    except ValueError as error:
        print(f"Error: {error}")
        return 1

    if changed:
        print(f"Updated release metadata: {previous_version} -> {target_version}")
    else:
        print(f"No changes needed. Current version: {target_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
