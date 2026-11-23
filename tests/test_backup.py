"""Real subprocess backup/restore proof, with WAL and byte-exact recipe images."""

import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "backup.py"


def cli(deploy, *args, success=True, database_url=None):
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    command = [sys.executable, str(SCRIPT), "--deploy-dir", str(deploy)]
    if database_url:
        command += ["--database-url", database_url]
    result = subprocess.run(
        command + list(map(str, args)),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    return result


@pytest.fixture
def source(tmp_path):
    deploy = tmp_path / "source"
    (deploy / "data").mkdir(parents=True)
    (deploy / "recipe-images" / "nested").mkdir(parents=True)
    (deploy / "recipe-images" / "nested" / "photo.jpg").write_bytes(
        b"\xff\xd8recipe image\xff\xd9"
    )
    (deploy / "recipe-images" / "manifest.json").write_text("image-file-name-edge-case")
    db = sqlite3.connect(deploy / "data" / "heritagekitchen.db")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE recipes (id INTEGER PRIMARY KEY, title TEXT)")
    db.execute("INSERT INTO recipes VALUES (1, 'WAL recipe')")
    db.commit()
    yield deploy, db
    db.close()


def make_backup(source, tmp_path):
    deploy, _ = source
    result = cli(
        deploy, "backup", "--backup-dir", tmp_path / "backups", "--writers-stopped"
    )
    return Path(result.stdout.strip())


def test_sqlite_wal_and_images_restore_proof(source, tmp_path):
    deploy, db = source
    assert (deploy / "data" / "heritagekitchen.db-wal").stat().st_size > 0
    archive = make_backup(source, tmp_path)
    assert archive.stat().st_mode & 0o777 == 0o600
    cli(deploy, "verify", archive)
    # Changes made after backup must not appear in the restored snapshot.
    db.execute("INSERT INTO recipes VALUES (2, 'after backup')")
    db.commit()
    restored = tmp_path / "restored"
    cli(restored, "restore", archive, "--writers-stopped")
    with sqlite3.connect(restored / "data" / "heritagekitchen.db") as result:
        assert result.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert result.execute("PRAGMA foreign_key_check").fetchall() == []
        assert result.execute("SELECT * FROM recipes").fetchall() == [(1, "WAL recipe")]
    for image in (deploy / "recipe-images").rglob("*"):
        if image.is_file():
            assert (
                restored / "recipe-images" / image.relative_to(deploy / "recipe-images")
            ).read_bytes() == image.read_bytes()
    cli(restored, "restore", archive, "--writers-stopped", success=False)
    cli(restored, "restore", archive, "--writers-stopped", "--replace")


def test_retention_only_prunes_completed_named_archives_after_success(source, tmp_path):
    archive = make_backup(source, tmp_path)
    ancient = time.time() - 31 * 86400
    os.utime(archive, (ancient, ancient))
    unrelated = archive.parent / "unrelated.tar.gz"
    unrelated.write_bytes(b"keep")
    partial = archive.parent / "heritagekitchen-old.partial"
    partial.write_bytes(b"keep")
    os.utime(unrelated, (ancient, ancient))
    new = make_backup(source, tmp_path)
    assert new.exists() and not archive.exists()
    assert unrelated.exists() and partial.exists()


def test_failed_backup_never_prunes_history(source, tmp_path):
    archive = make_backup(source, tmp_path)
    ancient = time.time() - 31 * 86400
    os.utime(archive, (ancient, ancient))
    (source[0] / "recipe-images" / "link.jpg").symlink_to(tmp_path / "missing")
    cli(
        source[0],
        "backup",
        "--backup-dir",
        archive.parent,
        "--writers-stopped",
        success=False,
    )
    assert archive.exists()


def test_missing_source_and_writer_acknowledgement(source, tmp_path):
    cli(source[0], "backup", "--backup-dir", tmp_path / "backups", success=False)
    missing = tmp_path / "missing"
    (missing / "recipe-images").mkdir(parents=True)
    cli(
        missing,
        "backup",
        "--backup-dir",
        tmp_path / "backups",
        "--writers-stopped",
        success=False,
    )
    assert not list((tmp_path / "backups").glob("*.tar.gz"))


@pytest.mark.parametrize(
    "member_name,kind",
    [
        ("../escaped", "file"),
        ("/absolute", "file"),
        ("recipe-images/link", "symlink"),
        ("recipe-images/link", "hardlink"),
    ],
)
def test_unsafe_archives_are_rejected_before_mutation(tmp_path, member_name, kind):
    archive_path = tmp_path / "bad.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        if kind != "file":
            member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
            member.linkname = "/etc/passwd"
        archive.addfile(member, io.BytesIO())
    cli(
        tmp_path / "target", "restore", archive_path, "--writers-stopped", success=False
    )
    assert not (tmp_path / "target" / "data").exists()
    assert not (tmp_path / "escaped").exists()


def test_tampered_backup_rejected_before_replace(source, tmp_path):
    archive = make_backup(source, tmp_path)
    tampered = tmp_path / "tampered.tar.gz"
    with tarfile.open(archive) as src, tarfile.open(tampered, "w:gz") as dest:
        for member in src:
            if member.name == "manifest.json":
                value = json.load(src.extractfile(member))
                value["files"]["database.sqlite3"] = "wrong"
                data = json.dumps(value).encode()
                member.size = len(data)
                dest.addfile(member, io.BytesIO(data))
            else:
                dest.addfile(
                    member, src.extractfile(member) if member.isfile() else None
                )
    target = tmp_path / "restored"
    cli(target, "restore", archive, "--writers-stopped")
    before = (target / "data" / "heritagekitchen.db").read_bytes()
    cli(target, "restore", tampered, "--writers-stopped", "--replace", success=False)
    assert (target / "data" / "heritagekitchen.db").read_bytes() == before


def test_restore_refuses_stale_sqlite_sidecars(source, tmp_path):
    archive = make_backup(source, tmp_path)
    target = tmp_path / "target"
    (target / "data").mkdir(parents=True)
    (target / "data" / "heritagekitchen.db-wal").write_bytes(b"preserve")
    cli(target, "restore", archive, "--writers-stopped", "--replace", success=False)
    assert (target / "data" / "heritagekitchen.db-wal").read_bytes() == b"preserve"


@pytest.mark.skipif(
    not os.environ.get("TEST_BACKUP_POSTGRES_URL"),
    reason="Dedicated PostgreSQL test server not configured",
)
def test_postgres_dump_restore_with_images(tmp_path):
    """Create two disposable databases; never restore into the supplied admin DB."""
    from importlib.util import module_from_spec, spec_from_file_location
    from urllib.parse import urlsplit, urlunsplit
    from uuid import uuid4

    spec = spec_from_file_location("heritagekitchen_backup", SCRIPT)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    url = os.environ["TEST_BACKUP_POSTGRES_URL"]
    _, admin_env = module.database_config(url, tmp_path)
    suffix = uuid4().hex[:12]
    names = ["heritagekitchen_backup_src_" + suffix, "heritagekitchen_backup_dst_" + suffix]
    created = []

    def sql(env, statement):
        return subprocess.run(
            [
                "psql",
                "-X",
                "--set",
                "ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--command",
                statement,
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def db_url(name):
        parsed = urlsplit(url)
        return urlunsplit(parsed._replace(path="/" + name))

    try:
        for name in names:
            sql(admin_env, f'CREATE DATABASE "{name}"')
            created.append(name)
        _, source_env = module.database_config(db_url(names[0]), tmp_path)
        _, target_env = module.database_config(db_url(names[1]), tmp_path)
        sql(
            source_env,
            "CREATE TABLE backup_proof (id integer PRIMARY KEY, title text); INSERT INTO backup_proof VALUES (1, 'recipe with image')",
        )
        deploy = tmp_path / "source"
        (deploy / "recipe-images").mkdir(parents=True)
        (deploy / "recipe-images" / "photo.jpg").write_bytes(b"postgres image")
        result = cli(
            deploy,
            "backup",
            "--backup-dir",
            tmp_path / "archives",
            "--writers-stopped",
            database_url=db_url(names[0]),
        )
        archive = Path(result.stdout.strip())
        cli(deploy, "verify", archive)
        sql(source_env, "INSERT INTO backup_proof VALUES (2, 'after snapshot')")
        target = tmp_path / "restored"
        cli(
            target,
            "restore",
            archive,
            "--writers-stopped",
            "--replace",
            database_url=db_url(names[1]),
        )
        assert (
            sql(target_env, "SELECT id, title FROM backup_proof ORDER BY id")
            == "1|recipe with image"
        )
        assert (
            target / "recipe-images" / "photo.jpg"
        ).read_bytes() == b"postgres image"
    finally:
        for name in reversed(created):
            sql(admin_env, f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.mark.parametrize(
    "was_running,backup_fails", [(True, False), (True, True), (False, False)]
)
def test_host_wrapper_restores_initial_container_state(
    source, tmp_path, was_running, backup_fails
):
    """Exercise the real host wrapper without manipulating a user's Docker daemon."""
    import shutil

    deploy, db = source
    db.close()
    scripts = tmp_path / "checkout"
    scripts.mkdir()
    shutil.copyfile(SCRIPT, scripts / "backup.py")
    shutil.copyfile(SCRIPT.with_suffix(".sh"), scripts / "backup.sh")
    shutil.copyfile(SCRIPT.with_name("backup_mounts.py"), scripts / "backup_mounts.py")
    # A stale checkout must never win over the actual container mounts.
    shutil.copytree(deploy / "data", scripts / "data")
    (scripts / "recipe-images").mkdir()
    (scripts / "recipe-images" / "stale.txt").write_text("stale checkout")
    if backup_fails:
        (deploy / "recipe-images" / "bad-link").symlink_to(tmp_path / "missing")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("""#!/bin/sh
case "$1" in
  inspect)
    case "$3" in
      *State.Running*) echo "$FAKE_RUNNING" ;;
      *Mounts*) echo "$FAKE_MOUNTS" ;;
      *) echo DATABASE_URL=sqlite:////data/heritagekitchen.db ;;
    esac ;;
  stop|start) echo "$1" >> "$FAKE_LOG" ;;
  *) exit 99 ;;
esac
""")
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=str(fake_bin) + os.pathsep + env["PATH"],
        FAKE_RUNNING=str(was_running).lower(),
        FAKE_LOG=str(tmp_path / "docker.log"),
        FAKE_MOUNTS=json.dumps([
            {"Type": "bind", "Destination": "/data", "Source": str(deploy / "data")},
            {"Type": "bind", "Destination": "/app/recipe-images", "Source": str(deploy / "recipe-images")},
        ]),
    )
    result = subprocess.run(
        ["sh", str(scripts / "backup.sh"), str(tmp_path / "archives")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (not backup_fails), result.stdout + result.stderr
    calls = (tmp_path / "docker.log").read_text().splitlines() if was_running else []
    assert calls == (["stop", "start"] if was_running else [])
    if not backup_fails:
        archives = list((tmp_path / "archives").glob("*.tar.gz"))
        assert len(archives) == 1
        with tarfile.open(archives[0]) as archive:
            assert not any("stale.txt" in name for name in archive.getnames())
            photo = next(name for name in archive.getnames() if name.endswith("nested/photo.jpg"))
            assert archive.extractfile(photo).read() == b"\xff\xd8recipe image\xff\xd9"


@pytest.mark.parametrize("layout", ["missing", "volume", "nested", "duplicate", "escape"])
def test_container_backup_rejects_unsupported_mounts(source, layout):
    import runpy

    resolve = runpy.run_path(str(SCRIPT.with_name("backup_mounts.py")))["resolve_sources"]
    deploy, _ = source
    mounts = [
        {"Type": "bind", "Destination": "/data", "Source": str(deploy / "data")},
        {"Type": "bind", "Destination": "/app/recipe-images", "Source": str(deploy / "recipe-images")},
    ]
    url = "sqlite:////data/heritagekitchen.db"
    if layout == "missing":
        mounts.pop()
    elif layout == "volume":
        mounts[1]["Type"] = "volume"
    elif layout == "nested":
        mounts.append({"Destination": "/app/recipe-images/hidden"})
    elif layout == "duplicate":
        mounts.append(mounts[0].copy())
    else:
        url = "sqlite:////data/../outside.db"
    with pytest.raises(ValueError):
        resolve(url, mounts)
