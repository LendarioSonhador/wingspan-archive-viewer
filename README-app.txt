Wingspan Preserve Archive Viewer
================================

See stats and charts for every Wingspan game in your Preserve Archive.

UNOFFICIAL FAN TOOL. Not affiliated with, endorsed by, or supported by Stonemaier
Games or Monster Couch. "Wingspan" and all game content belong to their respective
owners. This tool only READS save files already on your computer.


WHAT'S INSIDE
-------------
Three tabs' worth of your own history:

  DASHBOARD - win rate, score trends over time, where your points come from,
              your score distribution, head-to-head records, rotating insights,
              and a full, sortable game log.
  BIRDS     - an illustrated card for every bird you've played, showing how
              many games, your win rate with it, and its average end-of-game
              TOTAL points (base victory points + eggs + tucked cards + cached
              food), plus victory points / food cost / nest type / egg limit /
              wingspan / power text. Search, filter by habitat, and sort by
              most-played / highest avg total / best win rate / most eggs.
  BIRD      - click any bird card to open its detail sheet: its points game by
  DETAIL      game, your score with vs without it, where you place it, what it
              produces, short plain-language patterns, and "best partners" -
              birds that were on your board when it scored above its own average.

Plus a Forest/Grassland/Wetland habitat breakdown.


HOW TO USE
----------
1. Make sure you've played Wingspan on this PC at least once (so there are
   saved games to read).
2. Double-click  WingspanArchiveViewer.exe
3. A window opens with your dashboard. That's it.

The first launch can take a few seconds while it unpacks. Use the controls at
the top right to switch between All / Solo / Online games, pick which player is
"you", and toggle light/dark.


IS THIS SAFE? WHAT DOES IT TOUCH?
---------------------------------
- 100% offline. It makes no network connections of any kind, and nothing ever
  leaves your computer. The report it generates carries a security policy that
  forbids outbound requests, so that holds even if a save file contained
  something malicious.
- It only READS your own Wingspan save files. It never changes them, never
  touches the game, and never touches online play.
- It finds your saves automatically in your Steam folder. If you have several
  Steam accounts on this PC, it reads all of them.

It writes two files next to the .exe (or in your temp folder if that isn't
allowed):
  - WingspanArchive.html      the dashboard
  - WingspanViewer-log.txt    a small log, handy if something goes wrong

BE CAREFUL SHARING THOSE TWO FILES. WingspanArchive.html contains your full game
history, including the usernames of anyone you played online. The log contains
the path to your saves, which includes your Steam account ID.


"WINDOWS PROTECTED YOUR PC" MESSAGE
-----------------------------------
Because this is a small indie tool that isn't code-signed, Windows SmartScreen
may show a blue warning the first time. Click "More info" then "Run anyway".

Don't want to trust a binary? Every release publishes a SHA-256 checksum, and
the complete source is available so you can read it and run it yourself.


IT CAN'T FIND MY GAMES
----------------------
If auto-detection fails, drag your Steam "remote" folder onto the .exe. It's at:
  C:\Program Files (x86)\Steam\userdata\<your-id>\1054490\remote
(the folder that contains files named "local_...").


IF IT STOPS WORKING AFTER A GAME UPDATE
---------------------------------------
Wingspan saves are encrypted. If a future update changes that encryption, the
viewer would need a small update to match. That's the one thing that could
break it.


CREDITS
-------
Bird illustrations and card data come from the open-source Wingsearch project by
navarog (github.com/navarog/wingsearch), used under the GPLv3. The illustrations
are AI-generated "Unofficial Fan Art" from that project - not the game's official
artwork. The food, nest and habitat icons come from the same project. Thank you!


LICENSE
-------
This program is free software under the GNU General Public License v3.0, and it
comes with ABSOLUTELY NO WARRANTY. It includes GPLv3 material from Wingsearch, so
the whole program is distributed under those terms. You are free to use, study,
share and modify it, provided you pass on the same freedoms.

Full license text: LICENSE
Bundled components: THIRD-PARTY-NOTICES.txt
Complete source code: https://github.com/LendarioSonhador/wingspan-archive-viewer


Made for the Wingspan community. Enjoy!
