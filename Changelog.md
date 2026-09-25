# Changelog

## 2.1

Beverages are stored in a database instead of `drinks.json`.

### Changes

- **SQLite by default, PostgreSQL optional.** Without configuration the beverages are stored in `mount/taplist.db`.
  Setting `POSTGRES_HOST` (plus `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`/`POSTGRES_PASSWORD_FILE`,
  `POSTGRES_SSLMODE`) switches to PostgreSQL. `SQLITE_PATH` changes the location of the SQLite file.
- **Unique IDs.** Every beverage gets a generated UUID. The beverage name is no longer used as an identifier, so
  duplicate names are allowed, and the admin page deletes beverages by ID (taps and bottles are listed with their number).
- **Image names.** Uploaded images are stored as `/mount/img/<ID>.<ext>` instead of a name derived from the beverage name.
  Images stay in the mount folder, the database only stores their path.
- **Automatic migration.** An existing `drinks.json` is imported into an empty database on start and renamed to
  `drinks.json.migrated`. The legacy `srm` field and hand-set hex colors are carried over.
- The app waits up to 20 seconds for the database at startup and fails with a clear error if it stays unreachable.
- The sample `mount/drinks.json` was removed from the repository and image.
- New dependencies: `sqlalchemy` and `psycopg[binary]`.

### Security notes

- All queries go through SQLAlchemy with bound parameters. The PostgreSQL password can be passed as a file (Docker secret)
  and TLS can be required with `POSTGRES_SSLMODE`.
- `/mount` still only serves image files, so `taplist.db` and `drinks.json.migrated` are not publicly reachable.
- Deleting uses the ID from the form, and images are still only removed from `/mount/img/` when no other beverage uses them.

## 2.0

Security hardening release. The application, the container image and the way it is run were reworked
with security in mind. **This release contains breaking changes**, so read them before upgrading from 1.x.

### Breaking changes

- **Secrets are required.** The app refuses to start unless `SECRET_KEY` (at least 32 characters) and
  `ADMIN_PASS` (or `ADMIN_PASS_HASH`) are set. The old defaults (`CHANGE_ME_NOW`, `admin`/`password`) are rejected.
- **New port.** The container listens on **8080** instead of 80: use `-p 80:8080` instead of `-p 80:80`.
- **Non-root container.** The app runs as UID/GID `10001`. A bind-mounted folder must be writable by that
  user: `sudo chown -R 10001:10001 [PATH_TO_MOUNT_FOLDER]`.
- **Minimal Alpine-based image.** The image is now built on Alpine instead of Debian, and the runtime image
  has no shell, package manager or pip. `docker exec -it <container> sh` no longer works
  (see "Debugging" in the README).
- **Logout is POST only.** Bookmarks or links pointing to `/logout` no longer work; use the button.
- **Stricter input.** Untappd links must point to `untappd.com`. Numeric fields are range checked. Uploaded
  images must really be the format their extension says. A `color` given as text must be a `#rrggbb` value.
- **`/mount` serves only images.** Other files in the mount folder, such as `drinks.json`, are no longer publicly reachable.
- **Existing admin sessions are invalidated** when the secret key changes, so log in again after upgrading.

### Container image

- New multi-stage `dockerfile` on `python:3.14-alpine` (previously single-stage `python:3.14.4-slim-trixie`).
  A builder stage installs the dependencies. The runtime stage gets only Python, the dependencies and the app;
  the package manager, pip and busybox (shell) are removed.
- About 80 MB instead of 200 MB, no setuid binaries, and no known vulnerabilities at release time.
- Runs as UID/GID `10001`. The application code is read-only for that user; only `mount/` is writable.
- Hash-pinned dependencies (`requirements.txt` installed with `--require-hashes`) and a `HEALTHCHECK`.
- Runs under gunicorn instead of Flask's development server, and works with `--read-only` and `--cap-drop ALL`.

### Summary of changes

**Authentication and sessions**
- Admin password is stored hashed; optional pre-hashed `ADMIN_PASS_HASH`.
- Secrets can be read from files (`SECRET_KEY_FILE`, `ADMIN_PASS_FILE`, `ADMIN_PASS_HASH_FILE`) for Docker secrets.
- Login rate limit: 5 attempts per minute, 20 per hour per IP.
- Hardened session cookie (HttpOnly, SameSite=Lax, optional Secure). Sessions expire after `SESSION_LIFETIME_HOURS`.

**Web security**
- CSRF protection on all forms.
- Security headers: Content-Security-Policy with a per-request script nonce, `X-Frame-Options`,
  `X-Content-Type-Options`, `Referrer-Policy` and more.
- Protection against script injection through Untappd links and card colors.
- Subresource Integrity for the Bootstrap stylesheet, and `rel="noopener noreferrer"` on external links.

**Uploads and data**
- Uploaded images are verified and re-encoded with Pillow. This removes metadata and hidden payloads and rejects oversized images.
- `drinks.json` is written atomically and protected against concurrent edits.
- Images are only deleted when no other beverage uses them, and only from `/mount/img/`.
- Invalid form input shows an error message instead of crashing.

**Configuration**
- New environment variables: `ADMIN_PASS_HASH`, `SESSION_COOKIE_SECURE`, `SESSION_LIFETIME_HOURS`,
  `TRUSTED_PROXIES` (for running behind a reverse proxy), and the `_FILE` variants of the secrets.

**Project and CI**
- `requirements.in`/`requirements.txt` with pinned versions and hashes; `generate_requirements.sh` to regenerate them.
- GitHub Actions workflow that scans the image and the container configuration with Trivy: on every push,
  on pull requests and weekly.
- Dependabot keeps the base image, Python packages and actions up to date.
- `.dockerignore` keeps the build context minimal.
- README: hardened `docker run`, Docker Compose with secrets, and HTTPS with a reverse proxy.

## 1.2

Previous release. Single-stage image on `python:3.14.4-slim-trixie`, running as root on port 80.
