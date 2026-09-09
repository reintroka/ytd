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
    data = http_get(url)
    if "error" in data:
        return data

    media_url = (
        f"https://{host}/v20.0/{obj_id}/media?fields=like_count,comments_count,timestamp,media_type,media_product_type&limit=3&access_token="
        + urllib.parse.quote(token)
    )
    media = http_get(media_url)
    recent = media.get("data", [])
    if recent:
        data["recent_posts_sampled"] = len(recent)
        data["avg_likes"] = round(sum(m.get("like_count", 0) for m in recent) / len(recent), 1)
        data["avg_comments"] = round(sum(m.get("comments_count", 0) for m in recent) / len(recent), 1)
        data["latest_post_likes"] = recent[0].get("like_count")
        data["latest_post_comments"] = recent[0].get("comments_count")

        # 조회수: 릴스/동영상은 plays, 이미지/캐로셀은 reach(노출과 유사한 대체 지표)를
        # 써서 미디어 타입 섞여도 항상 값 하나는 얻도록 함(2026-09-09, 팔로워만 추적하던
        # collect_social.py에 조회수 추가 - Threads의 검증된 insights 패턴을 이식).
        views_list = []
        for m in recent:
            is_video = m.get("media_type") == "VIDEO" or m.get("media_product_type") == "REELS"
            # 2026-09-09: "plays"는 최신 Graph API(v26.0)에서 더 이상 유효한 값이 아님
            # (#100 에러로 확인) - 릴스/동영상도 "views"로 통합됨. Explorer에서
            # instagram_manage_insights 권한 추가 후 실측 확인.
            metric = "views" if is_video else "reach"
            insights_url = (
                f"https://{host}/v20.0/{m['id']}/insights?"
                + urllib.parse.urlencode({"metric": metric, "access_token": token})
            )
            insights = http_get(insights_url)
            if "error" in insights:
                print(f"[collect_social] IG insights({metric}) 실패 media={m.get('id')}: {insights['error']}")
                continue
            for item in insights.get("data", []):
                vals = item.get("values", [{}])
                if vals:
                    views_list.append(vals[0].get("value", 0))
        if views_list:
            data["avg_views"] = round(sum(views_list) / len(views_list), 1)
            data["latest_post_views"] = views_list[0]
    return data


def fetch_facebook_pages(pages, token):
    result = {}
    for name, page_id in pages.items():
        url = f"https://graph.facebook.com/v20.0/{page_id}?fields=name,fan_count,followers_count&access_token=" + urllib.parse.quote(token)
        data = http_get(url)
        if "error" not in data:
            # 조회수: 페이지 최근 동영상 3개의 views 평균(2026-09-09 신규 - 이전엔
            # 팔로워 수만 추적, 게시물별 조회수를 아예 조회한 적이 없었음). 처음엔
            # video_insights?metric=total_video_views로 시도했으나, 비디오 노드
            # 자체에 views 필드가 직접 있어 별도 insights 호출 없이 훨씬 간단하게
            # 가져올 수 있음을 Graph API Explorer 실측으로 확인(현재 3개 페이지
            # 모두 동영상 게시물이 없어 views_list는 계속 비어있을 수 있음 - 정상).
            videos_url = (
                f"https://graph.facebook.com/v20.0/{page_id}/videos?"
                + urllib.parse.urlencode({"fields": "created_time,views", "limit": 3, "access_token": token})
            )
            videos = http_get(videos_url)
            if "error" in videos:
                print(f"[collect_social] FB {name} videos 목록 조회 실패: {videos['error']}")
            recent_videos = videos.get("data", []) if "error" not in videos else []
            if "error" not in videos and not recent_videos:
                print(f"[collect_social] FB {name}: 최근 동영상 게시물 없음(videos edge는 정상 응답)")
            views_list = [v["views"] for v in recent_videos if "views" in v]
            if views_list:
                data["recent_posts_sampled"] = len(recent_videos)
                data["avg_views"] = round(sum(views_list) / len(views_list), 1)
                data["latest_post_views"] = views_list[0]
        result[name] = data
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
            print(f"[collect_social] 인스타그램 {name}: 팔로워 {data.get('followers_count')}명, 평균 조회수 {data.get('avg_views')}")

    pages = config.get("facebook_pages")
    if pages:
        fb_data = fetch_facebook_pages(pages, access_token)
        snapshot["facebook_pages"] = fb_data
        for name, data in fb_data.items():
            if "error" in data:
                print(f"[collect_social] 페이스북 {name} 조회 실패: {data['error']}")
            else:
                print(f"[collect_social] 페이스북 {name}: 팔로워 {data.get('followers_count')}명, 평균 조회수 {data.get('avg_views')}")

    return snapshot, token_state
