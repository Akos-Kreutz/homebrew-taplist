from flask import Flask, render_template, json, send_from_directory
from pathlib import Path
import os

app = Flask(__name__)

SRM_FILE = Path("srm_colors.json")
MOUNT_DIR = Path("mount")
DRINKS_FILE = MOUNT_DIR / "drinks.json"

@app.route("/mount/<path:filename>")
def mounted_files(filename):
    return send_from_directory(MOUNT_DIR, filename)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
