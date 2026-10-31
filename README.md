# Wingspan Preserve Archive Viewer

A free, offline desktop app that reads **your own** Wingspan "Preserve Archive" (your past
games), decrypts it locally, and turns it into a dashboard: win rate, score trends,
head-to-head records, and an illustrated card for every bird you have ever played,
with your personal stats on it.

Everything happens on your machine. The app makes **no network connections at all**.

> **Unofficial fan project.** Not affiliated with, endorsed by, or supported by
> Stonemaier Games or Monster Couch. "Wingspan" and all game content are the property of
> their respective owners. This tool only reads save files that are already on your
> computer; it never modifies them, and it does not touch online play.

---

## What it does

**Dashboard** — games played, win rate, average and best score, score over time, where
your points come from, score distribution, head-to-head records per opponent, rotating
insights, and a sortable game log.

**Birds** — a card for every bird you've played: illustration, habitats, food cost, nest
type, egg limit, wingspan, power text, and *your* record with it (games, win rate, average
end-of-game total points). Search, filter by habitat, sort.

**Bird detail** — click any bird card for a full breakdown: its points game by game, your
score with vs without it, where you place it, what it produces, plain-language patterns,
and "best partners" — birds whose presence on your board coincides with that bird scoring
above its own average.

---

## Install and run

1. Download `WingspanArchiveViewer.exe` from the
   [Releases page](https://github.com/LendarioSonhador/wingspan-archive-viewer/releases).
2. Double-click it.
3. A window opens with your dashboard.

No installer, no dependencies, no configuration. It finds your Steam saves automatically.

**Windows may show a SmartScreen warning** ("Windows protected your PC") because the app
isn't code-signed — code-signing certificates cost money that a free hobby tool doesn't
have. Click **More info → Run anyway**. If you'd rather not trust a binary, the checksum
is published with each release and you can run from source instead (see below).

---

## Privacy and safety

- **No network access.** The app never connects to the internet. The generated report even
  ships with a Content-Security-Policy that forbids outbound requests, so your game data
  cannot leave the machine.
- **Read-only.** It opens your save files for reading and never writes to them, never
  touches the game, and never touches online play.
- It writes two files next to the .exe: `WingspanArchive.html` (your dashboard) and
  `WingspanViewer-log.txt` (a small log).
- **Careful if you share those files.** `WingspanArchive.html` contains your full game
  history, and for online games that includes your opponents' usernames. The log records
  your Steam save path, which includes your Steam account ID.

---

## Where your saves live

Wingspan keeps archived games in Steam Cloud userdata, not the install folder:

```
<Steam>\userdata\<your-account-id>\1054490\remote\
```

`local_*` files are solo/local games, `*.nakama-*` are online games. The app finds these
automatically; if that fails, it shows a **Choose save folder…** button (or drag the
`remote` folder onto the .exe). Note that `userdata` sits under the **Steam client**
install, not the game's library folder, so "Browse local files" in Steam won't get you
there.

**Phone saves** (Android/iOS) are reportedly stored unencrypted (not yet tested against a
real phone save). Copy the save folder to your PC and
choose it; the app searches a picked folder a few levels deep and reads plain JSON saves
as well as encrypted ones.

The files are base64 with a short plaintext header (`V@1H@11@N` plus a format-version
digit) followed by a DES-CBC encrypted JSON game state. The app decrypts them in memory to
read your scores. It has a pure-Python decryption fallback so it works with no extra
libraries installed.

**Game dates** come from the filename, not the file's modified time: `local_<n>` is a
Windows FILETIME recording when the game started. (Modified times get reset whenever Steam
Cloud re-downloads your saves, which used to pile older games onto a single day.) Online
games take their date from the game's own archive index, the `Settings` file. Only the two
game lists are read from that file; it also holds account details, which the app ignores.

---

## Run from source

```sh
pip install pywebview           # pycryptodome is optional; it just makes decryption faster
python wingspan_viewer.py       # opens the window
python wingspan_viewer.py --html -o report.html    # write the report without opening a window
```

### Build the .exe

```sh
python -m PyInstaller --noconfirm --onefile --windowed \
  --name WingspanArchiveViewer --icon wingspan.ico \
  --add-data "bird_data.json;." --add-data "bird_names.json;." \
  --add-data "bird_art;bird_art" --add-data "icons;icons" \
  --collect-all webview --collect-all clr_loader --collect-all pythonnet \
  --distpath dist --workpath build --specpath . wingspan_viewer.py
```

All four `--add-data` arguments are required; without them the bird art and icons are
missing from the build.

### Regenerating the bird data

```sh
git clone --filter=blob:none https://github.com/navarog/wingsearch
python build_bird_data.py       # -> bird_data.json + bird_art/
python augment_bird_data.py --master wingsearch/.../master.json
python build_bird_names.py      # -> bird_names.json (reads your game install)
```

---

## Credits

Bird illustrations and card data come from the open-source
**[Wingsearch](https://github.com/navarog/wingsearch)** project by **navarog**, used under
the **GPLv3**. The illustrations are AI-generated "Unofficial Fan Art" from that project,
not the game's official artwork. The food/nest/habitat icons come from the same project.
Thank you!

Changes made to the Wingsearch material in this project: bird images were resized to a
maximum of 340px and converted for bundling; card records were matched to in-game bird IDs
by normalized common name; a subset of fields (victory points, food cost, habitats, nest,
egg limit, wingspan, scientific name, power colour and power text) was extracted into
`bird_data.json`.

Bird ID-to-name mapping in `bird_names.json` is derived from the local game installation's
own asset filenames.

## License

This project is licensed under the **GNU General Public License v3.0** — see
[LICENSE](LICENSE). It bundles GPLv3 material from Wingsearch, so the combined work is
distributed under the same terms. That means you get the complete source, and any
redistribution must also be GPLv3.

Third-party components bundled in the .exe are listed in
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
