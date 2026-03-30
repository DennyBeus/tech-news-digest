#!/usr/bin/env python3
"""Tests for database storage layer.

These tests mock psycopg2 to verify SQL logic without a real Postgres instance.

Run: python -m unittest tests/test_db.py -v
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Import store-merged as module
import importlib.util
spec = importlib.util.spec_from_file_location("store_merged", SCRIPTS_DIR / "store-merged.py")
store_mod = importlib.util.module_from_spec(spec)
# Mock psycopg2 before loading the module
sys.modules["psycopg2"] = MagicMock()
sys.modules["psycopg2.extras"] = MagicMock()
spec.loader.exec_module(store_mod)


class TestNormalizeUrl(unittest.TestCase):
    """Test URL normalization (same logic as merge-sources.py)."""

    def test_strips_www(self):
        self.assertEqual(store_mod.normalize_url("https://www.example.com/article"),
                         "example.com/article")

    def test_strips_trailing_slash(self):
        self.assertEqual(store_mod.normalize_url("https://example.com/article/"),
                         "example.com/article")

    def test_strips_query_params(self):
        self.assertEqual(store_mod.normalize_url("https://example.com/article?utm_source=twitter"),
                         "example.com/article")

    def test_lowercases_domain(self):
        self.assertEqual(store_mod.normalize_url("https://EXAMPLE.COM/Article"),
                         "example.com/Article")

    def test_handles_empty(self):
        self.assertEqual(store_mod.normalize_url(""), "")


class TestStoreArticles(unittest.TestCase):
    """Test article storage logic with mocked DB."""

    def setUp(self):
        self.merged_path = FIXTURES_DIR / "merged.json"
        if self.merged_path.exists():
            with open(self.merged_path, "r", encoding="utf-8") as f:
                self.merged_data = json.load(f)
        else:
            self.merged_data = {
                "topics": {
                    "ai": {
                        "count": 1,
                        "articles": [{
                            "title": "Test Article",
                            "link": "https://example.com/test",
                            "date": "2026-03-25T10:00:00+00:00",
                            "source_type": "rss",
                            "source_id": "test-rss",
                            "source_name": "Test",
                            "quality_score": 10.0,
                            "primary_topic": "ai",
                            "topics": ["ai"],
                        }]
                    }
                }
            }

    def test_store_articles_returns_count(self):
        """store_articles should return the number of articles processed."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        count = store_mod.store_articles(mock_conn, 1, self.merged_data)
        self.assertGreater(count, 0)

    def test_store_articles_empty_input(self):
        """store_articles with empty data should return 0."""
        mock_conn = MagicMock()
        count = store_mod.store_articles(mock_conn, 1, {"topics": {}})
        self.assertEqual(count, 0)

    def test_update_seen_urls_processes_all(self):
        """update_seen_urls should process all articles from all topics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store_mod.update_seen_urls(mock_conn, self.merged_data)
        mock_conn.commit.assert_called()

    def test_update_seen_urls_empty_input(self):
        """update_seen_urls with empty data should not commit."""
        mock_conn = MagicMock()
        store_mod.update_seen_urls(mock_conn, {"topics": {}})
        mock_conn.commit.assert_not_called()


class TestMergedFixtureStructure(unittest.TestCase):
    """Verify the merged fixture has expected structure for DB storage."""

    def setUp(self):
        merged_path = FIXTURES_DIR / "merged.json"
        if not merged_path.exists():
            self.skipTest("merged.json fixture not found")
        with open(merged_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_has_topics(self):
        self.assertIn("topics", self.data)
        self.assertGreater(len(self.data["topics"]), 0)

    def test_articles_have_required_fields(self):
        """All articles should have fields needed for DB insertion."""
        required = {"title", "link", "source_type", "quality_score"}
        for topic, topic_data in self.data["topics"].items():
            for article in topic_data.get("articles", []):
                for field in required:
                    self.assertIn(field, article,
                                  f"Article in {topic} missing '{field}': {article.get('title', '?')}")

    def test_articles_have_numeric_score(self):
        for topic_data in self.data["topics"].values():
            for article in topic_data.get("articles", []):
                self.assertIsInstance(article["quality_score"], (int, float))


class TestMigrateModule(unittest.TestCase):
    """Test db/migrate.py helpers."""

    def test_migrations_dir_exists(self):
        migrations_dir = Path(__file__).parent.parent / "db" / "migrations"
        self.assertTrue(migrations_dir.exists(), "db/migrations/ directory should exist")

    def test_initial_migration_exists(self):
        migration = Path(__file__).parent.parent / "db" / "migrations" / "001_initial.sql"
        self.assertTrue(migration.exists(), "001_initial.sql should exist")

    def test_initial_migration_has_tables(self):
        migration = Path(__file__).parent.parent / "db" / "migrations" / "001_initial.sql"
        content = migration.read_text()
        self.assertIn("CREATE TABLE pipeline_runs", content)
        self.assertIn("CREATE TABLE articles", content)
        self.assertIn("CREATE TABLE seen_urls", content)


if __name__ == "__main__":
    unittest.main()
