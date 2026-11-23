from app.api.routes.auth_route import router as auth_router
from app.api.routes.category_route import router as categories_router
from app.api.routes.favorite_route import router as favorites_router
from app.api.routes.health_route import router as health_router
from app.api.routes.recipe_comment_route import router as recipe_comments_router
from app.api.routes.recipe_image_route import router as recipe_images_router
from app.api.routes.recipe_rating_route import router as recipe_ratings_router
from app.api.routes.recipe_route import router as recipes_router
from app.api.routes.settings_route import router as settings_router
from app.api.routes.user_route import router as users_router

__all__ = [
    "auth_router",
    "categories_router",
    "favorites_router",
    "health_router",
    "recipe_comments_router",
    "recipe_images_router",
    "recipe_ratings_router",
    "recipes_router",
    "settings_router",
    "users_router",
]
