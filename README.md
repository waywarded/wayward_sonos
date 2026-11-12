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
