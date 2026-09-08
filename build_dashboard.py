"""3개 history 리스트 + 템플릿으로 완결된(standalone) dashboard.html 문자열을 만든다."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "dashboard_template.html"

PAGE_HEAD = (
    '<!DOCTYPE html>\n<html lang="ko">\n<head>\n'
    '<meta charset="UTF-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
)
HEAD_BODY_SPLIT = '<div class="wrap">'


def build(views_history: list, social_history: list, revenue_history: list) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    data_json = json.dumps(views_history, ensure_ascii=False)
    social_json = json.dumps(social_history, ensure_ascii=False)
    revenue_json = json.dumps(revenue_history, ensure_ascii=False)
    filled = (
        template
        .replace("__DATA_JSON__", data_json)
        .replace("__SOCIAL_DATA_JSON__", social_json)
        .replace("__REVENUE_DATA_JSON__", revenue_json)
    )

    head_part, body_part = filled.split(HEAD_BODY_SPLIT, 1)
    return (
        PAGE_HEAD
        + head_part
        + "</head>\n<body>\n"
        + HEAD_BODY_SPLIT
        + body_part
        + "\n</body>\n</html>\n"
    )
