import logging
import re
import threading
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import requests


# what a sub/wave station knows that Sonos doesn't pass on: the show and its host, ('Sleepytime', 'Wren'), and each
# song's exact cover and album. Sonos only gets "artist - title", so this asks the station's own server, at the
# stream's address, for /api/now-playing. A radio stream is taken to be sub/wave when that answers with an
# activeShow; servers that don't are remembered and not asked again.
# sub/wave runs ahead of the speakers (its stream buffer, then theirs), so the songs it reports are kept for a
# while: by the time the speaker gets to one, its cover is usually already known.
# Fetches run on their own thread so a slow or missing server never holds up the speaker updates; `onChange`
# is called when the show changes or a song arrives.
class WpSubwave:
    def __init__(self, onChange, refresh=30, timeout=3, keepSongs=10):
        self.onChange = onChange
        self.refresh = refresh
        self.timeout = timeout
        self.keepSongs = keepSongs
        self.notSubwave = set()     # servers that didn't answer like sub/wave
        self.server = None          # the one playing now
        self.show = ('', '')
        self.songs = OrderedDict()  # (artist, title), loosely -> (cover url, album), newest last
        self.missed = None          # the last song asked for and not known, so it's fetched for once
        self.fetchedAt = 0
        self.fetching = False
        self.lock = threading.Lock()

    # (show, host) for a stream link, as last fetched; starts a fetch when that's stale
    def showFor(self, uri):
        server = self.serverFor(uri)
        with self.lock:
            if server != self.server:
                self.server, self.show, self.fetchedAt = server, ('', ''), 0
                self.songs.clear()
            if server is None:
                return ('', '')
            if time.monotonic() - self.fetchedAt > self.refresh:
                self.startFetch(server)
            return self.show

    # (cover url, album) for a song on the stream showFor last saw, or None. A song not seen yet is fetched for,
    # once, unless `fetch` is False; onChange follows if it turns up
    def songFor(self, artist, title, fetch=True):
        key = self.songKey(artist, title)
        with self.lock:
            if self.server is None or not key[1]:
                return None
            found = self.songs.get(key)
            if found is None and fetch and key != self.missed:
                self.missed = key
                self.startFetch(self.server)
            return found

    # case, spacing and punctuation vary between the stream's tags and the library's
    def songKey(self, artist, title):
        return tuple(re.sub(r'\W+', '', (s or '').lower()) for s in (artist, title))

    # x-rincon-mp3radio://http://host:7700/stream.mp3 -> http://host:7700
    def serverFor(self, uri):
        url = (uri or '').split('://', 1)[-1] if uri and not uri.startswith('http') else (uri or '')
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            return None
        server = f'{parts.scheme}://{parts.netloc}'
        return None if server in self.notSubwave else server

    # with the lock held
    def startFetch(self, server):
        if not self.fetching:
            self.fetching = True
            threading.Thread(target=self.fetch, args=(server,), daemon=True, name='subwave').start()

    def fetch(self, server):
        show, song = ('', ''), None
        try:
            data = requests.get(f'{server}/api/now-playing', timeout=self.timeout).json()
            active = data.get('activeShow') if isinstance(data, dict) else None
            if not isinstance(active, dict):
                raise ValueError('no activeShow')
            name = (active.get('name') or '').strip()
            host = ((active.get('persona') or {}).get('name') or (data.get('dj') or {}).get('name') or '').strip()
            show = (name, host if name else '')
            playing = data.get('nowPlaying') or {}
            if playing.get('subsonic_id') and playing.get('title'):
                song = (self.songKey(playing.get('artist'), playing.get('title')),
                        (f"{server}/api/cover/{playing['subsonic_id']}", (playing.get('album') or '').strip()))
        except (requests.ConnectionError, requests.Timeout) as e:
            # unreachable for now: keep what's known and try again later
            logging.info(f'sub/wave: {server} not answering: {e}')
            with self.lock:
                self.fetching = False
                self.fetchedAt = time.monotonic()
            return
        except Exception as e:
            logging.info(f'sub/wave: {server} is not a sub/wave station ({e})')
            with self.lock:
                self.notSubwave.add(server)
        with self.lock:
            self.fetching = False
            self.fetchedAt = time.monotonic()
            if server != self.server:
                return
            changed = show != self.show
            self.show = show
            if song and song[0] not in self.songs:
                self.songs[song[0]] = song[1]
                while len(self.songs) > self.keepSongs:
                    self.songs.popitem(last=False)
                changed = True
        if changed:
            self.onChange()
