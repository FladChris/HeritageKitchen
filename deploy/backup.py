#!/usr/bin/env python3
"""Offline DB + image backups. Standard library only; PostgreSQL uses client tools."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

PREFIX = "heritagekitchen-"


def database_config(url, deploy_dir):
    if url.startswith("sqlite:///"):
        value = url.removeprefix("sqlite:///")
        if not value or value == ":memory:" or "?" in value:
            raise ValueError("Use a file-backed SQLite URL without query parameters")
        path = Path(value)
        return "sqlite", path if path.is_absolute() else deploy_dir / path
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("Supported databases: sqlite:/// and postgresql[+psycopg]://")
    env = os.environ.copy()
    for key in (
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGSERVICE",
    ):
        env.pop(key, None)
    for key, value in {
        "PGHOST": parsed.hostname or "localhost",
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": unquote(parsed.path.lstrip("/")),
        "PGUSER": unquote(parsed.username or ""),
        "PGPASSWORD": unquote(parsed.password or ""),
    }.items():
        env[key] = value
    if not env["PGDATABASE"]:
        raise ValueError("PostgreSQL URL must name a database")
    allowed = {"sslmode", "sslcert", "sslkey", "sslrootcert", "connect_timeout"}
    for key, values in parse_qs(parsed.query).items():
        if key not in allowed or len(values) != 1:
            raise ValueError("Unsupported PostgreSQL URL query option")
        env["PG" + key.upper().replace("_", "")] = values[0]
    return "postgres", env


def pg_run(command, env):
    # Credentials stay in the environment, never in argv, logs, or the manifest.
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"{command[0]} failed (exit {result.returncode}); check database/client configuration"
        )


def sqlite_check(path):
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key check failed")


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


@contextmanager
def operation_lock(deploy_dir):
    deploy_dir.mkdir(parents=True, exist_ok=True)
    with (deploy_dir / ".backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def backup(args):
    if not args.writers_stopped:
        raise ValueError(
            "Stop all app writers, then pass --writers-stopped (or use backup.sh)"
        )
    if args.retention_days < 1:
        raise ValueError("Retention must be at least one day")
    kind, source = database_config(args.database_url, args.deploy_dir)
    images = args.images_dir
    if not images.is_dir() or images.is_symlink():
        raise ValueError("Recipe images directory must exist and must not be a symlink")
    args.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.backup_dir.is_relative_to(images):
        raise ValueError("Backup directory must be outside recipe-images")
    with tempfile.TemporaryDirectory(
        prefix=".heritagekitchen-backup-", dir=args.backup_dir
    ) as work:
        stage = Path(work)
        if kind == "sqlite":
            if not source.is_file():
                raise ValueError("SQLite source does not exist")
            with (
                closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as src,
                closing(sqlite3.connect(stage / "database.sqlite3")) as target,
            ):
                src.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
            sqlite_check(stage / "database.sqlite3")
        else:
            pg_run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(stage / "database.dump"),
                ],
                source,
            )
        (stage / "recipe-images").mkdir()
        for item in images.rglob("*"):
            if item.is_symlink() or not (item.is_file() or item.is_dir()):
                raise ValueError("Recipe image tree contains a symlink or special file")
            dest = stage / "recipe-images" / item.relative_to(images)
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, dest)
        manifest = {
            "format": 1,
            "database": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "files": {
                p.relative_to(stage).as_posix(): digest(p)
                for p in stage.rglob("*")
                if p.is_file()
            },
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        name = (
            PREFIX
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex[:8]
            + ".tar.gz"
        )
        partial = stage / "archive.partial"
        with tarfile.open(partial, "w:gz") as archive:
            for item in sorted(stage.iterdir()):
                if item != partial:
                    archive.add(item, arcname=item.name)
        os.chmod(partial, 0o600)
        destination = args.backup_dir / name
        os.replace(partial, destination)
    # Only complete archives with our prefix; a failed backup never prunes history.
    cutoff = time.time() - args.retention_days * 86400
    for candidate in args.backup_dir.glob(PREFIX + "*.tar.gz"):
        if (
            candidate != destination
            and not candidate.is_symlink()
            and candidate.stat().st_mtime < cutoff
        ):
            candidate.unlink()
    print(destination)


def unpack(archive_path, target):
    seen = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or str(path) in seen
                or not (member.isdir() or member.isfile())
                or not path.parts
                or path.parts[0]
                not in {
                    "manifest.json",
                    "database.sqlite3",
                    "database.dump",
                    "recipe-images",
                }
            ):
                raise ValueError("Unsafe or duplicate backup archive entry")
            seen.add(str(path))
            destination = target / path
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with (
                    archive.extractfile(member) as source,
                    destination.open("xb") as dest,
                ):
                    shutil.copyfileobj(source, dest)
    manifest = json.loads((target / "manifest.json").read_text())
    if manifest.get("format") != 1 or manifest.get("database") not in {
        "sqlite",
        "postgres",
    }:
        raise ValueError("Unsupported backup manifest")
    actual = {
        p.relative_to(target).as_posix(): digest(p)
        for p in target.rglob("*")
        if p.is_file() and p != target / "manifest.json"
    }
    if actual != manifest.get("files"):
        raise ValueError("Backup checksum mismatch or incomplete backup")
    expected_db = (
        "database.sqlite3" if manifest["database"] == "sqlite" else "database.dump"
    )
    if expected_db not in actual or not (target / "recipe-images").is_dir():
        raise ValueError("Backup must contain its database and recipe-images")
    if manifest["database"] == "sqlite":
        sqlite_check(target / expected_db)
    else:
        pg_run(["pg_restore", "--list", str(target / expected_db)], os.environ.copy())
    return manifest


def restore(args):
    if not args.writers_stopped:
        raise ValueError(
            "Stop all app writers before restore and pass --writers-stopped"
        )
    kind, destination = database_config(args.database_url, args.deploy_dir)
    if args.images_dir.is_symlink():
        raise ValueError("Images destination must not be a symlink")
    if not args.replace and (
        args.images_dir.exists() or (kind == "sqlite" and destination.exists())
    ):
        raise ValueError(
            "Destination exists; use a fresh destination or explicitly pass --replace"
        )
    if kind == "sqlite" and any(
        Path(str(destination) + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError(
            "SQLite sidecar files exist; restore to a fresh path and preserve the old DB and sidecars together"
        )
    with tempfile.TemporaryDirectory(
        prefix=".heritagekitchen-verify-", dir=args.deploy_dir
    ) as work:
        stage = Path(work)
        manifest = unpack(args.archive, stage)
        if manifest["database"] != kind:
            raise ValueError("Backup database type differs from restore destination")
        args.images_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".heritagekitchen-images-", dir=args.images_dir.parent
        ) as image_work:
            staged_images = Path(image_work) / "images"
            shutil.copytree(stage / "recipe-images", staged_images)
            old_images = Path(image_work) / "previous"
            if kind == "postgres":
                # Explicitly required even for an empty PostgreSQL target: this drops matching objects.
                if not args.replace:
                    raise ValueError(
                        "PostgreSQL restore requires --replace and a dedicated empty target database"
                    )
                pg_run(
                    [
                        "pg_restore",
                        "--clean",
                        "--if-exists",
                        "--single-transaction",
                        "--no-owner",
                        "--no-acl",
                        "--dbname",
                        destination["PGDATABASE"],
                        str(stage / "database.dump"),
                    ],
                    destination,
                )
                swap_images(args.images_dir, staged_images, old_images)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.is_symlink():
                    raise ValueError("Database destination must not be a symlink")
                with tempfile.TemporaryDirectory(
                    prefix=".heritagekitchen-db-", dir=destination.parent
                ) as db_work:
                    staged_db = Path(db_work) / "database.sqlite3"
                    previous_db = Path(db_work) / "previous.sqlite3"
                    shutil.copyfile(stage / "database.sqlite3", staged_db)
                    os.chmod(staged_db, 0o600)
                    existed = destination.exists()
                    if existed:
                        os.replace(destination, previous_db)
                    try:
                        os.replace(staged_db, destination)
                        swap_images(args.images_dir, staged_images, old_images)
                    except BaseException:
                        destination.unlink(missing_ok=True)
                        if existed:
                            os.replace(previous_db, destination)
                        raise
    print(
        "Restored database and recipe-images; restart the app and verify /health and recipe images"
    )


def swap_images(destination, staged, previous):
    existed = destination.exists()
    if existed:
        os.replace(destination, previous)
    try:
        os.replace(staged, destination)
    except BaseException:
        if existed:
            os.replace(previous, destination)
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deploy-dir", type=Path, default=Path(__file__).resolve().parent
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--images-dir", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("backup")
    create.add_argument("--backup-dir", type=Path, required=True)
    create.add_argument("--retention-days", type=int, default=30)
    create.add_argument("--writers-stopped", action="store_true")
    recover = sub.add_parser("restore")
    recover.add_argument("archive", type=Path)
    recover.add_argument("--writers-stopped", action="store_true")
    recover.add_argument("--replace", action="store_true")
    check = sub.add_parser("verify")
    check.add_argument("archive", type=Path)
    args = parser.parse_args()
    args.deploy_dir = args.deploy_dir.resolve()
    args.images_dir = (args.images_dir or args.deploy_dir / "recipe-images").absolute()
    args.database_url = (
        args.database_url or f"sqlite:///{args.deploy_dir / 'data/heritagekitchen.db'}"
    )
    if args.command == "backup":
        args.backup_dir = args.backup_dir.resolve()
    try:
        with operation_lock(args.deploy_dir):
            if args.command == "backup":
                backup(args)
            elif args.command == "restore":
                restore(args)
            else:
                with tempfile.TemporaryDirectory(
                    prefix=".heritagekitchen-verify-", dir=args.deploy_dir
                ) as work:
                    unpack(args.archive, Path(work))
                print("Verified archive checksums, database and recipe-images")
    except (
        ValueError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        tarfile.TarError,
        KeyError,
    ) as exc:
        parser.exit(1, f"Backup operation failed: {exc}\n")


if __name__ == "__main__":
    main()
