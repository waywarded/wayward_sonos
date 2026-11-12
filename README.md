# wayward_sonos

Now-playing display for a round Raspberry Pi screen and a Stream Deck, controlling Sonos.

## Running

```
python3 launcher.py start     # detached: keeps running after you leave SSH
python3 launcher.py stop
python3 launcher.py restart
python3 launcher.py status    # running or not, which config, and the last lines of logs/run.log
python3 launcher.py run       # same, but in the foreground
```

- Settings come from `local.env` (not in git): `SOCO_CONFIG` picks the room config, `SOCO_FLAGS` replaces the default `-f` (set it empty for a window), `DISPLAY` defaults to `:0` on the Pi.
- To run a different room for a while: `python3 launcher.py start --config configKitchen.yaml` (or `restart --config ...`). It lasts until you stop it: crash restarts and a plain `restart` keep it; `stop` then `start` goes back to `local.env`.
- The launcher restarts the app 10 seconds after a crash. A deliberate quit (press and hold above the song title) stays quit.
- Only one copy can run: the launcher refuses a second start, and `main.py` itself refuses if another copy holds `logs/app.lock`, however it was started.
- Output goes to `logs/run.log`; the app's own log is `logs/app.log`.

## Favorites through the Sonos cloud

With `favorites.load_via: cloud` (display_config.yaml) a tapped favorite is started with one call to the Sonos cloud, like the Sonos app does, instead of soco filling the queue. Needs internet and a one-time sign-in per machine:

1. A Control Integration at developer.sonos.com gives a key and secret. Put them in `local.env` with the redirect address saved there:
   `SONOS_CLIENT_ID=...`, `SONOS_CLIENT_SECRET=...`, `SONOS_REDIRECT_URI=https://localhost/callback`
2. `uv run sonos_auth.py` prints a sign-in link. Approve, then run `uv run sonos_auth.py '<address the browser ended on>'` (the page won't load; the code is in the address).
3. Tokens go to `sonos_tokens.json` (not in git) and refresh on their own. Copying that file and `local.env` to the Pi works too.

Without the sign-in the app logs a warning and loads favorites locally.
