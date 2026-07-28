#!/usr/bin/env python3
"""
Wingspan Preserve Archive Viewer
================================
A friendly desktop app that reads YOUR Wingspan "Preserve Archive" (your past
games), decrypts them locally, and shows a visual dashboard of your results:
win rate, score trends, score breakdowns, head-to-head records, and a full
game log.

- 100% offline. Reads only your own Steam save files. Never touches the game,
  the network, or anyone else's data.
- Auto-detects your Steam save folder and figures out which player is "you".
- Covers solo/local games AND online (nakama) games.

Run it:
    python wingspan_viewer.py                 # opens the dashboard in a window
    python wingspan_viewer.py --html           # just write the HTML, don't open a window
    python wingspan_viewer.py "<remote folder>"  # point at a specific save folder

When packaged as wingspan_viewer.exe, friends just double-click it.

If a future Wingspan update changes the save encryption, the DES_KEY below is
the only thing that would need refreshing.
"""

import os, sys, json, base64, datetime, glob, argparse, webbrowser, tempfile

def resource_path(name):
    """Path to a bundled data file, whether running from source or a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(base, name),
                 os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), name)):
        if os.path.isfile(cand):
            return cand
    return os.path.join(base, name)

def load_bird_data():
    """gameId -> {name, vp, food, nest, hab[], set, art}. Falls back to names-only."""
    try:
        with open(resource_path("bird_data.json"), encoding="utf-8") as fh:
            return {int(k): v for k, v in json.load(fh).items()}
    except Exception:
        pass
    try:
        with open(resource_path("bird_names.json"), encoding="utf-8") as fh:
            return {int(k): {"name": v} for k, v in json.load(fh).items()}
    except Exception:
        return {}

BIRD_DATA = load_bird_data()

def collect_bird_art(games):
    """Base64 data-URIs for every bird that appears in these games (keeps the report self-contained)."""
    ids = set()
    for g in games:
        for p in g["players"]:
            for b in p.get("birds", []):
                ids.add(b["id"])
    art = {}
    for i in sorted(ids):
        path = resource_path(os.path.join("bird_art", "%d.webp" % i))
        if os.path.isfile(path):
            raw = open(path, "rb").read()
            art[str(i)] = "data:image/webp;base64," + base64.b64encode(raw).decode("ascii")
    return art

# Real Wingspan icons (from Wingsearch, github.com/navarog/wingsearch, GPLv3).
ICON_NAMES = ["invertebrate", "seed", "fish", "fruit", "rodent", "nectar", "wild",
              "bowl", "cavity", "ground", "platform", "star", "egg", "point", "wingspan",
              "forest", "grassland", "wetland", "card", "die", "predator", "flocking", "bird", "no-food"]

def collect_icons():
    """Base64 data-URIs for the bundled Wingspan icons; embedded once, referenced by CSS class."""
    out = {}
    for n in ICON_NAMES:
        path = resource_path(os.path.join("icons", n + ".webp"))
        if os.path.isfile(path):
            raw = open(path, "rb").read()
            out[n] = "data:image/webp;base64," + base64.b64encode(raw).decode("ascii")
    return out

# ============================ Wingspan crypto ================================
# Saves are base64 -> 10-byte header "V@1H@11@N4" -> DES-CBC (PKCS7). The IV is
# the first 8 bytes of the header, reused. (Recovered from the game's mono
# DESTransform key schedule; see project notes.)
DES_KEY = bytes.fromhex("9c30244604fcc4fc")
HEADER  = b"V@1H@11@N4"
APPID   = "1054490"
STEAM64_BASE = 76561197960265728   # SteamID64 = base + userdata account id

# ---- pure-Python DES fallback (so the app needs no dependencies at all) -----
_IP=[58,50,42,34,26,18,10,2,60,52,44,36,28,20,12,4,62,54,46,38,30,22,14,6,
     64,56,48,40,32,24,16,8,57,49,41,33,25,17,9,1,59,51,43,35,27,19,11,3,
     61,53,45,37,29,21,13,5,63,55,47,39,31,23,15,7]
_FP=[40,8,48,16,56,24,64,32,39,7,47,15,55,23,63,31,38,6,46,14,54,22,62,30,
     37,5,45,13,53,21,61,29,36,4,44,12,52,20,60,28,35,3,43,11,51,19,59,27,
     34,2,42,10,50,18,58,26,33,1,41,9,49,17,57,25]
_E=[32,1,2,3,4,5,4,5,6,7,8,9,8,9,10,11,12,13,12,13,14,15,16,17,
    16,17,18,19,20,21,20,21,22,23,24,25,24,25,26,27,28,29,28,29,30,31,32,1]
_P=[16,7,20,21,29,12,28,17,1,15,23,26,5,18,31,10,
    2,8,24,14,32,27,3,9,19,13,30,6,22,11,4,25]
_PC1=[57,49,41,33,25,17,9,1,58,50,42,34,26,18,10,2,59,51,43,35,27,
      19,11,3,60,52,44,36,63,55,47,39,31,23,15,7,62,54,46,38,30,22,
      14,6,61,53,45,37,29,21,13,5,28,20,12,4]
_PC2=[14,17,11,24,1,5,3,28,15,6,21,10,23,19,12,4,26,8,16,7,27,20,13,2,
      41,52,31,37,47,55,30,40,51,45,33,48,44,49,39,56,34,53,46,42,50,36,29,32]
_SHIFTS=[1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1]
_S=[
[14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7,0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8,
 4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0,15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13],
[15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10,3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5,
 0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15,13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9],
[10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8,13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1,
 13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7,1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12],
[7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15,13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9,
 10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4,3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14],
[2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9,14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6,
 4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14,11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3],
[12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11,10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8,
 9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6,4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13],
[4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1,13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6,
 1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2,6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12],
[13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7,1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2,
 7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8,2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11],
]
def _bits(data):
    out=[]
    for byte in data:
        for i in range(7,-1,-1): out.append((byte>>i)&1)
    return out
def _tobytes(bits):
    out=bytearray()
    for i in range(0,len(bits),8):
        b=0
        for j in range(8): b=(b<<1)|bits[i+j]
        out.append(b)
    return bytes(out)
def _perm(bits,table): return [bits[i-1] for i in table]
def _xor(a,b): return [x^y for x,y in zip(a,b)]
def _rot(bits,n): return bits[n:]+bits[:n]
def _subkeys(key):
    k=_perm(_bits(key),_PC1); C,D=k[:28],k[28:]; sk=[]
    for s in _SHIFTS:
        C=_rot(C,s); D=_rot(D,s); sk.append(_perm(C+D,_PC2))
    return sk
def _feistel(R,K):
    x=_xor(_perm(R,_E),K); out=[]
    for i in range(8):
        c=x[i*6:i*6+6]
        row=(c[0]<<1)|c[5]; col=(c[1]<<3)|(c[2]<<2)|(c[3]<<1)|c[4]
        v=_S[i][row*16+col]
        out+=[(v>>3)&1,(v>>2)&1,(v>>1)&1,v&1]
    return _perm(out,_P)
def _dec_block(block, subkeys):
    bits=_perm(_bits(block),_IP); L,R=bits[:32],bits[32:]
    for K in reversed(subkeys):
        L,R=R,_xor(L,_feistel(R,K))
    return _tobytes(_perm(R+L,_FP))
def _des_cbc_decrypt_pure(cipher, key, iv):
    sk=_subkeys(key); prev=iv; out=bytearray()
    for i in range(0,len(cipher),8):
        blk=cipher[i:i+8]
        out+=bytes(a^b for a,b in zip(_dec_block(blk,sk),prev))
        prev=blk
    return bytes(out)

try:
    from Crypto.Cipher import DES as _CDES
    def des_cbc_decrypt(cipher, key, iv):
        return _CDES.new(key, _CDES.MODE_CBC, iv).decrypt(cipher)
    FAST = True
except Exception:
    des_cbc_decrypt = _des_cbc_decrypt_pure
    FAST = False

def decrypt_save(raw):
    try:
        blob = base64.b64decode(raw)
    except Exception:
        return None
    if blob[:10] != HEADER:
        return None
    iv = blob[:8]
    body = blob[10:]
    body = body[:len(body) - (len(body) % 8)]
    pt = des_cbc_decrypt(body, DES_KEY, iv)
    if pt and 1 <= pt[-1] <= 8:      # strip PKCS7
        pt = pt[:-pt[-1]]
    return pt

# ==================== Steam save-folder auto-detection =======================
def find_remote_dirs():
    """Return list of (remote_dir, account_id) for Wingspan across all Steam accounts."""
    roots = []
    if os.name == "nt":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            roots.append(winreg.QueryValueEx(k, "SteamPath")[0])
        except Exception:
            pass
        roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        h = os.path.expanduser("~")
        roots += [os.path.join(h, ".steam/steam"),
                  os.path.join(h, ".local/share/Steam"),
                  os.path.join(h, "Library/Application Support/Steam")]
    seen = set(); out = []
    for r in roots:
        ud = os.path.join(r, "userdata")
        if not os.path.isdir(ud):
            continue
        for acct in os.listdir(ud):
            rem = os.path.join(ud, acct, APPID, "remote")
            canon = os.path.normcase(os.path.realpath(rem))   # dedupe same folder found via different roots/casing
            if os.path.isdir(rem) and canon not in seen:
                seen.add(canon); out.append((rem, acct))
    return out

# ============================ game parsing ===================================
SCORE = [("_bp","Birds"),("_bcp","Bonus cards"),("_gp","Goals"),("_ep","Eggs"),
         ("_cfp","Cached food"),("_tcp","Tucked cards"),("_snp","Nectar"),("_dlgp","Duet map")]

def player_label(p):
    return (p.get("Username") or "").strip() or p.get("ProfilePicture") or ("Player " + str(p.get("ID")))

def is_bot(p):
    if p.get("PlayerType") == 9:                 # Automa / AI
        return True
    u = (p.get("Username") or "")
    return u.startswith("AI_") or p.get("ProfilePicture") == "Automa"

HABITATS = [("_hf", "Forest"), ("_hg", "Grassland"), ("_hw", "Wetland")]

def habitat_stats(p):
    """Per-habitat totals AND a per-bird list with each bird's eggs/tucked/cached at game end."""
    out = {}
    bird_list = []
    for key, name in HABITATS:
        birds = (p.get(key) or {}).get("Birds", []) or []
        eggs = tucked = cached = 0
        for b in birds:
            be = b.get("e", 0) or 0
            bt = len(b.get("tc") or [])
            cf = b.get("cf") or {}
            bc = sum(v for v in cf.values() if isinstance(v, int))
            eggs += be; tucked += bt; cached += bc
            if "id" in b:
                bird_list.append({"id": b["id"], "hab": name, "e": be, "t": bt, "c": bc})
        out[name] = {"birds": len(birds), "eggs": eggs, "cached": cached, "tucked": tucked}
    return out, bird_list

def normalize_game(d, mtime, owner_sid, kind):
    scores = {s.get("_pid"): s for s in d.get("Scores", [])}
    players = {}
    for p in d.get("Players", []):
        players[str(p.get("ID"))] = p
    best = max((s.get("_ts", 0) for s in scores.values()), default=None)
    ranking = sorted(scores.items(), key=lambda kv: kv[1].get("_ts", 0), reverse=True)

    plist = []
    owner_index = None
    for rank, (pid, s) in enumerate(ranking, 1):
        p = players.get(str(pid), {})
        sid = (p.get("SteamID") or "").strip()
        bot = is_bot(p)
        is_owner = bool(owner_sid and sid == str(owner_sid))
        hab, bird_list = habitat_stats(p)
        row = {
            "label": player_label(p),
            "avatar": p.get("ProfilePicture") or "",
            "steamId": sid,
            "playerType": p.get("PlayerType"),
            "isBot": bot,
            "isOwner": is_owner,
            "total": s.get("_ts", 0),
            "rank": rank,
            "isWinner": s.get("_ts", 0) == best,
            "breakdown": {name: s.get(key, 0) for key, name in SCORE},
            "habitats": hab,
            "birds": bird_list,
        }
        if is_owner:
            owner_index = len(plist)
        plist.append(row)

    # Fallback owner detection when no SteamID matched (solo games have none):
    # the single human (PlayerType 0) is the archive owner.
    if owner_index is None:
        humans = [i for i, r in enumerate(plist)
                  if not r["isBot"] and r["playerType"] in (0, None) and not r["steamId"]]
        if len(humans) == 1:
            owner_index = humans[0]
            plist[owner_index]["isOwner"] = True

    # PRIVACY: SteamIDs have done their job (owner detection, just above) and the report
    # never displays them. Leaving them in would mean every shared WingspanArchive.html
    # carried the 64-bit SteamIDs of the user AND their online opponents, each of which
    # resolves straight to a Steam profile. Drop them before they reach the payload.
    for r in plist:
        r.pop("steamId", None)

    return {
        "id": d.get("MatchId") or "",
        "date": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": kind,                                   # "solo" | "online"
        "matchType": d.get("MatchType", ""),
        "gameMode": d.get("gameMode", ""),
        "rounds": d.get("RoundsCounter", ""),
        "finished": bool(d.get("IsFinished")),
        "numPlayers": len(plist),
        "winningScore": best,
        "players": plist,
        "ownerIndex": owner_index,
    }

def load_all_games(remotes):
    games = {}          # dedupe key -> (game, mtime, finished)
    total_files = 0
    for rem, acct in remotes:
        owner_sid = None
        try:
            owner_sid = STEAM64_BASE + int(acct)
        except Exception:
            pass
        local_files = glob.glob(os.path.join(rem, "local_*"))
        online_files = glob.glob(os.path.join(rem, "*.nakama-*"))
        for fp in local_files + online_files:
            total_files += 1
            try:
                pt = decrypt_save(open(fp, "rb").read())
                if not pt:
                    continue
                d = json.loads(pt.decode("utf-8"))
                if "Scores" not in d or "Players" not in d:
                    continue
                kind = "online" if ".nakama-" in os.path.basename(fp) else "solo"
                mtime = os.path.getmtime(fp)
                g = normalize_game(d, mtime, owner_sid, kind)
                key = g["id"] or os.path.basename(fp).split(".nakama-")[0]
                prev = games.get(key)
                # keep finished over unfinished; otherwise the newer file
                if (prev is None
                        or (g["finished"] and not prev["finished"])
                        or (g["finished"] == prev["finished"] and mtime > prev["_mtime"])):
                    g["_mtime"] = mtime
                    games[key] = g
            except Exception:
                continue
    out = []
    for g in games.values():
        g.pop("_mtime", None)
        out.append(g)
    out.sort(key=lambda g: g["date"])
    return out, total_files

# ============================ HTML dashboard =================================
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- The report is fully self-contained: inline CSS/JS, images as data: URIs, no network.
     "default-src 'none'" with no connect-src means this page CANNOT make an outbound
     request of any kind, so your game data physically cannot leave the machine, even if
     something malicious were ever smuggled in through a save file. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Wingspan Preserve Archive</title>
<style>
  :root{
    color-scheme: light;
    --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
    --brand:#2a78d6; --brand-soft:#cde2fb; --good:#0ca30c; --bad:#d03b3b; --good-ink:#006300;
    --hab-forest:#1f9d57; --hab-grass:#c98500; --hab-wet:#2f7fd6;
    --shadow:0 1px 2px rgba(11,11,11,.05),0 8px 24px rgba(11,11,11,.06);
  }
  @media (prefers-color-scheme: dark){
    :root:where(:not([data-theme="light"])){
      color-scheme: dark;
      --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
      --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
      --brand:#3987e5; --brand-soft:#184f95; --good:#0ca30c; --bad:#e66767; --good-ink:#0ca30c;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.5);
    }
  }
  :root[data-theme="dark"]{
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --brand:#3987e5; --brand-soft:#184f95; --good:#0ca30c; --bad:#e66767; --good-ink:#0ca30c;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.5);
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--page); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif; font-size:14px; line-height:1.45;}
  .wrap{max-width:1160px; margin:0 auto; padding:28px 22px 64px;}
  header.top{display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:6px;}
  .title h1{font-size:26px; margin:0; letter-spacing:-.02em;}
  /* header mark: the real Wingspan wings glyph (was a feather emoji, which tofus on Win10) */
  .title h1 .ic{display:inline-block; width:56px; height:26px; background-size:contain;
    background-position:center; background-repeat:no-repeat; vertical-align:-.08em; margin-right:12px; opacity:.9;}
  .title p{margin:2px 0 0; color:var(--ink2); font-size:13px;}
  .toolbar{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
  .seg{display:inline-flex; background:var(--surface); border:1px solid var(--border); border-radius:9px; padding:3px; box-shadow:var(--shadow);}
  .seg button{appearance:none; border:0; background:transparent; color:var(--ink2); font:inherit; font-size:13px;
    padding:6px 12px; border-radius:6px; cursor:pointer;}
  .seg button.on{background:var(--brand); color:#fff;}
  select.idsel{font:inherit; font-size:13px; color:var(--ink); background:var(--surface);
    border:1px solid var(--border); border-radius:8px; padding:6px 10px; box-shadow:var(--shadow); cursor:pointer;}
  .iconbtn{appearance:none; border:1px solid var(--border); background:var(--surface); color:var(--ink2);
    border-radius:8px; width:36px; height:34px; cursor:pointer; box-shadow:var(--shadow); font-size:16px;}
  .kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:22px 0;}
  .kpi{background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:var(--shadow);}
  .kpi .lbl{color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em;}
  .kpi .val{font-size:40px; font-weight:650; letter-spacing:-.03em; margin-top:2px; line-height:1.05;}
  .kpi .val small{font-size:17px; color:var(--ink2); font-weight:500;}
  .kpi .sub{color:var(--ink2); font-size:12.5px; margin-top:3px;}
  .meter{height:8px; border-radius:5px; background:var(--grid); margin-top:12px; overflow:hidden;}
  .meter>span{display:block; height:100%; background:var(--brand); border-radius:5px;}
  .kpi .valrow{display:flex; align-items:baseline; gap:9px; flex-wrap:wrap;}
  .delta{font-size:12.5px; font-weight:700; font-variant-numeric:tabular-nums; display:inline-flex; align-items:center; gap:2px;}
  .delta.up{color:var(--good);} .delta.down{color:var(--bad);} .delta.flat{color:var(--muted);}
  .kpi .form{display:flex; gap:4px; margin-top:14px; flex-wrap:wrap;}
  .kpi .form span{width:17px; height:17px; border-radius:5px; display:inline-flex; align-items:center; justify-content:center;
    font-size:9.5px; font-weight:800; color:#fff;}
  .kpi .form .w{background:var(--good);} .kpi .form .l{background:var(--bad);}
  .formline{display:flex; align-items:center; gap:5px; flex-wrap:wrap; margin:0 0 12px;}
  .formline .flabel{font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; margin-right:4px;}
  .formline .pip{width:18px; height:18px; border-radius:5px; display:inline-flex; align-items:center; justify-content:center;
    font-size:10px; font-weight:800; color:#fff;}
  .formline .pip.w{background:var(--good);} .formline .pip.l{background:var(--bad);}
  .insights{display:flex; flex-wrap:wrap; gap:10px; margin:-4px 0 20px;}
  .insight{background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:9px 13px;
    box-shadow:var(--shadow); font-size:12.7px; color:var(--ink2); display:flex; align-items:center; gap:9px; line-height:1.3;}
  .insight .ic{font-size:15px; line-height:1;}
  .insight b{color:var(--ink); font-weight:650;}
  .bdelta{font-size:10.5px; font-weight:700; font-variant-numeric:tabular-nums; margin-left:5px;}
  .bdelta.up{color:var(--good);} .bdelta.down{color:var(--bad);}
  .grid2{display:grid; grid-template-columns:1fr 1fr; gap:16px;}
  @media (max-width:820px){ .grid2{grid-template-columns:1fr;} }
  .card{background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:16px 18px 12px; box-shadow:var(--shadow); margin-bottom:16px;}
  .card h2{font-size:15px; margin:0 0 2px;}
  .card .cap{color:var(--ink2); font-size:12.5px; margin:0 0 10px;}
  .chartbox{width:100%; position:relative;}
  svg{display:block; width:100%; height:auto; overflow:visible;}
  .axis text{fill:var(--muted); font-size:11px; font-variant-numeric:tabular-nums;}
  .gridline{stroke:var(--grid); stroke-width:1;}
  .baseline{stroke:var(--axis); stroke-width:1;}
  text.lbl{fill:var(--ink2); font-size:11.5px;}
  text.val{fill:var(--ink); font-size:11.5px; font-variant-numeric:tabular-nums;}
  .legend{display:flex; gap:16px; flex-wrap:wrap; color:var(--ink2); font-size:12px; margin-top:8px;}
  .legend .sw{display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:6px; vertical-align:-1px;}
  table{width:100%; border-collapse:collapse; font-size:13px;}
  .tablewrap{overflow-x:auto;}
  th,td{padding:8px 10px; text-align:left; white-space:nowrap;}
  th{color:var(--muted); font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
    border-bottom:1px solid var(--border); cursor:pointer; user-select:none;}
  th.num,td.num{text-align:right; font-variant-numeric:tabular-nums;}
  tbody tr{border-bottom:1px solid var(--grid);}
  tbody tr.g:hover{background:color-mix(in srgb, var(--brand) 8%, transparent);}
  .pill{display:inline-block; padding:1px 8px; border-radius:20px; font-size:11.5px; font-weight:600;}
  .pill.win{background:color-mix(in srgb,var(--good) 16%,transparent); color:var(--good-ink);}
  .pill.loss{background:color-mix(in srgb,var(--bad) 16%,transparent); color:var(--bad);}
  .pill.online{background:color-mix(in srgb,var(--brand) 15%,transparent); color:var(--brand);}
  .pill.solo{background:var(--grid); color:var(--ink2);}
  tr.detail td{background:var(--page); padding:0;}
  .detwrap{padding:12px 16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px;}
  .detp{border:1px solid var(--border); border-radius:10px; padding:10px 12px; background:var(--surface);}
  .detp .nm{font-weight:600; margin-bottom:6px; display:flex; justify-content:space-between; gap:8px;}
  .detp .row{display:flex; justify-content:space-between; color:var(--ink2); font-size:12px; padding:1px 0;}
  .tip{position:fixed; pointer-events:none; z-index:50; background:var(--surface); color:var(--ink);
    border:1px solid var(--border); border-radius:9px; padding:8px 10px; font-size:12px; box-shadow:var(--shadow);
    opacity:0; transition:opacity .08s; max-width:240px;}
  .tip b{font-weight:650;}
  .tip .muted{color:var(--ink2);}
  .tabs{display:flex; gap:4px; margin:20px 0 4px; border-bottom:1px solid var(--border);}
  .tabs button{appearance:none; background:transparent; border:0; border-bottom:2px solid transparent;
    color:var(--ink2); font:inherit; font-size:14.5px; font-weight:600; padding:9px 16px; cursor:pointer; margin-bottom:-1px;}
  .tabs button:hover{color:var(--ink);}
  .tabs button.on{color:var(--brand); border-bottom-color:var(--brand);}
  .birdbar{display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:14px;}
  .birdctl{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
  #birdSearch{font:inherit; font-size:13px; color:var(--ink); background:var(--surface);
    border:1px solid var(--border); border-radius:8px; padding:6px 10px; box-shadow:var(--shadow); min-width:150px;}
  .birdgrid{display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:16px;}
  /* Real-card look: each tile renders as a physical Wingspan card (parchment in both themes). */
  .btile{position:relative; border-radius:14px; overflow:hidden; box-shadow:var(--shadow);
    background:linear-gradient(#f5f0e2,#eae1cd); color:#2c2723; border:1px solid #d8ccae;
    font-family:Georgia,'Times New Roman',serif;}
  /* base icon box — GLOBAL on purpose: ic() output is used in tiles, the header and the
     detail sheet, and scoping this to .btile made icons silently collapse elsewhere. */
  .ic{display:inline-block; width:16px; height:16px; background-size:contain; background-position:center; background-repeat:no-repeat; vertical-align:-.24em;}
  .btile .bart{position:relative; height:172px; background:#efe9da; overflow:hidden;}
  .btile .bart img{width:100%; height:100%; object-fit:cover; object-position:center 32%; display:block;}
  .btile .noart{font-size:48px; opacity:.4; display:flex; align-items:center; justify-content:center; height:100%;}
  .btile .noart .ic{width:52px; height:52px;}
  .btile .namebanner{background:linear-gradient(#efe7d2,#e7ddc4); border-top:1px solid #d8ccae;
    border-bottom:1px solid #d3c6a6; padding:6px 10px 5px; text-align:center;}
  .btile .bn{font-weight:700; font-size:14px; line-height:1.12; letter-spacing:.01em; color:#2b2620; text-transform:uppercase;}
  .btile .sci{font-size:10.5px; font-style:italic; color:#7a6f5a; margin-top:1px;}
  .btile .costrail{display:flex; align-items:center; justify-content:center; gap:14px; padding:6px 8px; background:#f1ead9; min-height:18px;}
  .btile .costrail .crg{display:inline-flex; align-items:center; gap:3px;}
  .btile .costrail .ic{width:20px; height:20px;}
  .btile .costrail .slash{font-size:13px; color:#5a5145; margin:0 1px;}
  .btile .statrail{display:flex; align-items:center; justify-content:center; gap:15px; padding:5px 8px;
    background:#ece4d0; border-top:1px solid #ddd2b6;}
  .btile .st{display:inline-flex; align-items:center; gap:3px; font-size:13px; font-weight:700; color:#3a342b;}
  .btile .st .ic{width:18px; height:18px;}
  .btile .st small{font-size:8.5px; font-weight:600; margin-left:1px; color:#6f6656;}
  .btile .powerband{padding:5px 9px 6px; min-height:36px; border-top:1px solid rgba(0,0,0,.12);}
  /* NOTE: powerband internals are deliberately UNSCOPED — the detail sheet reuses this
     markup, and scoping them to .btile silently dropped the styling there. */
  .powerband .plabel{font-family:Arial,Helvetica,sans-serif; font-size:8px; font-weight:800;
    letter-spacing:.06em; text-transform:uppercase; opacity:.8; display:block; margin-bottom:1px;}
  .powerband .ptext{font-family:Arial,Helvetica,sans-serif; font-size:10px; line-height:1.3;}
  .btile .powerband .ptext{display:-webkit-box; -webkit-line-clamp:2;   /* tiles only: keep height uniform */
    -webkit-box-orient:vertical; overflow:hidden;}
  .powerband .ptext .ic{width:12px; height:12px; vertical-align:-.15em;}
  .powerband .hd{width:9px;height:9px;border-radius:2px;display:inline-block;transform:rotate(45deg);vertical-align:0;margin:0 1px;}
  .pc-white{background:#f7f3e8; color:#2c2723;} .pc-brown{background:#8a6a49; color:#f6efe2;}
  .pc-pink{background:#e2a8bf; color:#3a2530;} .pc-teal{background:#5aa89d; color:#0f2e2a;}
  .pc-yellow{background:#e7cf6b; color:#3a3211;}
  .btile .metrics{padding:9px 11px 11px; background:linear-gradient(#f2ecdd,#e9e0cc); border-top:1px solid #d8ccae;}
  .btile .big{display:flex; align-items:baseline; gap:6px; margin:0 0 6px;}
  .btile .big .n{font-size:26px; font-weight:700; letter-spacing:-.02em; line-height:1; color:#2b2620;}
  .btile .big .u{font-size:11.5px; color:#6f6656;}
  .btile .srow{display:flex; justify-content:space-between; font-size:12px; color:#6f6656; padding:1px 0; font-family:Arial,sans-serif;}
  .btile .srow b{color:#2b2620; font-weight:700; font-variant-numeric:tabular-nums;}
  .btile .wr{height:6px; border-radius:4px; background:#dad0b8; overflow:hidden; margin:3px 0 8px;}
  .btile .wr>span{display:block; height:100%; background:#5a9e57; border-radius:4px;}
  .btile .bmostly{font-size:10.5px; color:#6f6656; margin:0 0 8px; font-family:Arial,sans-serif;}
  .btile .bmostly b{color:#2b2620; font-weight:700;}
  .btile .bdelta{font-size:10.5px; font-weight:800; margin-left:5px; font-family:Arial,sans-serif;}
  .btile .bdelta.up{color:#2f7d32;} .btile .bdelta.down{color:#c0392b;}
  .btile .etc{display:grid; grid-template-columns:repeat(3,1fr); gap:5px;}
  .btile .etc span{display:flex; flex-direction:column; align-items:center; gap:1px; background:#e6dcc4;
    border:1px solid #d8ccae; border-radius:8px; padding:5px 2px;}
  .btile .etc i{font-style:normal; font-size:8.5px; text-transform:uppercase; letter-spacing:.03em; color:#7a6f5a; font-family:Arial,sans-serif;}
  .btile .etc b{font-size:13px; font-variant-numeric:tabular-nums; color:#2b2620;}
  .habgrid{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px 26px;}
  .habpanel .pt{font-size:12.5px; color:var(--ink); font-weight:600; margin:6px 0 6px;}
  .mbrow{display:grid; grid-template-columns:84px 1fr 42px; align-items:center; gap:8px; padding:3px 0; font-size:12px;}
  .mbrow .ml{color:var(--ink2); text-align:right; white-space:nowrap;}
  .mbrow .mt{height:14px; background:var(--grid); border-radius:4px; overflow:hidden;}
  .mbrow .mf{display:block; height:100%; background:var(--brand); border-radius:4px; min-width:3px;}
  .mbrow .mv{font-variant-numeric:tabular-nums; color:var(--ink); text-align:right;}
  .empty{color:var(--ink2); text-align:center; padding:40px 10px;}
  footer{color:var(--muted); font-size:12px; margin-top:26px; text-align:center;}
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block;vertical-align:0;margin-right:5px;}

  /* ============ bird tile: hover affordance ============ */
  .btile{cursor:pointer; transition:transform .18s ease, box-shadow .18s ease;}
  .btile:hover{transform:translateY(-5px);
    box-shadow:0 0 0 1px #c9b482, 0 14px 30px -8px rgba(0,0,0,.5), 0 0 26px -6px rgba(226,186,110,.45);}
  .btile .bart img{transition:transform .3s ease;}
  .btile:hover .bart img{transform:scale(1.235);}

  /* the friendly "click to see more" nudge, after a beat of hovering */
  .hint{position:fixed; z-index:60; pointer-events:none; opacity:0; transform:translateY(5px);
    transition:opacity .2s ease, transform .2s ease; background:var(--surface); color:var(--ink);
    border:1px solid var(--border); border-radius:999px; padding:6px 13px; font-size:12.5px;
    font-weight:600; white-space:nowrap; box-shadow:0 10px 24px rgba(0,0,0,.34);}
  .hint.on{opacity:1; transform:translateY(0);}
  .hint .k{color:var(--brand);}

  /* ============ bird detail sheet (in-app overlay) ============ */
  .ovl{position:fixed; inset:0; z-index:70; display:none; justify-content:center;
    background:rgba(10,9,7,.66); overflow-y:auto; padding:28px 18px 48px;}
  .ovl.on{display:flex; align-items:flex-start;}
  .sheet{position:relative; width:min(1060px,100%); background:var(--surface);
    border:1px solid var(--border); border-radius:16px; box-shadow:0 30px 90px rgba(0,0,0,.55);
    animation:pop .2s ease;}
  @keyframes pop{from{opacity:0; transform:translateY(10px) scale(.99);} to{opacity:1; transform:none;}}
  .sheet .x{position:absolute; top:14px; right:14px; z-index:2; appearance:none; cursor:pointer;
    width:32px; height:32px; border-radius:50%; border:1px solid var(--border);
    background:var(--surface2,var(--surface)); color:var(--ink2); font-size:17px; line-height:1;}
  .sheet .x:hover{color:var(--ink); border-color:var(--axis);}
  .dhead{display:flex; gap:22px; padding:24px 26px 20px; border-bottom:1px solid var(--border);
    flex-wrap:wrap;}
  .dcard{flex:0 0 232px; width:232px; border-radius:12px; overflow:hidden;
    background:linear-gradient(#f5f0e2,#eae1cd); border:1px solid #d8ccae; color:#2c2723;
    font-family:Georgia,'Times New Roman',serif;}
  .dcard .dart{height:250px; background:#efe9da; overflow:hidden;}
  .dcard .dart img{width:100%; height:100%; object-fit:cover; object-position:center 30%; display:block;}
  .dcard .dart .noart{font-size:60px; opacity:.4; display:flex; align-items:center;
    justify-content:center; height:100%;}
  .dcard .dart .noart .ic{width:64px; height:64px;}
  .dcard .drails{padding:9px 10px 11px; display:flex; flex-direction:column; gap:7px; align-items:center;}
  .dcard .crg,.dcard .statrail{display:flex; gap:7px; align-items:center; justify-content:center;
    flex-wrap:wrap;}
  .dcard .ic{display:inline-block; width:17px; height:17px; background-size:contain;
    background-position:center; background-repeat:no-repeat; vertical-align:-.24em;}
  .dcard .st{display:inline-flex; align-items:center; gap:3px; font-size:12.5px;}
  .dcard .st b{font-variant-numeric:tabular-nums;}
  .dcard .st small{font-size:9px; color:#7a6f5a;}
  .dmeta{flex:1 1 380px; min-width:300px;}
  .dmeta h3{margin:0 0 2px; font-size:25px; letter-spacing:-.01em;}
  .dmeta .dsci{margin:0 0 14px; color:var(--ink2); font-size:13px; font-style:italic;}
  .dkpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr)); gap:10px; margin-bottom:14px;}
  .dk{background:var(--card,rgba(128,128,128,.09)); border:1px solid var(--border);
    border-radius:10px; padding:9px 11px;}
  .dk .dkl{font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);}
  .dk .dkv{font-size:19px; font-weight:700; font-variant-numeric:tabular-nums; margin-top:2px;}
  .dk .dkv small{font-size:11px; font-weight:600; color:var(--ink2);}
  /* reuse the real card's power-colour bands, just bigger for the sheet */
  .dmeta .powerband{border-radius:10px; border:1px solid rgba(0,0,0,.14); padding:9px 12px 10px;}
  .dmeta .powerband .plabel{font-size:9px;}
  .dmeta .powerband .ptext{font-size:12.5px; line-height:1.45;}
  .dmeta .powerband .ptext .ic{width:15px; height:15px;}
  .dsec{padding:20px 26px 4px;}
  .dsec h4{margin:0 0 3px; font-size:14.5px;}
  .dsec .cap{margin:0 0 10px;}
  .dgrid{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:20px 26px;}
  /* the mini bar charts need real width — squeezed into a 1/3 column their labels
     scale down to unreadable, since the SVG is a fixed viewBox */
  .dgrid.wide{grid-template-columns:repeat(auto-fit,minmax(420px,1fr));}
  /* partner list */
  .plist{display:flex; flex-direction:column; gap:7px;}
  .prow{display:grid; grid-template-columns:30px 1fr auto auto; gap:10px; align-items:center;
    padding:6px 9px; border:1px solid var(--border); border-radius:10px; font-size:13px;}
  .prow .pa{width:30px; height:30px; border-radius:6px; overflow:hidden; background:var(--grid);}
  .prow .pa img{width:100%; height:100%; object-fit:cover; object-position:center 30%; display:block;}
  .prow .pn{font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
  .prow .pn small{display:block; font-weight:500; color:var(--muted); font-size:11px;}
  .prow .pv{font-variant-numeric:tabular-nums; color:var(--ink2); font-size:12.5px;}
  .prow .lift{font-weight:700; font-variant-numeric:tabular-nums; font-size:13px;}
  .lift.up{color:var(--good);} .lift.down{color:var(--bad);}
  /* per-bird insight lines */
  .dins{display:flex; flex-direction:column; gap:8px;}
  .dins .di{display:flex; gap:9px; align-items:flex-start; font-size:13px; line-height:1.45;
    background:var(--card,rgba(128,128,128,.07)); border:1px solid var(--border);
    border-radius:10px; padding:9px 11px;}
  .dins .di .dicn{flex:0 0 auto; font-size:14px;}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="title">
      <h1><span id="hmark"></span>Wingspan Preserve Archive</h1>
      <p id="subtitle">Your game history, decrypted locally.</p>
    </div>
    <div class="toolbar">
      <label class="seg" role="group" aria-label="Player">
        <span style="align-self:center;color:var(--muted);font-size:11px;padding:0 8px 0 6px;text-transform:uppercase;letter-spacing:.06em;">You</span>
      </label>
      <select class="idsel" id="idsel" title="Which player is you"></select>
      <div class="seg" id="scopeSeg">
        <button data-scope="all" class="on">All</button>
        <button data-scope="solo">Solo</button>
        <button data-scope="online">Online</button>
      </div>
      <button class="iconbtn" id="themeBtn" title="Toggle light/dark">◐</button>
    </div>
  </header>

  <nav class="tabs" id="tabs">
    <button data-view="dashboard" class="on">Dashboard</button>
    <button data-view="birds">Birds</button>
  </nav>

  <div id="viewDashboard">
  <section class="kpis" id="kpis"></section>
  <section class="insights" id="insights"></section>

  <div class="grid2">
    <div class="card" style="grid-column:1/-1;">
      <h2>Score over time</h2>
      <p class="cap" id="capTrend">Your total score in each finished game.</p>
      <div class="chartbox" id="trend"></div>
      <div class="legend">
        <span><span class="dot" style="background:var(--brand)"></span>Your score</span>
        <span><span class="dot" style="background:var(--good)"></span>Win</span>
        <span><span class="dot" style="background:var(--bad)"></span>Loss</span>
        <span><span class="sw" style="background:var(--axis);height:2px;border-radius:0;width:16px;"></span>Your average</span>
      </div>
    </div>

    <div class="card">
      <h2>Average score composition</h2>
      <p class="cap">Where your points come from, on average.</p>
      <div class="chartbox" id="compo"></div>
    </div>

    <div class="card">
      <h2>Score distribution</h2>
      <p class="cap">How often you land in each score range.</p>
      <div class="chartbox" id="dist"></div>
    </div>

    <div class="card" style="grid-column:1/-1;" id="h2hCard">
      <h2>Head-to-head</h2>
      <p class="cap">Your win rate against each opponent (2+ games).</p>
      <div class="chartbox" id="h2h"></div>
    </div>
  </div>

  <div class="card">
    <h2>Game log</h2>
    <p class="cap" id="capLog">Click any row for the full score breakdown. Click a column to sort.</p>
    <div class="formline" id="formLine"></div>
    <div class="tablewrap"><table id="logtbl">
      <thead><tr>
        <th data-k="date">Date</th>
        <th data-k="kind">Type</th>
        <th class="num" data-k="players">Players</th>
        <th data-k="result">Result</th>
        <th class="num" data-k="me">Your score</th>
        <th class="num" data-k="best">Top score</th>
        <th data-k="winner">Winner</th>
      </tr></thead>
      <tbody id="logbody"></tbody>
    </table></div>
  </div>
  </div><!-- /viewDashboard -->

  <div id="viewBirds" hidden>
    <div class="card">
      <div class="birdbar">
        <div>
          <h2>Your birds</h2>
          <p class="cap" id="birdCap">Every bird you've played, with how it performs for you.</p>
        </div>
        <div class="birdctl">
          <input type="search" id="birdSearch" placeholder="Search birds…" autocomplete="off">
          <div class="seg" id="habSeg">
            <button data-hab="all" class="on">All</button>
            <button data-hab="Forest">Forest</button>
            <button data-hab="Grassland">Grassland</button>
            <button data-hab="Wetland">Wetland</button>
          </div>
          <select class="idsel" id="birdSort">
            <option value="played">Most played</option>
            <option value="total">Highest avg total pts</option>
            <option value="winrate">Best win rate</option>
            <option value="engine">Most extra pts (eggs+tuck+cache)</option>
            <option value="eggs">Most eggs</option>
            <option value="name">Name (A–Z)</option>
          </select>
        </div>
      </div>
      <div class="birdgrid" id="birdgrid"></div>
    </div>

    <div class="card">
      <h2>By habitat</h2>
      <p class="cap">Your per-game averages in each habitat row — Forest, Grassland, Wetland.</p>
      <div class="habgrid" id="habitat"></div>
    </div>
  </div><!-- /viewBirds -->

  <footer id="foot"></footer>
</div>
<div class="tip" id="tip"></div>
<div class="hint" id="hint">Click to see more details</div>
<div class="ovl" id="ovl" role="dialog" aria-modal="true" aria-labelledby="dName">
  <div class="sheet" id="sheet">
    <button class="x" id="ovlClose" title="Close (Esc)" aria-label="Close">&#10005;</button>
    <div id="sheetBody"></div>
  </div>
</div>

<script>
const DATA = __WINGSPAN_DATA__;
// GPLv3 requires the source to be available to anyone you give the program to.
// Update this in one place if the repository moves.
const SOURCE_URL = 'https://github.com/LendarioSonhador/wingspan-archive-viewer';
const $ = s => document.querySelector(s);
const tip = $('#tip');
function showTip(html, x, y){ tip.innerHTML=html; tip.style.opacity=1;
  let tx=x+14, ty=y+14; const w=tip.offsetWidth, h=tip.offsetHeight;
  if(tx+w>innerWidth-8) tx=x-w-14; if(ty+h>innerHeight-8) ty=y-h-14;
  tip.style.left=tx+'px'; tip.style.top=ty+'px'; }
function hideTip(){ tip.style.opacity=0; }

// ---------- state ----------
let scope='all';
let identity='__AUTO__';   // set of labels considered "you"; __AUTO__ = per-game owner flag
let view='dashboard', birdSort='played', birdHab='all', birdSearch='';

function fmtDate(iso){ const d=new Date(iso);
  return d.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'}); }
function niceNum(n){ return (Math.round(n*10)/10).toString(); }

// which player index in a game is "me"
function meIndex(g){
  if(identity==='__AUTO__') return g.ownerIndex;
  let found=-1;
  g.players.forEach((p,i)=>{ if(p.label===identity) found=i; });
  return found>=0?found:null;
}

function myGames(){
  let gs = DATA.games.filter(g=>g.finished);
  if(scope!=='all') gs = gs.filter(g=>g.kind===scope);
  return gs.map(g=>{
    const mi=meIndex(g);
    if(mi==null || mi<0) return null;
    const me=g.players[mi];
    const others=g.players.filter((_,i)=>i!==mi);
    const oppBest=Math.max(...others.map(p=>p.total), 0);
    return {g, me, others, oppBest, win: me.rank===1, margin: me.total-oppBest};
  }).filter(Boolean);
}

// ---------- KPI ----------
function renderKPIs(rows){
  const n=rows.length;
  const wins=rows.filter(r=>r.win).length;
  const wr = n? wins/n : 0;
  const totals=rows.map(r=>r.me.total);
  const best=totals.length?Math.max(...totals):0;
  const avg=totals.length?totals.reduce((a,b)=>a+b,0)/totals.length:0;
  const solo=rows.filter(r=>r.g.kind==='solo').length;
  const online=n-solo;
  // recent window (chronological → last games are most recent)
  const W=Math.min(10,n);
  const recent=rows.slice(n-W);
  const rWins=recent.filter(r=>r.win).length;
  const rWr = W? rWins/W : 0;
  const rAvg = W? recent.reduce((a,r)=>a+r.me.total,0)/W : 0;
  const showDelta = n>=15;   // need a meaningful baseline before flagging a trend
  const delta=(v,unit)=>{
    if(!showDelta) return '';
    const cls = v>0.5?'up':(v<-0.5?'down':'flat');
    const arrow = v>0.5?'▲':(v<-0.5?'▼':'▬');
    const disp = unit==='pp' ? Math.abs(Math.round(v))+'pp' : Math.abs(v).toFixed(1);
    return `<span class="delta ${cls}" title="last ${W} games vs your all-time">${arrow} ${disp}</span>`;
  };
  const el=$('#kpis');
  el.innerHTML='';
  const cards=[
    {lbl:'Games', val:n, sub: n? (solo+' solo · '+online+' online'):'no finished games'},
    {lbl:'Win rate', val:Math.round(wr*100)+'<small>%</small>', delta:delta((rWr-wr)*100,'pp'),
      sub: wins+' of '+n+' won', meter:wr},
    {lbl:'Average score', val: n? niceNum(avg):'—', delta:delta(rAvg-avg,'pts'),
      sub: n? 'across '+n+' games':''},
    {lbl:'Best score', val:best||'—', sub: best? 'your personal best':''},
  ];
  for(const c of cards){
    const d=document.createElement('div'); d.className='kpi';
    d.innerHTML=`<div class="lbl">${c.lbl}</div>`
      +`<div class="valrow"><div class="val">${c.val}</div>${c.delta||''}</div>`
      +(c.meter!=null?`<div class="meter"><span style="width:${Math.round(c.meter*100)}%"></span></div>`:'')
      +(c.sub?`<div class="sub">${c.sub}</div>`:'');
    el.appendChild(d);
  }
}

// ---------- Recent form pips (a quiet line above the game log) ----------
function renderForm(rows){
  const box=$('#formLine'); if(!box) return;
  const n=rows.length, F=Math.min(10,n);
  if(!F){ box.innerHTML=''; return; }
  const recent=rows.slice(n-F);
  box.innerHTML=`<span class="flabel">Last ${F}</span>`
    + recent.map(r=>`<span class="pip ${r.win?'w':'l'}" title="${r.me.total} pts · ${fmtDate(r.g.date)}">${r.win?'W':'L'}</span>`).join('');
}

// ---------- Insights strip: rotating, seeded once per launch ----------
// A fresh seed each time the report loads → the strip surfaces different
// patterns from session to session, but stays stable across re-renders (filters).
const INSIGHT_BASE = Math.floor(Math.random()*2147483646)+1;
function rngFrom(seed){ let s=seed%2147483647; if(s<=0) s+=2147483646;
  return ()=>{ s=(s*16807)%2147483647; return (s-1)/2147483646; }; }
function shuffle(arr, rnd){ const a=arr.slice();
  for(let i=a.length-1;i>0;i--){ const j=Math.floor(rnd()*(i+1)); [a[i],a[j]]=[a[j],a[i]]; } return a; }

function buildInsights(rows){
  const n=rows.length; if(!n) return [];
  const avg=rows.reduce((a,r)=>a+r.me.total,0)/n;
  const bd=DATA.birdData||{};
  const pinned=[];
  // current streak — dynamic anchor, always relevant "right now"
  const tw=rows[n-1].win; let ts=0;
  for(let i=n-1;i>=0;i--){ if(rows[i].win===tw) ts++; else break; }
  if(tw && ts>=3) pinned.push({ic:'🔥', html:`On a <b>${ts}-game win streak</b>`});
  else if(!tw && ts>=3) pinned.push({ic:'🧊', html:`Cold spell: <b>${ts} losses</b> in a row`});

  // ---- general pattern pool (each returns obj|null); avoids stats already on screen ----
  const G=[
    ()=>{ let b=rows[0]; rows.forEach(r=>{ if(r.me.total>b.me.total) b=r; });
      return {ic:'⭐', html:`Best game: <b>${b.me.total} pts</b> on ${fmtDate(b.g.date)}`}; },
    ()=>{ let lg=0,run=0; rows.forEach(r=>{ if(r.win){run++;lg=Math.max(lg,run);}else run=0; });
      return lg>=3?{ic:'🏆', html:`Longest win streak: <b>${lg} games</b>`}:null; },
    ()=>{ const th=Math.round(avg), ab=rows.filter(r=>r.me.total>=th), w=ab.filter(r=>r.win).length;
      return ab.length>=5?{ic:'📈', html:`When you score <b>${th}+</b>, you win <b>${Math.round(w/ab.length*100)}%</b>`}:null; },
    ()=>{ const won=rows.filter(r=>r.win); if(won.length<5) return null;
      const m=won.reduce((a,r)=>a+Math.max(0,r.margin),0)/won.length;
      return {ic:'📏', html:`You win by <b>${niceNum(m)} pts</b> on average`}; },
    ()=>{ const s=rows.filter(r=>r.g.kind==='solo'); if(s.length<5||s.length===n) return null;
      const w=s.filter(r=>r.win).length; return {ic:'🤖', html:`In solo games you win <b>${Math.round(w/s.length*100)}%</b>`}; },
    ()=>{ const mo={}; rows.forEach(r=>{ const d=new Date(r.g.date); if(isNaN(d.getTime())) return;
        const k=d.getFullYear()+'-'+d.getMonth(); (mo[k]=mo[k]||{s:0,c:0,d}); mo[k].s+=r.me.total; mo[k].c++; });
      const arr=Object.values(mo).filter(x=>x.c>=5); if(arr.length<2) return null;
      arr.sort((a,b)=>b.s/b.c-a.s/a.c); const t=arr[0];
      return {ic:'📅', html:`Your best month: <b>${t.d.toLocaleString('en-US',{month:'long'})}</b> — avg <b>${niceNum(t.s/t.c)}</b>`}; },
    ()=>{ if(n<6) return null; const s=rows.map(r=>r.me.total).sort((a,b)=>a-b);
      const md=n%2?s[(n-1)/2]:(s[n/2-1]+s[n/2])/2;
      return {ic:'⚖️', html:`Half your games top <b>${niceNum(md)} pts</b>`}; },
    ()=>{ const set=new Set(); rows.forEach(r=>(r.me.birds||[]).forEach(b=>set.add(b.id)));
      return set.size>=20?{ic:'🌈', html:`You've played <b>${set.size} different birds</b>`}:null; },
    ()=>{ const k=rows.filter(r=>r.me.total>=100).length;
      return k>=3?{ic:'💯', html:`You've broken <b>100 pts</b> in <b>${k} games</b>`}:null; },
    ()=>{ const agg={}; rows.forEach(r=>(r.me.birds||[]).forEach(b=>{ const a=agg[b.id]||(agg[b.id]={s:0,c:0}); a.s+=r.me.total; a.c++; }));
      let id=null,best=-1,c=0; for(const k in agg){ if(agg[k].c>=5){ const v=agg[k].s/agg[k].c; if(v>best){best=v;id=k;c=agg[k].c;} } }
      if(id==null) return null; const nm=(bd[id]&&bd[id].name)||('Bird #'+id);
      return {ic:'🎯', html:`With <b>${escapeHtml(nm)}</b> in play, you average <b>${niceNum(best)} total pts</b> <span class="muted">(${c} games)</span>`}; },
  ];
  // ---- bird slot: cycles between all-time best and recently-hot ----
  const B=[
    ()=>{ const bs=birdStats(rows).filter(b=>b.games>=5).sort((a,b)=>b.wr-a.wr||b.games-a.games);
      return bs.length?{ic:'🐦', html:`Best bird: <b>${escapeHtml(bs[0].name)}</b> — ${Math.round(bs[0].wr)}% over ${bs[0].games} games`}:null; },
    ()=>{ const F=Math.min(10,n), recent=rows.slice(n-F), cnt={};
      recent.forEach(r=>(r.me.birds||[]).forEach(b=>{ cnt[b.id]=(cnt[b.id]||0)+1; }));
      let id=null,c=0; for(const k in cnt){ if(cnt[k]>c){c=cnt[k];id=k;} }
      if(id==null||c<2) return null; const nm=(bd[id]&&bd[id].name)||('Bird #'+id);
      return {ic:'⚡', html:`Hot lately: <b>${escapeHtml(nm)}</b> — in <b>${c} of your last ${F}</b> games`}; },
  ];
  const rnd=rngFrom(INSIGHT_BASE);
  const gPicked=shuffle(G, rnd).map(fn=>fn()).filter(Boolean);
  const bPicked=shuffle(B, rnd).map(fn=>fn()).filter(Boolean);
  const wantG = pinned.length ? 2 : 3;   // keep the strip ~4 pills wide
  return pinned.concat(gPicked.slice(0, wantG)).concat(bPicked.slice(0,1));
}
function renderInsights(rows){
  const box=$('#insights'); if(!box) return;
  box.innerHTML=buildInsights(rows).map(x=>`<div class="insight"><span class="ic">${x.ic}</span><span>${x.html}</span></div>`).join('');
}

// ---------- helpers for SVG ----------
const NS='http://www.w3.org/2000/svg';
function svg(w,h){ const s=document.createElementNS(NS,'svg');
  s.setAttribute('viewBox',`0 0 ${w} ${h}`); s.setAttribute('preserveAspectRatio','xMidYMid meet'); return s; }
function el(tag,attrs){ const e=document.createElementNS(NS,tag);
  for(const k in attrs) e.setAttribute(k,attrs[k]); return e; }
function css(v){ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

// ---------- Trend (line) ----------
function renderTrend(rows){
  const box=$('#trend'); box.innerHTML='';
  if(rows.length<2){ box.innerHTML='<div class="empty">Need at least 2 games to draw a trend.</div>'; return; }
  const W=1000,H=300, m={l:42,r:16,t:14,b:34};
  const iw=W-m.l-m.r, ih=H-m.t-m.b;
  const xs=rows.map((_,i)=>i);
  const ys=rows.map(r=>r.me.total);
  const ymin=Math.max(0, Math.floor((Math.min(...ys)-8)/10)*10);
  const ymax=Math.ceil((Math.max(...ys)+8)/10)*10;
  const avg=ys.reduce((a,b)=>a+b,0)/ys.length;
  const X=i=> m.l + (rows.length===1?iw/2: iw*i/(rows.length-1));
  const Y=v=> m.t + ih*(1-(v-ymin)/(ymax-ymin));
  const s=svg(W,H);
  // gridlines + y ticks
  const g=el('g',{class:'axis'});
  const ticks=5;
  for(let t=0;t<=ticks;t++){
    const v=ymin+(ymax-ymin)*t/ticks; const y=Y(v);
    g.appendChild(el('line',{class:'gridline',x1:m.l,y1:y,x2:W-m.r,y2:y}));
    const tx=el('text',{x:m.l-8,y:y+4,'text-anchor':'end'}); tx.textContent=Math.round(v); g.appendChild(tx);
  }
  // x labels (~6)
  const step=Math.ceil(rows.length/6);
  for(let i=0;i<rows.length;i+=step){
    const tx=el('text',{x:X(i),y:H-12,'text-anchor':'middle'});
    tx.textContent=fmtDate(rows[i].g.date); g.appendChild(tx);
  }
  s.appendChild(g);
  // average reference line
  s.appendChild(el('line',{x1:m.l,y1:Y(avg),x2:W-m.r,y2:Y(avg),
    stroke:css('--axis'),'stroke-width':1.5,'stroke-dasharray':'5 5'}));
  // area + line
  const dLine=rows.map((r,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(r.me.total).toFixed(1)}`).join(' ');
  const dArea=dLine+` L${X(rows.length-1).toFixed(1)},${Y(ymin)} L${X(0).toFixed(1)},${Y(ymin)} Z`;
  const grad=el('linearGradient',{id:'ga',x1:0,y1:0,x2:0,y2:1});
  grad.appendChild(el('stop',{offset:'0%','stop-color':css('--brand'),'stop-opacity':.22}));
  grad.appendChild(el('stop',{offset:'100%','stop-color':css('--brand'),'stop-opacity':0}));
  s.appendChild(grad);
  s.appendChild(el('path',{d:dArea,fill:'url(#ga)'}));
  s.appendChild(el('path',{d:dLine,fill:'none',stroke:css('--brand'),'stroke-width':2,'stroke-linejoin':'round'}));
  // points
  rows.forEach((r,i)=>{
    const c=el('circle',{cx:X(i),cy:Y(r.me.total),r:4.5,
      fill: r.win?css('--good'):css('--bad'), stroke:css('--surface'),'stroke-width':2});
    c.style.cursor='pointer';
    c.addEventListener('mousemove',e=>{
      showTip(`<b>${fmtDate(r.g.date)}</b> · ${r.g.kind}<br>Your score <b>${r.me.total}</b> — ${r.win?'Win':'Loss'}`+
        `<br><span class="muted">Top ${Math.max(r.me.total,r.oppBest)} · ${r.g.numPlayers}p</span>`, e.clientX,e.clientY);
    });
    c.addEventListener('mouseleave',hideTip);
    s.appendChild(c);
  });
  box.appendChild(s);
}

// ---------- horizontal sequential bars ----------
function renderHBars(box, items, opts){
  opts=opts||{}; box.innerHTML='';
  if(!items.length){ box.innerHTML='<div class="empty">No data.</div>'; return; }
  const rowH=opts.rowH||30, W=opts.W||1000, m={l:opts.labelW||150,r:opts.r||60,t:6,b:6};
  const H=m.t+m.b+items.length*rowH;
  const iw=W-m.l-m.r;
  const max=Math.max(...items.map(d=>d.value),1);
  const s=svg(W,H);
  items.forEach((d,i)=>{
    const y=m.t+i*rowH;
    const bw=Math.max(iw*d.value/max, d.value>0?3:0);
    const lb=el('text',{x:m.l-10,y:y+rowH/2+4,'text-anchor':'end',class:'lbl'}); lb.textContent=d.label;
    s.appendChild(lb);
    s.appendChild(el('rect',{x:m.l,y:y+5,width:iw,height:rowH-12,rx:4,fill:css('--grid'),opacity:.5}));
    const bar=el('rect',{x:m.l,y:y+5,width:bw,height:rowH-12,rx:4,fill:css('--brand')});
    bar.style.cursor='pointer';
    // escaped: these labels can be opponent-chosen usernames, and showTip uses innerHTML
    bar.addEventListener('mousemove',e=>showTip(`<b>${escapeHtml(d.label)}</b><br>${d.tip||niceNum(d.value)}`,e.clientX,e.clientY));
    bar.addEventListener('mouseleave',hideTip);
    s.appendChild(bar);
    const vt=el('text',{x:m.l+bw+8,y:y+rowH/2+4,class:'val'}); vt.textContent=opts.fmt?opts.fmt(d):niceNum(d.value);
    s.appendChild(vt);
  });
  box.appendChild(s);
}

function renderCompo(rows){
  const box=$('#compo');
  if(!rows.length){ box.innerHTML='<div class="empty">No data.</div>'; return; }
  const names=DATA.scoreCats;
  const sums={}; names.forEach(n=>sums[n]=0);
  rows.forEach(r=>names.forEach(n=>sums[n]+=(r.me.breakdown[n]||0)));
  const items=names.map(n=>({label:n, value:sums[n]/rows.length}))
    .sort((a,b)=>b.value-a.value);
  renderHBars(box, items, {fmt:d=>niceNum(d.value)+' pts'});
}

// ---------- distribution (histogram) ----------
function renderDist(rows){
  const box=$('#dist'); box.innerHTML='';
  if(rows.length<2){ box.innerHTML='<div class="empty">Not enough games yet.</div>'; return; }
  const vals=rows.map(r=>r.me.total);
  const bin=10;
  const lo=Math.floor(Math.min(...vals)/bin)*bin;
  const hi=Math.ceil((Math.max(...vals)+1)/bin)*bin;
  const nb=Math.max(1,(hi-lo)/bin);
  const counts=new Array(nb).fill(0);
  vals.forEach(v=>{ let b=Math.floor((v-lo)/bin); if(b>=nb)b=nb-1; if(b<0)b=0; counts[b]++; });
  const W=1000,H=240,m={l:36,r:12,t:12,b:34};
  const iw=W-m.l-m.r, ih=H-m.t-m.b;
  const max=Math.max(...counts,1);
  const bw=iw/nb;
  const s=svg(W,H);
  const g=el('g',{class:'axis'});
  for(let t=0;t<=max;t+=Math.ceil(max/4)){
    const y=m.t+ih*(1-t/max);
    g.appendChild(el('line',{class:'gridline',x1:m.l,y1:y,x2:W-m.r,y2:y}));
    const tx=el('text',{x:m.l-6,y:y+4,'text-anchor':'end'}); tx.textContent=t; g.appendChild(tx);
  }
  s.appendChild(g);
  counts.forEach((c,i)=>{
    const x=m.l+i*bw, h=ih*c/max, y=m.t+ih-h;
    if(c>0){
      const bar=el('rect',{x:x+3,y:y,width:bw-6,height:Math.max(h,2),rx:4,fill:css('--brand')});
      bar.style.cursor='pointer';
      const range=(lo+i*bin)+'–'+(lo+(i+1)*bin-1);
      bar.addEventListener('mousemove',e=>showTip(`<b>${range} pts</b><br>${c} game${c>1?'s':''}`,e.clientX,e.clientY));
      bar.addEventListener('mouseleave',hideTip);
      s.appendChild(bar);
    }
    if(i%1===0){ const tx=el('text',{x:x+bw/2,y:H-12,'text-anchor':'middle',class:'axis'});
      tx.setAttribute('fill',css('--muted')); tx.style.fontSize='10px'; tx.textContent=lo+i*bin; s.appendChild(tx); }
  });
  box.appendChild(s);
}

// ---------- head to head ----------
function renderH2H(rows){
  const box=$('#h2h');
  const rec={};   // opponent label -> {g,w}
  rows.forEach(r=>{
    r.others.forEach(o=>{
      const key=o.label+(o.isBot?' (AI)':'');
      rec[key]=rec[key]||{g:0,w:0,bot:o.isBot};
      rec[key].g++; if(r.win) rec[key].w++;
    });
  });
  let items=Object.entries(rec).filter(([_,v])=>v.g>=2)
    .map(([label,v])=>({label, value:v.w/v.g*100, g:v.g, w:v.w}))
    .sort((a,b)=>b.value-a.value).slice(0,12);
  if(!items.length){ $('#h2hCard').style.display='none'; return; }
  $('#h2hCard').style.display='';
  renderHBars(box, items.map(d=>({label:d.label,value:d.value,
      tip:`Win rate <b>${Math.round(d.value)}%</b><br><span class="muted">${d.w} of ${d.g} games</span>`})),
    {fmt:d=>Math.round(d.value)+'%'});
}

// ---------- Birds tab: card grid ----------
const HABCOLOR={Forest:'var(--hab-forest)', Grassland:'var(--hab-grass)', Wetland:'var(--hab-wet)'};
const HABORDER={Forest:0, Grassland:1, Wetland:2};
const habSort=arr=>[...arr].sort((a,b)=>(HABORDER[a]??9)-(HABORDER[b]??9));

// ---------- Real Wingspan icons (Wingsearch, GPLv3): embedded as data-URIs, referenced by CSS class ----------
function installIconCSS(){
  const icons=DATA.icons||{}; let css='';
  for(const n in icons) css+=`.i-${n}{background-image:url(${icons[n]})}`;
  const s=document.createElement('style'); s.textContent=css; document.head.appendChild(s);
}
const hasIcon=n=>!!(DATA.icons && DATA.icons[n]);
const ic=n=> hasIcon(n)?`<i class="ic i-${n}"></i>`:'';
const FOODNAME={inv:'invertebrate', seed:'seed', fish:'fish', fruit:'fruit', rodent:'rodent', nectar:'nectar', wild:'wild'};
const NESTNAME={bowl:'bowl', cavity:'cavity', ground:'ground', platform:'platform', wild:'star'};
const HABICON={Forest:'forest', Grassland:'grassland', Wetland:'wetland'};
const POWERLABEL={white:'When Played', brown:'When Activated', pink:'Once Between Turns', teal:'Round End', yellow:'When Activated'};
function foodHtml(d){
  const f=d.foods||[];
  if(!f.length) return d.foodStar?ic('no-food'):'';
  if(d.foodChoice) return f.map(([k])=>ic(FOODNAME[k]||k)).join('<span class="slash">/</span>');
  const p=[]; f.forEach(([k,n])=>{ for(let i=0;i<n && p.length<5;i++) p.push(ic(FOODNAME[k]||k)); });
  return p.join('');
}
const TOKEN={egg:'egg',card:'card',die:'die',seed:'seed',invertebrate:'invertebrate',fish:'fish',
  rodent:'rodent',fruit:'fruit',nectar:'nectar',wild:'wild',forest:'forest',grassland:'grassland',
  wetland:'wetland',ground:'ground',bowl:'bowl',cavity:'cavity',platform:'platform',star:'star',
  predator:'predator',flocking:'flocking',bird:'bird'};
function tokenize(t){
  return escapeHtml(t).replace(/\[([^\]]+)\]/g,(m,tok)=>{
    const n=TOKEN[tok.toLowerCase()];
    return (n && hasIcon(n)) ? ic(n) : '<b>'+tok+'</b>';
  });
}
function birdStats(rows){
  const bd=DATA.birdData||{}, art=DATA.birdArt||{}, agg={};
  rows.forEach(r=>{
    (r.me.birds||[]).forEach(b=>{
      let a=agg[b.id]; if(!a){ a=agg[b.id]={games:0,wins:0,e:0,t:0,c:0,habs:{}}; }
      a.games++; if(r.win) a.wins++; a.e+=b.e; a.t+=b.t; a.c+=b.c;
      a.habs[b.hab]=(a.habs[b.hab]||0)+1;
    });
  });
  return Object.entries(agg).map(([id,a])=>{
    const d=bd[id]||{};
    const playedHab=Object.entries(a.habs).sort((x,y)=>y[1]-x[1])[0][0];
    const engine=(a.e+a.t+a.c)/a.games;
    const vp=(typeof d.vp==='number')?d.vp:null;
    const elig=(Array.isArray(d.hab)&&d.hab.length)?habSort(d.hab):[playedHab];
    return {id, name:d.name||('Bird #'+id), games:a.games, wr:a.wins/a.games*100,
      eggs:a.e/a.games, tuck:a.t/a.games, cache:a.c/a.games, engine,
      vp, total:(vp!=null)? vp+engine : null, food:d.food, nest:d.nest,
      sci:d.sci||null, set:d.set||null, egg:(typeof d.egg==='number')?d.egg:null, wing:d.wing||null,
      foods:d.foods||[], foodChoice:!!d.foodChoice, foodStar:!!d.foodStar,
      color:d.color||null, power:d.power||null,
      habs:elig, played:playedHab, art:art[id]||null};
  });
}
function renderBirds(rows){
  const grid=$('#birdgrid');
  let items=birdStats(rows);
  if(birdHab!=='all') items=items.filter(d=>d.habs.includes(birdHab));
  const q=(birdSearch||'').trim().toLowerCase();
  if(q) items=items.filter(d=>d.name.toLowerCase().includes(q));
  const S={ played:(a,b)=>b.games-a.games||a.name.localeCompare(b.name),
    winrate:(a,b)=>b.wr-a.wr||b.games-a.games,
    total:(a,b)=>(b.total==null?-1:b.total)-(a.total==null?-1:a.total)||b.games-a.games,
    engine:(a,b)=>b.engine-a.engine||b.games-a.games,
    eggs:(a,b)=>b.eggs-a.eggs||b.games-a.games, name:(a,b)=>a.name.localeCompare(b.name) };
  items.sort(S[birdSort]||S.played);
  const owr = rows.length? rows.filter(r=>r.win).length/rows.length*100 : 0;
  const benchChip=(wr,games)=>{
    if(games<3) return '';                       // too few games to compare fairly
    const diff=Math.round(wr-owr); if(!diff) return '';
    const cls=diff>0?'up':'down';
    return `<span class="bdelta ${cls}" title="${diff>0?'+'+diff:diff}pp vs your ${Math.round(owr)}% overall win rate">${diff>0?'+'+diff:diff}</span>`;
  };
  $('#birdCap').textContent = `${items.length} bird${items.length!==1?'s':''} across your ${rows.length} game${rows.length!==1?'s':''}.`;
  if(!items.length){ grid.innerHTML='<div class="empty">No birds match this filter.</div>'; return; }
  grid.innerHTML = items.map(d=>{
    const art = d.art ? `<img loading="lazy" src="${d.art}" alt="${escapeHtml(d.name)}">`
                      : `<div class="noart">${ic('bird') || '🐦'}</div>`;
    const big = (d.total!=null)
      ? `<span class="n">${niceNum(d.total)}</span><span class="u">avg total pts</span>`
      : `<span class="n">+${niceNum(d.engine)}</span><span class="u">avg extra pts</span>`;
    const habs=d.habs.map(h=>ic(HABICON[h])).join('');
    const food=foodHtml(d);
    const mostly=(d.habs.length>1)?`<div class="bmostly">Mostly played in <b>${d.played}</b></div>`:'';
    const rail=[
      d.vp!=null?`<span class="st" title="${d.vp} victory points">${ic('point')}<b>${d.vp}</b></span>`:'',
      d.egg!=null?`<span class="st" title="egg limit ${d.egg}">${ic('egg')}<b>${d.egg}</b></span>`:'',
      (d.nest&&d.nest!=='none'&&NESTNAME[d.nest])?`<span class="st" title="${d.nest} nest">${ic(NESTNAME[d.nest])}</span>`:'',
      d.wing?`<span class="st" title="${d.wing} cm wingspan">${ic('wingspan')}<b>${d.wing}</b><small>cm</small></span>`:'',
    ].filter(Boolean).join('');
    const power=d.power?`<div class="powerband pc-${d.color||'white'}"><span class="plabel">${POWERLABEL[d.color]||''}</span><span class="ptext">${tokenize(d.power)}</span></div>`:'';
    return `
    <div class="btile" data-id="${d.id}" tabindex="0" role="button"
         aria-label="${escapeHtml(d.name)} — open details">
      <div class="bart">${art}</div>
      <div class="namebanner"><div class="bn">${escapeHtml(d.name)}</div>${d.sci?`<div class="sci">${escapeHtml(d.sci)}</div>`:''}</div>
      <div class="costrail">${habs?`<span class="crg">${habs}</span>`:''}${food?`<span class="crg food">${food}</span>`:''}</div>
      <div class="statrail">${rail}</div>
      ${power}
      <div class="metrics">
        <div class="big">${big}</div>
        <div class="srow"><span>${d.games} game${d.games!==1?'s':''}</span><b>${Math.round(d.wr)}% won${benchChip(d.wr,d.games)}</b></div>
        <div class="wr"><span style="width:${Math.round(d.wr)}%"></span></div>
        ${mostly}
        <div class="etc">
          <span><i>Eggs</i><b>${niceNum(d.eggs)}</b></span>
          <span><i>Tucked</i><b>${niceNum(d.tuck)}</b></span>
          <span><i>Cached</i><b>${niceNum(d.cache)}</b></span>
        </div>
      </div>
    </div>`;
  }).join('');
}
function rerenderBirds(){ renderBirds(myGames()); }

// ======================= bird detail sheet =======================
// Every game where this bird was on your board, plus what it produced there.
function birdGames(rows, id){
  const key=String(id), d=(DATA.birdData||{})[key]||{};
  const vp=(typeof d.vp==='number')?d.vp:0;
  const out=[];
  rows.forEach(r=>{
    const list=r.me.birds||[];
    const b=list.find(x=>String(x.id)===key);
    if(!b) return;
    out.push({r, hab:b.hab, e:b.e, t:b.t, c:b.c, pts:vp+b.e+b.t+b.c,
      partners:list.filter(x=>String(x.id)!==key).map(x=>String(x.id))});
  });
  return out;
}

// "Best partners": birds whose presence lines up with THIS bird scoring above its own
// average. lift = its avg points in games sharing the board with Y, minus its overall avg.
function partnerStats(gs, minN){
  const avgAll = gs.reduce((a,x)=>a+x.pts,0)/gs.length;
  const agg={};
  gs.forEach(x=>{
    const seen={};                      // count a partner once per game, not per copy
    x.partners.forEach(pid=>{
      if(seen[pid]) return; seen[pid]=1;
      const a=agg[pid]||(agg[pid]={n:0,pts:0,wins:0});
      a.n++; a.pts+=x.pts; if(x.r.win) a.wins++;
    });
  });
  const bd=DATA.birdData||{}, art=DATA.birdArt||{};
  return Object.entries(agg).map(([pid,a])=>({
      id:pid, name:(bd[pid]||{}).name||('Bird #'+pid), art:art[pid]||null,
      n:a.n, avg:a.pts/a.n, lift:a.pts/a.n-avgAll, wr:a.wins/a.n*100}))
    .filter(p=>p.n>=minN)
    .sort((x,y)=>y.lift-x.lift||y.n-x.n);
}

// per-game bars for one bird: what it produced, game by game, coloured by result
function renderBirdBars(box, gs){
  box.innerHTML='';
  if(gs.length<2){ box.innerHTML='<div class="empty">Only one game with this bird so far — no trend to draw yet.</div>'; return; }
  const W=1000,H=200,m={l:34,r:14,t:12,b:26};
  const iw=W-m.l-m.r, ih=H-m.t-m.b;
  const max=Math.max(...gs.map(x=>x.pts),1);
  // whole-number ticks: these are points, so fractional gridline labels read as wrong
  const step=Math.max(1, Math.ceil(max/4));
  const top=Math.max(step, Math.ceil(max/step)*step);
  const avg=gs.reduce((a,x)=>a+x.pts,0)/gs.length;
  const bw=Math.max(3, Math.min(26, iw/gs.length*0.72));
  const X=i=> m.l + iw*(i+0.5)/gs.length;
  const Y=v=> m.t + ih*(1-v/top);
  const s=svg(W,H);
  const g=el('g',{class:'axis'});
  for(let v=0;v<=top;v+=step){
    const y=Y(v);
    g.appendChild(el('line',{class:'gridline',x1:m.l,y1:y,x2:W-m.r,y2:y}));
    const tx=el('text',{x:m.l-7,y:y+4,'text-anchor':'end'}); tx.textContent=v;
    g.appendChild(tx);
  }
  // a few date anchors so the run of games is orientable
  [0, Math.floor((gs.length-1)/2), gs.length-1].filter((v,i,a)=>a.indexOf(v)===i).forEach(i=>{
    const tx=el('text',{x:X(i),y:H-10,'text-anchor':i===0?'start':(i===gs.length-1?'end':'middle')});
    tx.textContent=fmtDate(gs[i].r.g.date); g.appendChild(tx);
  });
  s.appendChild(g);
  gs.forEach((x,i)=>{
    const h=Math.max(2, ih*x.pts/top);
    const bar=el('rect',{x:X(i)-bw/2, y:m.t+ih-h, width:bw, height:h, rx:3,
      fill:x.r.win?css('--good'):css('--bad'), opacity:.85});
    bar.style.cursor='pointer';
    bar.addEventListener('mousemove',e=>showTip(
      `<b>${fmtDate(x.r.g.date)}</b><br>${niceNum(x.pts)} pts from this bird`+
      `<br><span class="muted">${x.hab} · ${x.e} eggs · ${x.t} tucked · ${x.c} cached</span>`+
      `<br><span class="muted">Game total ${x.r.me.total} — ${x.r.win?'Win':'Loss'}</span>`,
      e.clientX,e.clientY));
    bar.addEventListener('mouseleave',hideTip);
    s.appendChild(bar);
  });
  s.appendChild(el('line',{x1:m.l,y1:Y(avg),x2:W-m.r,y2:Y(avg),stroke:css('--axis'),
    'stroke-width':1.5,'stroke-dasharray':'5 5'}));
  const lb=el('text',{x:W-m.r,y:Y(avg)-6,'text-anchor':'end',class:'val'});
  lb.textContent='avg '+niceNum(avg); s.appendChild(lb);
  box.appendChild(s);
}

// short, plain-language patterns for this one bird
function birdInsights(d, gs, rows, partners){
  const out=[];
  const avg=gs.reduce((a,x)=>a+x.pts,0)/gs.length;
  const best=gs.reduce((a,x)=>x.pts>a.pts?x:a,gs[0]);
  out.push({ic:'🏆', html:`Best outing: <b>${niceNum(best.pts)} pts</b> from this bird on `+
    `${fmtDate(best.r.g.date)} (game total ${best.r.me.total}).`});
  const owr = rows.length? rows.filter(r=>r.win).length/rows.length*100 : 0;
  const wr = gs.filter(x=>x.r.win).length/gs.length*100;
  if(gs.length>=3){
    const dp=Math.round(wr-owr);
    if(Math.abs(dp)>=3) out.push({ic:dp>0?'📈':'🎯',
      html:`You win <b>${Math.round(wr)}%</b> of games with it — `+
        `${dp>0?'<b>+'+dp+'pp</b> above':'<b>'+Math.abs(dp)+'pp</b> below'} your ${Math.round(owr)}% overall.`});
  }
  const withAvg = gs.reduce((a,x)=>a+x.r.me.total,0)/gs.length;
  const ids={}; gs.forEach(x=>ids[x.r.g.id]=1);
  const without = rows.filter(r=>!ids[r.g.id]);
  if(without.length>=3){
    const wo = without.reduce((a,r)=>a+r.me.total,0)/without.length;
    const diff=withAvg-wo;
    if(Math.abs(diff)>=2) out.push({ic:'⭐',
      html:`Your games with it average <b>${Math.round(withAvg)}</b> pts vs <b>${Math.round(wo)}</b> `+
        `without it — ${diff>0?'+':''}${niceNum(diff)}.`});
  }
  const byHab={};
  gs.forEach(x=>{ (byHab[x.hab]=byHab[x.hab]||[]).push(x.pts); });
  const hl=Object.entries(byHab).filter(([,v])=>v.length>=2)
    .map(([h,v])=>({h, avg:v.reduce((a,b)=>a+b,0)/v.length, n:v.length}))
    .sort((a,b)=>b.avg-a.avg);
  if(hl.length>=2 && (hl[0].avg-hl[hl.length-1].avg)>=1){
    const lo=hl[hl.length-1];
    out.push({ic:'🌈', html:`It pays best in <b>${hl[0].h}</b> — ${niceNum(hl[0].avg)} pts across `+
      `${hl[0].n} games, vs ${niceNum(lo.avg)} in ${lo.h}.`});
  }
  if(partners.length && partners[0].lift>=1){
    const p=partners[0];
    out.push({ic:'🔥', html:`Sharing a board with <b>${escapeHtml(p.name)}</b> it averages `+
      `<b>${niceNum(p.avg)} pts</b> — ${niceNum(p.lift)} above its own average (${p.n} games together).`});
  }
  const win=Math.min(20,rows.length);
  const key=String(d.id);
  const recent=rows.slice(-win).filter(r=>(r.me.birds||[]).some(b=>String(b.id)===key)).length;
  if(recent) out.push({ic:'📅', html:`Played in <b>${recent}</b> of your last ${win} games.`});
  if(d.egg!=null && d.egg>0){
    const ae=gs.reduce((a,x)=>a+x.e,0)/gs.length;
    if(ae>0) out.push({ic:'🥚', html:`Averages <b>${niceNum(ae)}</b> eggs against an egg limit of `+
      `<b>${d.egg}</b> — ${Math.round(ae/d.egg*100)}% full.`});
  }
  return out;
}

function openBird(id){
  const rows=myGames();
  const d=birdStats(rows).find(x=>String(x.id)===String(id));
  const gs=birdGames(rows,id);
  if(!d || !gs.length) return;
  hideHint();
  let partners=partnerStats(gs,3), relaxed=false;
  if(!partners.length){ partners=partnerStats(gs,2); relaxed=partners.length>0; }

  const art = d.art?`<img src="${d.art}" alt="${escapeHtml(d.name)}">`
                   :`<div class="noart">${ic('bird')||'🐦'}</div>`;
  const habs=d.habs.map(h=>ic(HABICON[h])).join('');
  const food=foodHtml(d);
  const rail=[
    d.vp!=null?`<span class="st" title="${d.vp} victory points">${ic('point')}<b>${d.vp}</b></span>`:'',
    d.egg!=null?`<span class="st" title="egg limit ${d.egg}">${ic('egg')}<b>${d.egg}</b></span>`:'',
    (d.nest&&d.nest!=='none'&&NESTNAME[d.nest])?`<span class="st" title="${d.nest} nest">${ic(NESTNAME[d.nest])}</span>`:'',
    d.wing?`<span class="st" title="${d.wing} cm wingspan">${ic('wingspan')}<b>${d.wing}</b><small>cm</small></span>`:'',
  ].filter(Boolean).join('');
  const power=d.power?`<div class="powerband pc-${d.color||'white'}">`+
    `<span class="plabel">${POWERLABEL[d.color]||''}</span>`+
    `<span class="ptext">${tokenize(d.power)}</span></div>`:'';

  const avgPts=gs.reduce((a,x)=>a+x.pts,0)/gs.length;
  const bestPts=Math.max(...gs.map(x=>x.pts));
  const gameAvg=gs.reduce((a,x)=>a+x.r.me.total,0)/gs.length;
  const kpi=(l,v,s)=>`<div class="dk"><div class="dkl">${l}</div><div class="dkv">${v}${s?`<small> ${s}</small>`:''}</div></div>`;

  const plist = partners.length
    ? `<div class="plist">${partners.slice(0,6).map(p=>`
        <div class="prow">
          <span class="pa">${p.art?`<img src="${p.art}" alt="">`:''}</span>
          <span class="pn">${escapeHtml(p.name)}<small>${p.n} games together · ${Math.round(p.wr)}% won</small></span>
          <span class="pv">${p.avg.toFixed(1)} pts</span>
          <span class="lift ${p.lift>=0?'up':'down'}">${p.lift>=0?'+':''}${p.lift.toFixed(1)}</span>
        </div>`).join('')}</div>
       <p class="cap" style="margin-top:9px">Change in <b>this bird's</b> own points when that bird shares the board${relaxed?' — only 2+ shared games available, so treat these as weak signals':''}.</p>`
    : `<div class="empty">Not enough shared games yet to spot partners.</div>`;

  const ins=birdInsights(d,gs,rows,partners);

  $('#sheetBody').innerHTML=`
    <div class="dhead">
      <div class="dcard">
        <div class="dart">${art}</div>
        <div class="drails">
          ${habs||food?`<span class="crg">${habs}${food?`<span style="margin-left:9px">${food}</span>`:''}</span>`:''}
          ${rail?`<span class="statrail">${rail}</span>`:''}
        </div>
      </div>
      <div class="dmeta">
        <h3 id="dName">${escapeHtml(d.name)}</h3>
        <p class="dsci">${d.sci?escapeHtml(d.sci):''}${d.set?`${d.sci?' · ':''}${escapeHtml(d.set)} set`:''}</p>
        <div class="dkpis">
          ${kpi('Games',d.games,'')}
          ${kpi('Win rate',Math.round(d.wr)+'%','')}
          ${kpi('Avg pts from it',niceNum(avgPts),'pts')}
          ${kpi('Best game',niceNum(bestPts),'pts')}
          ${kpi('Your avg score',Math.round(gameAvg),'pts')}
        </div>
        ${power}
      </div>
    </div>

    <div class="dsec">
      <h4>Points from this bird, game by game</h4>
      <p class="cap">Base ${d.vp!=null?d.vp+' VP':'VP'} plus eggs, tucked cards and cached food it held at scoring. Green = you won that game.</p>
      <div class="chartbox" id="dBars"></div>
    </div>

    <div class="dsec">
      <div class="dgrid">
        <div>
          <h4>Best partners</h4>
          <p class="cap">Birds that were on your board when this one scored above its own average.</p>
          ${plist}
        </div>
        <div>
          <h4>Patterns</h4>
          <p class="cap">What stands out across your ${gs.length} game${gs.length!==1?'s':''} with it.</p>
          <div class="dins">${ins.map(i=>`<div class="di"><span class="dicn">${i.ic}</span><span>${i.html}</span></div>`).join('')}</div>
        </div>
      </div>
    </div>

    <div class="dsec" style="padding-bottom:22px">
      <div class="dgrid wide">
        <div><h4>Your score with vs without it</h4><p class="cap">Average total game score.</p>
          <div class="chartbox" id="dWith"></div></div>
        <div><h4>Where you place it</h4><p class="cap">Habitat row you actually played it in.</p>
          <div class="chartbox" id="dHab"></div></div>
        <div><h4>What it produces</h4><p class="cap">Per-game averages.</p>
          <div class="chartbox" id="dProd"></div></div>
      </div>
    </div>`;

  renderBirdBars($('#dBars'), gs);

  const ids={}; gs.forEach(x=>ids[x.r.g.id]=1);
  const without=rows.filter(r=>!ids[r.g.id]);
  const wItems=[{label:'With it', value:gameAvg, tip:`${niceNum(gameAvg)} pts over ${gs.length} games`}];
  if(without.length) wItems.push({label:'Without it',
    value:without.reduce((a,r)=>a+r.me.total,0)/without.length,
    tip:`${niceNum(without.reduce((a,r)=>a+r.me.total,0)/without.length)} pts over ${without.length} games`});
  renderHBars($('#dWith'), wItems, {W:480, labelW:96, r:52, rowH:34, fmt:d=>Math.round(d.value)});

  const habCount={};
  gs.forEach(x=>habCount[x.hab]=(habCount[x.hab]||0)+1);
  renderHBars($('#dHab'), (DATA.habitats||[]).filter(h=>habCount[h]).map(h=>({
    label:h, value:habCount[h], tip:`${habCount[h]} of ${gs.length} games`})),
    {W:480, labelW:96, r:52, rowH:32, fmt:d=>d.value});

  renderHBars($('#dProd'), [
    {label:'Eggs', value:gs.reduce((a,x)=>a+x.e,0)/gs.length},
    {label:'Tucked', value:gs.reduce((a,x)=>a+x.t,0)/gs.length},
    {label:'Cached', value:gs.reduce((a,x)=>a+x.c,0)/gs.length},
  ], {W:480, labelW:96, r:52, rowH:32});

  $('#ovl').classList.add('on');
  $('#sheet').scrollTop=0;
  document.body.style.overflow='hidden';
  $('#ovlClose').focus();
}

function closeBird(){
  $('#ovl').classList.remove('on');
  document.body.style.overflow='';
  hideTip();
}

// ---------- hover affordance: nudge after a beat ----------
const hintEl=$('#hint');
let hintTimer=null;
function hideHint(){ if(hintTimer){ clearTimeout(hintTimer); hintTimer=null; } hintEl.classList.remove('on'); }
function armHint(tile){
  hideHint();
  hintTimer=setTimeout(()=>{
    const r=tile.getBoundingClientRect();
    hintEl.classList.add('on');
    const w=hintEl.offsetWidth, h=hintEl.offsetHeight;
    let x=r.left+r.width/2-w/2, y=r.top-h-9;
    if(y<8) y=r.bottom+9;                                  // flip below if it would clip
    hintEl.style.left=Math.max(8,Math.min(x,innerWidth-w-8))+'px';
    hintEl.style.top=y+'px';
  }, 900);
}

// ---------- by habitat (small multiples) ----------
function renderHabitat(rows){
  const box=$('#habitat'); box.innerHTML='';
  if(!rows.length){ box.innerHTML='<div class="empty">No data.</div>'; return; }
  const habs=DATA.habitats;                       // ["Forest","Grassland","Wetland"]
  const metrics=[['birds','Birds'],['eggs','Eggs'],['cached','Cached food'],['tucked','Tucked cards']];
  const sums={};
  habs.forEach(h=>sums[h]={birds:0,eggs:0,cached:0,tucked:0});
  rows.forEach(r=>habs.forEach(h=>{
    const hd=(r.me.habitats||{})[h]; if(!hd) return;
    sums[h].birds+=hd.birds; sums[h].eggs+=hd.eggs; sums[h].cached+=hd.cached; sums[h].tucked+=hd.tucked;
  }));
  const n=rows.length;
  metrics.forEach(([key,label])=>{
    const panel=document.createElement('div'); panel.className='habpanel';
    const t=document.createElement('div'); t.className='pt'; t.textContent=label; panel.appendChild(t);
    const chart=document.createElement('div'); chart.className='chartbox'; panel.appendChild(chart);
    const items=habs.map(h=>({label:h, value:sums[h][key]/n}));
    const max=Math.max(...items.map(d=>d.value),1e-9);
    items.forEach(d=>{
      const row=document.createElement('div'); row.className='mbrow';
      const w=Math.max(3, d.value/max*100);
      row.innerHTML=`<span class="ml">${d.label}</span>`+
        `<span class="mt" title="${d.label}: ${niceNum(d.value)}"><span class="mf" style="width:${w}%"></span></span>`+
        `<span class="mv">${niceNum(d.value)}</span>`;
      chart.appendChild(row);
    });
    box.appendChild(panel);
  });
}

// ---------- game log ----------
let sortK='date', sortDir=-1;
function renderLog(rows){
  const body=$('#logbody'); body.innerHTML='';
  const data=rows.map(r=>({
    date:r.g.date, kind:r.g.kind, players:r.g.numPlayers,
    result:r.win?1:0, me:r.me.total, best:Math.max(r.me.total,r.oppBest),
    winner:r.g.players.find(p=>p.rank===1), r
  }));
  data.sort((a,b)=>{
    let av=a[sortK], bv=b[sortK];
    if(sortK==='winner'){ av=a.winner?a.winner.label:''; bv=b.winner?b.winner.label:''; }
    if(av<bv) return -sortDir; if(av>bv) return sortDir; return 0;
  });
  if(!data.length){ body.innerHTML='<tr><td colspan="7"><div class="empty">No games match this filter.</div></td></tr>'; return; }
  for(const d of data){
    const tr=document.createElement('tr'); tr.className='g';
    const w=d.winner;
    tr.innerHTML=`<td>${fmtDate(d.date)}</td>
      <td><span class="pill ${d.kind}">${d.kind}</span></td>
      <td class="num">${d.players}</td>
      <td><span class="pill ${d.result?'win':'loss'}">${d.result?'Win':'Loss'}</span></td>
      <td class="num">${d.me}</td>
      <td class="num">${d.best}</td>
      <td>${w?escapeHtml(w.label)+(w.isBot?' 🤖':''):'—'}</td>`;
    const det=document.createElement('tr'); det.className='detail'; det.style.display='none';
    const cell=document.createElement('td'); cell.colSpan=7;
    const dw=document.createElement('div'); dw.className='detwrap';
    d.r.g.players.forEach(p=>{
      const card=document.createElement('div'); card.className='detp';
      let rowsH='';
      DATA.scoreCats.forEach(n=>{ const v=p.breakdown[n]||0; if(v) rowsH+=`<div class="row"><span>${n}</span><span>${v}</span></div>`; });
      card.innerHTML=`<div class="nm"><span>${escapeHtml(p.label)}${p.isOwner?' <span class="muted">(you)</span>':''}${p.isBot?' 🤖':''}</span><b>${p.total}</b></div>${rowsH}`;
      dw.appendChild(card);
    });
    cell.appendChild(dw); det.appendChild(cell);
    tr.addEventListener('click',()=>{ det.style.display = det.style.display==='none'?'':'none'; });
    body.appendChild(tr); body.appendChild(det);
  }
}
function escapeHtml(s){ return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// ---------- identity selector ----------
function buildIdentitySelect(){
  const sel=$('#idsel');
  // gather human (non-bot) labels, most frequent first
  const freq={};
  DATA.games.forEach(g=>g.players.forEach(p=>{ if(!p.isBot){ freq[p.label]=(freq[p.label]||0)+1; }}));
  const labels=Object.entries(freq).sort((a,b)=>b[1]-a[1]).map(e=>e[0]);
  const autoLabels=[...new Set(DATA.games.map(g=>g.ownerIndex!=null?g.players[g.ownerIndex].label:null).filter(Boolean))];
  const autoTxt = autoLabels.length? ('Auto ('+autoLabels.join(' / ')+')') : 'Auto-detect';
  sel.innerHTML='';
  const o0=document.createElement('option'); o0.value='__AUTO__'; o0.textContent=autoTxt; sel.appendChild(o0);
  labels.forEach(l=>{ const o=document.createElement('option'); o.value=l; o.textContent=l; sel.appendChild(o); });
  sel.value='__AUTO__';
  sel.addEventListener('change',()=>{ identity=sel.value; render(); });
}

// ---------- render all ----------
function render(){
  const rows=myGames();
  $('#subtitle').textContent =
    `${DATA.totalGames} games in your archive · decrypted locally on ${fmtDate(DATA.generatedAt)}`;
  $('#hmark').innerHTML = ic('wingspan');   // empty string if icons aren't bundled — no tofu, no gap
  renderKPIs(rows);
  renderInsights(rows);
  renderTrend(rows);
  renderCompo(rows);
  renderDist(rows);
  renderH2H(rows);
  renderBirds(rows);
  renderHabitat(rows);
  renderLog(rows);
  renderForm(rows);
  $('#foot').innerHTML =
    `Wingspan Preserve Archive Viewer · ${DATA.totalGames} games · offline &amp; private · your data never leaves this machine.`+
    `<br>Bird art &amp; card data from <b>Wingsearch</b> by navarog (GPLv3) — illustrations are “Unofficial Fan Art”, not official game artwork.`+
    `<br>Free software under the <b>GPLv3</b>, with no warranty. Source: ${SOURCE_URL}`+
    `<br><span class="muted">Unofficial fan tool — not affiliated with or endorsed by Stonemaier Games or Monster Couch. `+
    `“Wingspan” and all game content belong to their respective owners.</span>`;
}

// tab switching (both views are always rendered; we just toggle visibility)
$('#tabs').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  view=b.dataset.view;
  [...$('#tabs').children].forEach(c=>c.classList.toggle('on',c===b));
  $('#viewDashboard').hidden = view!=='dashboard';
  $('#viewBirds').hidden = view!=='birds';
});
// bird-tab controls (re-render only the grid)
$('#habSeg').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  birdHab=b.dataset.hab;
  [...$('#habSeg').children].forEach(c=>c.classList.toggle('on',c===b));
  rerenderBirds();
});
$('#birdSort').addEventListener('change',()=>{ birdSort=$('#birdSort').value; rerenderBirds(); });
$('#birdSearch').addEventListener('input',()=>{ birdSearch=$('#birdSearch').value; rerenderBirds(); });

// scope buttons
$('#scopeSeg').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  scope=b.dataset.scope;
  [...$('#scopeSeg').children].forEach(c=>c.classList.toggle('on',c===b));
  render();
});
// sorting
document.querySelectorAll('#logtbl th').forEach(th=>{
  th.addEventListener('click',()=>{ const k=th.dataset.k;
    if(k===sortK) sortDir*=-1; else { sortK=k; sortDir = (k==='date')?-1:1; }
    render();
  });
});
// theme toggle
$('#themeBtn').addEventListener('click',()=>{
  const cur=document.documentElement.getAttribute('data-theme');
  const next = cur==='dark' ? 'light' : (cur==='light' ? 'dark' :
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'light':'dark'));
  document.documentElement.setAttribute('data-theme',next);
  render();
});

// bird tiles: hover nudge + click through to the detail sheet (delegated — tiles re-render)
$('#birdgrid').addEventListener('mouseover',e=>{
  const t=e.target.closest('.btile'); if(!t) return;
  if(t!==armHint.last){ armHint.last=t; armHint(t); }
});
$('#birdgrid').addEventListener('mouseout',e=>{
  const t=e.target.closest('.btile'); if(!t) return;
  if(e.relatedTarget && t.contains(e.relatedTarget)) return;   // still inside the same tile
  armHint.last=null; hideHint();
});
$('#birdgrid').addEventListener('click',e=>{
  const t=e.target.closest('.btile'); if(!t) return;
  openBird(t.dataset.id);
});
$('#birdgrid').addEventListener('keydown',e=>{
  if(e.key!=='Enter' && e.key!==' ') return;
  const t=e.target.closest('.btile'); if(!t) return;
  e.preventDefault(); openBird(t.dataset.id);
});
$('#ovlClose').addEventListener('click',closeBird);
$('#ovl').addEventListener('click',e=>{ if(e.target===$('#ovl')) closeBird(); });  // backdrop only
addEventListener('keydown',e=>{ if(e.key==='Escape' && $('#ovl').classList.contains('on')) closeBird(); });
addEventListener('scroll',hideHint,{passive:true});

installIconCSS();
buildIdentitySelect();
render();
addEventListener('resize',()=>{ /* SVG scales via viewBox; nothing needed */ });
</script>
</body>
</html>
"""

ERROR_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Wingspan Preserve Archive</title>
<style>
  :root{color-scheme:light dark;}
  body{margin:0;font-family:system-ui,"Segoe UI",sans-serif;background:#0d0d0d;color:#fff;
    display:flex;align-items:center;justify-content:center;min-height:100vh;}
  @media (prefers-color-scheme:light){body{background:#f9f9f7;color:#0b0b0b;}}
  .box{max-width:560px;padding:36px 40px;text-align:center;}
  h1{font-size:24px;margin:0 0 6px;} p{color:#c3c2b7;line-height:1.55;}
  @media (prefers-color-scheme:light){p{color:#52514e;}}
  code{background:rgba(128,128,128,.18);padding:2px 7px;border-radius:6px;font-size:12.5px;
    display:inline-block;margin-top:8px;word-break:break-all;}
</style></head><body><div class="box">
  <div style="font-size:44px">🐦</div>
  <h1>__TITLE__</h1>
  <p>__MSG__</p>
</div></body></html>"""

def build_error_html(title, msg):
    return ERROR_TEMPLATE.replace("__TITLE__", title).replace("__MSG__", msg)

def build_html(games, total_files):
    generated = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    payload = {
        "generatedAt": generated,
        "totalGames": len(games),
        "totalFiles": total_files,
        "scoreCats": [name for _, name in SCORE],
        "habitats": [name for _, name in HABITATS],
        "birdData": {str(i): r for i, r in BIRD_DATA.items()},
        "birdArt": collect_bird_art(games),
        "icons": collect_icons(),
        "games": games,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # SECURITY: this JSON is embedded inside a <script> block, and it carries strings we do
    # not control — online opponents pick their own usernames. A username containing
    # "</script>" would close the block early, killing the app and injecting arbitrary HTML
    # into the report (verified: the injected element lands in the DOM). Escaping these four
    # characters as \uXXXX is still valid JSON and decodes back to the exact same string,
    # so no data is altered. U+2028/9 are escaped because they are raw line breaks in JS.
    bs = chr(92)                                  # a single backslash
    for ch, esc in (("&", bs+"u0026"), ("<", bs+"u003c"), (">", bs+"u003e"),
                    (chr(0x2028), bs+"u2028"), (chr(0x2029), bs+"u2029")):
        blob = blob.replace(ch, esc)
    return HTML_TEMPLATE.replace("__WINGSPAN_DATA__", blob)

# ============================ app entry ======================================
def resolve_remotes(arg):
    if arg:
        # user passed a folder directly
        if os.path.isdir(arg):
            # try to sniff account id from path .../userdata/<id>/1054490/remote
            acct = ""
            parts = os.path.normpath(arg).split(os.sep)
            if "userdata" in parts:
                try: acct = parts[parts.index("userdata") + 1]
                except Exception: acct = ""
            return [(arg, acct)]
        return []
    return find_remote_dirs()

def open_window(html=None, file_path=None):
    """Show the dashboard in a native window; fall back to the browser if unavailable.

    A file_path is loaded via a file:// URL (no size limit). Passing html= uses
    WebView2's NavigateToString, which caps at ~2 MB — only used for tiny pages
    like the error screen; the full report (with embedded art) always uses a file.
    """
    try:
        import webview
        if file_path:
            url = "file:///" + os.path.abspath(file_path).replace("\\", "/")
            webview.create_window("Wingspan Preserve Archive", url=url,
                                  width=1240, height=900, min_size=(900, 640))
        else:
            webview.create_window("Wingspan Preserve Archive", html=html,
                                  width=1240, height=900, min_size=(900, 640))
        webview.start()
        return True
    except Exception as e:
        print("  (native window unavailable: %s)" % (str(e)[:90]))
        if file_path:
            print("  Opening in your default browser instead...")
            webbrowser.open("file:///" + os.path.abspath(file_path).replace("\\", "/"))
        return False

def _write_report(html, out_arg):
    out = out_arg
    if not out:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        try:
            open(os.path.join(base, ".wtest"), "w").close(); os.remove(os.path.join(base, ".wtest"))
        except Exception:
            base = tempfile.gettempdir()
        out = os.path.join(base, "WingspanArchive.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out

def main():
    ap = argparse.ArgumentParser(description="Wingspan Preserve Archive Viewer")
    ap.add_argument("remote", nargs="?", help="path to a Steam '...\\1054490\\remote' folder")
    ap.add_argument("--html", action="store_true", help="only write the HTML report; don't open a window")
    ap.add_argument("-o", "--out", help="where to write the HTML report")
    args = ap.parse_args()

    print("=" * 60)
    print("  Wingspan Preserve Archive Viewer")
    print("=" * 60)
    print("  Decryption:", "fast (pycryptodome)" if FAST else "built-in (no extra libraries)")

    remotes = resolve_remotes(args.remote)
    if not remotes:
        print("\n  Could not find your Wingspan save folder automatically.")
        msg = ("Couldn't find your Wingspan save folder automatically. Make sure Steam is "
               "installed and you've played Wingspan at least once, then run this again. "
               "Advanced: drag your <code>...\\1054490\\remote</code> folder onto this program.")
        if not args.html:
            open_window(build_error_html("No save folder found", msg))
        _pause(); return
    for rem, acct in remotes:
        print("  Save folder:", rem, ("(account %s)" % acct) if acct else "")

    print("  Reading and decrypting games...", flush=True)
    games, total_files = load_all_games(remotes)
    print("  Decrypted %d games from %d save files." % (len(games), total_files))
    if not games:
        msg = ("Found your save folder but couldn't read any games from it. If Wingspan "
               "recently updated, its save encryption may have changed and this tool would "
               "need an update.")
        if not args.html:
            open_window(build_error_html("No games could be read", msg))
        _pause(); return

    finished = sum(1 for g in games if g["finished"])
    owned = [g for g in games if g["ownerIndex"] is not None and g["finished"]]
    wins = sum(1 for g in owned if g["players"][g["ownerIndex"]]["rank"] == 1)
    print("  Finished games: %d   Your wins: %d/%d" % (finished, wins, len(owned)))

    html = build_html(games, total_files)
    out = _write_report(html, args.out)
    print("  Report written to:", out)

    if args.html:
        _pause(); return
    print("  Opening dashboard...")
    open_window(file_path=out)

def _pause():
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n  Press Enter to close...")
    except Exception:
        pass

class _Tee:
    """Mirror stdout/stderr to a log file so windowed (no-console) runs are diagnosable."""
    def __init__(self, stream, fh):
        self.stream = stream; self.fh = fh
    def write(self, s):
        try:
            if self.stream: self.stream.write(s); self.stream.flush()
        except Exception: pass
        try:
            self.fh.write(s); self.fh.flush()
        except Exception: pass
    def flush(self):
        for t in (self.stream, self.fh):
            try:
                if t: t.flush()
            except Exception: pass

def _setup_logging():
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    for cand in (base, tempfile.gettempdir()):
        try:
            path = os.path.join(cand, "WingspanViewer-log.txt")
            fh = open(path, "w", encoding="utf-8")
            sys.stdout = _Tee(sys.__stdout__, fh)
            sys.stderr = _Tee(sys.__stderr__, fh)
            return path
        except Exception:
            continue
    return None

if __name__ == "__main__":
    _logpath = _setup_logging()
    try:
        main()
    except Exception:
        import traceback
        print("\n  Something went wrong:\n", traceback.format_exc())
        try:
            open_window(build_error_html("Something went wrong",
                "The viewer hit an unexpected error. Details were written to "
                "<code>WingspanViewer-log.txt</code> next to this program."))
        except Exception:
            pass
        _pause()
