"""인스타그램/페이스북 팔로워 스냅샷 수집 (클라우드용)."""
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config_social.json"


def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return {"error": json.loads(body)}
        except Exception:
            return {"error": body}


def fetch_instagram(cfg, token):
    host = cfg["host"]
    obj_id = cfg.get("object_id", "me")
    url = f"https://{host}/v20.0/{obj_id}?fields=username,followers_count,media_count&access_token=" + urllib.parse.quote(token)
    return http_get(url)


def fetch_facebook_pages(pages, token):
    result = {}
    for name, page_id in pages.items():
        url = f"https://graph.facebook.com/v20.0/{page_id}?fields=name,fan_count,followers_count&access_token=" + urllib.parse.quote(token)
        result[name] = http_get(url)
    return result


def collect(access_token: str) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "instagram": {},
        "facebook_pages": {},
    }

    for name, cfg in config.get("instagram", {}).items():
        data = fetch_instagram(cfg, access_token)
        snapshot["instagram"][name] = data
        if "error" in data:
            print(f"[collect_social] 인스타그램 {name} 조회 실패: {data['error']}")
        else:
            print(f"[collect_social] 인스타그램 {name}: 팔로워 {data.get('followers_count')}명")

    pages = config.get("facebook_pages")
    if pages:
        fb_data = fetch_facebook_pages(pages, access_token)
        snapshot["facebook_pages"] = fb_data
        for name, data in fb_data.items():
            if "error" in data:
                print(f"[collect_social] 페이스북 {name} 조회 실패: {data['error']}")
            else:
                print(f"[collect_social] 페이스북 {name}: 팔로워 {data.get('followers_count')}명")

    return snapshot
