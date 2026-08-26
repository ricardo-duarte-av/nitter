#!/usr/bin/env python3
"""Create a Nitter cookie session from a logged-in browser's cookies.

Nitter's OAuth login flow (get_session.py) no longer works: X gates the
onboarding/task.json endpoint behind a per-request x-client-transaction-id,
so password login returns HTTP 500 (code 131) before credentials are ever
sent. Cookie sessions still authenticate normally, so this script turns the
two cookies X sets on a logged-in web session into a sessions.jsonl entry.

How to get the cookies (do this once, in a browser logged in to x.com):
  1. Open x.com while logged in.
  2. Open DevTools -> Application/Storage -> Cookies -> https://x.com
  3. Copy the values of the `auth_token` and `ct0` cookies.

Then:
  python3 get_cookie_session.py <auth_token> <ct0> <path> [username]

  > pip install requests   # the only dependency
"""
import json
import sys

import requests

# Public web bearer token; used only to reach the auth-check endpoint.
BEARER = ("Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz"
          "4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")


def validate(auth_token, ct0):
    """Confirm the cookies authenticate against X.

    Uses help/settings.json: it is a plain authenticated endpoint that still
    exists (200 with valid cookies, 401 without). The old account/settings.json
    and verify_credentials.json endpoints now return 404 (code 34) for everyone,
    so they can't be used to check a session anymore.
    """
    resp = requests.get(
        "https://api.x.com/1.1/help/settings.json",
        headers={
            "Authorization": BEARER,
            "x-csrf-token": ct0,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "cookie": f"auth_token={auth_token}; ct0={ct0}",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/142.0.0.0 Safari/537.36"),
        },
    )
    if resp.status_code == 200:
        return

    try:
        errors = resp.json().get("errors", [])
    except ValueError:
        errors = resp.text[:300]
    print(f"Cookies did not authenticate (HTTP {resp.status_code}): {errors}")
    if resp.status_code == 401:
        print("The auth_token/ct0 are wrong, expired, or swapped. "
              "Re-copy them from a browser that is currently logged in, "
              "and make sure ct0 is the ~160-char token (not a 32-char one). "
              "Note: logging out in that browser invalidates auth_token.")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print("Usage: python3 get_cookie_session.py "
              "<auth_token> <ct0> <path> [username]")
        sys.exit(1)

    auth_token = sys.argv[1]
    ct0 = sys.argv[2]
    path = sys.argv[3]
    # X no longer exposes an endpoint that returns the screen name for a cookie
    # session, so the username is taken from the optional 4th argument. It is
    # only used by Nitter for logging, so leaving it empty is harmless.
    username = sys.argv[4] if len(sys.argv) == 5 else ""

    validate(auth_token, ct0)

    session_entry = {
        "kind": "cookie",
        "username": username,
        "auth_token": auth_token,
        "ct0": ct0,
    }

    try:
        with open(path, "a") as f:
            f.write(json.dumps(session_entry) + "\n")
    except Exception as e:
        print(f"Failed to write session information: {e}")
        sys.exit(1)

    who = f" (@{username})" if username else ""
    print(f"Authentication successful{who}. "
          f"Cookie session appended to {path}")
