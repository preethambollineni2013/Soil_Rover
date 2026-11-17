"""Soil analysis: laser texture, colour, soil type, crop suggestions and water ranking.

These are simple, explainable rules. Calibrate the thresholds in config.py against samples you
have tested in a lab, and treat the output as a field guide, not a replacement for a soil test.
"""
import colorsys
import math

import numpy as np

import config as C


# ------------------------------------------------------------------ image features
def laser_profile(on_rgb, off_rgb):
    """Find the laser line (frame with laser minus frame without) and measure how bumpy it is."""
    on, off = on_rgb.astype(np.int16), off_rgb.astype(np.int16)
    d = (on[:, :, 0] - off[:, :, 0]) - 0.5 * ((on[:, :, 1] - off[:, :, 1]) + (on[:, :, 2] - off[:, :, 2]))
    d = np.clip(d, 0, None)
    h, w = d.shape
    peak = d.argmax(axis=0)
    ok = d[peak, np.arange(w)] > C.LASER_THRESH
    if ok.sum() < 0.2 * w:
        return {"ok": False, "reason": "laser line not found"}
    xs, ys = [], []
    for x in np.nonzero(ok)[0]:
        y0, y1 = max(peak[x] - 8, 0), min(peak[x] + 9, h)
        wts = d[y0:y1, x].astype(np.float64) ** 2
        ys.append((np.arange(y0, y1) * wts).sum() / wts.sum())
        xs.append(x)
    xs, ys = np.array(xs, float), np.array(ys)
    res = ys - np.polyval(np.polyfit(xs, ys, 1), xs)
    keep = np.abs(res) < 3 * res.std() + 1e-9
    coef = np.polyfit(xs[keep], ys[keep], 1)
    res = ys[keep] - np.polyval(coef, xs[keep])
    k = 1.0 / (C.PX_PER_MM * math.sin(math.radians(C.TRI_ANGLE_DEG)))   # pixels -> mm of height
    relief = np.percentile(res, 95) - np.percentile(res, 5)
    return {"ok": True, "coverage": round(float(ok.mean()), 2),
            "roughness_mm": round(float(res.std() * k), 2), "relief_mm": round(float(relief * k), 2)}


def color_features(rgb):
    h, w, _ = rgb.shape
    c = rgb[h // 4:3 * h // 4, w // 4:3 * w // 4].astype(np.float32)
    mean = c.reshape(-1, 3).mean(0)
    hh, s, v = colorsys.rgb_to_hsv(*(mean / 255.0))
    g = c.mean(2)
    grain = (np.abs(np.diff(g, axis=1)).mean() + np.abs(np.diff(g, axis=0)).mean()) / 2
    return {"rgb": [int(x) for x in mean], "hue": int(round(hh * 360)), "sat": round(s, 2),
            "val": round(v, 2), "grain": round(float(grain), 1)}


def texture_class(laser, color):
    if laser and laser.get("ok"):
        r = laser["roughness_mm"]
        return "smooth" if r < C.ROUGH_SMOOTH_MM else "coarse" if r > C.ROUGH_COARSE_MM else "medium"
    g = color["grain"]
    return "smooth" if g < 3 else "coarse" if g > 8 else "medium"


def classify_soil(color, tex):
    h, s, v = color["hue"], color["sat"], color["val"]
    if v < 0.25:
        return "black", "Black / dark clay-rich soil"
    if (h <= 25 or h >= 340) and s > 0.35 and v < 0.75:
        return "red", "Red soil (laterite / red loam)"
    if tex == "coarse" and v >= 0.45:
        return "sandy", "Sandy / gravelly soil"
    if tex == "smooth" and v < 0.55:
        return "clay", "Clay-rich soil"
    return "loam", "Loam"


# ------------------------------------------------------------------ crops
# soils: how well the crop likes each soil class (1 = good). n/p/k: nutrient level the crop wants.
CROPS = {
    "Rice":       dict(ph=(5.5, 7.0), soils=dict(clay=1, black=.8, loam=.7), n=2, p=1, k=1, water="high", temp=(20, 35)),
    "Wheat":      dict(ph=(6.0, 7.5), soils=dict(loam=1, clay=.8, black=.8), n=2, p=1, k=1, water="med", temp=(10, 25)),
    "Maize":      dict(ph=(5.8, 7.0), soils=dict(loam=1, red=.7, sandy=.6), n=2, p=1, k=1, water="med", temp=(18, 32)),
    "Cotton":     dict(ph=(6.0, 8.0), soils=dict(black=1, clay=.8, loam=.7), n=1, p=1, k=1, water="med", temp=(21, 35)),
    "Sugarcane":  dict(ph=(6.0, 8.0), soils=dict(loam=1, clay=.9, black=.8), n=2, p=1, k=2, water="high", temp=(20, 35)),
    "Groundnut":  dict(ph=(5.5, 7.0), soils=dict(sandy=1, red=.9, loam=.8), n=0, p=1, k=1, water="low", temp=(20, 32)),
    "Chickpea":   dict(ph=(6.0, 8.0), soils=dict(loam=1, black=.9, sandy=.7), n=0, p=1, k=0, water="low", temp=(15, 30)),
    "Pigeon pea": dict(ph=(5.0, 7.5), soils=dict(red=1, loam=.9, sandy=.7), n=0, p=1, k=0, water="low", temp=(20, 35)),
    "Soybean":    dict(ph=(6.0, 7.0), soils=dict(loam=1, black=.9, clay=.7), n=0, p=1, k=1, water="med", temp=(20, 32)),
    "Potato":     dict(ph=(5.0, 6.5), soils=dict(loam=1, sandy=.9, red=.7), n=2, p=2, k=2, water="med", temp=(10, 25)),
    "Tomato":     dict(ph=(6.0, 6.8), soils=dict(loam=1, red=.8, sandy=.7), n=1, p=2, k=2, water="med", temp=(18, 30)),
    "Pearl millet": dict(ph=(5.5, 7.5), soils=dict(sandy=1, red=.9, loam=.8), n=0, p=0, k=0, water="low", temp=(25, 38)),
    "Sorghum":    dict(ph=(5.5, 8.0), soils=dict(black=1, loam=.9, red=.8, sandy=.6), n=1, p=0, k=0, water="low", temp=(22, 35)),
    "Mustard":    dict(ph=(6.0, 7.5), soils=dict(loam=1, sandy=.8, clay=.7), n=1, p=1, k=0, water="low", temp=(10, 25)),
    "Banana":     dict(ph=(6.0, 7.5), soils=dict(loam=1, clay=.7, red=.7), n=2, p=1, k=2, water="high", temp=(22, 35)),
    "Turmeric":   dict(ph=(5.5, 7.5), soils=dict(loam=1, red=.9, clay=.7), n=1, p=1, k=2, water="high", temp=(20, 32)),
}
LEVEL_NAMES = ["low", "medium", "high"]


def level(v, lims):
    return 0 if v < lims[0] else 2 if v > lims[1] else 1


def nutrient_levels(soil):
    return {"n": level(soil["n"], C.N_LEVELS), "p": level(soil["p"], C.P_LEVELS), "k": level(soil["k"], C.K_LEVELS)}


def moisture_class(m):
    return "dry" if m < C.MOISTURE_DRY else "wet" if m > C.MOISTURE_WET else "moist"


def recommend(soil, soil_class, top=3):
    """Rank crops for one sample. soil = reading dict from the RS485 probe."""
    have = nutrient_levels(soil)
    ph, temp, moist = soil["ph"], soil.get("temp_c", 25.0), soil.get("moisture", 20.0)
    ranked = []
    for name, c in CROPS.items():
        lo, hi = c["ph"]
        dph = 0.0 if lo <= ph <= hi else min(abs(ph - lo), abs(ph - hi))
        f_ph = max(0.0, 1.0 - dph / 1.5)
        f_soil = c["soils"].get(soil_class, 0.25)
        f_nut = np.mean([1.0 if have[k] >= c[k] else 0.55 if have[k] == c[k] - 1 else 0.2 for k in "npk"])
        dt = 0.0 if c["temp"][0] <= temp <= c["temp"][1] else min(abs(temp - c["temp"][0]), abs(temp - c["temp"][1]))
        f_temp = max(0.0, 1.0 - dt / 10.0)
        score = 0.35 * f_ph + 0.30 * f_soil + 0.25 * f_nut + 0.10 * f_temp
        notes = []
        if ph < lo - 0.3:
            notes.append(f"soil pH {ph} is acidic for this crop: add lime")
        elif ph > hi + 0.3:
            notes.append(f"soil pH {ph} is alkaline for this crop: add gypsum or organic matter")
        for k, label in (("n", "nitrogen"), ("p", "phosphorus"), ("k", "potassium")):
            if have[k] < c[k]:
                notes.append(f"low {label}: fertilise")
        if c["water"] == "high" and moisture_class(moist) == "dry":
            notes.append("needs irrigation")
        if c["water"] == "low" and moisture_class(moist) == "wet":
            notes.append("waterlogging risk")
        ranked.append({"name": name, "score": int(round(score * 100)), "notes": notes})
    ranked.sort(key=lambda r: -r["score"])
    return ranked[:top]


def analyse(on_rgb, off_rgb, soil, thermal=None):
    """Combine every measurement for one stop into a result dict."""
    laser = laser_profile(on_rgb, off_rgb) if on_rgb is not None else {"ok": False, "reason": "no laser frame"}
    color = color_features(off_rgb)
    tex = texture_class(laser, color)
    cls, label = classify_soil(color, tex)
    out = {"laser": laser, "color": color, "texture": tex, "soil_class": cls, "soil_label": label}
    if soil:
        out["moisture_class"] = moisture_class(soil["moisture"])
        out["levels"] = {k: LEVEL_NAMES[v] for k, v in nutrient_levels(soil).items()}
        out["crops"] = recommend(soil, cls)
    return out


def water_rank(samples):
    """Rank sample stops by how likely they are to hold water: wet probe reading, cooler ground."""
    temps = [s["thermal"]["mean"] for s in samples if s.get("thermal")]
    ref = float(np.median(temps)) if temps else None
    out = []
    for s in samples:
        soil = s.get("soil")
        if not soil:
            continue
        bonus = 1.5 * (ref - s["thermal"]["mean"]) if ref is not None and s.get("thermal") else 0.0
        out.append({"id": s["id"], "score": round(soil["moisture"] + bonus, 1), "moisture": soil["moisture"]})
    out.sort(key=lambda r: -r["score"])
    return out
