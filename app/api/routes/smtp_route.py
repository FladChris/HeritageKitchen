from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.dependencies import DbSession, RequireAdmin
from app.api.schemas.smtp_schema import SmtpStatus, SmtpTestRequest, SmtpUpdate
from app.services import smtp_service


class SmtpRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                # The default 422 response can echo raw input, including credentials.
                raise HTTPException(
                    status_code=422,
                    detail="Bitte prüfe die Angaben für den SMTP-Versand.",
                ) from None

        return handle


router = APIRouter(prefix="/smtp", route_class=SmtpRoute)


@router.get("")
def get_smtp_settings(db_session: DbSession, current_user: RequireAdmin) -> SmtpStatus:
    return smtp_service.status(smtp_service.get_settings(db_session))


@router.put("")
def update_smtp_settings(
    request: SmtpUpdate, db_session: DbSession, current_user: RequireAdmin
) -> SmtpStatus:
    return smtp_service.update_settings(db_session, request, current_user.id)


@router.post("/test")
def send_test(
    request: SmtpTestRequest, db_session: DbSession, current_user: RequireAdmin
) -> SmtpStatus:
    if request.settings is not None:
        return smtp_service.test_draft(
            db_session, request.settings, request.recipient, current_user.id
        )
    return smtp_service.send_test(db_session, request.recipient)
