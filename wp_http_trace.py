import logging
import threading
import time
import requests
from urllib.parse import urlsplit

# dev aid (--trace_http): logs every HTTP request the app makes, which is every soco call plus art downloads,
# so a slow tap shows what else was talking to the speaker at the same moment (grep "HTTP" in logs/app.log)
_lock = threading.Lock()
_inFlight = 0

def install():
    original = requests.Session.request

    def tracedRequest(self, method, url, *args, **kwargs):
        global _inFlight
        parts = urlsplit(url)
        # soco names the UPnP action in this header, e.g. "...:AVTransport:1#Play"; art and info requests don't have one
        action = (kwargs.get('headers') or {}).get('SOAPACTION', '')
        if action:
            service, _, name = action.strip('"').rpartition('#')
            what = f"{service.split(':')[-2]}#{name}"
        else:
            what = parts.path + ('?…' if parts.query else '')
        with _lock:
            _inFlight += 1
            others = _inFlight - 1
        started = time.monotonic()
        result = 'error'
        try:
            response = original(self, method, url, *args, **kwargs)
            result = str(response.status_code)
            return response
        finally:
            with _lock:
                _inFlight -= 1
            logging.info(f"HTTP {time.monotonic() - started:5.2f}s {method.upper()} {parts.hostname} {what} -> {result} "
                         f"[{threading.current_thread().name}, {others} others in flight at start]")

    requests.Session.request = tracedRequest
