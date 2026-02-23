import os
from pathlib import Path
import re
from flask import (
    Flask, render_template, request, json,
    redirect, url_for, flash, send_from_directory
)
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from werkzeug.utils import secure_filename

# --------------------
# App Setup
# --------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE_ME_NOW")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

SRM_FILE = Path("srm_colors.json")

MOUNT_DIR = Path("mount")
DRINKS_FILE = MOUNT_DIR / "drinks.json"
IMG_DIR = MOUNT_DIR / "img"
BACKGROUND_FILE = MOUNT_DIR / "background.png"
FAVICON_FILE = MOUNT_DIR / "favicon.png"

PNG_EXTENSION = ".png"
PNG_MIMETYPE = "image/png"
BEVERAGE_CATEGORIES = ("taps", "bottles", "spirits")

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB limit

# --------------------
# Authentication Setup
# --------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password")

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# --------------------
# Public Routes
# --------------------

@app.route("/")
def index():
    with DRINKS_FILE.open() as f:
        data = json.load(f)

    srm_map = load_srm_map()

    for section in ("taps", "bottles", "spirits"):
        items = data.get(section, [])

        normalized = [normalize_drink(item, srm_map) for item in items]

        normalized.sort(key=lambda x: x.get("number", 9999))
        data[section] = normalized

    return render_template("index.html", data=data)

# --------------------
# Login Routes
# --------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USER and password == ADMIN_PASS:
            login_user(User(username))
            return redirect(url_for("admin"))

        flash("Invalid credentials")

    return render_template("login.html")

@app.route("/logout")
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
    category = request.form.get("category")
    name = request.form.get("name")

    if category not in ["taps", "bottles", "spirits"]:
        flash("Invalid category")
        return redirect(url_for("admin"))

    data = load_drinks()

    image_to_check = None
    new_list = []

    # ---- Remove item and capture image path ----
    for item in data[category]:
        if item.get("name") == name:
            image_to_check = item.get("image")
        else:
            new_list.append(item)

    if image_to_check is None:
        flash("Item not found")
        return redirect(url_for("admin"))

    data[category] = new_list

    # ---- Check if image still used elsewhere ----
    image_still_used = False

    for cat in ["taps", "bottles", "spirits"]:
        for item in data[cat]:
            if item.get("image") == image_to_check:
                image_still_used = True
                break

    # ---- Delete image if unused ----
    if not image_still_used and image_to_check:
        # image_to_check looks like "/mount/img/file.png"
        filename = Path(image_to_check).name
        file_path = IMG_DIR / filename

        if file_path.exists():
            file_path.unlink()

    save_drinks(data)
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
    
    if not request.form.get("name"):
        flash("Name is required")
        return redirect(url_for("admin"))
    
    if category == "taps":
        if not request.form.get("number"):
            flash("Number is required")
            return redirect(url_for("admin"))

    data = load_drinks()

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

    # ---- Generate safe filename from beverage name ----
    raw_name = request.form.get("name", "")

    if not raw_name.strip():
        flash("Name is required")
        return redirect(url_for("admin"))

    # Normalize
    safe_name = raw_name.strip().lower()

    # Replace whitespace with underscore
    safe_name = re.sub(r"\s+", "_", safe_name)

    # Remove non-alphanumeric (keep underscore and dash)
    safe_name = re.sub(r"[^a-z0-9_-]", "", safe_name)

    if not safe_name:
        flash("Invalid beverage name")
        return redirect(url_for("admin"))

    filename = f"{safe_name}{original_ext}"
    save_path = IMG_DIR / filename

    # ---- Prevent overwrite by adding suffix ----
    counter = 1
    while save_path.exists():
        filename = f"{safe_name}_{counter}{original_ext}"
        save_path = IMG_DIR / filename
        counter += 1

    image_file.save(save_path)

    image_path = f"/mount/img/{filename}"

    # ---------- Build Item ----------
    item = {
        "name": request.form.get("name"),
        "style": request.form.get("style"),
        "image": image_path,
    }

    # Attribute mapping
    if request.form.get("abv"):
        item["abv"] = float(request.form.get("abv"))

    if request.form.get("untappd"):
        item["untappd"] = request.form.get("untappd")

    if request.form.get("number"):
        item["number"] = int(request.form.get("number"))

    if request.form.get("color"):
        item["color"] = float(request.form.get("color"))

    if request.form.get("ibu"):
        item["ibu"] = int(request.form.get("ibu"))

    if request.form.get("info"):
        item["info"] = request.form.get("info")

    if request.form.get("kcal"):
        item["kcal"] = int(request.form.get("kcal"))

    # ---------- Tap Override ----------
    if category == "taps" and "number" in item:
        existing_tap = next(
            (t for t in data["taps"] if t.get("number") == item["number"]),
            None
        )

        if existing_tap:
            # Delete existing image file
            image_path = existing_tap.get("image")
            if image_path:
                filename = os.path.basename(image_path)
                full_path = os.path.join(IMG_DIR, filename)

                if os.path.exists(full_path):
                    os.remove(full_path)

        # Remove old tap entry
        data["taps"] = [
            t for t in data["taps"]
            if t.get("number") != item["number"]
        ]

    data[category].append(item)

    save_drinks(data)
    flash("Item added successfully")

    return redirect(url_for("admin"))

@app.route("/admin/update_background_image", methods=["POST"])
@login_required
def update_background_image():
    file = request.files.get("background_file")

    if not file or file.filename == "":
        flash("No file selected")
        return redirect(url_for("admin"))

    if Path(file.filename).suffix.lower() != PNG_EXTENSION:
        flash("Only PNG files are allowed")
        return redirect(url_for("admin"))

    if file.mimetype != PNG_MIMETYPE:
        flash("Invalid file type")
        return redirect(url_for("admin"))

    file.save(BACKGROUND_FILE)
    flash("Background updated successfully")

    return redirect(url_for("admin"))

@app.route("/admin/update_favicon", methods=["POST"])
@login_required
def update_favicon():
    file = request.files.get("favicon_file")

    if not file or file.filename == "":
        flash("No file selected")
        return redirect(url_for("admin"))

    if Path(file.filename).suffix.lower() != PNG_EXTENSION:
        flash("Only PNG files are allowed")
        return redirect(url_for("admin"))

    if file.mimetype != PNG_MIMETYPE:
        flash("Invalid file type")
        return redirect(url_for("admin"))

    file.save(FAVICON_FILE)
    flash("Favicon updated successfully")

    return redirect(url_for("admin"))

# --------------------
# Helpers
# --------------------

@app.route("/mount/<path:filename>")
def mounted_files(filename):
    return send_from_directory(MOUNT_DIR, filename)

def load_drinks():
    with open(DRINKS_FILE, "r") as f:
        return json.load(f)

def save_drinks(data):
    with open(DRINKS_FILE, "w") as f:
        json.dump(data, f, indent=2)

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

def normalize_drink(d, srm_map):
    d["display_ibu"] = d.get("ibu")

    color_field = d.get("color")
    srm_field = d.get("srm")

    color_hex = None
    display_srm = None

    if isinstance(color_field, (int, float)):
        display_srm = float(color_field)
        color_hex = srm_to_hex(display_srm, srm_map)

    elif isinstance(srm_field, (int, float)):
        display_srm = float(srm_field)
        color_hex = srm_to_hex(display_srm, srm_map)

    elif isinstance(color_field, str):
        color_hex = color_field

    if not color_hex:
        color_hex = "#333333"

    d["display_color_hex"] = color_hex
    d["display_srm"] = display_srm

    return d

# --------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
