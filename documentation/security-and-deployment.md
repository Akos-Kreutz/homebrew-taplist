# Security & Deployment

How the application is hardened and how to run it. Part of [Architecture Overview](architecture-overview.md).

---

## Hardening

| Area | What the code does |
|---|---|
| **Secrets** | `get_secret(NAME)` reads `NAME` or the file in `NAME_FILE`. `""`, `CHANGE_ME_NOW`, `password`, `admin`, `changeme` are refused; `SECRET_KEY` needs 32+ characters. The app will not start otherwise |
| **Admin password** | `ADMIN_PASS_HASH` is preferred; otherwise `ADMIN_PASS` is hashed at start. One user (`ADMIN_USER`, default `admin`), compared in constant time; the hash is always checked so the timing does not reveal the user name |
| **Rate limit** | `POST /login`: 5 per minute, 20 per hour per client, kept in memory |
| **Sessions** | `HttpOnly`, `SameSite=Lax`, `Secure` with `SESSION_COOKIE_SECURE=true`, lifetime `SESSION_LIFETIME_HOURS` (default 8). Flask-Login session protection is **`strong`**: the session ends when the client's address or browser identity changes |
| **CSRF** | Flask-WTF on every form; logout is `POST` only |
| **Headers** | Content-Security-Policy with a **per-request nonce** for scripts (`g.csp_nonce`), `style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'` (the cards use inline color styles), `img-src 'self' data:`, `object-src 'none'`, `frame-ancestors 'none'`; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`. `Cache-Control: no-store` on `/admin` and `/login` |
| **Uploads** | Extension allow list, the content must match the extension, re-encoded, 40 megapixel cap, 10 MB request cap. Files get server-made names (`<ID>.<ext>`), never the uploaded name |
| **Links** | Untappd links must point to `untappd.com`; external links carry `rel="noopener noreferrer"`; Bootstrap loads with a Subresource Integrity hash |
| **Files** | `/mount` serves image files only; deletion is limited to `/mount/img/` |
| **Database** | SQLAlchemy with bound parameters. `POSTGRES_PASSWORD_FILE` and `POSTGRES_SSLMODE` supported |
| **Proxy** | `TRUSTED_PROXIES=N` enables `ProxyFix` so the limiter and the session protection see the real client address |

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` (`_FILE`) | **required** | 32+ characters |
| `ADMIN_PASS` (`_FILE`) or `ADMIN_PASS_HASH` (`_FILE`) | **one required** | Password or its hash |
| `ADMIN_USER` | `admin` | |
| `SESSION_LIFETIME_HOURS` | `8` | |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `TRUSTED_PROXIES` | `0` | Number of reverse proxies |
| `SQLITE_PATH` | `mount/taplist.db` | Location of the SQLite file |
| `POSTGRES_HOST` | none | **Setting it switches to PostgreSQL** |
| `POSTGRES_PORT`, `_DB`, `_USER` | `5432`, `taplist`, `taplist` | |
| `POSTGRES_PASSWORD` (`_FILE`), `POSTGRES_SSLMODE` | none | |

## The container

* **Image:** two stages on `python:3.15-alpine`; the builder installs the hash-pinned requirements into a venv and removes pip, the final image removes `apk` and busybox, so there is no shell. The mount folder is owned by `10001`. User `10001:10001`, port **8080**, health check on `GET /`.
* **Server:** gunicorn, 1 worker, 4 threads, `--worker-tmp-dir /dev/shm`, access log to stdout. One worker keeps the in-memory limiter and the write lock correct.
* **State:** mount `mount/` (`/app/mount`) and chown it for `10001`: `sudo chown -R 10001:10001 <folder>`. It holds `taplist.db`, the pictures, the background and the favicon.

```
docker run -d --name taplist --restart unless-stopped \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 100 --memory 256m \
  --env-file taplist.env -p 80:8080 \
  -v <mount folder>:/app/mount \
  kreutzakos/homebrew-taplist:<version>
```

`taplist.env` holds `ADMIN_USER`, `ADMIN_PASS` and `SECRET_KEY` (`chmod 600`). Use a version tag, not `latest`.

### Compose

The README has a Compose file with Docker secrets (`ADMIN_PASS_FILE`, `SECRET_KEY_FILE`; the secret files must be readable by UID 10001) and a variant with a `postgres:17-alpine` service (`POSTGRES_HOST=db`, `POSTGRES_PASSWORD_FILE`). The mount folder is still needed for the pictures.

### HTTPS

The app speaks HTTP. Put a TLS proxy in front (Caddy: `reverse_proxy taplist:8080`), set `SESSION_COOKIE_SECURE=true` and `TRUSTED_PROXIES=1`, and publish only the proxy's port.

### Debugging

No shell in the image: `docker logs taplist`; `docker exec taplist python3 -c "..."` (for example reading the SQLite file with `sqlite3`); or a helper container with `--pid=container:taplist --network=container:taplist`.

### Dependencies and releases

`./generate_requirements.sh` recompiles the lock file. The Changelog records 2.0 (security hardening: required secrets, port 8080, non-root, Alpine image, CSRF, rate limit, headers) and 2.1 (database instead of `drinks.json`, unique IDs, image names by ID).
