"""심리학 채널 YouTube Analytics 수익 스냅샷 수집 (클라우드용)."""
from datetime import date, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CHANNEL_ID = "UC2zmJCoGdOHLvy9SSNIsnRw"  # 오늘의 심리학

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def collect(oauth_info: dict) -> dict:
    creds = Credentials.from_authorized_user_info(oauth_info, SCOPES)
    yta = build("youtubeAnalytics", "v2", credentials=creds)

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=27)

    report = yta.reports().query(
        ids=f"channel=={CHANNEL_ID}",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics="estimatedRevenue,estimatedAdRevenue,views,estimatedMinutesWatched",
        dimensions="day",
    ).execute()

    rows = report.get("rows", [])
    total_revenue = sum(r[1] for r in rows)
    total_ad_revenue = sum(r[2] for r in rows)
    total_views = sum(r[3] for r in rows)

    print(f"[collect_revenue] {start} ~ {end} 총수익 ${total_revenue:.2f} (광고 ${total_ad_revenue:.2f}), 조회수 {total_views}")

    return {
        "checked_at": date.today().isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "total_revenue": round(total_revenue, 3),
        "total_ad_revenue": round(total_ad_revenue, 3),
        "total_views": total_views,
        "daily": rows,
    }
