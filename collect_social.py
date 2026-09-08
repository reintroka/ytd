"""인스타그램/페이스북 팔로워 스냅샷 수집 (클라우드용).

토큰 자동갱신: state(access_token+발급일)를 GCS에 저장해두고, 40일 이상
지나면 fb_exchange_token 그랜트로 재발급한다(무료, 재인증 불필요).
META_APP_ID/META_APP_SECRET이 있어야 자동갱신이 동작하며, 없으면 갱신을
건너뛰고 넘겨받은 access_token을 그대로 쓴다.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config_social.json"

REFRESH_MIN_AGE_DAYS = 40


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


def maybe_refresh_token(token_state: dict, app_id: str, app_secret: str) -> dict:
    """token_state: {"access_token": str, "obtained_at": iso str}.
    40일 이상 지났으면 fb_exchange_token으로 재발급, 아니면 그대로 반환."""
    if not app_id or not app_secret:
        return token_state

    obtained_at = datetime.fromisoformat(token_state["obtained_at"])
    age_days = (datetime.now(timezone.utc) - obtained_at).days
    if age_days < REFRESH_MIN_AGE_DAYS:
        return token_state

    url = (
        "https://graph.facebook.com/v20.0/oauth/access_token?"
        + urllib.parse.urlencode(
            {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": token_state["access_token"],
            }
        )
    )
    result = http_get(url)
    if "access_token" not in result:
        print(f"[collect_social] 토큰 갱신 실패, 기존 토큰 계속 사용: {result}")
        return token_state

    print(f"[collect_social] 토큰 자동 갱신 완료 (나이 {age_days}일)")
    return {
        "access_token": result["access_token"],
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }


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


def collect(token_state: dict, app_id: str, app_secret: str):
    """token_state: {"access_token": ..., "obtained_at": ...}.
    반환: (snapshot, 갱신된 token_state)"""
    token_state = maybe_refresh_token(token_state, app_id, app_secret)
    access_token = token_state["access_token"]

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

    return snapshot, token_state
