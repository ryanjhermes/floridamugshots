"""Instagram token setup and health checks.

python -m bot auth url              # Print the login URL (only needed if the dashboard can't generate a token)
python -m bot auth exchange CODE    # Trade the ?code= from the redirect for a 60-day token
python -m bot auth check            # Who the token belongs to, and today's publishing quota
python -m bot auth refresh          # Extend the token another 60 days (token must be 24h+ old)

Long-lived tokens expire after 60 days unless refreshed, and an expired one can't be refreshed.
Tokens are printed once so you can paste them into .env; never commit or share them.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from . import config


def _get(url, **params):
    r = requests.get(url, params=params, timeout=30)
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise SystemExit(f"❌ {r.status_code}: {data.get('error', data)}")
    return data


def _expiry(expires_in):
    return (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).date()


def auth_url():
    if not config.APP_ID:
        raise SystemExit("❌ Set IG_APP_ID in .env (Instagram app ID, not the Meta app ID)")
    print(config.OAUTH_AUTHORIZE_URL + "?" + urlencode({
        "client_id": config.APP_ID,
        "redirect_uri": config.REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(config.SCOPES),
        "enable_fb_login": 0,
        "force_reauth": "true",
    }))
    print(f"\nLog in as florida.mugshots, approve, then copy the code= value from the {config.REDIRECT_URI} "
          "redirect (drop any trailing #_). Codes expire in 1 hour.")


def exchange(code):
    if not (config.APP_ID and config.APP_SECRET):
        raise SystemExit("❌ Set IG_APP_ID and IG_APP_SECRET in .env")
    r = requests.post(config.OAUTH_TOKEN_URL, timeout=30, data={
        "client_id": config.APP_ID,
        "client_secret": config.APP_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": config.REDIRECT_URI,
        "code": code.split("#")[0],
    })
    short = r.json()
    if r.status_code != 200 or "access_token" not in short:
        raise SystemExit(f"❌ {r.status_code}: {short}")
    long = _get(f"{config.GRAPH_API_UNVERSIONED}/access_token", grant_type="ig_exchange_token",
                client_secret=config.APP_SECRET, access_token=short["access_token"])
    print(f"✅ Long-lived token (expires {_expiry(long['expires_in'])}). Put these in .env:\n")
    print(f"IG_ACCESS_TOKEN={long['access_token']}")
    print(f"IG_USER_ID={short['user_id']}")
    print(f"\nGranted: {short.get('permissions', 'see check')}")


def check():
    if not config.ACCESS_TOKEN:
        raise SystemExit("❌ Set IG_ACCESS_TOKEN in .env")
    me = _get(f"{config.GRAPH_API}/me", access_token=config.ACCESS_TOKEN,
              fields="user_id,username,account_type,media_count,followers_count")
    print(f"✅ @{me['username']} ({me.get('account_type')}), user_id {me['user_id']}, "
          f"{me.get('media_count', 0)} posts, {me.get('followers_count', 0)} followers")
    if config.USER_ID and config.USER_ID != str(me["user_id"]):
        print(f"⚠️  IG_USER_ID in .env is {config.USER_ID}, but the token belongs to {me['user_id']}")
    quota = _get(f"{config.GRAPH_API}/{me['user_id']}/content_publishing_limit",
                 access_token=config.ACCESS_TOKEN, fields="quota_usage,config")["data"][0]
    print(f"📊 Published in the last 24h: {quota.get('quota_usage', 0)}/"
          f"{quota.get('config', {}).get('quota_total', '?')}")


def refresh(save_path=None):
    """Extend the token. save_path (CI) writes the token to a file for `gh secret set`, never to the log."""
    if not config.ACCESS_TOKEN:
        raise SystemExit("❌ Set IG_ACCESS_TOKEN in .env")
    data = _get(f"{config.GRAPH_API_UNVERSIONED}/refresh_access_token",
                grant_type="ig_refresh_token", access_token=config.ACCESS_TOKEN)
    print(f"✅ Refreshed, expires {_expiry(data['expires_in'])}")
    if save_path:
        with open(save_path, "w") as f:
            f.write(data["access_token"])
    elif data["access_token"] != config.ACCESS_TOKEN:
        print(f"Token changed. Update .env:\nIG_ACCESS_TOKEN={data['access_token']}")
