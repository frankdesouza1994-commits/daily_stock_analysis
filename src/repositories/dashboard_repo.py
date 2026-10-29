# -*- coding: utf-8 -*-
"""Custom dashboard repository.

Stores one JSON document per dashboard slug with an integer version used for
optimistic concurrency between the Web UI and external agents (openclaw).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.storage import CustomDashboardRecord, DatabaseManager


class DashboardRepository:
    """DB access layer for custom dashboard documents."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def get(self, slug: str) -> Optional[CustomDashboardRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(CustomDashboardRecord).where(CustomDashboardRecord.slug == slug).limit(1)
            ).scalar_one_or_none()

    def save(
        self,
        slug: str,
        document: str,
        *,
        base_version: int,
        updated_by: Optional[str],
    ) -> Optional[CustomDashboardRecord]:
        """Write ``document`` only if the stored version still equals ``base_version``.

        ``base_version == 0`` means the dashboard has never been saved. Returns
        the updated row, or ``None`` when another writer got there first.
        """
        now = datetime.now()
        with self.db.get_session() as session:
            if base_version == 0:
                exists = session.execute(
                    select(CustomDashboardRecord.id).where(CustomDashboardRecord.slug == slug).limit(1)
                ).scalar_one_or_none()
                if exists is not None:
                    return None
                row = CustomDashboardRecord(
                    slug=slug,
                    document=document,
                    version=1,
                    updated_by=updated_by,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    return None
                session.refresh(row)
                return row

            result = session.execute(
                update(CustomDashboardRecord)
                .where(
                    CustomDashboardRecord.slug == slug,
                    CustomDashboardRecord.version == base_version,
                )
                .values(
                    document=document,
                    version=base_version + 1,
                    updated_by=updated_by,
                    updated_at=now,
                )
            )
            session.commit()
            if not result.rowcount:
                return None
            return session.execute(
                select(CustomDashboardRecord).where(CustomDashboardRecord.slug == slug).limit(1)
            ).scalar_one_or_none()
