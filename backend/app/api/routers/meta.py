"""Health and customer notification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.container import Services, get_services
from app.api.mappers import notification_out
from app.api.schemas.admin import NotificationOut
from app.infrastructure.persistence.models import User

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "alya-fiit-backend"}


@router.get("/notifications/mine", response_model=list[NotificationOut])
def my_notifications(
    user: User = Depends(get_current_user), services: Services = Depends(get_services)
) -> list[NotificationOut]:
    return [notification_out(n) for n in services.notifications_repo.list_recent()]
