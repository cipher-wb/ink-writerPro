"""Debug CLI — status / report / toggle."""
from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from ink_writer.debug.config import deep_merge, load_config
from ink_writer.debug.indexer import Indexer
from ink_writer.debug.reporter import Reporter

KEY_TO_PATH = {
    "master": ("master_enabled",),
    "layer_a": ("layers", "layer_a_hooks"),
    "layer_b": ("layers", "layer_b_checker_router"),
    "layer_c": ("layers", "layer_c_invariants"),
    "layer_d": ("layers", "layer_d_adversarial"),
}


def _enable_cli_utf8_stdio() -> None:
    """Enable UTF-8 stdio for Windows CLI launches; no-op elsewhere."""
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / "ink-writer" / "scripts",
        here.parents[3],
    )
    for scripts_dir in candidates:
        if scripts_dir.is_dir():
            import sys

            scripts_path = str(scripts_dir)
            if scripts_path not in sys.path:
                sys.path.insert(0, scripts_path)
            try:
                from runtime_compat import enable_windows_utf8_stdio

                enable_windows_utf8_stdio()
                return
            except Exception:
                continue


def cmd_status(*, project_root: Path, global_yaml: Path) -> None:
    cfg = load_config(global_yaml_path=global_yaml, project_root=project_root)
    Indexer(cfg).sync()
    db = cfg.base_path() / "debug.db"
    print(f"[debug status] 项目: {project_root.name}")
    print("=" * 60)
    print(f"开关: master={'on' if cfg.master_enabled else 'off'}  "
          f"layer_a={'on' if cfg.layers.layer_a_hooks else 'off'}  "
          f"layer_b={'on' if cfg.layers.layer_b_checker_router else 'off'}  "
          f"layer_c={'on' if cfg.layers.layer_c_invariants else 'off'}  "
          f"layer_d={'on' if cfg.layers.layer_d_adversarial else 'off'}")
    print("=" * 60)
    if not db.exists():
        print("最近 24h: 无数据")
        return
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn = sqlite3.connect(db)
    rows = list(conn.execute(
        "SELECT severity, kind FROM incidents WHERE ts >= ?", (cutoff_24h,)
    ))
    conn.close()
    sev = Counter(r[0] for r in rows)
    kinds = Counter(r[1] for r in rows)
    print("最近 24h:")
    for s in ("info", "warn", "error"):
        print(f"  {s}: {sev.get(s, 0)}")
    print("=" * 60)
    print("top3 频发 kind:")
    for k, n in kinds.most_common(3):
        print(f"  {k}  ×{n}")
    print("=" * 60)
    print("完整报告：/ink-debug-report --since 1d")


def cmd_report(*, project_root: Path, global_yaml: Path,
               since: str, run_id: str | None, severity: str) -> Path:
    cfg = load_config(global_yaml_path=global_yaml, project_root=project_root)
    Indexer(cfg).sync()
    md = Reporter(cfg).render(since=since, run_id=run_id, severity=severity)
    reports_dir = cfg.base_path() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"manual-{ts}.md"
    path.write_text(md, encoding="utf-8")
    print(f"报告已生成 → {path}")
    return path


def cmd_toggle(*, project_root: Path, global_yaml: Path, key: str, value: bool) -> None:
    if key not in KEY_TO_PATH:
        sub = key.split(".", 1)
        if len(sub) == 2 and sub[0] == "invariants":
            override = {"invariants": {sub[1]: {"enabled": value}}}
        else:
            raise SystemExit(f"unknown key: {key}")
    else:
        path = KEY_TO_PATH[key]
        override: dict = {}
        cur = override
        for p in path[:-1]:
            cur[p] = {}
            cur = cur[p]
        cur[path[-1]] = value

    local_path = project_root / ".ink-debug" / "config.local.yaml"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if local_path.exists():
        existing = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
    merged = deep_merge(existing, override)
    local_path.write_text(yaml.safe_dump(merged, allow_unicode=True), encoding="utf-8")
    print(f"已写入 {local_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ink-debug")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--global-yaml", type=Path, default=Path("config/debug.yaml"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    p_report = sub.add_parser("report")
    p_report.add_argument("--since", default="1d")
    p_report.add_argument("--run-id", default=None)
    p_report.add_argument("--severity", default="info")

    p_toggle = sub.add_parser("toggle")
    p_toggle.add_argument("key")
    p_toggle.add_argument("value", choices=["on", "off"])

    args = parser.parse_args(argv)
    if args.cmd == "status":
        cmd_status(project_root=args.project_root, global_yaml=args.global_yaml)
    elif args.cmd == "report":
        cmd_report(project_root=args.project_root, global_yaml=args.global_yaml,
                   since=args.since, run_id=args.run_id, severity=args.severity)
    elif args.cmd == "toggle":
        cmd_toggle(project_root=args.project_root, global_yaml=args.global_yaml,
                   key=args.key, value=(args.value == "on"))
    return 0


if __name__ == "__main__":
    _enable_cli_utf8_stdio()
    raise SystemExit(main())
