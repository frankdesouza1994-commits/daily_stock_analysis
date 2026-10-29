# -*- coding: utf-8 -*-
"""Contract tests for the editable custom dashboard API (Web UI + openclaw)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class DashboardApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "dashboard_api_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.client = TestClient(create_app(static_dir=self.data_dir / "empty-static"))

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()
        _reset_auth_globals()

    def test_empty_dashboard_has_version_zero(self) -> None:
        resp = self.client.get("/api/v1/dashboard")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["version"], 0)
        self.assertEqual(body["widgets"], [])
        self.assertIsNone(body["updated_by"])

    def test_widget_crud_bumps_version_and_records_actor(self) -> None:
        resp = self.client.post(
            "/api/v1/dashboard/widgets",
            json={
                "type": "metric",
                "title": "Watchlist P&L",
                "width": "sm",
                "data": {"value": "+3.2%", "tone": "success"},
                "actor": "openclaw",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["updated_by"], "openclaw")
        widget = body["widgets"][0]
        self.assertTrue(widget["id"])
        self.assertEqual(widget["data"], {"value": "+3.2%", "tone": "success"})

        resp = self.client.post(
            "/api/v1/dashboard/widgets",
            json={"id": "notes", "type": "markdown", "title": "Notes", "data": {"content": "# Hi"}, "position": 0},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual([w["id"] for w in resp.json()["widgets"]], ["notes", widget["id"]])

        # data is shallow-merged: tone is preserved while value changes; position moves the widget
        resp = self.client.patch(
            f"/api/v1/dashboard/widgets/{widget['id']}",
            json={"data": {"value": "+4.0%"}, "position": 0, "actor": "web"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["version"], 3)
        self.assertEqual(body["updated_by"], "web")
        self.assertEqual(body["widgets"][0]["id"], widget["id"])
        self.assertEqual(body["widgets"][0]["data"], {"value": "+4.0%", "tone": "success"})

        resp = self.client.delete("/api/v1/dashboard/widgets/notes")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual([w["id"] for w in resp.json()["widgets"]], [widget["id"]])

        resp = self.client.delete("/api/v1/dashboard/widgets/notes")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "not_found")

    def test_replace_dashboard_and_meta_update(self) -> None:
        resp = self.client.put(
            "/api/v1/dashboard",
            json={
                "title": "Morning board",
                "description": "Maintained by openclaw",
                "widgets": [
                    {"id": "picks", "type": "stock_list", "title": "Picks",
                     "data": {"items": [{"code": "600519", "name": "Moutai", "note": "hold"}, {"code": "AAPL"}]}},
                ],
                "expected_version": 0,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["title"], "Morning board")
        self.assertEqual(body["widgets"][0]["data"]["items"][1], {"code": "AAPL"})

        resp = self.client.patch("/api/v1/dashboard", json={"title": "Evening board"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["title"], "Evening board")
        self.assertEqual(resp.json()["description"], "Maintained by openclaw")
        self.assertEqual(len(self.client.get("/api/v1/dashboard").json()["widgets"]), 1)

    def test_stale_expected_version_is_rejected(self) -> None:
        self.client.post("/api/v1/dashboard/widgets", json={"type": "markdown", "data": {"content": "a"}})
        resp = self.client.post(
            "/api/v1/dashboard/widgets",
            json={"type": "markdown", "data": {"content": "b"}, "expected_version": 0},
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["error"], "version_conflict")
        self.assertEqual(resp.json()["detail"]["current_version"], 1)
        self.assertEqual(len(self.client.get("/api/v1/dashboard").json()["widgets"]), 1)

    def test_invalid_widget_data_is_rejected(self) -> None:
        resp = self.client.post(
            "/api/v1/dashboard/widgets",
            json={"type": "metric", "data": {"value": "1", "tone": "rainbow"}},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["error"], "validation_error")

        resp = self.client.post(
            "/api/v1/dashboard/widgets",
            json={"type": "stock_list", "data": {"items": [{"name": "missing code"}]}},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

        resp = self.client.post("/api/v1/dashboard/widgets", json={"id": "dup", "type": "markdown"})
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.post("/api/v1/dashboard/widgets", json={"id": "dup", "type": "markdown"})
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(self.client.get("/api/v1/dashboard").json()["version"], 1)


if __name__ == "__main__":
    unittest.main()
