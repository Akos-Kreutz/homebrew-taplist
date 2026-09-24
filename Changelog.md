# Changelog

## 2.0

Security hardening release. The application, the container image and the way it is run were reworked
with security in mind. **This release contains breaking changes**, so read them before upgrading from 1.x.

### Breaking changes

- **Secrets are required.** The app refuses to start unless `SECRET_KEY` (at least 32 characters) and
  `ADMIN_PASS` (or `ADMIN_PASS_HASH`) are set. The old defaults (`CHANGE_ME_NOW`, `admin`/`password`) are rejected.
- **New port.** The container listens on **8080** instead of 80: use `-p 80:8080` instead of `-p 80:80`.
- **Non-root container.** The app runs as UID/GID `10001`. A bind-mounted folder must be writable by that
  user: `sudo chown -R 10001:10001 [PATH_TO_MOUNT_FOLDER]`.
- **Alpine is the new default image.** The runtime image has no shell, package manager or pip, so
  `docker exec -it <container> sh` no longer works (see "Debugging" in the README).
- **Logout is POST only.** Bookmarks or links pointing to `/logout` no longer work; use the button.
- **Stricter input.** Untappd links must point to `untappd.com`. Numeric fields are range checked. Uploaded
  images must really be the format their extension says. A `color` given as text must be a `#rrggbb` value.
- **`/mount` serves only images.** Other files in the mount folder, such as `drinks.json`, are no longer publicly reachable.
- **Existing admin sessions are invalidated** when the secret key changes, so log in again after upgrading.

### Container images

- **Alpine (default)**, `alpine.containerfile`: multi-stage build on `python:3.14-alpine`. The runtime stage
  gets only the app and its dependencies; the package manager, pip and busybox (shell) are removed.
  About 80 MB instead of the previous 200 MB, and no known vulnerabilities at release time.
  `dockerfile` and `containerfile` point to it.
- **Debian (still available, not default)**, `debian.containerfile`: `python:3.14.4-slim-trixie` pinned by
  digest, non-root user, root-owned code. Use it if you need a shell or glibc inside the container.
- Both images:
  - use hash-pinned dependencies (`requirements.txt` with `--require-hashes`) and a `HEALTHCHECK`
  - run under gunicorn instead of Flask's development server
  - work with `--read-only` and `--cap-drop ALL`

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
