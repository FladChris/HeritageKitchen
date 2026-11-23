"""The two administrative whole-cookbook download endpoints."""

from fastapi import APIRouter, Response

from app.api.dependencies import DbSession, RequireAdmin
from app.services.cookbook_export_service import export_cookbook

router = APIRouter(prefix="/export", tags=["settings"])


@router.get("/zip", response_class=Response)
def export_cookbook_zip(db_session: DbSession, current_user: RequireAdmin) -> Response:
    return Response(
        export_cookbook(db_session, "zip"),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="heritagekitchen-cookbook.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/pdf", response_class=Response)
def export_cookbook_pdf(db_session: DbSession, current_user: RequireAdmin) -> Response:
    return Response(
        export_cookbook(db_session, "pdf"),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="heritagekitchen-cookbook.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
