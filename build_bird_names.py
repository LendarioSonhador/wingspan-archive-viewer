#!/usr/bin/env python3
"""
Build bird_names.json  (card ID -> bird common name) for the Wingspan viewer.

Source of truth = the Wingspan install itself, so the table matches whatever
version/expansions are installed and needs no internet:
  1. Every bird has an asset bundle named "<slug>_<id>.assetbundle" in
     StreamingAssets/AssetBundles  -> gives a 100%% id->slug mapping.
  2. data.unity3d contains many display names as text -> gives exact
     hyphenation/punctuation for the ~287 birds that appear there.
  3. For the rest we title-case the slug and repair the two predictable
     punctuation cases: eponymous possessives (Annas -> Anna's) and
     colour/size + participle compounds (Red Tailed -> Red-Tailed).

Re-run this after a game update, then rebuild the exe:
    python build_bird_names.py
Point --game at your install if it isn't on F:.
"""
import os, re, json, argparse

# Probe the usual Steam library locations; override with --game if yours is elsewhere.
CANDIDATE_GAMES = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Wingspan\Wingspan_Data",
    r"C:\SteamLibrary\steamapps\common\Wingspan\Wingspan_Data",
    r"D:\SteamLibrary\steamapps\common\Wingspan\Wingspan_Data",
    r"E:\SteamLibrary\steamapps\common\Wingspan\Wingspan_Data",
    r"F:\SteamLibrary\steamapps\common\Wingspan\Wingspan_Data",
]
DEFAULT_GAME = next((p for p in CANDIDATE_GAMES if os.path.isdir(p)), CANDIDATE_GAMES[0])

POSS = {'abbotts','annas','bairds','barrows','bells','bewicks','bonapartes','brandts','brewers',
 'bullocks','cassins','clarks','coopers','costas','couchs','forsters','franklins','gambels',
 'hammonds','harriss','heermanns','huttons','kirtlands','lawrences','lecontes','lewiss',
 'lincolns','lucys','macgillivrays','nuttalls','rosss','sabines','says','scotts','stellers',
 'swainsons','townsends','vauxs','williamsons','wilsons','wrights','xantuss','bachmans',
 'bendires','botteris','spragues','wurdemanns'}
COLORSIZE = {'red','black','white','blue','yellow','golden','green','gray','grey','rose','ruby','ash',
 'buff','olive','chestnut','rusty','violet','long','short','sharp','rough','ring','broad','narrow',
 'cinnamon','lazuli','pied','pink','purple','brown','tri','double','scissor','swallow','fork'}
COLOR2 = {'gray','grey','green','blue','crowned','backed','winged'}

def norm(s):
    s = s.replace('’', "'").replace("'", "")
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')

def title(slug):
    return slug.replace('_', ' ').title()

def build(game_data):
    ab = os.path.join(game_data, 'StreamingAssets', 'AssetBundles')
    id2slug = {}
    for fn in os.listdir(ab):
        if fn.endswith('.assetbundle') and '_vo_' not in fn:
            m = re.match(r'^(.*)_(\d+)\.assetbundle$', fn)
            if m:
                id2slug[int(m.group(2))] = m.group(1)
    slug2id = {v: k for k, v in id2slug.items()}

    exact = {}
    data_path = os.path.join(game_data, 'data.unity3d')
    if os.path.isfile(data_path):
        text = open(data_path, 'rb').read().decode('utf-8', 'ignore')
        phrase = re.compile(r"[A-Z][a-zé]+(?:['’]s)?(?:[ -][A-Za-zé]+(?:['’]s)?){1,3}")
        for m in phrase.finditer(text):
            p = m.group().replace('’', "'")
            k = norm(p)
            if k in slug2id and k not in exact:
                exact[k] = p

    def fix(slug, name):
        words = slug.split('_')
        if words and words[0] in POSS and "'" not in name:
            surname = words[0][:-1].title()
            rest = ' '.join(w.title() for w in words[1:])
            name = ("%s's %s" % (surname, rest)).strip()
        if name == title(slug):
            w = slug.split('_')
            if len(w) >= 2 and w[0] in COLORSIZE and (w[1].endswith('ed') or w[1] in COLOR2):
                name = ' '.join([w[0].title() + '-' + w[1].title()] + [x.title() for x in w[2:]])
        return name

    return {i: fix(s, exact.get(s) or title(s)) for i, s in id2slug.items()}, len(exact)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=DEFAULT_GAME, help='path to Wingspan_Data')
    ap.add_argument('-o', '--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bird_names.json'))
    a = ap.parse_args()
    id2name, exact = build(a.game)
    json.dump({str(i): n for i, n in id2name.items()}, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False)
    print("Wrote %d bird names (%d exact from game data) -> %s" % (len(id2name), exact, a.out))

if __name__ == '__main__':
    main()
