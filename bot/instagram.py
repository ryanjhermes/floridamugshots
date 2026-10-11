"""Publishing through the Instagram API with Instagram Login (graph.instagram.com).

Instagram fetches media from a public URL; it can't take an upload. Publishing is: create a container,
wait until Instagram finishes processing it (status_code FINISHED), then publish it.
"""
import time

import requests

from . import config


def _call(method, path, **params):
    r = requests.request(method, f"{config.GRAPH_API}/{path}", timeout=60,
                         **({"data": params} if method == "POST" else {"params": params}))
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"{method} {path.split('?')[0]} -> {r.status_code}: {data.get('error', data)}")
    return data


def post(caption, image_url=None, video_url=None):
    """Publish a Reel (video_url) or a photo (image_url). Returns the published media id."""
    token, user = config.ACCESS_TOKEN, config.USER_ID
    if not token or not user:
        raise RuntimeError("IG_ACCESS_TOKEN and IG_USER_ID must be set")

    params = {"caption": caption, "access_token": token}
    if video_url:
        params.update(media_type="REELS", video_url=video_url, share_to_feed="true")
    else:
        params["image_url"] = image_url
    container = _call("POST", f"{user}/media", **params)["id"]
    print(f"📦 Container {container} for {video_url or image_url}")

    # Publishing before FINISHED fails with "Media ID is not available". Up to 5 min for video, 1 for photos
    for _ in range(60 if video_url else 12):
        status = _call("GET", container, fields="status_code", access_token=token).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram couldn't process the media: {status}")
        time.sleep(5)
    else:
        raise RuntimeError("Timed out waiting for Instagram to process the media")

    media_id = _call("POST", f"{user}/media_publish", creation_id=container, access_token=token)["id"]
    print(f"🎉 Published {media_id}")
    return media_id
