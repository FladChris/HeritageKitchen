# Heritage Kitchen

[![CI](https://github.com/FladChris/HeritageKitchen/actions/workflows/ci.yml/badge.svg)](https://github.com/FladChris/HeritageKitchen/actions/workflows/ci.yml)

A self-hosted family cookbook with a German interface. **Early release 0.1.0.** [Changelog](CHANGELOG.md) · [Screenshots](docs/screenshots.md)

## Why Heritage Kitchen?

Keep family recipes, photos and the stories behind them in one place. The installed app keeps a full offline copy of the cookbook, including photos, on each signed-in device after its first sync. Heritage Kitchen stays small enough to run as a single container with built-in storage.

The scope excludes meal planning, shopping lists, web recipe import or scraping, and nutrition data. This release uses local accounts and has no SSO or OpenID Connect (OIDC) integration.

## Features

- Group ingredients, add family stories and source notes, and split recipes into named days with timed steps.
- Add up to 20 photos per recipe with cropping, alt text and a swipeable gallery.
- Search titles, ingredients, steps and comments with or without accents. Organize recipes with categories, favorites and personal sorting.
- Scale servings and check off ingredients and steps in cooking mode. The interface supports keyboard and screen reader navigation.
- Share recipes as text or links, or print them to PDF. Administrators can export the cookbook as a JSON ZIP with photos or as a PDF.
- Read as a guest, or sign in to cook along, comment and rate in half-star increments. Reader, editor and admin roles support shared editing with approval for new registrations.

## Self-hosting

Runs as a single Docker container with built-in SQLite; PostgreSQL and SMTP are
optional. Save this as `compose.yml` and run `docker compose up -d`:

```yaml
services:
  heritagekitchen:
    image: ghcr.io/fladchris/heritagekitchen:latest
    container_name: heritagekitchen
    restart: unless-stopped
    ports:
      - "${APP_BIND_IP:-127.0.0.1}:${HTTP_PORT:-8081}:8000"
    volumes:
      - ./data:/data
      - ./recipe-images:/app/recipe-images
    environment:
      DATABASE_URL: ${DATABASE_URL:-sqlite:////data/heritagekitchen.db}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-auto}
      FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-127.0.0.1}
      RESET_BASE_URL: ${RESET_BASE_URL:-}
      MAIL_CREDENTIALS_KEY: ${MAIL_CREDENTIALS_KEY:-}
```

Open `http://localhost:8081` on the server and register: the first account
becomes the administrator. Anyone who can reach the instance can read the
recipes, so keep it in your home network or behind a VPN, and use HTTPS through
a reverse proxy so phones can install the app.

The [deployment guide](deploy/README.md) covers Unraid/Portainer template
values, `docker run`, building from source, platforms, HTTPS, email, backups
and updates.

## Background

Heritage Kitchen started as a way to keep our family's recipes in one place. I have worked on it on and off for about two years, threw early versions away and started over more than once. This repository is a cleaned-up fresh start of that work, which is why the history begins with a single commit.

I have little experience with Svelte and UI design, so a large part of the frontend and the design was generated with AI coding assistants. They also helped with clean-up work in the backend. Changes are reviewed and covered by tests, and the app runs on my own home server.

## Development

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node.js 24.15+.
Run `uv sync && uv run python main.py` for the backend and `npm ci && npm run dev` in `site/` for the frontend. Checks include `uv run ruff check .`, `uv run pytest` and, in `site/`, `npm run check`, `npm test` and `npm run build`.

## License

[MIT](LICENSE)
