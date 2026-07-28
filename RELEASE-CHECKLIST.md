# Release checklist

Run through this before publishing a build. The first section is the one that matters
most — it stops your own data from shipping with the app.

## 1. Don't ship your own data

- [ ] Delete `dist\WingspanArchive.html` — it contains your **entire game history**,
      including the usernames of everyone you played online.
- [ ] Delete `dist\WingspanViewer-log.txt` — it records your save path, which contains
      your **Steam account ID**.
- [ ] Delete any stray `*.html` renders in the repo root (`_reg.html`, `preview_*.html`, …).
- [ ] Confirm no CSV exports (`wingspan_archive.csv`, `wingspan_games.csv`) or
      `plaintext/` folder are included. These are gitignored but exist locally.

```sh
# quick sweep
rm -f dist/WingspanArchive.html dist/WingspanViewer-log.txt
git status --short          # should be clean; anything untracked is worth a look
```

## 2. Source URL

- [x] Done: `https://github.com/LendarioSonhador/wingspan-archive-viewer` is set in
      `README.md`, `README-app.txt`, and `SOURCE_URL` in `wingspan_viewer.py`.
      If the repo is ever renamed or moved, update all three.
- [ ] Copy `README-app.txt` to `dist\README.txt` so the shipped copy matches.

## 3. Decide what goes in the public repo

- [ ] **Leave the reverse-engineering scripts out**: `frida_diag.py`, `frida_dump.py`,
      `frida_key.py`, `frida_wide.py`, `recover_key.py`. The GPL obliges you to publish the
      source of the program you distribute — not the tooling used to work out the format.
      A repo full of Frida injection scripts reads like a cracking kit; the same repo
      without them reads like a stats viewer.
- [ ] Decide whether `decrypt_all.py` / `parse_archive.py` (the CSV exporters) belong in
      the public repo or stay local.

## 4. Build

- [ ] Close any running copy of the app first, or PyInstaller can't overwrite the exe.
- [ ] Build with **all four** `--add-data` arguments (see `README.md`). Missing
      `--add-data "icons;icons"` silently ships a build with no icons.
- [ ] Verify the bundle contents:

```sh
python -m PyInstaller.utils.cliutils.archive_viewer --list dist/WingspanArchiveViewer.exe \
  | grep -c icons          # expect 24
```

- [ ] Launch the built exe once and confirm it opens, finds saves, and renders both tabs
      plus a bird detail sheet.

## 5. Publish

- [ ] Include `LICENSE` and `THIRD-PARTY-NOTICES.txt` alongside the exe and in the repo.
- [ ] Publish the SHA-256 in the release notes:

```sh
certutil -hashfile dist\WingspanArchiveViewer.exe SHA256
```

- [ ] Optional but helpful: upload to VirusTotal and link the scan, since an unsigned
      PyInstaller one-file exe attracts false positives.
- [ ] Tag the release so the source and the binary correspond. GPLv3 requires the
      *corresponding* source for the binary you hand out.

## 6. Before posting anywhere public

- [ ] Read Stonemaier Games' current IP / fan-content policy and confirm the disclaimer
      wording still fits.
- [ ] Keep it free. Charging money changes the IP conversation entirely.
- [ ] Consider a short, friendly heads-up to Monster Couch before wide posting. Being the
      person who told them beats being the person they discovered.
- [ ] Post to GitHub Releases first, then link from BGG / Reddit. Save the Steam
      Community forum for last — it's the publisher's own turf.
