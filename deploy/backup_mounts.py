"""Resolve backup sources from Docker metadata, rejecting unsupported layouts."""

import json
import os
from pathlib import Path, PurePosixPath


def resolve_sources(database_url, mounts):
    def source_for(destination):
        matches = [m for m in mounts if m.get("Destination") == destination]
        if len(matches) != 1 or matches[0].get("Type") != "bind":
            raise ValueError(f"Expected exactly one bind mount at {destination}")
        # Nested mounts can hide files from the parent host directory.
        if any(m.get("Destination", "").startswith(destination + "/") for m in mounts):
            raise ValueError(f"Nested mounts at {destination} are unsupported")
        source = Path(matches[0]["Source"])
        if not source.is_absolute() or not source.is_dir():
            raise ValueError(f"Missing absolute host directory for {destination}")
        return source.resolve()

    images = source_for("/app/recipe-images")
    if database_url.startswith("sqlite:////data/"):
        data = source_for("/data")
        relative = PurePosixPath(database_url.removeprefix("sqlite:////data/"))
        if ".." in relative.parts or relative.is_absolute():
            raise ValueError("Unsafe SQLite path")
        database = (data / relative).resolve()
        if not database.is_relative_to(data) or not database.is_file():
            raise ValueError("SQLite database is missing or outside its bind mount")
        database_url = "sqlite:///" + str(database)
    elif not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("Unsupported database URL; use the Python backup CLI")
    if any(c in database_url + str(images) for c in "\r\n"):
        raise ValueError("Backup source must not contain line breaks")
    return database_url, str(images)


if __name__ == "__main__":
    try:
        print("\n".join(resolve_sources(
            os.environ["CONTAINER_DATABASE_URL"], json.loads(os.environ["CONTAINER_MOUNTS"])
        )))
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Cannot resolve container backup sources: {exc}") from exc
