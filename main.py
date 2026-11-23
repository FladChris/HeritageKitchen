import uvicorn

from app.core import settings


def run() -> None:
    uvicorn.run(
        "app.api:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
    )


if __name__ == "__main__":
    run()
