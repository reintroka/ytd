"""스레드(Threads) 팔로워/게시물 조회수 스냅샷 수집 (클라우드용).

토큰 자동갱신: Threads 장기 토큰은 60일 유효, th_refresh_token 그랜트로
자체 재발급 가능(앱 시크릿 불필요 - 지금 토큰만 있으면 됨). state(현재
토큰+발급일)를 GCS에 저장해두고 50일 이상 지나면 자동 재발급한다.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config_threads.json"

REFRESH_MIN_AGE_DAYS = 50
RECENT_POSTS_LIMIT = 3


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


def maybe_refresh_token(token_state: dict) -> dict:
    obtained_at = datetime.fromisoformat(token_state["obtained_at"])
    age_days = (datetime.now(timezone.utc) - obtained_at).days
    if age_days < REFRESH_MIN_AGE_DAYS:
        return token_state

    url = (
        "https://graph.threads.net/v1.0/refresh_access_token?"
        + urllib.parse.urlencode(
            {"grant_type": "th_refresh_token", "access_token": token_state["access_token"]}
        )
    )
    result = http_get(url)
    if "access_token" not in result:
        print(f"[collect_threads] 토큰 갱신 실패, 기존 토큰 계속 사용: {result}")
        return token_state

    print(f"[collect_threads] 토큰 자동 갱신 완료 (나이 {age_days}일)")
    return {
        "access_token": result["access_token"],
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_account(user_id: str, token: str) -> dict:
    followers_url = (
        f"https://graph.threads.net/v1.0/{user_id}/threads_insights?"
        + urllib.parse.urlencode({"metric": "followers_count", "access_token": token})
    )
    followers_resp = http_get(followers_url)
    if "error" in followers_resp:
        return followers_resp

    followers_count = None
    for item in followers_resp.get("data", []):
        if item.get("name") == "followers_count":
            followers_count = item.get("total_value", {}).get("value")

    posts_url = (
        f"https://graph.threads.net/v1.0/{user_id}/threads?"
        + urllib.parse.urlencode(
            {"fields": "id,timestamp", "limit": RECENT_POSTS_LIMIT, "access_token": token}
        )
    )
    posts_resp = http_get(posts_url)
    posts = posts_resp.get("data", [])

    views_list, likes_list = [], []
    for p in posts:
        insights_url = (
            f"https://graph.threads.net/v1.0/{p['id']}/insights?"
            + urllib.parse.urlencode({"metric": "views,likes", "access_token": token})
        )
        insights = http_get(insights_url)
        for item in insights.get("data", []):
            v = item.get("values", [{}])[0].get("value", 0)
            if item.get("name") == "views":
                views_list.append(v)
            elif item.get("name") == "likes":
                likes_list.append(v)

    result = {"followers_count": followers_count, "recent_posts_sampled": len(posts)}
    if views_list:
        result["avg_views"] = round(sum(views_list) / len(views_list), 1)
        result["latest_post_views"] = views_list[0]
    if likes_list:
        result["avg_likes"] = round(sum(likes_list) / len(likes_list), 1)
    return result


def collect(token_state: dict):
    """token_state: {"access_token": ..., "obtained_at": ...}.
    반환: (snapshot, 갱신된 token_state)"""
    token_state = maybe_refresh_token(token_state)
    token = token_state["access_token"]

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    snapshot = {"timestamp": datetime.now(timezone.utc).isoformat(), "accounts": {}}

    for name, user_id in config.get("accounts", {}).items():
        data = fetch_account(user_id, token)
        snapshot["accounts"][name] = data
        if "error" in data:
            print(f"[collect_threads] {name} 조회 실패: {data['error']}")
        else:
            print(
                f"[collect_threads] {name}: 팔로워 {data.get('followers_count')}명, "
                f"최근 게시물 평균 조회수 {data.get('avg_views')}"
            )

    return snapshot, token_state
