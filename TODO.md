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
4a. **Favorites refresh.** Read the favorites list from Sonos on connect, when the refresh button is tapped, and on a slow background timer (`connection.favs_refresh_time`, default 600s), since the app runs for days or months and favorites get edited on the phone. Stop re-reading favorites on every playback event. The refresh button sits right of the "Favorites" heading (about `[425, 45]`, 30px; `favs_refresh_button_*` config, `assets/RefreshBtn.png` from Ed). The tap only sets a flag; the Sonos thread does the fetch so the display never waits on the network. The Stream Deck picks up whatever the latest list is.
   Test: refresh button sets the flag and the list updates; timer refresh fires; no favorites fetch on playback events.
4b. **Favorite art.** Move `WPStreamDeckUI._get_image_from_fav` (Ed's fetch code) somewhere shared and use it from both the deck and the screen: one fetch path, not a second copy. Cache images by art link, so unchanged favorites never download again and art for removed favorites is dropped (keeps memory flat over weeks). Add the speaker address to relative `/getaa?...` links, fetch off the display thread, and turn the deck call back on. Playing a favorite already goes through the same `content`/`play_fav` handler from both.
   Test: art on tiles and keys; refresh with no changes downloads nothing; a changed favorite downloads only its art. Done (`wp_fav_art.WPFavArtCache` on `WPAppStatus.favArt`; real Kitchen favorites incl. a `/getaa` one all load).
   Screen tiles: art (120px) with the name underneath; until art arrives, the first two letters on a solid tile (`favs_tile_size`, `favs_label_*`, `favs_initials_*`).
   Stream Deck keys still draw the name over the art, which is hard to read on light art (e.g. See-Through); consider a dark band or stronger shadow in `renderButtonLabel`.
5. Later: a more circular favorites layout.
6. Later: make the volume button work: open a volume control, maybe a drag control.
7. **Bigger hit boxes.** `WPDisplayButton` gets a tap padding around its art (`button_hit_padding`, 20px) for the small buttons: prev/next, play/pause, favorites, volume, back, refresh, page arrows. Art size unchanged; favorites tiles get no padding (their gaps are smaller than that).
   Test: taps just outside the art still hit; neighboring tap areas don't overlap. Done.
8. **Press-and-hold to quit.** Replace "tap any blank spot → quit confirm" with an invisible hold area above the song title, where the room name is (`quit_hold_area`, `quit_hold_time` ~1.5s). Only on now playing, not while favorites is up. Holding long enough opens the existing quit confirm. Blank taps then do nothing.
   Test: short tap does nothing; hold opens confirm; hold elsewhere or with favorites up does nothing; releasing early cancels.
9. **Line-in favorite.** Always the first favorite, on the screen grid and the Stream Deck, when the room config names the speaker with the line-in (`line_in_device`, e.g. "Front Room"). Uses the existing `line_in_track_image` art and `line_in_track_name` label. Picking it sends the same `content`/`play_fav` event; `handleContentEvent` switches the main group's coordinator to that speaker's line-in (`switch_to_line_in(source=...)`).
   Test: present with 0 favorites and with several; absent when `line_in_device` isn't set; plays the record player on Front Room.
10. Later: a UI for switching which device/group the display controls.

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
- Remove leftover `print()` debugging (e.g. `mainCoordinator()` prints "get coordinator" on every call; transport info, fav dumps).
- `handleTransportEvent` has a dead `play_fav` case (favorites go through the `content` event).
