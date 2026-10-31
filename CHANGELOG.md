# Changelog

## v1.1.0 — 2026-10-31

**Fixes**
- **Game dates are now correct after a Steam Cloud re-download.** Dates used to come from
  each file's modified time, which Steam resets when it re-downloads your saves (new PC,
  reinstall, sync conflict), piling older games onto one day. Dates now come from the save
  filename, which records when the game started. Online games use the date from the game's
  own archive index. Dates shift by a few minutes compared to v1.0.0 (game start instead of
  last save).
- **Saves with a different format version are no longer silently skipped.** v1.0.0
  required the exact header of current saves; any other format-version digit was dropped
  without a message.

**New**
- **Choose save folder…** button when your saves can't be found automatically, and an
  **Open a different save folder…** link at the bottom of the dashboard.
- **Phone saves:** plain (unencrypted) JSON saves, which is reportedly how the mobile
  versions store games, are read too (not yet tested against a real phone save). A folder
  you pick is searched a few levels deep.
- The dashboard footer says how many games your in-game archive lists whose save files
  aren't on this PC.

## v1.0.0 — 2026-07-28

First public release.
