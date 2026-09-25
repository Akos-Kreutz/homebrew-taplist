import os
import io
import hmac
import math
import secrets
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
import re
from urllib.parse import urlparse
from flask import (
    Flask, render_template, request, json, g, session,
    redirect, url_for, flash, send_from_directory, abort
)
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image
from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    String, Integer, Float, Text, URL, select, delete, func
)
from sqlalchemy.exc import OperationalError

# --------------------
# Secrets
# --------------------

INSECURE_DEFAULTS = {"", "CHANGE_ME_NOW", "password", "admin", "changeme"}

def get_secret(name, required=True):
    """
    Read a secret from NAME or from the file referenced by NAME_FILE
    (e.g. a Docker secret mounted under /run/secrets).
    """
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        value = Path(file_path).read_text().strip()
    else:
        value = os.environ.get(name, "").strip()

    if required and value in INSECURE_DEFAULTS:
        raise RuntimeError(
            f"{name} (or {name}_FILE) must be set to a non-default value"
        )

    return value or None

# --------------------
# App Setup
# --------------------

app = Flask(__name__)
app.secret_key = get_secret("SECRET_KEY")

if len(app.secret_key) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters long")

# Number of reverse proxies in front of the app (0 = none). Needed so the
# login rate limit and session protection see the real client IP.
TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "0"))
if TRUSTED_PROXIES > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=TRUSTED_PROXIES, x_proto=TRUSTED_PROXIES
    )

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
)

# Extension -> Pillow format the file content must actually have
IMAGE_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".gif": "GIF",
    ".webp": "WEBP",
}
ALLOWED_IMAGE_EXTENSIONS = set(IMAGE_FORMATS)

# Reject decompression bombs (tiny files that expand to huge bitmaps)
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

SRM_FILE = Path("srm_colors.json")

MOUNT_DIR = Path("mount")
LEGACY_DRINKS_FILE = MOUNT_DIR / "drinks.json"
DEFAULT_SQLITE_FILE = MOUNT_DIR / "taplist.db"
IMG_DIR = MOUNT_DIR / "img"
IMG_URL_PREFIX = "/mount/img/"
BACKGROUND_FILE = MOUNT_DIR / "background.png"
FAVICON_FILE = MOUNT_DIR / "favicon.png"

BEVERAGE_CATEGORIES = ("taps", "bottles", "spirits")
HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")

# Form field -> (type, min, max)
NUMERIC_FIELDS = {
    "number": (int, 0, 99999),
    "abv": (float, 0, 100),
    "color": (float, 0, 50),  # SRM, matches srm_colors.json
    "ibu": (int, 0, 1000),
    "kcal": (int, 0, 10000),
}
MAX_TEXT_LENGTH = 200
MAX_INFO_LENGTH = 1000

# Serializes add/delete (tap override, image cleanup) across gunicorn threads
WRITE_LOCK = threading.Lock()

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB limit

# ---- Session cookie hardening ----
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Only enable when served over HTTPS, otherwise the browser drops the cookie
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=int(os.environ.get("SESSION_LIFETIME_HOURS", "8"))
    ),
)

# ---- Security headers ----
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}'; "
    # Inline style attributes are used for the card colors
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

@app.before_request
def set_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)

@app.context_processor
def inject_csp_nonce():
    return {"csp_nonce": g.get("csp_nonce", "")}

@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY.format(
        nonce=g.get("csp_nonce", "")
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    if request.path.startswith(("/admin", "/login")):
        response.headers["Cache-Control"] = "no-store"

    return response

# --------------------
# Database
# --------------------

def build_database_url():
    """
    PostgreSQL when POSTGRES_HOST is set, otherwise a SQLite file in the
    mount folder (SQLITE_PATH overrides its location).
    """
    host = os.environ.get("POSTGRES_HOST", "").strip()

    if not host:
        sqlite_path = os.environ.get("SQLITE_PATH", "").strip() or str(DEFAULT_SQLITE_FILE)
        return URL.create("sqlite", database=sqlite_path)

    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER", "taplist"),
        password=get_secret("POSTGRES_PASSWORD", required=False),
        host=host,
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "taplist"),
    )

def build_connect_args(url):
    if url.get_backend_name() == "postgresql":
        args = {"connect_timeout": 5}
        sslmode = os.environ.get("POSTGRES_SSLMODE", "").strip()
        if sslmode:
            args["sslmode"] = sslmode
        return args
    return {}

def wait_for_database(timeout=20):
    """
    The database container may still be starting (e.g. with Docker Compose),
    so retry for a while. Stays below gunicorn's 30s worker boot timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect():
                return
        except OperationalError as e:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Could not connect to the database: {e.orig or e}"
                ) from None
            app.logger.warning("Database not reachable yet, retrying")
            time.sleep(2)

DATABASE_URL = build_database_url()
engine = create_engine(
    DATABASE_URL,
    connect_args=build_connect_args(DATABASE_URL),
    pool_pre_ping=True,
)

metadata = MetaData()

beverages = Table(
    "beverages", metadata,
    Column("id", String(36), primary_key=True),
    Column("category", String(20), nullable=False, index=True),
    Column("name", Text, nullable=False),
    Column("style", Text),
    Column("info", Text),
    Column("untappd", Text),
    Column("image", Text),
    Column("number", Integer),
    Column("abv", Float),
    Column("color", Float),  # SRM
    Column("color_hex", String(7)),  # only set by the drinks.json import
    Column("ibu", Integer),
    Column("kcal", Integer),
)

def new_id():
    return str(uuid.uuid4())

def import_legacy_drinks():
    """
    One-time import of a 1.x/2.0 drinks.json into an empty database. The file
    is renamed afterwards so it is not imported again.
    """
    if not LEGACY_DRINKS_FILE.exists():
        return

    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(beverages)).scalar():
            app.logger.warning(
                "%s ignored: the database already contains beverages", LEGACY_DRINKS_FILE
            )
            return

        data = json.loads(LEGACY_DRINKS_FILE.read_text())
        rows = []

        for category in BEVERAGE_CATEGORIES:
            for item in data.get(category, []):
                row = {"id": new_id(), "category": category, "color_hex": None}

                for column in ("name", "style", "info", "untappd", "image"):
                    row[column] = item.get(column)
                for field in NUMERIC_FIELDS:
                    value = item.get(field)
                    row[field] = value if isinstance(value, (int, float)) else None

                # Legacy "srm" field, and hex colors that could only be set by hand
                color = item.get("color")
                if row["color"] is None and isinstance(item.get("srm"), (int, float)):
                    row["color"] = item["srm"]
                elif isinstance(color, str) and HEX_COLOR_RE.fullmatch(color):
                    row["color_hex"] = color

                if row["name"]:
                    rows.append(row)

        if rows:
            conn.execute(beverages.insert(), rows)

    LEGACY_DRINKS_FILE.rename(LEGACY_DRINKS_FILE.with_name("drinks.json.migrated"))
    app.logger.warning(
        "Imported %d beverages from %s into the database", len(rows), LEGACY_DRINKS_FILE
    )

wait_for_database()
metadata.create_all(engine)
import_legacy_drinks()

def load_drinks():
    """All beverages grouped by category."""
    with engine.connect() as conn:
        rows = conn.execute(select(beverages)).mappings().all()

    data = {category: [] for category in BEVERAGE_CATEGORIES}
    for row in rows:
        if row["category"] in data:
            data[row["category"]].append(dict(row))

    return data

# --------------------
# Authentication Setup
# --------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.session_protection = "strong"
login_manager.init_app(app)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")

# Prefer a pre-hashed password (ADMIN_PASS_HASH), fall back to hashing ADMIN_PASS
# at startup so the plaintext is never kept around or compared directly.
ADMIN_PASS_HASH = get_secret("ADMIN_PASS_HASH", required=False)
if not ADMIN_PASS_HASH:
    ADMIN_PASS_HASH = generate_password_hash(get_secret("ADMIN_PASS"))

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    if user_id is not None and hmac.compare_digest(user_id, ADMIN_USER):
        return User(user_id)
    return None

# --------------------
# Public Routes
# --------------------

@app.route("/")
def index():
    data = load_drinks()
    srm_map = load_srm_map()

    for section, items in data.items():
        normalized = [normalize_drink(item, srm_map) for item in items]

        normalized.sort(key=lambda x: (
            x["number"] if x["number"] is not None else 9999, x["name"].lower()
        ))
        data[section] = normalized

    return render_template("index.html", data=data)

# --------------------
# Login Routes
# --------------------

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        # Always run the hash check so timing does not reveal a valid username
        user_ok = hmac.compare_digest(username, ADMIN_USER)
        pass_ok = check_password_hash(ADMIN_PASS_HASH, password)

        if user_ok and pass_ok:
            session.permanent = True
            login_user(User(ADMIN_USER))
            return redirect(url_for("admin"))

        flash("Invalid credentials")

    return render_template("login.html")

@app.errorhandler(429)
def too_many_requests(e):
    flash("Too many login attempts, try again later")
    return render_template("login.html"), 429

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# --------------------
# Admin Routes
# --------------------

@app.route("/admin")
@login_required
def admin():
    drinks = load_drinks()

    images = [
        p.name for p in IMG_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
    ]

    return render_template(
        "admin.html",
        drinks=drinks,
        images=images
    )

@app.route("/admin/delete_item", methods=["POST"])
@login_required
def delete_item():
    item_id = request.form.get("id", "")

    with WRITE_LOCK:
        with engine.begin() as conn:
            removed = conn.execute(
                delete(beverages)
                .where(beverages.c.id == item_id)
                .returning(beverages.c.image)
            ).all()

        if not removed:
            flash("Item not found")
            return redirect(url_for("admin"))

        for (image,) in removed:
            delete_image_if_unused(image)

    flash("Item deleted")

    return redirect(url_for("admin"))

@app.route("/admin/add_item", methods=["POST"])
@login_required
def add_item():
    # ---------- Checking Requested Attributes ----------
    category = request.form.get("category")

    if category not in BEVERAGE_CATEGORIES:
        flash("Invalid category")
        return redirect(url_for("admin"))

    try:
        name = parse_text("name", required=True)
        style = parse_text("style")
        info = parse_text("info", max_length=MAX_INFO_LENGTH)
        untappd = parse_text("untappd")

        if untappd and not is_safe_untappd_url(untappd):
            raise ValueError("Untappd link must be an https://untappd.com URL")

        numbers = {
            field: parse_number(field, cast, low, high)
            for field, (cast, low, high) in NUMERIC_FIELDS.items()
        }
    except ValueError as e:
        flash(str(e))
        return redirect(url_for("admin"))

    if category == "taps" and numbers["number"] is None:
        flash("Number is required")
        return redirect(url_for("admin"))

    # ---------- Image Upload ----------
    image_file = request.files.get("image_file")

    if not image_file or image_file.filename == "":
        flash("Image file is required")
        return redirect(url_for("admin"))

    # Validate extension
    original_ext = Path(image_file.filename).suffix.lower()
    if original_ext not in ALLOWED_IMAGE_EXTENSIONS:
        flash("Invalid image type")
        return redirect(url_for("admin"))

    image_bytes = sanitize_image(image_file, IMAGE_FORMATS[original_ext])
    if image_bytes is None:
        flash("Image content is invalid or does not match its extension")
        return redirect(url_for("admin"))

    # ---------- Build Item ----------
    # The image is named after the beverage's ID, so it never collides
    item_id = new_id()
    filename = f"{item_id}{original_ext}"

    item = {
        "id": item_id,
        "category": category,
        "name": name,
        "style": style,
        "info": info,
        "untappd": untappd,
        "image": f"{IMG_URL_PREFIX}{filename}",
        **numbers,
    }

    with WRITE_LOCK:
        (IMG_DIR / filename).write_bytes(image_bytes)

        try:
            with engine.begin() as conn:
                # ---------- Tap Override ----------
                replaced_images = []
                if category == "taps":
                    replaced_images = conn.execute(
                        delete(beverages)
                        .where(beverages.c.category == "taps")
                        .where(beverages.c.number == item["number"])
                        .returning(beverages.c.image)
                    ).scalars().all()

                conn.execute(beverages.insert().values(**item))
        except Exception:
            (IMG_DIR / filename).unlink(missing_ok=True)
            raise

        # Only remove the old tap's image if no other item still uses it
        for image in replaced_images:
            delete_image_if_unused(image)

    flash("Item added successfully")

    return redirect(url_for("admin"))

@app.route("/admin/update_background_image", methods=["POST"])
@login_required
def update_background_image():
    file = request.files.get("background_file")

    if not file or file.filename == "":
        flash("No file selected")
        return redirect(url_for("admin"))

    if Path(file.filename).suffix.lower() != ".png":
        flash("Only PNG files are allowed")
        return redirect(url_for("admin"))

    image_bytes = sanitize_image(file, "PNG")
    if image_bytes is None:
        flash("File is not a valid PNG image")
        return redirect(url_for("admin"))

    BACKGROUND_FILE.write_bytes(image_bytes)
    flash("Background updated successfully")

    return redirect(url_for("admin"))

@app.route("/admin/update_favicon", methods=["POST"])
@login_required
def update_favicon():
    file = request.files.get("favicon_file")

    if not file or file.filename == "":
        flash("No file selected")
        return redirect(url_for("admin"))

    if Path(file.filename).suffix.lower() != ".png":
        flash("Only PNG files are allowed")
        return redirect(url_for("admin"))

    image_bytes = sanitize_image(file, "PNG")
    if image_bytes is None:
        flash("File is not a valid PNG image")
        return redirect(url_for("admin"))

    FAVICON_FILE.write_bytes(image_bytes)
    flash("Favicon updated successfully")

    return redirect(url_for("admin"))

# --------------------
# Helpers
# --------------------

@app.route("/mount/<path:filename>")
def mounted_files(filename):
    # Only serve images; keeps the SQLite database and anything else in mount/ private
    if Path(filename).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        abort(404)
    return send_from_directory(MOUNT_DIR, filename)

def sanitize_image(file_storage, expected_format):
    """
    Check that the upload really is an image of expected_format and return
    it re-encoded (drops metadata and anything appended to the image data).
    Returns None if the file is not a valid image.
    """
    data = file_storage.read()

    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != expected_format:
                return None
            if img.width * img.height > MAX_IMAGE_PIXELS:
                return None
            img.verify()

        # verify() leaves the image unusable, so open it again to re-encode
        with Image.open(io.BytesIO(data)) as img:
            out = io.BytesIO()
            save_args = {"format": expected_format}

            if getattr(img, "is_animated", False):
                save_args["save_all"] = True
            if expected_format == "JPEG":
                save_args["quality"] = "keep"

            img.save(out, **save_args)
            return out.getvalue()

    except (Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        return None

def delete_image_if_unused(image):
    """
    Delete an uploaded image unless another beverage still references it.
    Only files the admin page uploaded (under /mount/img/) are ever removed.
    """
    if not image or not image.startswith(IMG_URL_PREFIX):
        return

    with engine.connect() as conn:
        still_used = conn.execute(
            select(beverages.c.id).where(beverages.c.image == image).limit(1)
        ).first()

    if still_used:
        return

    file_path = IMG_DIR / Path(image).name
    file_path.unlink(missing_ok=True)

def parse_text(field, required=False, max_length=MAX_TEXT_LENGTH):
    value = request.form.get(field, "").strip()

    if required and not value:
        raise ValueError(f"{field.capitalize()} is required")
    if len(value) > max_length:
        raise ValueError(f"{field.capitalize()} must be at most {max_length} characters")

    return value or None

def parse_number(field, cast, low, high):
    """
    Parse an optional numeric form field. Raises ValueError with a
    user-facing message for non-numbers, NaN/inf and out-of-range values.
    """
    raw = request.form.get(field, "").strip()
    if not raw:
        return None

    try:
        value = cast(raw)
    except ValueError:
        raise ValueError(f"{field.upper()} must be a number") from None

    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{field.upper()} must be between {low} and {high}")

    return value

def load_srm_map():
    with SRM_FILE.open() as f:
        return json.load(f)

def srm_to_hex(srm_value, srm_map):
    """
    Given a decimal SRM value, find the closest color hex in srm_map.
    """
    keys = [float(k) for k in srm_map.keys()]
    closest = min(keys, key=lambda x: abs(x - srm_value))
    return srm_map[f"{closest:.1f}"]

def is_safe_untappd_url(url):
    """
    Only allow http(s) links pointing to untappd.com, blocking
    javascript:/data: URLs that would execute in the guest's browser.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    host = (parsed.hostname or "").lower()

    return (
        parsed.scheme in ("http", "https")
        and (host == "untappd.com" or host.endswith(".untappd.com"))
    )

def normalize_drink(d, srm_map):
    d["display_ibu"] = d.get("ibu")

    # The database can also be edited by hand, so re-check links on render
    if d.get("untappd") and not is_safe_untappd_url(d["untappd"]):
        d["untappd"] = None

    color_field = d.get("color")
    hex_field = d.get("color_hex")

    color_hex = None
    display_srm = None

    if isinstance(color_field, (int, float)):
        display_srm = float(color_field)
        color_hex = srm_to_hex(display_srm, srm_map)

    elif isinstance(hex_field, str) and HEX_COLOR_RE.fullmatch(hex_field):
        color_hex = hex_field

    if not color_hex:
        color_hex = "#333333"

    d["display_color_hex"] = color_hex
    d["display_srm"] = display_srm

    return d

# --------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
