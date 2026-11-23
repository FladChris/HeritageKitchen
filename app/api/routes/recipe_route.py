from decimal import Decimal
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import (
    CurrentUser,
    ExpectedRecipeVersion,
    OptionalUser,
    RequireEditor,
)
from app.api.schemas import (
    RecipeCreateRequest,
    RecipeImageOrderRequest,
    RecipeImageResponse,
    RecipeListResponse,
    RecipeResponse,
    RecipeUpdateRequest,
)
from app.api.schemas.recipe_image_schema import RecipeImageAltText
from app.api.schemas.recipe_order_schema import RecipeOrderRequest
from app.core.db import get_db
from app.services import (
    recipe_image_service,
    recipe_order_service,
    recipe_service,
)

router = APIRouter(prefix="/recipes", tags=["recipes"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=RecipeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create recipe",
    description="Creates a new recipe and returns the saved recipe data.",
)
def create_recipe(
    recipe_create_request: RecipeCreateRequest,
    db_session: DbSession,
    current_user: RequireEditor,
) -> RecipeResponse:
    return recipe_service.create_recipe(
        db_session=db_session,
        recipe_create_request=recipe_create_request,
    )


@router.get(
    "",
    response_model=RecipeListResponse,
    summary="List recipes",
    description="Returns a searchable, paginated list of recipes.",
)
def list_recipes(
    db_session: DbSession,
    search: str | None = Query(default=None, min_length=1, max_length=150),
    category_id: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: Literal["title", "newest", "manual"] = "title",
    summary: bool = False,
    current_user: OptionalUser = None,
) -> RecipeListResponse:
    if sort == "manual" and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Personal order requires a login."
        )
    if sort == "manual" and category_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Personal order requires a category.",
        )
    return recipe_service.list_recipes(
        db_session=db_session,
        search=search,
        category_id=category_id,
        page=page,
        page_size=page_size,
        sort=sort,
        summary=summary,
        user=current_user,
    )


@router.put(
    "/order",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Save personal recipe order",
    description="Stores the signed-in user's recipe order for one category.",
)
def set_recipe_order(
    request: RecipeOrderRequest, db_session: DbSession, current_user: CurrentUser
) -> Response:
    recipe_order_service.set_recipe_order(db_session=db_session, user=current_user, order=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})


@router.get(
    "/{recipe_id}",
    response_model=RecipeResponse,
    summary="Get recipe",
    description="Returns one recipe by its ID.",
)
def get_recipe(
    recipe_id: int,
    db_session: DbSession,
    response: Response,
) -> RecipeResponse:
    recipe = recipe_service.get_recipe(db_session=db_session, recipe_id=recipe_id)
    response.headers["ETag"] = f'"{recipe.version}"'
    response.headers["Cache-Control"] = "no-store"
    return recipe


@router.put(
    "/{recipe_id}",
    response_model=RecipeResponse,
    summary="Update recipe",
    description="Updates one recipe by its ID and returns the updated data.",
)
def update_recipe(
    recipe_id: int,
    recipe_update_request: RecipeUpdateRequest,
    db_session: DbSession,
    current_user: RequireEditor,
    response: Response,
    expected_version: ExpectedRecipeVersion,
) -> RecipeResponse:
    recipe = recipe_service.update_recipe(
        db_session=db_session,
        recipe_id=recipe_id,
        recipe_update_request=recipe_update_request,
        expected_version=expected_version,
    )
    response.headers["ETag"] = f'"{recipe.version}"'
    response.headers["Cache-Control"] = "no-store"
    return recipe


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete recipe",
    description="Deletes one recipe by its ID.",
)
def delete_recipe(
    recipe_id: int,
    db_session: DbSession,
    current_user: RequireEditor,
) -> Response:
    recipe_service.delete_recipe(
        db_session=db_session,
        recipe_id=recipe_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{recipe_id}/images",
    response_model=RecipeImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload recipe image",
    description="Uploads a new image for a recipe and returns the saved image data.",
)
def create_recipe_image(
    recipe_id: int,
    db_session: DbSession,
    current_user: RequireEditor,
    image: Annotated[
        UploadFile,
        File(
            description=(
                "Image file (JPEG, PNG or WebP, max 20 MB). "
                "Automatically resized and re-encoded as JPEG on the server."
            )
        ),
    ],
    response: Response,
    expected_version: ExpectedRecipeVersion,
    alt_text: Annotated[RecipeImageAltText, Form()] = None,
) -> RecipeImageResponse:
    result = recipe_image_service.create_recipe_image(
        db_session=db_session,
        recipe_id=recipe_id,
        image=image,
        alt_text=alt_text,
        expected_version=expected_version,
    )
    recipe_image_service.apply_version_headers(db_session, response)
    return result


@router.put(
    "/{recipe_id}/images/order",
    response_model=list[RecipeImageResponse],
    summary="Reorder recipe images",
    description="Stores a new gallery order; the IDs must be exactly the images of the recipe.",
)
def reorder_recipe_images(
    recipe_id: int,
    recipe_image_order_request: RecipeImageOrderRequest,
    db_session: DbSession,
    current_user: RequireEditor,
    response: Response,
    expected_version: ExpectedRecipeVersion,
) -> list[RecipeImageResponse]:
    result = recipe_image_service.reorder_recipe_images(
        db_session=db_session,
        recipe_id=recipe_id,
        image_ids=recipe_image_order_request.image_ids,
        expected_version=expected_version,
    )
    recipe_image_service.apply_version_headers(db_session, response)
    return result


@router.get(
    "/{recipe_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def export_recipe_pdf(
    recipe_id: int,
    db_session: DbSession,
    factor: Annotated[Decimal, Query(gt=0, le=1000, max_digits=7, decimal_places=4)] = Decimal(1),
) -> Response:
    from app.services.recipe_pdf_service import pdf_filename, render_recipe_pdf

    recipe = recipe_service.get_recipe(db_session=db_session, recipe_id=recipe_id)
    return Response(
        content=render_recipe_pdf(recipe, factor=factor),
        media_type="application/pdf",
        headers={"Content-Disposition": pdf_filename(recipe.title), "Cache-Control": "no-store"},
    )
