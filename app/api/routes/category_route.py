from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, RequireAdmin
from app.api.schemas import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.api.schemas.category_schema import CategoryOrderRequest
from app.core.db import get_db
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category",
    description="Creates a new category and returns the saved category data.",
)
def create_category(
    category_create_request: CategoryCreateRequest,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> CategoryResponse:
    return category_service.create_category(
        db_session=db_session,
        category_create_request=category_create_request,
    )


@router.get(
    "",
    response_model=list[CategoryResponse],
    summary="List categories",
    description="Returns categories by name with their current recipe counts.",
)
def list_categories(db_session: DbSession) -> list[CategoryResponse]:
    return category_service.list_categories(db_session=db_session)


@router.put(
    "/order",
    response_model=list[CategoryResponse],
    summary="Save and activate personal category order",
)
def set_category_order(
    request: CategoryOrderRequest,
    db_session: DbSession,
    current_user: CurrentUser,
    response: Response,
) -> list[CategoryResponse]:
    response.headers["Cache-Control"] = "no-store"
    return category_service.set_category_order(
        db_session=db_session, user=current_user, order=request
    )


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get category",
    description="Returns one category by its ID.",
)
def get_category(
    category_id: int,
    db_session: DbSession,
) -> CategoryResponse:
    return category_service.get_category(
        db_session=db_session,
        category_id=category_id,
    )


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update category",
    description="Updates one category by its ID and returns the updated data.",
)
def update_category(
    category_id: int,
    category_update_request: CategoryUpdateRequest,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> CategoryResponse:
    return category_service.update_category(
        db_session=db_session,
        category_id=category_id,
        category_update_request=category_update_request,
    )


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete category",
    description="Deletes one category by its ID.",
)
def delete_category(
    category_id: int,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> Response:
    category_service.delete_category(
        db_session=db_session,
        category_id=category_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{category_id}/image",
    response_model=CategoryResponse,
    summary="Set category image",
    description=(
        "Uploads an image (JPEG, PNG or WebP) for the category. "
        "It is resized and stored as JPEG, an older image is replaced."
    ),
)
def set_category_image(
    category_id: int,
    image: Annotated[UploadFile, File(description="Image file, max 20 MB.")],
    db_session: DbSession,
    current_user: RequireAdmin,
) -> CategoryResponse:
    return category_service.set_category_image(
        db_session=db_session, category_id=category_id, image=image
    )


@router.delete(
    "/{category_id}/image",
    response_model=CategoryResponse,
    summary="Remove category image",
    description="Removes the image of the category.",
)
def remove_category_image(
    category_id: int,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> CategoryResponse:
    return category_service.remove_category_image(
        db_session=db_session, category_id=category_id
    )
