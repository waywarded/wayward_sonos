# One-time sign-in to the Sonos cloud API, so the app can load favorites through it.
#   uv run sonos_auth.py               prints the Sonos sign-in link
#   uv run sonos_auth.py '<url>'       after approving, pass the address the browser ended up on
#                                      (the page won't load; the code is in the address)
# Reads SONOS_CLIENT_ID, SONOS_CLIENT_SECRET and SONOS_REDIRECT_URI from local.env and saves the
# tokens to sonos_tokens.json (gitignored). The app refreshes them on its own after this.
import sys
import json
import time
import secrets
import urllib.parse
import requests

from launcher import loadEnv
from wp_sonos_cloud import TOKENS_FILE, TOKEN_URL

AUTH_URL = 'https://api.sonos.com/login/v3/oauth'


def signInLink(env):
    query = urllib.parse.urlencode({
        'client_id': env['SONOS_CLIENT_ID'],
        'response_type': 'code',
        'state': secrets.token_urlsafe(8),
        'scope': 'playback-control-all',
        'redirect_uri': env['SONOS_REDIRECT_URI'],
    })
    return f"{AUTH_URL}?{query}"


def exchangeCode(env, redirectedUrl):
    params = urllib.parse.parse_qs(urllib.parse.urlparse(redirectedUrl).query)
    if 'code' not in params:
        sys.exit(f"No code in that address: {params.get('error', ['?'])[0]}")
    response = requests.post(
        TOKEN_URL,
        auth=(env['SONOS_CLIENT_ID'], env['SONOS_CLIENT_SECRET']),
        data={'grant_type': 'authorization_code', 'code': params['code'][0],
              'redirect_uri': env['SONOS_REDIRECT_URI']},
        timeout=15)
    if not response.ok:
        sys.exit(f"Sonos refused the code ({response.status_code}): {response.text}")
    tokens = response.json()
    tokens['expires_at'] = time.time() + tokens.get('expires_in', 0)
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    print(f"Signed in. Tokens saved to {TOKENS_FILE} (access token good for {tokens.get('expires_in', 0) // 3600}h, refreshed automatically).")


if __name__ == '__main__':
    env = loadEnv()
    missing = [k for k in ('SONOS_CLIENT_ID', 'SONOS_CLIENT_SECRET', 'SONOS_REDIRECT_URI') if not env.get(k)]
    if missing:
        sys.exit(f"Add {', '.join(missing)} to local.env first")
    if len(sys.argv) > 1:
        exchangeCode(env, sys.argv[1])
    else:
        print("Open this link, sign in and approve, then run again with the address you land on:\n")
        print(signInLink(env))
