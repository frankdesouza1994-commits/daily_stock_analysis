# -*- coding: utf-8 -*-
"""Custom dashboard API schemas.

Widget ``data`` is validated per ``type`` by ``src.services.dashboard_service``:

- ``markdown``: ``{"content": "..."}``
- ``metric``: ``{"value": "12.3%", "hint": "...", "tone": "default|primary|success|warning|danger"}``
- ``stock_list``: ``{"items": [{"code": "600519", "name": "...", "note": "..."}]}``
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

WidgetTypeValue = Literal["markdown", "metric", "stock_list"]
WidgetWidthValue = Literal["sm", "md", "lg", "full"]


class DashboardWidget(BaseModel):
    id: str
    type: WidgetTypeValue
    title: str = ""
    width: WidgetWidthValue = "md"
    data: Dict[str, Any] = Field(default_factory=dict)


class DashboardWidgetInput(BaseModel):
    id: Optional[str] = Field(None, max_length=64, description="Omit to let the server generate one")
    type: WidgetTypeValue
    title: str = Field("", max_length=120)
    width: WidgetWidthValue = "md"
    data: Dict[str, Any] = Field(default_factory=dict)


class DashboardWriteOptions(BaseModel):
    expected_version: Optional[int] = Field(
        None,
        ge=0,
        description="If set, the write is rejected with 409 when the stored version differs",
    )
    actor: Optional[str] = Field(None, max_length=64, description="Who made the change, e.g. openclaw or web")


class DashboardReplaceRequest(DashboardWriteOptions):
    title: str = Field("", max_length=120)
    description: str = Field("", max_length=2000)
    widgets: List[DashboardWidgetInput] = Field(default_factory=list)


class DashboardMetaUpdateRequest(DashboardWriteOptions):
    title: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)


class DashboardWidgetCreateRequest(DashboardWriteOptions, DashboardWidgetInput):
    position: Optional[int] = Field(None, ge=0, description="Insert index; omit to append")


class DashboardWidgetUpdateRequest(DashboardWriteOptions):
    title: Optional[str] = Field(None, max_length=120)
    width: Optional[WidgetWidthValue] = None
    data: Optional[Dict[str, Any]] = Field(None, description="Shallow-merged into the existing widget data")
    position: Optional[int] = Field(None, ge=0, description="Move the widget to this index")


class DashboardResponse(BaseModel):
    slug: str
    title: str
    description: str = ""
    widgets: List[DashboardWidget] = Field(default_factory=list)
    version: int = Field(..., description="0 until the dashboard is first saved")
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None
