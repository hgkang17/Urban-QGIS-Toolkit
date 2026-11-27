
import json
import math
import re
import urllib.parse
import urllib.request


POSSESSION_API_URL = "https://api.vworld.kr/ned/data/getPossessionAttr"
POSSESSION_PAGE_SIZE = 1000
POSSESSION_MAX_PAGES_PER_QUERY = 100

PRIVATE_OWNER_CODES = {"0", "1", "3", "6", "7", "8", "9"}
NATIONAL_OWNER_CODES = {"2"}
PUBLIC_OWNER_CODES = {"4", "5"}
OWNER_CATEGORY_ORDER = ("사유지", "국유지", "공유지", "미분류")
PRIVATE_OWNER_NAMES = {
    "일본인",
    "창씨명등",
    "개인",
    "외국인",
    "외국공공기관",
    "법인",
    "종중",
    "종교단체",
    "기타단체",
}


def classify_owner_category(code, name=""):
    code_text = str(code or "").strip()
    normalized_code = code_text.lstrip("0") or ("0" if code_text else "")
    if normalized_code in NATIONAL_OWNER_CODES:
        return "국유지"
    if normalized_code in PUBLIC_OWNER_CODES:
        return "공유지"
    if normalized_code in PRIVATE_OWNER_CODES:
        return "사유지"

    return classify_owner_value(name)


def classify_owner_value(value):
    text = str(value or "").strip()
    if not text:
        return "미분류"

    code_match = re.match(r"^0?([0-9])$", text)
    if code_match:
        normalized_code = code_match.group(1)
        if normalized_code in NATIONAL_OWNER_CODES:
            return "국유지"
        if normalized_code in PUBLIC_OWNER_CODES:
            return "공유지"
        if normalized_code in PRIVATE_OWNER_CODES:
            return "사유지"

    code_with_name = re.match(r"^0?[0-9]\s+(.+)$", text)
    if code_with_name:
        text = code_with_name.group(1).strip()

    normalized = re.sub(r"\s+", "", text)
    if "국유" in normalized or normalized in {"국가소유", "국가", "대한민국"}:
        return "국유지"
    if normalized in {
        "공유지",
        "공유",
        "지자체소유",
        "시유지",
        "도유지",
        "시,도유지",
        "시도유지",
        "군유지",
        "구유지",
    }:
        return "공유지"
    if "사유" in normalized or normalized in PRIVATE_OWNER_NAMES:
        return "사유지"
    return "미분류"


def sort_owner_categories(values):
    order = {value: index for index, value in enumerate(OWNER_CATEGORY_ORDER)}
    return sorted(values, key=lambda value: (order.get(value, len(order)), value))


def normalize_pnu(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits if len(digits) == 19 else ""


def build_pnu_queries(pnus, prefix_length=13):
    normalized = sorted({normalize_pnu(pnu) for pnu in pnus} - {""})
    if len(normalized) <= 20:
        return normalized
    return sorted({pnu[:prefix_length] for pnu in normalized})


def parse_possession_response(payload):
    if not isinstance(payload, dict):
        raise RuntimeError("VWorld 소유정보 응답이 JSON 객체가 아닙니다.")

    root = payload.get("possessions") or payload.get("response") or payload
    if not isinstance(root, dict):
        raise RuntimeError("VWorld 소유정보 응답 구조를 확인할 수 없습니다.")

    result_code = str(root.get("resultCode") or "").strip()
    if result_code and result_code.upper() not in {"0", "00", "OK", "SUCCESS"}:
        result_message = root.get("resultMsg") or "VWorld 소유정보 조회에 실패했습니다."
        raise RuntimeError(f"{result_code}: {result_message}")

    records = root.get("field")
    if records is None:
        fields = root.get("fields")
        records = fields.get("field") if isinstance(fields, dict) else fields
    if records is None:
        records = []
    elif isinstance(records, dict):
        records = [records]
    elif not isinstance(records, list):
        records = []

    try:
        total_count = int(root.get("totalCount", len(records)))
    except (TypeError, ValueError):
        total_count = len(records)
    return records, max(total_count, 0)


def fetch_possession_records(
    api_key,
    pnu_queries,
    urlopen=None,
    progress_callback=None,
):
    if urlopen is None:
        urlopen = urllib.request.urlopen
    api_key = str(api_key or "").strip()
    if not api_key:
        raise RuntimeError("VWorld API 인증키가 없습니다.")

    queries = list(pnu_queries)
    all_records = []
    for query_index, pnu_query in enumerate(queries, start=1):
        page_number = 1
        page_total = 1
        while page_number <= page_total:
            params = {
                "key": api_key,
                "pnu": pnu_query,
                "format": "json",
                "numOfRows": str(POSSESSION_PAGE_SIZE),
                "pageNo": str(page_number),
            }
            url = POSSESSION_API_URL + "?" + urllib.parse.urlencode(params)
            try:
                with urlopen(url, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as error:
                safe_error = str(error).replace(api_key, "***")
                raise RuntimeError(
                    f"VWorld 소유정보 요청 실패({pnu_query}, {page_number}페이지): "
                    f"{safe_error}"
                ) from error

            page_records, total_count = parse_possession_response(payload)
            all_records.extend(page_records)
            page_total = max(1, math.ceil(total_count / POSSESSION_PAGE_SIZE))
            if page_total > POSSESSION_MAX_PAGES_PER_QUERY:
                raise RuntimeError(
                    f"PNU 접두어 {pnu_query}의 조회량이 {total_count:,}건으로 너무 많습니다. "
                    "조회 범위를 줄여 다시 실행하세요."
                )

            if progress_callback:
                progress_callback(
                    query_index,
                    len(queries),
                    page_number,
                    page_total,
                    len(all_records),
                )
            if not page_records or page_number >= page_total:
                break
            page_number += 1
    return all_records


def aggregate_possession_records(records, target_pnus):
    targets = {normalize_pnu(pnu) for pnu in target_pnus} - {""}
    buckets = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        pnu = normalize_pnu(record.get("pnu"))
        if not pnu or pnu not in targets:
            continue
        bucket = buckets.setdefault(
            pnu,
            {
                "codes": set(),
                "names": set(),
                "categories": set(),
                "months": set(),
                "updated_dates": set(),
                "record_count": 0,
            },
        )
        code = str(record.get("posesnSeCode") or "").strip()
        name = str(record.get("posesnSeCodeNm") or "").strip()
        month = str(record.get("stdrYm") or "").strip()
        updated_date = str(record.get("lastUpdtDt") or "").strip()
        if code:
            bucket["codes"].add(code)
        if name:
            bucket["names"].add(name)
        bucket["categories"].add(classify_owner_category(code, name))
        if month:
            bucket["months"].add(month)
        if updated_date:
            bucket["updated_dates"].add(updated_date)
        bucket["record_count"] += 1

    aggregated = {}
    for pnu, bucket in buckets.items():
        names = sorted(bucket["names"])
        codes = sorted(bucket["codes"])
        aggregated[pnu] = {
            "PNU": pnu,
            "소유구분코드": " / ".join(codes),
            "소유구분": " / ".join(names) or "코드 " + " / ".join(codes),
            "소유대분류": " / ".join(sort_owner_categories(bucket["categories"])),
            "기준연월": " / ".join(sorted(bucket["months"])),
            "자료기준일": " / ".join(sorted(bucket["updated_dates"])),
            "조회건수": bucket["record_count"],
        }
    return aggregated
