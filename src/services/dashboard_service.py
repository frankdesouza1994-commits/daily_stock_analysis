# -*- coding: utf-8 -*-
"""Custom dashboard service.

A dashboard is a JSON document (title, description, ordered widgets) that both
the Web UI and external agents such as openclaw edit over the REST API. Every
write bumps ``version``; callers may pass ``expected_version`` to avoid
overwriting edits they have not seen.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.repositories.dashboard_repo import DashboardRepository
from src.storage import CustomDashboardRecord, DatabaseManager

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARD_SLUG = "default"
DEFAULT_DASHBOARD_TITLE = "My Dashboard"
MAX_WIDGETS = 50

WidgetType = Literal["markdown", "metric", "stock_list"]
WidgetWidth = Literal["sm", "md", "lg", "full"]
MetricTone = Literal["default", "primary", "success", "warning", "danger"]


class MarkdownWidgetData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field("", max_length=20000)


class MetricWidgetData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Union[str, int, float] = ""
    hint: Optional[str] = Field(None, max_length=200)
    tone: MetricTone = "default"


class StockListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=32)
    name: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=500)


class StockListWidgetData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[StockListItem] = Field(default_factory=list, max_length=100)


WIDGET_DATA_MODELS: Dict[str, type[BaseModel]] = {
    "markdown": MarkdownWidgetData,
    "metric": MetricWidgetData,
    "stock_list": StockListWidgetData,
}


class DashboardServiceError(ValueError):
    """Invalid dashboard request."""

    error_code = "validation_error"


class DashboardWidgetNotFoundError(DashboardServiceError):
    error_code = "not_found"


class DashboardVersionConflictError(DashboardServiceError):
    error_code = "version_conflict"

    def __init__(self, current_version: int):
        super().__init__(
            f"Dashboard was modified by another client (current version {current_version}); "
            "reload and retry"
        )
        self.current_version = current_version


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return "; ".join(parts) or str(exc)


class DashboardService:
    """Read and edit the custom dashboard document."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None, slug: str = DEFAULT_DASHBOARD_SLUG):
        self.repo = DashboardRepository(db_manager)
        self.slug = slug

    # ------------------------------------------------------------------ reads

    def get_dashboard(self) -> Dict[str, Any]:
        row = self.repo.get(self.slug)
        return self._to_payload(row)

    # ----------------------------------------------------------------- writes

    def replace_dashboard(
        self,
        payload: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self._load_for_write(expected_version)
        widgets = [self.normalize_widget(item) for item in payload.get("widgets") or []]
        self._check_widget_limits(widgets)
        document = {
            "title": payload.get("title") or DEFAULT_DASHBOARD_TITLE,
            "description": payload.get("description") or "",
            "widgets": widgets,
        }
        return self._save(document, current["version"], actor)

    def update_meta(
        self,
        payload: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self._load_for_write(expected_version)
        document = self._document_of(current)
        if payload.get("title") is not None:
            document["title"] = payload["title"] or DEFAULT_DASHBOARD_TITLE
        if payload.get("description") is not None:
            document["description"] = payload["description"]
        return self._save(document, current["version"], actor)

    def add_widget(
        self,
        payload: Dict[str, Any],
        *,
        position: Optional[int] = None,
        expected_version: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self._load_for_write(expected_version)
        document = self._document_of(current)
        widget = self.normalize_widget(payload)
        widgets = document["widgets"]
        if any(item["id"] == widget["id"] for item in widgets):
            raise DashboardServiceError(f"Widget id already exists: {widget['id']}")
        widgets.insert(self._clamp_position(position, len(widgets)), widget)
        self._check_widget_limits(widgets)
        return self._save(document, current["version"], actor)

    def update_widget(
        self,
        widget_id: str,
        payload: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Partially update a widget; ``data`` keys are shallow-merged into the existing data."""
        current = self._load_for_write(expected_version)
        document = self._document_of(current)
        widgets = document["widgets"]
        index = self._find_widget(widgets, widget_id)
        widget = dict(widgets[index])
        if payload.get("title") is not None:
            widget["title"] = payload["title"]
        if payload.get("width") is not None:
            widget["width"] = payload["width"]
        if payload.get("data") is not None:
            widget["data"] = {**(widget.get("data") or {}), **payload["data"]}
        widget = self.normalize_widget(widget)
        widgets.pop(index)
        position = payload.get("position")
        widgets.insert(index if position is None else self._clamp_position(position, len(widgets)), widget)
        return self._save(document, current["version"], actor)

    def delete_widget(
        self,
        widget_id: str,
        *,
        expected_version: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self._load_for_write(expected_version)
        document = self._document_of(current)
        widgets = document["widgets"]
        widgets.pop(self._find_widget(widgets, widget_id))
        return self._save(document, current["version"], actor)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def normalize_widget(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Validate one widget and return its canonical dict form."""
        if not isinstance(raw, dict):
            raise DashboardServiceError("Widget must be an object")
        widget_type = raw.get("type")
        data_model = WIDGET_DATA_MODELS.get(widget_type)  # type: ignore[arg-type]
        if data_model is None:
            raise DashboardServiceError(
                f"Unsupported widget type: {widget_type!r}; expected one of {sorted(WIDGET_DATA_MODELS)}"
            )
        width = raw.get("width") or "md"
        if width not in WidgetWidth.__args__:  # type: ignore[attr-defined]
            raise DashboardServiceError(f"Unsupported widget width: {width!r}")
        title = str(raw.get("title") or "").strip()
        if len(title) > 120:
            raise DashboardServiceError("Widget title must be at most 120 characters")
        widget_id = str(raw.get("id") or "").strip() or uuid.uuid4().hex[:12]
        if len(widget_id) > 64:
            raise DashboardServiceError("Widget id must be at most 64 characters")
        try:
            data = data_model.model_validate(raw.get("data") or {}).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise DashboardServiceError(f"Invalid {widget_type} widget data: {_format_validation_error(exc)}") from exc
        return {"id": widget_id, "type": widget_type, "title": title, "width": width, "data": data}

    @staticmethod
    def _check_widget_limits(widgets: List[Dict[str, Any]]) -> None:
        if len(widgets) > MAX_WIDGETS:
            raise DashboardServiceError(f"A dashboard holds at most {MAX_WIDGETS} widgets")
        ids = [item["id"] for item in widgets]
        if len(ids) != len(set(ids)):
            raise DashboardServiceError("Widget ids must be unique")

    @staticmethod
    def _clamp_position(position: Optional[int], length: int) -> int:
        if position is None:
            return length
        return max(0, min(int(position), length))

    @staticmethod
    def _find_widget(widgets: List[Dict[str, Any]], widget_id: str) -> int:
        for index, item in enumerate(widgets):
            if item.get("id") == widget_id:
                return index
        raise DashboardWidgetNotFoundError(f"Widget not found: {widget_id}")

    @staticmethod
    def _document_of(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": payload["title"],
            "description": payload["description"],
            "widgets": [dict(item) for item in payload["widgets"]],
        }

    def _load_for_write(self, expected_version: Optional[int]) -> Dict[str, Any]:
        current = self.get_dashboard()
        if expected_version is not None and expected_version != current["version"]:
            raise DashboardVersionConflictError(current["version"])
        return current

    def _save(self, document: Dict[str, Any], base_version: int, actor: Optional[str]) -> Dict[str, Any]:
        row = self.repo.save(
            self.slug,
            json.dumps(document, ensure_ascii=False),
            base_version=base_version,
            updated_by=(actor or "api")[:64],
        )
        if row is None:
            raise DashboardVersionConflictError(self.get_dashboard()["version"])
        return self._to_payload(row)

    def _to_payload(self, row: Optional[CustomDashboardRecord]) -> Dict[str, Any]:
        if row is None:
            return {
                "slug": self.slug,
                "title": DEFAULT_DASHBOARD_TITLE,
                "description": "",
                "widgets": [],
                "version": 0,
                "updated_by": None,
                "updated_at": None,
            }
        try:
            document = json.loads(row.document or "{}")
        except (TypeError, ValueError):
            logger.error("Stored dashboard %s is not valid JSON; returning empty widgets", row.slug)
            document = {}
        widgets: List[Dict[str, Any]] = []
        for item in document.get("widgets") or []:
            try:
                widgets.append(self.normalize_widget(item))
            except DashboardServiceError as exc:
                logger.warning("Skipping invalid stored dashboard widget: %s", exc)
        return {
            "slug": row.slug,
            "title": document.get("title") or DEFAULT_DASHBOARD_TITLE,
            "description": document.get("description") or "",
            "widgets": widgets,
            "version": int(row.version or 0),
            "updated_by": row.updated_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
