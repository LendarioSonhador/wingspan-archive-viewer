#!/usr/bin/env python3
"""
One-off augmentation: enrich the existing bird_data.json with the extra
Wingsearch master.json fields needed to render cards that mirror the real
Wingspan card (food *types*, egg limit, wingspan, scientific name, nest,
power color + text). Joins by normalized common name, same as build_bird_data.py.
Art is untouched. Safe to re-run.

    python augment_bird_data.py --master <path to master.json>
"""
import os, re, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))

def norm(s):
    s = (s or "").replace("’", "'").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())

FOODS = [("Invertebrate", "inv"), ("Seed", "seed"), ("Fish", "fish"),
         ("Fruit", "fruit"), ("Rodent", "rodent"), ("Nectar", "nectar"),
         ("Wild (food)", "wild")]

def foods_of(e):
    out = []
    for col, key in FOODS:
        v = e.get(col)
        if isinstance(v, (int, float)) and v > 0:
            out.append([key, int(v)])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "bird_data.json"))
    ap.add_argument("--names", default=os.path.join(HERE, "bird_names.json"))
    a = ap.parse_args()

    master = json.load(open(a.master, encoding="utf-8"))
    by_name = {}
    for e in master:
        if e.get("CardType") != "Bird":
            continue
        k = norm(e.get("Common name"))
        if k and k not in by_name:
            by_name[k] = e

    data = json.load(open(a.data, encoding="utf-8"))
    names = json.load(open(a.names, encoding="utf-8"))

    enriched = 0
    for gid, rec in data.items():
        nm = names.get(gid) or rec.get("name")
        e = by_name.get(norm(nm))
        if not e:
            continue
        sci = e.get("Scientific name")
        egg = e.get("Egg limit")
        wing = e.get("Wingspan")
        if sci: rec["sci"] = sci
        if isinstance(egg, (int, float)): rec["egg"] = int(egg)
        if isinstance(wing, (int, float)): rec["wing"] = int(wing)
        rec["foods"] = foods_of(e)
        rec["foodChoice"] = e.get("/ (food cost)") == "X"   # cost is an OR between foods
        rec["foodStar"] = e.get("* (food cost)") == "X"      # alternative / "no food" option
        col = e.get("Color")
        if col: rec["color"] = col
        pt = e.get("Power text")
        if pt: rec["power"] = pt
        enriched += 1

    json.dump(data, open(a.data, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("birds in data: %d | enriched from master: %d" % (len(data), enriched))
    print("wrote", a.data)

if __name__ == "__main__":
    main()
