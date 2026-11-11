# TODO

## Plan: on-screen favorites
One step at a time, each tested before the next.

0. **Test aids** (dev only, off by default). `--round` paints everything outside the circle white (`display.round_mask_color`) so the Mac window looks like the Pi. The `S` key (or `kill -USR1 <pid>`) saves a screenshot to `logs/screen.png`. Done.
   Test: run on the Mac, compare the masked window and screenshot with the Pi.
1. **Get in and out.** New `WpDisplayState.FAVORITES`. `assets/FavsBtn.png` sits left of play/pause, same y and size (about `[230, 640]`, 45px; `favs_button_pos/size/asset` in `display_config.yaml`). A disabled volume button mirrors it right of play/pause (about `[450, 640]`; `volume_button_*` config, `assets/VolBtn.png`): drawn, but a tap on it does nothing (and doesn't open quit confirm). Other positions stay as they are. It shows whenever connected, line-in included. The favorites screen is the background plus a back button (`favs_back_button_*` config; placeholder art until there's a real icon).
   Test: tap in, tap back; a tap elsewhere on now playing still opens quit confirm.
2. **Grid.** `WpFavContentDisplay` builds a 3x3 page of `WPDisplayButton`s from a snapshot of `sonosFavs`, with left/right page arrows (prev/next track art). Tapping a tile sends the existing `content` / `play_fav` event and returns to now playing. Tiles are plain, numbered squares until step 3. `--fake_favs N` replaces the real favorites with N fake ones (the Stream Deck shows them too).
   Taps use the same polling as the now-playing buttons: loop over the page's tiles with `check_tap` and send the matching favorite. `fetchState` builds the new favorites dict and swaps it in, so the screen never catches it half-built from the other thread.
   Test: 0 favorites ("No favorites" message), 1, 9, 10, 25; arrows only when there's another page; playing a favorite works. Done (grid layout in `favs_grid_*` / `favs_tile_*` / `favs_*_page_*` config).
2b. **Slide-in.** Favorites slides up from the bottom over now playing, and the back button becomes a down button (`assets/DownBtn.png`). Draw the favorites panel to its own surface and blit it at a y offset; a 0→1 slide value moves with `deltaTime`; stay in `FAVORITES` until fully slid out; ignore taps while moving. `_draw_centered_text` gets an optional target surface. Panel may want its own background/tint so it reads as a layer.
   Test: open/close animate both ways; taps ignored mid-slide; grid taps and paging still work once open. Done (panel is solid `favs_panel_color`, default black; `favs_slide_time` 0.3s).
3. **Labels.** New `wp_button_label.py` draws a labeled tile as a PIL image (moved from `WPStreamDeckUI._setupButtonWithLabel`). The Stream Deck uses it as-is; `WPDisplayButton` can be built from a PIL image.
   Test: deck labels look the same as before; screen tiles show names; long names split or truncate. Done (deck output pixel-identical; screen tile text in `favs_tile_font_sizes` / `favs_tile_font_asset`).
   Label quirks seen (shared code, so both deck and screen): it shrinks the font before trying two lines, so tiles end up in mixed sizes; a name too long for two lines truncates to one line instead of two lines with "..." on the second; a hyphen split rejoins with a space ("See- Through").
4. **Favorite art.** Move `WPStreamDeckUI._get_image_from_fav` (Ed's fetch code) somewhere shared and use it from both the deck and the screen: one fetch path, not a second copy. Add the speaker address to relative `/getaa?...` URIs, cache each image after the first download, fetch off the display thread, and turn the deck call back on. Playing a favorite already goes through the same `content`/`play_fav` handler from both.
5. Later: a more circular favorites layout.
6. Later: make the volume button work: open a volume control, maybe a drag control.

## Round display
The screen is a 720px circle: usable width at height `y` is `2·sqrt(360² − (y−360)²)`.
- Status line (y 690, width 360) is wider than the circle there (~288px), so long messages get clipped.
- Track title line 1 (~y 99, width 480) can clip a few pixels per side (circle ~448px wide there).
- The not-connected status text is drawn at x 20 near the bottom: in the corner, outside the circle.
- Consider a helper that returns usable width at a given y for new layout elements.

## Cleanup
- On-screen taps (transport and favorites) call Sonos on the display thread; playing a favorite also sleeps 0.5s, so the screen freezes briefly. Consider handing commands to the Sonos thread.
- Pause icon looks smaller than play: `PauseBtn.png` is 63×81 with padding, squashed to 45×45 (Ed fixing the art).
- `display_config.yaml` asks for `assets/VolDownBtn.png` but the file is `assets/volDownBtn.png`. Works on the Mac (case-insensitive), fails on the Pi.
- Stream Deck loop redraws every favorite key every second; only redraw when favorites change.
- `fetchState()` re-fetches Sonos favorites on every Sonos event; fetch on connect (and occasionally) instead.
- Remove leftover `print()` debugging (e.g. `mainCoordinator()` prints "get coordinator" on every call; transport info, fav dumps).
- `handleTransportEvent` has a dead `play_fav` case (favorites go through the `content` event).
