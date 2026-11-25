import logging
import threading
import time
from urllib.parse import urlsplit

import requests


# the show on a sub/wave station and its host, ('Sleepytime', 'Wren'). Sonos only passes on the song, so this asks the
# station's own server, at the stream's address, for /api/now-playing. A radio stream is taken to be sub/wave
# when that answers with an activeShow; servers that don't are remembered and not asked again.
# Fetches run on their own thread so a slow or missing server never holds up the speaker updates; `onChange`
# is called with the new (show, host) (or ('', '')) when it changes.
class WpSubwave:
    def __init__(self, onChange, refresh=30, timeout=3):
        self.onChange = onChange
        self.refresh = refresh
        self.timeout = timeout
        self.notSubwave = set()     # servers that didn't answer like sub/wave
        self.server = None          # the one playing now
        self.show = ('', '')
        self.fetchedAt = 0
        self.fetching = False
        self.lock = threading.Lock()

    # (show, host) for a stream link, as last fetched; starts a fetch when that's stale
    def showFor(self, uri):
        server = self.serverFor(uri)
        with self.lock:
            if server != self.server:
                self.server, self.show, self.fetchedAt = server, ('', ''), 0
            if server is None:
                return ('', '')
            if not self.fetching and time.monotonic() - self.fetchedAt > self.refresh:
                self.fetching = True
                threading.Thread(target=self.fetch, args=(server,), daemon=True, name='subwave').start()
            return self.show

    # x-rincon-mp3radio://http://host:7700/stream.mp3 -> http://host:7700
    def serverFor(self, uri):
        url = (uri or '').split('://', 1)[-1] if uri and not uri.startswith('http') else (uri or '')
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            return None
        server = f'{parts.scheme}://{parts.netloc}'
        return None if server in self.notSubwave else server

    def fetch(self, server):
        show = ('', '')
        try:
            data = requests.get(f'{server}/api/now-playing', timeout=self.timeout).json()
            active = data.get('activeShow') if isinstance(data, dict) else None
            if not isinstance(active, dict):
                raise ValueError('no activeShow')
            name = (active.get('name') or '').strip()
            host = ((active.get('persona') or {}).get('name') or (data.get('dj') or {}).get('name') or '').strip()
            show = (name, host if name else '')
        except (requests.ConnectionError, requests.Timeout) as e:
            # unreachable for now: keep the last show and try again later
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
            if server != self.server or show == self.show:
                return
            self.show = show
        self.onChange(show)
