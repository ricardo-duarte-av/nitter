#!/usr/bin/env python3
import requests
import json
import sys
import pyotp
import cloudscraper

# NOTE: pyotp, requests and cloudscraper are dependencies
# > pip install pyotp requests cloudscraper

TW_CONSUMER_KEY = '3nVuSoBZnx6U4vzUxf5w'
TW_CONSUMER_SECRET = 'Bcs59EFbbsdF6Sl9Ng71smgStWEGwXXKSjYvPVt7qys'

EXPLAINED_SUBTASKS = {
    "LoginAcid": "X wants an email/phone confirmation code. Log in from a browser "
                 "once to clear it, or use an account without this check.",
    "LoginTwoFactorAuthChallenge": "2FA is required - pass the TOTP secret as the "
                                   "3rd argument (the base32 string, not a 6-digit code).",
    "DenyLoginSubtask": "X refused the login (bad credentials, or the account is "
                        "locked/suspended/flagged).",
    "ArkoseLogin": "A captcha challenge was triggered. This script cannot solve it; "
                   "log in from a browser first, or try from a different IP.",
    "LoginEnterAlternateIdentifierSubtask": "X wants a phone number or username "
                                            "instead of the identifier given.",
}


def check_task(name, response):
    """Abort with a useful message if an onboarding step failed."""
    if response.status_code != 200:
        print(f"Step {name} failed with HTTP {response.status_code}:")
        print(response.text[:2000])
        sys.exit(1)

    try:
        body = response.json()
    except ValueError:
        print(f"Step {name} returned a non-JSON response:")
        print(response.text[:2000])
        sys.exit(1)

    if 'errors' in body:
        print(f"Step {name} returned errors: {body['errors']}")
        sys.exit(1)

    for subtask in body.get('subtasks', []):
        sid = subtask.get('subtask_id')
        if sid in EXPLAINED_SUBTASKS and sid != "LoginTwoFactorAuthChallenge":
            print(f"Step {name} -> {sid}: {EXPLAINED_SUBTASKS[sid]}")
            sys.exit(1)


def auth(username, password, otp_secret):
    bearer_token_req = requests.post("https://api.twitter.com/oauth2/token",
        auth=(TW_CONSUMER_KEY, TW_CONSUMER_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data='grant_type=client_credentials'
    ).json()

    if 'access_token' not in bearer_token_req:
        print("Failed to obtain bearer token:", bearer_token_req)
        sys.exit(1)

    bearer_token = f"{bearer_token_req['token_type']} {bearer_token_req['access_token']}"

    guest_token = requests.post(
        "https://api.twitter.com/1.1/guest/activate.json",
        headers={
            'Authorization': bearer_token,
             "User-Agent": "TwitterAndroid/10.21.0-release.0 (310210000-r-0) ONEPLUS+A3010/9"
        }
    ).json().get('guest_token')

    if not guest_token:
        print("Failed to obtain guest token.")
        sys.exit(1)

    twitter_header = {
        'Authorization': bearer_token,
        "Content-Type": "application/json",
        "User-Agent": "TwitterAndroid/10.21.0-release.0 (310210000-r-0) ONEPLUS+A3010/9 (OnePlus;ONEPLUS+A3010;OnePlus;OnePlus3;0;;1;2016)",
        "X-Twitter-API-Version": '5',
        "X-Twitter-Client": "TwitterAndroid",
        "X-Twitter-Client-Version": "10.21.0-release.0",
        "OS-Version": "28",
        "System-User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ONEPLUS A3010 Build/PKQ1.181203.001)",
        "X-Twitter-Active-User": "yes",
        "X-Guest-Token": guest_token,
        "X-Twitter-Client-DeviceID": ""
    }

    scraper = cloudscraper.create_scraper()
    scraper.headers = twitter_header

    task1 = scraper.post(
        'https://api.twitter.com/1.1/onboarding/task.json',
        params={
            'flow_name': 'login',
            'api_version': '1',
            'known_device_token': '',
            'sim_country_code': 'us'
        },
        json={
            "flow_token": None,
            "input_flow_data": {
                "country_code": None,
                "flow_context": {
                    "referrer_context": {
                        "referral_details": "utm_source=google-play&utm_medium=organic",
                        "referrer_url": ""
                    },
                    "start_location": {
                        "location": "deeplink"
                    }
                },
                "requested_variant": None,
                "target_user_id": 0
            }
        }
    )

    check_task("LoginFlowStart", task1)
    scraper.headers['att'] = task1.headers.get('att')

    task2 = scraper.post(
        'https://api.twitter.com/1.1/onboarding/task.json',
        json={
            "flow_token": task1.json().get('flow_token'),
            "subtask_inputs": [{
                "enter_text": {
                    "suggestion_id": None,
                    "text": username,
                    "link": "next_link"
                },
                "subtask_id": "LoginEnterUserIdentifier"
            }]
        }
    )

    check_task("LoginEnterUserIdentifier", task2)

    task3 = scraper.post(
        'https://api.twitter.com/1.1/onboarding/task.json',
        json={
            "flow_token": task2.json().get('flow_token'),
            "subtask_inputs": [{
                "enter_password": {
                    "password": password,
                    "link": "next_link"
                },
                "subtask_id": "LoginEnterPassword"
            }],
        }
    )

    check_task("LoginEnterPassword", task3)

    for t3_subtask in task3.json().get('subtasks', []):
        if "open_account" in t3_subtask:
            return t3_subtask["open_account"]
        elif "enter_text" in t3_subtask:
            response_text = t3_subtask["enter_text"]["hint_text"]
            totp = pyotp.TOTP(otp_secret)
            generated_code = totp.now()
            task4resp = scraper.post(
                "https://api.twitter.com/1.1/onboarding/task.json",
                json={
                    "flow_token": task3.json().get("flow_token"),
                    "subtask_inputs": [
                        {
                            "enter_text": {
                                "suggestion_id": None,
                                "text": generated_code,
                                "link": "next_link",
                            },
                            "subtask_id": "LoginTwoFactorAuthChallenge",
                        }
                    ],
                }
            )
            check_task("LoginTwoFactorAuthChallenge", task4resp)
            task4 = task4resp.json()
            for t4_subtask in task4.get("subtasks", []):
                if "open_account" in t4_subtask:
                    return t4_subtask["open_account"]
            print("2FA accepted but no session was returned. Subtasks:",
                  [t.get("subtask_id") for t in task4.get("subtasks", [])])
            return None

    print("Login did not produce a session. Subtasks returned:",
          [t.get("subtask_id") for t in task3.json().get("subtasks", [])])
    print("See EXPLAINED_SUBTASKS below for what these mean.")
    return None

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python3 get_session.py <username> <password> <2fa secret> <path>")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    otp_secret = sys.argv[3]
    path = sys.argv[4]

    result = auth(username, password, otp_secret)
    if result is None:
        print("Authentication failed.")
        sys.exit(1)

    session_entry = {
        "oauth_token": result.get("oauth_token"),
        "oauth_token_secret": result.get("oauth_token_secret")
    }

    try:
        with open(path, "a") as f:
            f.write(json.dumps(session_entry) + "\n")
        print("Authentication successful. Session appended to", path)
    except Exception as e:
        print(f"Failed to write session information: {e}")
        sys.exit(1)
