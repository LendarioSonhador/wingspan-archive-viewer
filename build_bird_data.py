#!/usr/bin/env python3
"""
Build bird_data.json + the bird_art/ folder for the Wingspan viewer, using the
open-source Wingsearch dataset (github.com/navarog/wingsearch, GPLv3):

  - master.json     -> base victory points, food cost, nest, habitat, expansion
  - cards/birds-diffusion/<id>.webp  -> copyright-safe "Unofficial Fan Art" images

Join is by BIRD NAME (Wingsearch IDs differ from the game's internal IDs), using
our game-id -> name table in bird_names.json. Output is keyed by the GAME's bird
id (what the save files use):

  bird_data.json:  { "<gameId>": {name, vp, food, nest, hab[], set} , ... }
  bird_art/<gameId>.webp  (resized ~340px wide)

Run after refreshing the Wingsearch checkout:
    python build_bird_data.py --wingsearch ./wingsearch
"""
import os, re, json, argparse, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

def norm(s):
    s = (s or "").replace("’", "'").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wingsearch", default=os.path.join(HERE, "wingsearch"))
    ap.add_argument("--names", default=os.path.join(HERE, "bird_names.json"))
    ap.add_argument("--maxw", type=int, default=340)
    a = ap.parse_args()

    assets = os.path.join(a.wingsearch, "src", "assets")
    master = json.load(open(os.path.join(assets, "data", "master.json"), encoding="utf-8"))
    art_src = os.path.join(assets, "cards", "birds-diffusion")
    by_name = {}
    for e in master:
        if e.get("CardType") != "Bird":
            continue
        k = norm(e.get("Common name"))
        if k and k not in by_name:
            by_name[k] = e

    names = json.load(open(a.names, encoding="utf-8"))       # gameId -> name

    from PIL import Image
    art_out = os.path.join(HERE, "bird_art")
    if os.path.isdir(art_out):
        shutil.rmtree(art_out)
    os.makedirs(art_out)

    HABS = [("Forest", "Forest"), ("Grassland", "Grassland"), ("Wetland", "Wetland")]
    FOODS = [("Invertebrate", "inv"), ("Seed", "seed"), ("Fish", "fish"),
             ("Fruit", "fruit"), ("Rodent", "rodent"), ("Nectar", "nectar"), ("Wild (food)", "wild")]
    def foods_of(e):
        return [[key, int(v)] for col, key in FOODS
                for v in [e.get(col)] if isinstance(v, (int, float)) and v > 0]
    data = {}
    matched = withart = 0
    for gid, nm in names.items():
        e = by_name.get(norm(nm))
        rec = {"name": nm}
        if e:
            matched += 1
            vp = e.get("Victory points")
            food = e.get("Total food cost")
            rec["vp"] = int(vp) if isinstance(vp, (int, float)) else None
            rec["food"] = int(food) if isinstance(food, (int, float)) else None
            rec["nest"] = e.get("Nest type") or None
            rec["set"] = e.get("Set") or None
            rec["hab"] = [name for key, name in HABS if e.get(key) == "X"]
            # extra fields to render cards that mirror the real Wingspan card
            if e.get("Scientific name"): rec["sci"] = e.get("Scientific name")
            egg = e.get("Egg limit"); wing = e.get("Wingspan")
            if isinstance(egg, (int, float)): rec["egg"] = int(egg)
            if isinstance(wing, (int, float)): rec["wing"] = int(wing)
            rec["foods"] = foods_of(e)
            rec["foodChoice"] = e.get("/ (food cost)") == "X"
            rec["foodStar"] = e.get("* (food cost)") == "X"
            if e.get("Color"): rec["color"] = e.get("Color")
            if e.get("Power text"): rec["power"] = e.get("Power text")
            src = os.path.join(art_src, str(e.get("id")) + ".webp")
            if os.path.isfile(src):
                try:
                    im = Image.open(src).convert("RGBA")
                    if im.width > a.maxw:
                        h = round(im.height * a.maxw / im.width)
                        im = im.resize((a.maxw, h), Image.LANCZOS)
                    im.save(os.path.join(art_out, gid + ".webp"), "WEBP", quality=80, method=6)
                    rec["art"] = True
                    withart += 1
                except Exception as ex:
                    print("  art fail", nm, ex)
        data[gid] = rec

    json.dump(data, open(os.path.join(HERE, "bird_data.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    total_art_mb = sum(os.path.getsize(os.path.join(art_out, f)) for f in os.listdir(art_out)) / 1e6
    print("birds total: %d | with data: %d | with art: %d" % (len(data), matched, withart))
    print("bird_art/ size: %.1f MB (%d files)" % (total_art_mb, len(os.listdir(art_out))))
    print("wrote bird_data.json")

if __name__ == "__main__":
    main()
