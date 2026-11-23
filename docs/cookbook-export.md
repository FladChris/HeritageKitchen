# Cookbook export

Administrators can download the full cookbook from **Einstellungen →
Gesamtes Kochbuch exportieren**.

- `GET /api/settings/export/zip` returns `cookbook.json` and all referenced
  images under `images/`.
- `GET /api/settings/export/pdf` returns a printable document of the current
  recipes without images. The document metadata uses the cookbook or app name.

Both endpoints require an active administrator session. Editors and readers
receive HTTP 403. Both downloads use `Cache-Control: no-store`.

## ZIP format, version 1

`cookbook.json` contains `format`, `format_version`, `exported_at`,
`categories`, `recipes`, and `media`. The `format` value is
`heritagekitchen-cookbook`.

Each recipe includes its current ingredients, steps, images, times, origin,
notes, comments, and ratings. Comments use the current username of the
comment author. `archive_path` points to an image in the ZIP. Each `media`
entry records the path, byte length, and SHA-256 digest.

The export excludes password hashes, sessions, tokens, SMTP credentials, and
recoverable login accounts. To restore an instance, use the
[backup tools](../deploy/README.md#back-up-and-restore).

## Consistency

SQLite uses an explicit read transaction. PostgreSQL uses a `REPEATABLE READ,
READ ONLY` transaction. The server reads and checks referenced images before
returning the ZIP. A missing or corrupt image returns HTTP 503.
