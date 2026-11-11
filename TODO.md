# TODO

## Next
- `wp_fav_content_display.py`: on-screen favorites grid (fits the round display). Fix the import (`WpAppStatus` → `WPAppStatus` from `wp_app_status`).

## Round display
The screen is a 720px circle: usable width at height `y` is `2·sqrt(360² − (y−360)²)`.
- Status line (y 690, width 360) is wider than the circle there (~288px), so long messages get clipped.
- Track title line 1 (~y 99, width 480) can clip a few pixels per side (circle ~448px wide there).
- Consider a helper that returns usable width at a given y for new layout elements.

## Cleanup
- Stream Deck loop redraws every favorite key every second; only redraw when favorites change.
- `fetchState()` re-fetches Sonos favorites on every Sonos event; fetch on connect (and occasionally) instead.
- Favorite key art: `_get_image_from_fav` is stubbed out; cache images before enabling it.
- Remove leftover `print()` debugging (e.g. `mainCoordinator()` prints "get coordinator" on every call; transport info, fav dumps).
- `handleTransportEvent` has a dead `play_fav` case (favorites go through the `content` event).
