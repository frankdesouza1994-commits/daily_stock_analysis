# -*- coding: utf-8 -*-
"""Custom dashboard API endpoints.

Editable by the Web UI and by external agents such as openclaw.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.dashboard import (
    DashboardMetaUpdateRequest,
    DashboardReplaceRequest,
    DashboardResponse,
    DashboardWidgetCreateRequest,
    DashboardWidgetUpdateRequest,
)
from src.services.dashboard_service import (
    DashboardService,
    DashboardServiceError,
    DashboardVersionConflictError,
    DashboardWidgetNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_WRITE_RESPONSES = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}
_WRITE_OPTION_FIELDS = {"expected_version", "actor"}


def _to_http_error(exc: Exception, message: str) -> HTTPException:
    if isinstance(exc, DashboardVersionConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "error": exc.error_code,
                "message": str(exc),
                "detail": {"current_version": exc.current_version},
            },
        )
    if isinstance(exc, DashboardWidgetNotFoundError):
        return HTTPException(status_code=404, detail={"error": exc.error_code, "message": str(exc)})
    if isinstance(exc, DashboardServiceError):
        return HTTPException(status_code=400, detail={"error": exc.error_code, "message": str(exc)})
    logger.error("%s: %s", message, exc, exc_info=True)
    return HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": f"{message}: {str(exc)}"},
    )


@router.get(
    "",
    response_model=DashboardResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get the custom dashboard",
)
def get_dashboard() -> DashboardResponse:
    try:
        return DashboardResponse(**DashboardService().get_dashboard())
    except Exception as exc:
        raise _to_http_error(exc, "Load dashboard failed")


@router.put(
    "",
    response_model=DashboardResponse,
    responses=_WRITE_RESPONSES,
    summary="Replace the whole dashboard (title, description and ordered widgets)",
)
def replace_dashboard(request: DashboardReplaceRequest) -> DashboardResponse:
    try:
        return DashboardResponse(**DashboardService().replace_dashboard(
            request.model_dump(exclude=_WRITE_OPTION_FIELDS),
            expected_version=request.expected_version,
            actor=request.actor,
        ))
    except Exception as exc:
        raise _to_http_error(exc, "Replace dashboard failed")


@router.patch(
    "",
    response_model=DashboardResponse,
    responses=_WRITE_RESPONSES,
    summary="Update dashboard title or description",
)
def update_dashboard_meta(request: DashboardMetaUpdateRequest) -> DashboardResponse:
    try:
        return DashboardResponse(**DashboardService().update_meta(
            request.model_dump(exclude=_WRITE_OPTION_FIELDS),
            expected_version=request.expected_version,
            actor=request.actor,
        ))
    except Exception as exc:
        raise _to_http_error(exc, "Update dashboard failed")


@router.post(
    "/widgets",
    response_model=DashboardResponse,
    responses=_WRITE_RESPONSES,
    summary="Add a widget",
)
def add_widget(request: DashboardWidgetCreateRequest) -> DashboardResponse:
    try:
        return DashboardResponse(**DashboardService().add_widget(
            request.model_dump(exclude=_WRITE_OPTION_FIELDS | {"position"}),
            position=request.position,
            expected_version=request.expected_version,
            actor=request.actor,
        ))
    except Exception as exc:
        raise _to_http_error(exc, "Add dashboard widget failed")


@router.patch(
    "/widgets/{widget_id}",
    response_model=DashboardResponse,
    responses=_WRITE_RESPONSES,
    summary="Update a widget (data is shallow-merged)",
)
def update_widget(widget_id: str, request: DashboardWidgetUpdateRequest) -> DashboardResponse:
    try:
        return DashboardResponse(**DashboardService().update_widget(
            widget_id,
            request.model_dump(exclude=_WRITE_OPTION_FIELDS),
            expected_version=request.expected_version,
            actor=request.actor,
        ))
    except Exception as exc:
        raise _to_http_error(exc, "Update dashboard widget failed")


@router.delete(
    "/widgets/{widget_id}",
    response_model=DashboardResponse,
    responses=_WRITE_RESPONSES,
    summary="Delete a widget",
)
def delete_widget(
    widget_id: str,
    expected_version: Optional[int] = Query(None, ge=0),
    actor: Optional[str] = Query(None, max_length=64),
) -> DashboardResponse:
    try:
        return DashboardResponse(**DashboardService().delete_widget(
            widget_id,
            expected_version=expected_version,
            actor=actor,
        ))
    except Exception as exc:
        raise _to_http_error(exc, "Delete dashboard widget failed")
