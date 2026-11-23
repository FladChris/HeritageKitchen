import unicodedata

from fastapi import HTTPException, status
from sqlalchemy import (
    JSON,
    String,
    case,
    cast,
    column,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, load_only, selectinload
from sqlalchemy.sql.expression import FunctionElement

from app.api.schemas import (
    RecipeCreateRequest,
    RecipeListResponse,
    RecipeResponse,
    RecipeUpdateRequest,
)
from app.api.schemas.recipe_schema import (
    OtherCategoryHit,
    RecipeSummaryResponse,
    StepTimesResponse,
)
from app.models.category_model import Category
from app.models.recipe_comment_model import RecipeComment
from app.models.recipe_model import (
    Recipe,
    RecipeIngredient,
    RecipeIngredientGroup,
    RecipeStep,
)
from app.models.user_model import User, UserRecipePosition
from app.services import recipe_image_storage, recipe_lock_service, recipe_order_service
from app.services.category_service import require_category_for_assignment


# SQLite lower() only handles ASCII, so case, umlauts and accents are folded by replace() for
# every Latin letter with a diacritic; the search term uses the same table.
def _build_fold_table() -> dict[str, str]:
    table = {"ß": "ss", "ẞ": "ss"}
    for code in range(0xC0, 0x180):
        char = chr(code)
        base = "".join(
            part for part in unicodedata.normalize("NFD", char) if not unicodedata.combining(part)
        ).lower()
        if base != char.lower() and base.isascii():
            table[char] = base
    return table


_FOLD_TABLE = _build_fold_table()
# Umlaut spellings ("kaese") fold like the umlaut ("käse" -> "kase"), as for category names.
_SPELLING_FOLDS = (("ae", "a"), ("oe", "o"), ("ue", "u"))


def _fold_term(term: str) -> str:
    folded = "".join(_FOLD_TABLE.get(char, char) for char in term).lower()
    for spelling, replacement in _SPELLING_FOLDS:
        folded = folded.replace(spelling, replacement)
    return folded


class _fold_text(FunctionElement):
    """Lower-cased text with the fold table applied."""

    type = String()
    inherit_cache = True


@compiles(_fold_text)
def _compile_fold_text(element, compiler, **kw):
    # Rendered as a flat string: nesting one func.replace per character exceeds the recursion limit.
    sql = f"lower({compiler.process(element.clauses, **kw)})"
    for char, replacement in _FOLD_TABLE.items():
        sql = f"replace({sql}, '{char}', '{replacement}')"
    for spelling, replacement in _SPELLING_FOLDS:
        sql = f"replace({sql}, '{spelling}', '{replacement}')"
    return sql


def _fold_column(column, dialect_name: str):
    if dialect_name == "postgresql":
        # PostgreSQL ILIKE-style matching requires a deterministic collation.
        column = column.collate("default")
    return _fold_text(column)


def _search_filters(search_term: str, dialect_name: str):
    term = _fold_term(search_term)

    def matches(column):
        return _fold_column(column, dialect_name).contains(term, autoescape=True)

    title = matches(Recipe.title)
    ingredient = or_(
        exists().where(
            RecipeIngredient.recipe_id == Recipe.id,
            or_(matches(RecipeIngredient.name), matches(RecipeIngredient.note)),
        ),
        exists().where(
            RecipeIngredientGroup.recipe_id == Recipe.id, matches(RecipeIngredientGroup.name)
        ),
    )
    day_titles = _day_titles(dialect_name)
    other = or_(
        *(matches(column) for column in (
            Recipe.summary, Recipe.origin_person, Recipe.history, Recipe.notes, Recipe.important_notes,
        )),
        exists().where(
            RecipeStep.recipe_id == Recipe.id,
            or_(matches(RecipeStep.instruction), matches(RecipeStep.heading), matches(RecipeStep.note)),
        ),
        exists().where(RecipeComment.recipe_id == Recipe.id, matches(RecipeComment.text)),
        exists(select(1).select_from(day_titles).where(matches(day_titles.c.value))),
    )
    return title, ingredient, other


def _day_titles(dialect_name: str):
    """Rows of the recipe's optional day titles, stored as a JSON list."""
    value = column("value", String)
    if dialect_name == "postgresql":
        # A missing list may be stored as JSON null, which cannot be expanded.
        titles = case(
            (func.json_typeof(Recipe.day_titles) == "array", Recipe.day_titles),
            else_=cast(literal("[]"), JSON),
        )
        return func.json_array_elements_text(titles).table_valued(value).render_derived()
    return func.json_each(Recipe.day_titles).table_valued(value)


def make_ingredients(items, groups):
    by_position = {group.position: group for group in groups}
    return [
        RecipeIngredient(
            position=item.position, name=item.name,
            amount=item.amount, unit=item.unit,
            note=item.note,
            group=by_position.get(item.group_position),
        )
        for item in items
    ]


def _validate_days(days: int, step_days: list[int], titles: list[str] | None) -> None:
    if any(day > days for day in step_days):
        raise HTTPException(422, "Assign every step to one of the remaining preparation days.")
    if titles is not None and len(titles) > days:
        raise HTTPException(422, "Remove the titles of removed preparation days.")


def create_recipe(
    *,
    db_session: Session,
    recipe_create_request: RecipeCreateRequest,
) -> RecipeResponse:
    create_data = recipe_create_request.model_dump(exclude={"ingredients", "ingredient_groups", "steps"})
    _validate_days(
        recipe_create_request.preparation_days, [step.day for step in recipe_create_request.steps],
        recipe_create_request.day_titles,
    )
    require_category_for_assignment(db_session, recipe_create_request.category_id)

    groups = [RecipeIngredientGroup(**group.model_dump()) for group in recipe_create_request.ingredient_groups]
    recipe = Recipe(
        **create_data,
        ingredient_groups=groups,
        ingredients=make_ingredients(recipe_create_request.ingredients, groups),
        steps=[
            RecipeStep(**step.model_dump()) for step in recipe_create_request.steps
        ],
    )
    db_session.add(recipe)
    return _save_recipe(db_session, recipe, previous_category_id=None)


def list_recipes(
    *,
    db_session: Session,
    search: str | None,
    category_id: int | None,
    page: int,
    page_size: int,
    sort: str = "title",
    summary: bool = False,
    user: User | None = None,
) -> RecipeListResponse:
    search_term = search.strip() if search else None
    count_statement = select(func.count(Recipe.id))
    recipe_statement = select(Recipe).options(
        selectinload(Recipe.category),
        selectinload(Recipe.images),
    )
    if summary:
        recipe_statement = recipe_statement.add_columns(*(
            select(func.sum(RecipeStep.duration_minutes))
            .where(RecipeStep.recipe_id == Recipe.id, RecipeStep.time_kind == kind)
            .scalar_subquery().label(kind)
            for kind in ("preparation", "cooking", "rest")
        )).options(load_only(
            Recipe.id, Recipe.title, Recipe.summary, Recipe.origin_person,
            Recipe.preparation_days, Recipe.preparation_time, Recipe.cooking_time,
            Recipe.cooking_time_max, Recipe.rest_time, Recipe.rest_time_max,
            Recipe.servings, Recipe.category_id, Recipe.created_at, Recipe.updated_at, Recipe.version,
        ))
    else:
        recipe_statement = recipe_statement.options(
            selectinload(Recipe.ingredients).selectinload(RecipeIngredient.group),
            selectinload(Recipe.ingredient_groups),
            selectinload(Recipe.steps),
        )

    if category_id is not None:
        count_statement = count_statement.where(Recipe.category_id == category_id)
        recipe_statement = recipe_statement.where(Recipe.category_id == category_id)

    dialect_name = db_session.get_bind().dialect.name
    relevance = []
    other_categories = []
    if search_term:
        title_match, ingredient_match, other_match = _search_filters(search_term, dialect_name)
        search_filter = or_(title_match, ingredient_match, other_match)
        count_statement = count_statement.where(search_filter)
        recipe_statement = recipe_statement.where(search_filter)
        # Title matches come before ingredient matches, those before matches in the remaining texts.
        relevance = [case((title_match, 0), (ingredient_match, 1), else_=2)]

    total = db_session.scalar(count_statement) or 0
    title_key = _fold_column(Recipe.title, dialect_name)
    if dialect_name == "postgresql":
        title_key = title_key.collate("C")
    if sort == "newest":
        ordering = (Recipe.created_at.desc(), Recipe.id.desc())
    elif sort == "manual" and user is not None:
        recipe_statement = recipe_statement.outerjoin(
            UserRecipePosition,
            (UserRecipePosition.recipe_id == Recipe.id) & (UserRecipePosition.user_id == user.id),
        )
        ordering = (
            UserRecipePosition.position.is_(None), UserRecipePosition.position,
            title_key, Recipe.created_at, Recipe.id,
        )
    else:
        ordering = (title_key, Recipe.created_at, Recipe.id)
    rows = db_session.execute(
        recipe_statement.order_by(*relevance, *ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if summary:
        items = [
            RecipeSummaryResponse.model_validate(recipe).model_copy(update={
                "step_times": StepTimesResponse(preparation=preparation, cooking=cooking, rest=rest),
            })
            for recipe, preparation, cooking, rest in rows
        ]
    else:
        items = [RecipeResponse.model_validate(row[0]) for row in rows]

    if search_term and category_id is not None and total == 0:
        other_categories = [
            OtherCategoryHit(id=row.id, name=row.name, count=row.count)
            for row in db_session.execute(
                select(Category.id, Category.name, func.count(Recipe.id).label("count"))
                .join(Recipe, Recipe.category_id == Category.id)
                .where(search_filter, Category.id != category_id)
                .group_by(Category.id, Category.name)
                .order_by(Category.name, Category.id)
            )
        ]

    return RecipeListResponse(
        items=items,
        total=total,
        other_categories=other_categories,
        page=page,
        page_size=page_size,
    )


def get_recipe(*, db_session: Session, recipe_id: int) -> RecipeResponse:
    statement = (
        select(Recipe)
        .options(
            selectinload(Recipe.category),
            selectinload(Recipe.images),
            selectinload(Recipe.ingredient_groups),
            selectinload(Recipe.ingredients).selectinload(RecipeIngredient.group),
            selectinload(Recipe.steps),
        )
        .where(Recipe.id == recipe_id)
        .execution_options(populate_existing=True)
    )
    connection = db_session.connection()
    # The eager loaders issue separate SELECTs. Start a SQLite read snapshot
    # explicitly, or hold a shared row lock against PostgreSQL recipe writers.
    if connection.dialect.name == "sqlite":
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
    elif connection.dialect.name == "postgresql":
        statement = statement.with_for_update(read=True, of=Recipe)
    recipe = db_session.scalar(statement)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found.")
    return RecipeResponse.model_validate(recipe)


def update_recipe(
    *,
    db_session: Session,
    recipe_id: int,
    recipe_update_request: RecipeUpdateRequest,
    expected_version: int,
) -> RecipeResponse:
    # SQLite acquires BEGIN IMMEDIATE and PostgreSQL uses a row write lock.
    recipe = recipe_lock_service.lock_recipe(
        db_session, recipe_id, not_found="Recipe deleted while editing."
    )
    recipe_lock_service.require_recipe_version(db_session, recipe, expected_version)
    previous_category_id = recipe.category_id
    update_data = recipe_update_request.model_dump(
        exclude_unset=True,
        exclude={"ingredients", "ingredient_groups", "steps"},
    )
    if "category_id" in update_data:
        require_category_for_assignment(db_session, update_data["category_id"], sqlite_locked=True)

    _validate_days(
        update_data.get("preparation_days", recipe.preparation_days),
        [step.day for step in (recipe_update_request.steps if recipe_update_request.steps is not None else recipe.steps)],
        update_data.get("day_titles", recipe.day_titles),
    )

    for field_name, field_value in update_data.items():
        setattr(recipe, field_name, field_value)

    if recipe_update_request.ingredient_groups is not None:
        groups = [
            RecipeIngredientGroup(**group.model_dump())
            for group in recipe_update_request.ingredient_groups
        ]
        with db_session.no_autoflush:
            if recipe_update_request.ingredients is None:
                groups_by_position = {group.position: group for group in groups}
                for ingredient in recipe.ingredients:
                    ingredient.group = groups_by_position.get(ingredient.group_position)
            recipe.ingredient_groups = groups

    if recipe_update_request.ingredients is not None:
        groups = recipe.ingredient_groups
        positions = {group.position for group in groups}
        if any(item.group_position is not None and item.group_position not in positions for item in recipe_update_request.ingredients):
            raise HTTPException(status_code=422, detail="Ingredient group does not exist.")
        with db_session.no_autoflush:
            recipe.ingredients = make_ingredients(recipe_update_request.ingredients, groups)

    if recipe_update_request.steps is not None:
        recipe.steps = [
            RecipeStep(**step.model_dump()) for step in recipe_update_request.steps
        ]

    recipe.version += 1
    return _save_recipe(db_session, recipe, previous_category_id=previous_category_id)


def _save_recipe(
    db_session: Session, recipe: Recipe, *, previous_category_id: int | None,
) -> RecipeResponse:
    db_session.flush()
    if recipe.category_id != previous_category_id:
        recipe_order_service.place_recipe_last(db_session, recipe.id, recipe.category_id)
    db_session.expire(recipe, ["category", "images", "ingredients", "ingredient_groups", "steps"])
    response = RecipeResponse.model_validate(recipe)
    db_session.commit()
    return response


def delete_recipe(*, db_session: Session, recipe_id: int) -> None:
    recipe = recipe_lock_service.lock_recipe(db_session, recipe_id)
    queued = recipe_image_storage.queue_recipe_file_deletions(
        db_session, recipe_id, {image.file_path for image in recipe.images},
    )
    recipe_order_service.place_recipe_last(db_session, recipe_id, None)
    db_session.delete(recipe)
    db_session.commit()
    if queued:
        recipe_image_storage.retry_recipe_file_deletions(db_session.get_bind().engine, recipe_id)
