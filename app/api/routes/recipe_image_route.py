from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import ExpectedRecipeVersion, RequireEditor
from app.api.schemas import RecipeImageResponse, RecipeImageUpdateRequest
from app.core.db import get_db
from app.services import recipe_image_service

DbSession = Annotated[Session, Depends(get_db)]
router = APIRouter(prefix="/recipe-images", tags=["recipe_images"])


@router.get(
    "",
    response_model=list[RecipeImageResponse],
    summary="List recipe images",
    description="Returns all recipe images.",
)
def list_recipe_images(
    db_session: DbSession,
) -> list[RecipeImageResponse]:
    return recipe_image_service.list_recipe_images(db_session=db_session)


@router.get(
    "/{recipe_image_id}",
    response_model=RecipeImageResponse,
    summary="Get recipe image",
    description="Returns one recipe image by its ID.",
)
def get_recipe_image(
    recipe_image_id: int,
    db_session: DbSession,
) -> RecipeImageResponse:
    return recipe_image_service.get_recipe_image(
        db_session=db_session,
        recipe_image_id=recipe_image_id,
    )


@router.put(
    "/{recipe_image_id}",
    response_model=RecipeImageResponse,
    summary="Update recipe image",
    description="Updates the alt text or main image flag of one recipe image by its ID.",
)
def update_recipe_image(
    recipe_image_id: int,
    recipe_image_update_request: RecipeImageUpdateRequest,
    db_session: DbSession,
    current_user: RequireEditor,
    response: Response,
    expected_version: ExpectedRecipeVersion,
) -> RecipeImageResponse:
    result = recipe_image_service.update_recipe_image(
        db_session=db_session,
        recipe_image_id=recipe_image_id,
        recipe_image_update_request=recipe_image_update_request,
        expected_version=expected_version,
    )
    recipe_image_service.apply_version_headers(db_session, response)
    return result


@router.put("/{recipe_image_id}/crop")
def crop_recipe_image(
    recipe_image_id: int, db_session: DbSession, current_user: RequireEditor,
    image: Annotated[UploadFile, File()], response: Response,
    expected_version: ExpectedRecipeVersion,
) -> RecipeImageResponse:
    result = recipe_image_service.crop_recipe_image(
        db_session=db_session, recipe_image_id=recipe_image_id, image=image,
        expected_version=expected_version,
    )
    recipe_image_service.apply_version_headers(db_session, response)
    return result


@router.delete(
    "/{recipe_image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete recipe image",
    description="Deletes one recipe image by its ID.",
)
def delete_recipe_image(
    recipe_image_id: int,
    db_session: DbSession,
    current_user: RequireEditor,
    expected_version: ExpectedRecipeVersion,
) -> Response:
    recipe_image_service.delete_recipe_image(
        db_session=db_session,
        recipe_image_id=recipe_image_id,
        expected_version=expected_version,
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    recipe_image_service.apply_version_headers(db_session, response)
    return response
