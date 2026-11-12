import os
import json
import time
import logging
import requests

from launcher import loadEnv

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_FILE = os.path.join(APP_DIR, 'sonos_tokens.json')
TOKEN_URL = 'https://api.sonos.com/login/v3/oauth/access'
CONTROL_URL = 'https://api.ws.sonos.com/control/api/v1'


class SonosCloudError(Exception):
    pass


# Loads favorites through the Sonos cloud API. The speakers can't load some favorites themselves
# (Apple Music library playlists fail after 20s, locally or through soco); the cloud loads all of them fast.
# Needs a one-time `uv run sonos_auth.py`; the access token lasts a day and is refreshed here.
# Favorite and group ids are the same as soco's (FV:2/19 is favorite '19', group.uid is the group id).
class WPSonosCloud:
    def __init__(self, timeout=15):
        self.timeout = timeout
        self.env = loadEnv()
        self.tokens = None

    def ready(self):
        return os.path.exists(TOKENS_FILE) and bool(self.env.get('SONOS_CLIENT_ID'))

    def accessToken(self):
        if self.tokens is None:
            if not os.path.exists(TOKENS_FILE):
                raise SonosCloudError("Not signed in to Sonos (run sonos_auth.py)")
            with open(TOKENS_FILE) as f:
                self.tokens = json.load(f)
        if time.time() > self.tokens.get('expires_at', 0) - 300:
            self.refresh()
        return self.tokens['access_token']

    def refresh(self):
        logging.info("Refreshing Sonos cloud token")
        response = requests.post(
            TOKEN_URL,
            auth=(self.env.get('SONOS_CLIENT_ID', ''), self.env.get('SONOS_CLIENT_SECRET', '')),
            data={'grant_type': 'refresh_token', 'refresh_token': self.tokens['refresh_token']},
            timeout=self.timeout)
        if not response.ok:
            raise SonosCloudError(f"Sonos token refresh failed ({response.status_code}): {response.text[:200]}")
        newTokens = response.json()
        newTokens.setdefault('refresh_token', self.tokens['refresh_token'])
        newTokens['expires_at'] = time.time() + newTokens.get('expires_in', 0)
        self.tokens = newTokens
        with open(TOKENS_FILE, 'w') as f:
            json.dump(newTokens, f, indent=2)

    def request(self, method, path, body=None):
        response = requests.request(
            method, CONTROL_URL + path,
            headers={'Authorization': 'Bearer ' + self.accessToken()},
            json=body, timeout=self.timeout)
        if response.status_code == 401:
            # token revoked or expired early: one refresh and retry
            self.refresh()
            response = requests.request(
                method, CONTROL_URL + path,
                headers={'Authorization': 'Bearer ' + self.tokens['access_token']},
                json=body, timeout=self.timeout)
        if not response.ok:
            raise SonosCloudError(f"Sonos cloud {method} {path} failed ({response.status_code}): {response.text[:200]}")
        return response.json() if response.content else {}

    # favItemId is soco's 'FV:2/19' or plain '19'
    def loadFavorite(self, groupId, favItemId, play=True):
        favoriteId = favItemId.split('/')[-1]
        self.request('POST', f'/groups/{groupId}/favorites',
                     {'favoriteId': favoriteId, 'playOnCompletion': play})
