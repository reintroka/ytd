"""유튜브 조회수/구독자 스냅샷 수집 (클라우드용 - GCS에 누적 저장하는 run_daily.py에서 호출됨)."""
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config_channels.json"

API_BASE = "https://www.googleapis.com/youtube/v3"
SHORT_MAX_SECONDS = 183
MAX_RECENT_PER_TYPE = 6


def _api_get(path: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}/{path}?{query}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_duration_seconds(iso_duration: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not m:
        return 0
    h, mnt, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mnt * 60 + s


def fetch_channel_snapshot(api_key: str, channel_id: str) -> dict:
    ch = _api_get(
        "channels",
        {"part": "contentDetails,statistics", "id": channel_id, "key": api_key},
    )
    items = ch.get("items", [])
    if not items:
        return {"error": "channel not found or no access"}

    uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    subscriber_count = items[0].get("statistics", {}).get("subscriberCount")

    playlist = _api_get(
        "playlistItems",
        {
            "part": "contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": 30,
            "key": api_key,
        },
    )
    video_ids = [it["contentDetails"]["videoId"] for it in playlist.get("items", [])]
    if not video_ids:
        return {"subscriber_count": subscriber_count, "shorts": [], "longform": []}

    videos = _api_get(
        "videos",
        {
            "part": "statistics,contentDetails,snippet",
            "id": ",".join(video_ids),
            "key": api_key,
        },
    )

    shorts, longform = [], []
    for v in videos.get("items", []):
        duration_s = _parse_duration_seconds(v["contentDetails"]["duration"])
        entry = {
            "video_id": v["id"],
            "title": v["snippet"]["title"],
            "published_at": v["snippet"]["publishedAt"],
            "view_count": int(v.get("statistics", {}).get("viewCount", 0)),
            "duration_seconds": duration_s,
        }
        (shorts if duration_s <= SHORT_MAX_SECONDS else longform).append(entry)

    shorts.sort(key=lambda x: x["published_at"], reverse=True)
    longform.sort(key=lambda x: x["published_at"], reverse=True)

    return {
        "subscriber_count": subscriber_count,
        "shorts": shorts[:MAX_RECENT_PER_TYPE],
        "longform": longform[:MAX_RECENT_PER_TYPE],
    }


def collect(api_key: str) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    channels = config["channels"]

    snapshot = {"timestamp": datetime.now(timezone.utc).isoformat(), "channels": {}}
    for channel_id, name in channels.items():
        print(f"[collect_views] {name} ({channel_id}) 조회 중...")
        try:
            data = fetch_channel_snapshot(api_key, channel_id)
        except Exception as exc:
            data = {"error": str(exc)}
            print(f"  실패: {exc}")
        snapshot["channels"][name] = {"channel_id": channel_id, **data}
    return snapshot
