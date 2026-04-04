"""Dashboard app.py 冒烟测试 — 验证 FastAPI 路由的基本行为。"""

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# 导入 dashboard 包（相对导入需要包上下文）
import dashboard  # noqa: F401
from dashboard.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _init_index_db(db_path: Path):
    """创建最小化的 index.db 表结构 + 测试数据。"""
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, canonical_name TEXT NOT NULL,
            tier TEXT DEFAULT '装饰', desc TEXT, current_json TEXT,
            first_appearance INTEGER DEFAULT 0, last_appearance INTEGER DEFAULT 0,
            is_protagonist INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO entities (id, type, canonical_name, first_appearance, last_appearance)
            VALUES ('xiao_yan', '角色', '萧炎', 1, 10);
        INSERT INTO entities (id, type, canonical_name, first_appearance, last_appearance, is_archived)
            VALUES ('old_npc', '角色', '路人甲', 1, 2, 1);

        CREATE TABLE aliases (
            alias TEXT NOT NULL, entity_id TEXT NOT NULL, entity_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
        INSERT INTO aliases VALUES ('小炎子', 'xiao_yan', '角色', CURRENT_TIMESTAMP);

        CREATE TABLE state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT NOT NULL,
            field TEXT NOT NULL, old_value TEXT, new_value TEXT, reason TEXT,
            chapter INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO state_changes (entity_id, field, old_value, new_value, reason, chapter)
            VALUES ('xiao_yan', '实力', '斗者', '斗师', '突破', 5);

        CREATE TABLE relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT, from_entity TEXT NOT NULL,
            to_entity TEXT NOT NULL, relation_type TEXT, desc TEXT,
            chapter INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO relationships (from_entity, to_entity, relation_type, chapter)
            VALUES ('xiao_yan', 'old_npc', '师徒', 1);

        CREATE TABLE chapters (
            chapter INTEGER PRIMARY KEY, title TEXT, summary TEXT, word_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO chapters VALUES (1, '天才少年', '萧炎初登场', 2500, CURRENT_TIMESTAMP);

        CREATE TABLE scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chapter INTEGER, scene_index INTEGER,
            location TEXT, summary TEXT
        );
        INSERT INTO scenes (chapter, scene_index, location, summary) VALUES (1, 0, '萧家', '开场');

        CREATE TABLE chapter_reading_power (
            chapter INTEGER PRIMARY KEY, score REAL
        );
        INSERT INTO chapter_reading_power VALUES (1, 85.0);

        CREATE TABLE review_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, start_chapter INTEGER,
            end_chapter INTEGER, score REAL
        );
        INSERT INTO review_metrics (start_chapter, end_chapter, score) VALUES (1, 5, 78.5);
    """)
    conn.close()


@pytest.fixture
def project(tmp_path):
    """创建带 state.json + index.db 的最小项目。"""
    ink = tmp_path / ".ink"
    ink.mkdir()
    (ink / "state.json").write_text(
        json.dumps({"progress": {"current_chapter": 1}, "version": "5.4"}),
        encoding="utf-8",
    )
    _init_index_db(ink / "index.db")

    # 创建文件目录
    for name in ("正文", "大纲", "设定集"):
        d = tmp_path / name
        d.mkdir()
    (tmp_path / "正文" / "第0001章-天才少年.md").write_text("# 天才少年\n正文内容")
    (tmp_path / "设定集" / "人物.md").write_text("# 角色设定")

    return tmp_path


@pytest.fixture
def client(project):
    app = create_app(project_root=project)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def empty_client(tmp_path):
    """无 index.db 的空项目。"""
    ink = tmp_path / ".ink"
    ink.mkdir()
    (ink / "state.json").write_text("{}", encoding="utf-8")
    app = create_app(project_root=tmp_path)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 项目信息
# ---------------------------------------------------------------------------

class TestProjectInfo:
    def test_project_info(self, client):
        r = client.get("/api/project/info")
        assert r.status_code == 200
        data = r.json()
        assert data["progress"]["current_chapter"] == 1

    def test_project_info_no_state(self, tmp_path):
        ink = tmp_path / ".ink"
        ink.mkdir()
        app = create_app(project_root=tmp_path)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/project/info")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 实体 API
# ---------------------------------------------------------------------------

class TestEntities:
    def test_list_entities(self, client):
        r = client.get("/api/entities")
        assert r.status_code == 200
        data = r.json()
        # 默认不含 archived
        ids = [e["id"] for e in data]
        assert "xiao_yan" in ids
        assert "old_npc" not in ids

    def test_list_entities_include_archived(self, client):
        r = client.get("/api/entities?include_archived=true")
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert "old_npc" in ids

    def test_list_entities_filter_type(self, client):
        r = client.get("/api/entities?type=角色")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_list_entities_invalid_type(self, client):
        r = client.get("/api/entities?type=无效类型")
        assert r.status_code == 400

    def test_get_entity(self, client):
        r = client.get("/api/entities/xiao_yan")
        assert r.status_code == 200
        assert r.json()["canonical_name"] == "萧炎"

    def test_get_entity_not_found(self, client):
        r = client.get("/api/entities/nonexistent")
        assert r.status_code == 404

    def test_no_db(self, empty_client):
        r = empty_client.get("/api/entities")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 关系 API
# ---------------------------------------------------------------------------

class TestRelationships:
    def test_list_relationships(self, client):
        r = client.get("/api/relationships")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_list_relationships_by_entity(self, client):
        r = client.get("/api/relationships?entity=xiao_yan")
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ---------------------------------------------------------------------------
# 章节 / 场景 API
# ---------------------------------------------------------------------------

class TestChaptersAndScenes:
    def test_list_chapters(self, client):
        r = client.get("/api/chapters")
        assert r.status_code == 200
        assert r.json()[0]["chapter"] == 1

    def test_list_scenes(self, client):
        r = client.get("/api/scenes?chapter=1")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_list_scenes_all(self, client):
        r = client.get("/api/scenes")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 阅读力 / 审查指标
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_reading_power(self, client):
        r = client.get("/api/reading-power")
        assert r.status_code == 200
        assert r.json()[0]["score"] == 85.0

    def test_review_metrics(self, client):
        r = client.get("/api/review-metrics")
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ---------------------------------------------------------------------------
# 别名 / 状态变化
# ---------------------------------------------------------------------------

class TestAliasesAndStateChanges:
    def test_list_aliases(self, client):
        r = client.get("/api/aliases")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_list_aliases_by_entity(self, client):
        r = client.get("/api/aliases?entity=xiao_yan")
        assert r.status_code == 200

    def test_list_state_changes(self, client):
        r = client.get("/api/state-changes")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_list_state_changes_by_entity(self, client):
        r = client.get("/api/state-changes?entity=xiao_yan")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 文件浏览 API
# ---------------------------------------------------------------------------

class TestFileBrowsing:
    def test_file_tree(self, client):
        r = client.get("/api/files/tree")
        assert r.status_code == 200
        data = r.json()
        assert "正文" in data
        assert "设定集" in data

    def test_file_read(self, client):
        r = client.get("/api/files/read?path=设定集/人物.md")
        assert r.status_code == 200
        assert "角色设定" in r.json()["content"]

    def test_file_read_forbidden_path(self, client):
        r = client.get("/api/files/read?path=../../../etc/passwd")
        assert r.status_code == 403

    def test_file_read_outside_allowed_dirs(self, client):
        r = client.get("/api/files/read?path=.ink/state.json")
        assert r.status_code == 403

    def test_file_read_not_found(self, client):
        r = client.get("/api/files/read?path=正文/不存在.md")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 扩展表（graceful fallback：表不存在时返回空列表）
# ---------------------------------------------------------------------------

class TestExtendedTables:
    def test_chapter_memory_cards_missing_table(self, client):
        r = client.get("/api/chapter-memory-cards")
        assert r.status_code == 200
        assert r.json() == []

    def test_plot_threads_missing_table(self, client):
        r = client.get("/api/plot-threads")
        assert r.status_code == 200

    def test_overrides_missing_table(self, client):
        r = client.get("/api/overrides")
        assert r.status_code == 200

    def test_debts_missing_table(self, client):
        r = client.get("/api/debts")
        assert r.status_code == 200

    def test_checklist_scores_missing_table(self, client):
        r = client.get("/api/checklist-scores")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_relationship_events_bad_range(self, client):
        r = client.get("/api/relationship-events?from_chapter=10&to_chapter=1")
        assert r.status_code == 400
