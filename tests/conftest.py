"""Revision-aware client behavior for tests written before If-Match became mandatory.

Older route tests cover validation, roles and recipe content rather than concurrency.
Keep those requests conditional, just as the Svelte client now does; dedicated
concurrency tests call .request() or supply an explicit If-Match themselves.
"""
import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def conditional_legacy_recipe_writes(monkeypatch):
    def conditional_method(original):
        def conditional_write(self, url, *args, **kwargs):
            path = str(url)
            recipe_path = None
            if re.fullmatch(r"/(?:api/)?recipes/[1-9][0-9]*(?:/images(?:/order)?)?/?", path):
                recipe_path = re.sub(r"/images.*$", "", path)
            elif re.fullmatch(r"/(?:api/)?recipe-images/[1-9][0-9]*(?:/crop)?/?", path):
                image = self.get(path.removesuffix("/crop"))
                if image.status_code == 200:
                    recipe_path = f"/api/recipes/{image.json()['recipe_id']}"
                else:
                    recipe_path = "/api/recipes/0"
            headers = dict(kwargs.get("headers") or {})
            if recipe_path and not any(key.lower() == "if-match" for key in headers):
                # Legacy cases exercise ordinary writes, not concurrency. Explicit
                # headers and request() bypass this adapter for precondition tests.
                for _ in range(4):
                    response = self.get(recipe_path)
                    version = response.json().get("version", 1) if response.status_code == 200 else 1
                    headers["If-Match"] = f'"{version}"'
                    kwargs["headers"] = headers
                    result = original(self, url, *args, **kwargs)
                    detail = result.json().get("detail") if result.status_code == 409 else None
                    if not isinstance(detail, dict) or detail.get("code") != "recipe_version_conflict":
                        return result
                return result
            return original(self, url, *args, **kwargs)
        return conditional_write

    for method in ("put", "post", "delete"):
        monkeypatch.setattr(TestClient, method, conditional_method(getattr(TestClient, method)))
