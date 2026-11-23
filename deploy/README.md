# Deploy Heritage Kitchen

The image contains the FastAPI backend and the built SvelteKit app. Docker
Compose publishes HTTP on `127.0.0.1:8081` by default. Anyone who can reach the
app can read recipes. Keep access on your private network or VPN.

## Docker Compose

Run these commands in `deploy/` to use `ghcr.io/fladchris/heritagekitchen:latest`.

```sh
cp .env.example .env
docker compose pull
docker compose up -d
```

Open `http://localhost:8081` on the Docker host. The first account becomes the
administrator. Set `HERITAGEKITCHEN_TAG` in `.env` to pin a published version.
To build a local image, see [Build from source](#build-from-source).

The service mounts `./data` at `/data` and `./recipe-images` at `/app/recipe-images`.
Both mounts must be writable by the container process (UID/GID `0:0` by default).
SQLite stores its database at `/data/heritagekitchen.db`. To use an external
PostgreSQL instance, set `DATABASE_URL` in `.env` and keep the photo mount.
The app applies migrations at startup and exposes `GET /health` on port `8000`.

## Container template reference

Use these values for Unraid Docker templates, Portainer or a Docker host running on Proxmox.

| Setting | Value |
| --- | --- |
| Image | `ghcr.io/fladchris/heritagekitchen:latest` |
| Port | `8000/tcp` in the container, `8081` on the host in the examples |
| Database mount | `/data` (read/write), with the SQLite file at `/data/heritagekitchen.db` |
| Image mount | `/app/recipe-images` (read/write). Holds uploaded recipe, category and profile images |
| Required environment | None for SQLite. The container sets `SQLITE_DATABASE_PATH` |
| Optional database environment | `DATABASE_URL` for PostgreSQL or a different SQLite file. In a container with `DATABASE_URL` unset, `SQLITE_DATABASE_PATH` changes the SQLite file |
| Optional proxy and email environment | `SESSION_COOKIE_SECURE` (default `auto`), `FORWARDED_ALLOW_IPS` (trusted proxy addresses), `RESET_BASE_URL` (canonical URL for email links), `MAIL_CREDENTIALS_KEY` (required for password-authenticated SMTP) |
| Health check | `GET /health` on container port `8000`. The image includes a Docker health check |
| User and permissions | Defaults to UID/GID `0:0` in the container. Both mounts must be writable by the container process |

## Docker run

The Compose setup as a single command in a POSIX shell:

```sh
docker run -d --name heritagekitchen --restart unless-stopped -p "${APP_BIND_IP:-127.0.0.1}:${HTTP_PORT:-8081}:8000" -v "$PWD/data:/data" -v "$PWD/recipe-images:/app/recipe-images" -e "DATABASE_URL=${DATABASE_URL:-sqlite:////data/heritagekitchen.db}" -e "SESSION_COOKIE_SECURE=${SESSION_COOKIE_SECURE:-auto}" -e "FORWARDED_ALLOW_IPS=${FORWARDED_ALLOW_IPS:-127.0.0.1}" -e "RESET_BASE_URL=${RESET_BASE_URL:-}" -e "MAIL_CREDENTIALS_KEY=${MAIL_CREDENTIALS_KEY:-}" ghcr.io/fladchris/heritagekitchen:latest
```

## Build from source

```sh
git clone https://github.com/FladChris/HeritageKitchen.git
cd HeritageKitchen
docker build -f deploy/Dockerfile.backend --build-arg APP_VERSION=0.1.0 -t ghcr.io/fladchris/heritagekitchen:latest .
cd deploy
docker compose up -d --pull never
```

## Platforms and resources

The Dockerfile supports `linux/amd64` and `linux/arm64`. Both built locally with Buildx. The arm64 build used emulation on an amd64 host.

| Platform | Image content | Local disk usage |
| --- | --- | --- |
| `linux/amd64` | 94.5 MB | 423 MB |
| `linux/arm64` | 95.2 MB | 408 MB |

Docker Desktop reported these approximate image sizes. On amd64, `docker stats --no-stream` showed about 100 MiB of idle RAM with a fresh SQLite database and 115 MiB after browsing a small cookbook.

## Configuration

The default SQLite setup needs no environment variables. Set overrides in
`.env` for Compose or pass them to the container environment with Docker.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL. Compose defaults to `sqlite:////data/heritagekitchen.db`. Use `postgresql+psycopg://…` for PostgreSQL. |
| `SQLITE_DATABASE_PATH` | Optional with `docker run` when `DATABASE_URL` is unset. Defaults to `/data/heritagekitchen.db` in the image. |
| `SESSION_COOKIE_SECURE` | `auto` detects HTTPS, `true` for HTTPS only, `false` for local HTTP. |
| `RESET_BASE_URL` | Canonical URL used in verification and password reset links. |
| `MAIL_CREDENTIALS_KEY` | Fernet key required when saving an SMTP password. |
| `FORWARDED_ALLOW_IPS` | Trusted reverse proxy addresses (Compose default `127.0.0.1`). |
| `APP_BIND_IP`, `HTTP_PORT`, `HERITAGEKITCHEN_TAG` | Compose bind address, port and image tag (`127.0.0.1`, `8081`, `latest`). |

The full cookbook export format is described in [cookbook-export.md](../docs/cookbook-export.md).

## HTTPS and reverse proxy

For access from other devices, use an HTTPS origin so browsers can install the
PWA and enable offline support. A reverse proxy on the Docker host can forward
to `http://127.0.0.1:8081`. Configure your hostname, certificate paths, and public
port using the [nginx template](nginx.conf.template).
For a reverse proxy in Docker, attach it to the app's Docker network and
forward to `http://heritagekitchen:8000`. See the [SWAG example](swag-heritagekitchen.subdomain.conf.sample).

Set `FORWARDED_ALLOW_IPS` to the trusted proxy address as seen by the app. A host
proxy can appear as the Docker bridge gateway. Forward the original host and
scheme and set `SESSION_COOKIE_SECURE=true` for an HTTPS-only deployment. Set
`RESET_BASE_URL` to the HTTPS address users open, including any non-default port.

## Email

If your SMTP server requires a password, generate a Fernet key and store it as
`MAIL_CREDENTIALS_KEY` in `.env` before starting the app.

```sh
python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Set `RESET_BASE_URL`, then configure, test, and save SMTP as an administrator
to enable email confirmation and password reset links. Keep the Fernet key
separately from database backups so you can restore access to the saved SMTP
password. To reset an administrator password from the Docker host, run
`docker compose exec heritagekitchen /app/.venv/bin/python -m app.admin_password USERNAME`.

## Back up and restore

From `deploy/` on the Linux Docker host, run the backup wrapper with Docker,
`flock`, and Python 3 available. The wrapper stops the app during backup and
restarts it if it was running. Stop any other writers before running the wrapper.
PostgreSQL requires compatible `pg_dump` and `pg_restore` tools on the host and an
address reachable from the host.

```sh
sh backup.sh /path/to/private/backups 30
```

The archive contains the database and recipe photos. Verify the archive and
stop all app writers before restoring. The example uses the default SQLite
paths. For PostgreSQL, set the target `DATABASE_URL` in the shell and add
`--replace` to the restore command. For SQLite, add `--replace` when you intend
to overwrite existing data or images.

```sh
archive=/path/to/private/backups/ARCHIVE.tar.gz
python3 backup.py verify "$archive"
docker compose stop
python3 backup.py restore "$archive" --writers-stopped
```

After a successful restore, run `docker compose up -d` and check `/health`,
login, and recipe photos.

## Release images

Pushing a version tag such as `v0.1.0` runs the release workflow. It builds the
image natively for `linux/amd64` and `linux/arm64` and publishes
`ghcr.io/fladchris/heritagekitchen` with the tags `0.1.0`, `0.1` and `latest`.

## Build and publish images manually

From the repository root, choose a release version. Authenticate with GHCR
using an account that can publish the package.

```sh
version=0.1.0
image=ghcr.io/fladchris/heritagekitchen
docker build -f deploy/Dockerfile.backend --build-arg "APP_VERSION=$version" -t "$image:$version" .
docker tag "$image:$version" "$image:latest"
docker login ghcr.io
docker push "$image:$version"
docker push "$image:latest"
```
