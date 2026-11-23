from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.dependencies import RequireAdmin
from app.api.routes.cookbook_export_route import router as export_router
from app.api.routes.smtp_route import router as smtp_router
from app.api.schemas.base_schema import BaseRequest
from app.core.db import get_db
from app.models.app_setting_model import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])
router.include_router(smtp_router)
router.include_router(export_router)
DbSession = Annotated[Session, Depends(get_db)]
DEFAULT_TAGLINE = "Unsere Rezepte, gesammelt und weitergegeben."
DEFAULT_COOKBOOK_NAME = "Heritage Kitchen"
DEFAULT_HOME_TITLE = "Lieblingsrezepte"
DEFAULTS = {
    "home_tagline": DEFAULT_TAGLINE,
    "cookbook_name": DEFAULT_COOKBOOK_NAME,
    "home_title": DEFAULT_HOME_TITLE,
    "footer_text": "",
}


class SettingsResponse(BaseModel):
    home_tagline: str
    cookbook_name: str
    home_title: str
    footer_text: str


class DatabaseInfoResponse(BaseModel):
    backend: str


@router.get("/database", response_model=DatabaseInfoResponse)
def get_database_info(
    db_session: DbSession,
    current_user: RequireAdmin,
) -> DatabaseInfoResponse:
    return DatabaseInfoResponse(backend=db_session.get_bind().dialect.name)


class SettingsUpdateRequest(BaseRequest):
    home_tagline: str | None = Field(default=None, max_length=200)
    cookbook_name: str | None = Field(default=None, min_length=1, max_length=100)
    home_title: str | None = Field(default=None, min_length=1, max_length=100)
    footer_text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def reject_explicit_null(self) -> "SettingsUpdateRequest":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


@router.get("", response_model=SettingsResponse)
def get_settings(db_session: DbSession) -> SettingsResponse:
    values = {}
    for key, default in DEFAULTS.items():
        setting = db_session.get(AppSetting, key)
        values[key] = setting.value if setting else default
    return SettingsResponse(**values)


@router.put("", response_model=SettingsResponse)
def update_settings(
    request: SettingsUpdateRequest,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> SettingsResponse:
    for key, value in request.model_dump(exclude_unset=True).items():
        setting = db_session.get(AppSetting, key)
        if value:
            if setting is None:
                db_session.add(AppSetting(key=key, value=value))
            else:
                setting.value = value
        elif setting is not None:
            db_session.delete(setting)
    db_session.commit()
    return get_settings(db_session)
