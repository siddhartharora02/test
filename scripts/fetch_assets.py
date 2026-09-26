"""Download and cache the free CC0 assets used by the office render.

Sources:
  * Poly Haven  (https://polyhaven.com)  - HDRI, PBR textures, furniture/decor models
  * ambientCG   (https://ambientcg.com)  - PBR textures

Everything lands in <repo>/assets/ (git-ignored). Files that are already
present are skipped, so re-running is cheap. Works with plain `python3`
(macOS / Linux) and inside Blender's bundled Python.

    python3 scripts/fetch_assets.py            # fetch everything
"""

import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "assets")

PH_API = "https://api.polyhaven.com/files/"
ACG_GET = "https://ambientcg.com/get?file={id}_{res}-JPG.zip"

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
HDRI = ("belfast_farmhouse", "4k")  # partly cloudy morning, trees on the horizon

PH_TEXTURES = {  # id -> resolution; maps: diffuse, normal (GL), roughness, displacement
    "laminate_floor_02": "2k",  # wood-look plank floor tiles
    "oak_veneer_01": "2k",  # desk top, shelves, cabinet top
    "rough_linen": "2k",  # sheer curtains
}

PH_MODELS = {
    "potted_plant_01": "2k",  # tall floor plant
    "potted_plant_02": "2k",  # medium floor plant
    "potted_plant_04": "1k",  # small succulent for the shelves
    "desk_lamp_arm_01": "2k",
    "modern_ceiling_lamp_01": "2k",  # pendant over the round table
    "dining_chair_02": "2k",  # round-table chairs
    "decorative_book_set_01": "2k",
    "book_encyclopedia_set_01": "2k",
    "ceramic_vase_01": "1k",
    "brass_vase_03": "1k",
    "carved_wooden_elephant": "1k",
    "standing_picture_frame_02": "1k",
    "office_notepads": "1k",
    "stationery_supplies": "1k",
    "wall_clock": "1k",
    "round_spectacles": "1k",
}

ACG_TEXTURES = {
    "Carpet016": "2K",  # rug
    "PaintedPlaster017": "2K",  # painted walls / ceiling
    "Metal032": "2K",  # brushed metal
    "Fabric031": "2K",  # office chair upholstery
}


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------
def _ssl_context():
    for cafile in (os.environ.get("SSL_CERT_FILE"), "/root/.ccr/ca-bundle.crt"):
        if cafile and os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    try:
        import certifi  # noqa: F401

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url, dest):
    """Download url -> dest atomically. Uses urllib, falls back to curl."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "office-render/1.0"})
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except Exception as exc:  # e.g. missing CA bundle in Blender's Python on macOS
        if not shutil.which("curl"):
            raise
        print(f"  urllib failed ({exc.__class__.__name__}), retrying with curl: {url}")
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", tmp, url], check=True)
    os.replace(tmp, dest)
    return dest


def _json(url):
    cache = os.path.join(ASSETS, "_api", url.rsplit("/", 1)[-1] + ".json")
    if not os.path.exists(cache):
        _download(url, cache)
    with open(cache) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Poly Haven
# ---------------------------------------------------------------------------
def hdri_path():
    name, res = HDRI
    return os.path.join(ASSETS, "polyhaven", "hdri", f"{name}_{res}.exr")


def fetch_hdri():
    name, res = HDRI
    files = _json(PH_API + name)
    return _download(files["hdri"][res]["exr"]["url"], hdri_path())


def ph_texture_dir(name):
    return os.path.join(ASSETS, "polyhaven", "textures", name)


def fetch_ph_texture(name, res):
    files = _json(PH_API + name)
    maps = {"Diffuse": "diff", "nor_gl": "nor_gl", "Rough": "rough", "Displacement": "disp"}
    out = {}
    for key, short in maps.items():
        if key in files:
            url = files[key][res]["jpg"]["url"]
            out[short] = _download(url, os.path.join(ph_texture_dir(name), f"{name}_{short}_{res}.jpg"))
    return out


def ph_model_blend(name):
    res = PH_MODELS[name]
    return os.path.join(ASSETS, "polyhaven", "models", name, f"{name}_{res}.blend")


def fetch_ph_model(name, res):
    files = _json(PH_API + name)
    blend = files["blend"][res]["blend"]
    folder = os.path.join(ASSETS, "polyhaven", "models", name)
    for rel, inc in blend.get("include", {}).items():
        _download(inc["url"], os.path.join(folder, rel))
    return _download(blend["url"], ph_model_blend(name))


# ---------------------------------------------------------------------------
# ambientCG
# ---------------------------------------------------------------------------
def acg_dir(asset_id):
    return os.path.join(ASSETS, "ambientcg", asset_id)


def fetch_acg(asset_id, res):
    folder = acg_dir(asset_id)
    marker = os.path.join(folder, ".done")
    if os.path.exists(marker):
        return folder
    zpath = os.path.join(ASSETS, "ambientcg", f"{asset_id}_{res}.zip")
    _download(ACG_GET.format(id=asset_id, res=res), zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(folder)
    os.remove(zpath)
    open(marker, "w").close()
    return folder


def acg_maps(asset_id):
    """Return {'diff','nor_gl','rough','disp','metal'} -> path for an ambientCG folder."""
    folder = acg_dir(asset_id)
    out = {}
    for fn in os.listdir(folder):
        low = fn.lower()
        if not low.endswith((".jpg", ".png")):
            continue
        if "_color" in low:
            out["diff"] = os.path.join(folder, fn)
        elif "_normalgl" in low:
            out["nor_gl"] = os.path.join(folder, fn)
        elif "_roughness" in low:
            out["rough"] = os.path.join(folder, fn)
        elif "_displacement" in low:
            out["disp"] = os.path.join(folder, fn)
        elif "_metalness" in low:
            out["metal"] = os.path.join(folder, fn)
    return out


# ---------------------------------------------------------------------------
def fetch_all(workers=6):
    jobs = [lambda: fetch_hdri()]
    jobs += [lambda n=n, r=r: fetch_ph_texture(n, r) for n, r in PH_TEXTURES.items()]
    jobs += [lambda n=n, r=r: fetch_ph_model(n, r) for n, r in PH_MODELS.items()]
    jobs += [lambda n=n, r=r: fetch_acg(n, r) for n, r in ACG_TEXTURES.items()]
    print(f"[assets] checking {len(jobs)} assets in {ASSETS}")
    with ThreadPoolExecutor(workers) as pool:
        for fut in [pool.submit(j) for j in jobs]:
            fut.result()
    print("[assets] all assets present")


if __name__ == "__main__":
    fetch_all()
    sys.exit(0)
