"""매일 실행되는 오케스트레이터: 조회수/소셜/수익 수집 -> GCS에 history 누적 저장
-> 대시보드 HTML 생성 -> 같은 버킷에 업로드.

필요 환경변수:
  YOUTUBE_API_KEY      - YouTube Data API v3 키 (필수)
  META_ACCESS_TOKEN    - 인스타/페북 조회용 액세스 토큰 (없으면 소셜 스킵)
  YT_REVENUE_OAUTH_JSON - YouTube Analytics OAuth 토큰 JSON 문자열 (없으면 수익 스킵)
  GCS_SA_KEY_JSON      - 버킷 쓰기 권한 서비스계정 키 JSON 문자열 (필수)
  GCS_BUCKET           - 기본값 coredlab-youtube-dashboard
"""
import json
import os

from google.cloud import storage

import collect_views
import collect_social
import collect_revenue
import build_dashboard

BUCKET_NAME = os.environ.get("GCS_BUCKET", "coredlab-youtube-dashboard")
DATA_PREFIX = "data/"


def get_bucket():
    sa_key = json.loads(os.environ["GCS_SA_KEY_JSON"])
    client = storage.Client.from_service_account_info(sa_key)
    return client.bucket(BUCKET_NAME)


def load_json_blob(bucket, path, default):
    blob = bucket.blob(path)
    if not blob.exists():
        return default
    return json.loads(blob.download_as_text(encoding="utf-8"))


def save_json_blob(bucket, path, data):
    blob = bucket.blob(path)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json",
    )


def main():
    bucket = get_bucket()

    views_history = load_json_blob(bucket, DATA_PREFIX + "views_history.json", [])
    social_history = load_json_blob(bucket, DATA_PREFIX + "social_history.json", [])
    revenue_history = load_json_blob(bucket, DATA_PREFIX + "revenue_history.json", [])

    try:
        api_key = os.environ["YOUTUBE_API_KEY"]
        snap = collect_views.collect(api_key)
        views_history.append(snap)
        save_json_blob(bucket, DATA_PREFIX + "views_history.json", views_history)
        print(f"[run_daily] views 스냅샷 저장 완료 (총 {len(views_history)}개)")
    except Exception as exc:
        print(f"[run_daily] 조회수 수집 실패: {exc}")

    try:
        token = os.environ.get("META_ACCESS_TOKEN")
        if token:
            snap = collect_social.collect(token)
            social_history.append(snap)
            save_json_blob(bucket, DATA_PREFIX + "social_history.json", social_history)
            print(f"[run_daily] social 스냅샷 저장 완료 (총 {len(social_history)}개)")
        else:
            print("[run_daily] META_ACCESS_TOKEN 미설정 - 소셜 수집 스킵")
    except Exception as exc:
        print(f"[run_daily] 소셜 수집 실패: {exc}")

    try:
        oauth_json = os.environ.get("YT_REVENUE_OAUTH_JSON")
        if oauth_json:
            snap = collect_revenue.collect(json.loads(oauth_json))
            revenue_history.append(snap)
            save_json_blob(bucket, DATA_PREFIX + "revenue_history.json", revenue_history)
            print(f"[run_daily] revenue 스냅샷 저장 완료 (총 {len(revenue_history)}개)")
        else:
            print("[run_daily] YT_REVENUE_OAUTH_JSON 미설정 - 수익 수집 스킵")
    except Exception as exc:
        print(f"[run_daily] 수익 수집 실패: {exc}")

    html = build_dashboard.build(views_history, social_history, revenue_history)
    out_blob = bucket.blob("dashboard.html")
    out_blob.upload_from_string(html, content_type="text/html; charset=utf-8")
    print(f"[run_daily] dashboard.html 업로드 완료 -> gs://{BUCKET_NAME}/dashboard.html")
    print(f"[run_daily] 열람 URL: https://storage.cloud.google.com/{BUCKET_NAME}/dashboard.html")


if __name__ == "__main__":
    main()
