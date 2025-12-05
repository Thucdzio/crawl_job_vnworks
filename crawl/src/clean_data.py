import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

VN_DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"]

CITY_MAP = {
    "Hồ Chí Minh": ["Hồ Chí Minh", "TP HCM", "TP.HCM", "TP. HCM", "Ho Chi Minh", "Tp Hồ Chí Minh"],
    "Hà Nội": ["Hà Nội", "Ha Noi", "Hanoi"],
    "Đà Nẵng": ["Đà Nẵng", "Da Nang"],
    "Bình Dương": ["Bình Dương"],
    "Đồng Nai": ["Đồng Nai"],
    "Hải Phòng": ["Hải Phòng", "Hai Phong"],
    "Cần Thơ": ["Cần Thơ", "Can Tho"],
}

def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE).strip()
    s = unicodedata.normalize("NFC", s)
    return s

def parse_date_any(s: str):
    s = normalize_text(s)
    for fmt in VN_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return pd.NaT

_CURRENCY = {
    "vnd": "VND", "đ": "VND", "₫": "VND", "vnđ": "VND",
    "usd": "USD", "$": "USD",
    "eur": "EUR", "€": "EUR"
}

def detect_currency(s: str):
    s_low = s.lower()
    for k, v in _CURRENCY.items():
        if k in s_low:
            return v
    return None

def parse_salary(s: str):
    out = dict(salary_text=normalize_text(s or ""), currency=None, min=None, max=None, period="month")
    st = out["salary_text"]
    if not st or re.search(r"thỏa thuận|tho[aâ]? thu[aâ]n|negotiable", st, re.I):
        return out
    cur = detect_currency(st) or "VND"
    out["currency"] = cur
    million = bool(re.search(r"\b(triệu|tr|million)\b", st, re.I))
    thousand = bool(re.search(r"(?<![A-Za-z])[kK]\b|nghìn|ngan", st, re.I))
    nums = [float(x.replace(",", "").replace(".", "")) for x in re.findall(r"\d[\d,\.]*", st)]
    if not nums:
        return out
    lo = min(nums); hi = max(nums)
    if cur == "VND":
        if million:
            lo *= 1_000_000; hi *= 1_000_000
        elif thousand:
            lo *= 1_000; hi *= 1_000
        elif (1 <= lo <= 300) and ("đ" in st.lower() or "vnd" in st.lower() or "₫" in st or "triệu" in st.lower() or "tr" in st.lower()):
            lo *= 1_000_000; hi *= 1_000_000
    out["min"], out["max"] = int(lo), int(hi)
    if re.search(r"/\s*(mo|month)|theo tháng|/tháng", st, re.I):
        out["period"] = "month"
    elif re.search(r"/\s*(yr|year)|/năm|theo năm", st, re.I):
        out["period"] = "year"
    return out

def split_skills(s: str):
    s = normalize_text(s)
    if not s:
        return []
    parts = [p.strip() for p in re.split(r",|;|\|", s) if p.strip()]
    seen = set(); out = []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key); out.append(p)
    return out

def parse_benefits(val):
    if isinstance(val, list):
        raw = " ".join([normalize_text(x) for x in val])
    else:
        raw = normalize_text(val or "")
    if not raw:
        return []
    raw = re.sub(r"(Healthcare)(\s*benefit)", r"\1 \2", raw, flags=re.I)
    raw = re.sub(r"(performance bonus)(Healthcare)", r"\1; \2", raw, flags=re.I)
    raw = re.sub(r"(Healthcare)(\s*benefit)(Allowances?)", r"\1 \2; \3", raw, flags=re.I)
    parts = re.split(r";|•|\||\n|,(?=\s*[A-Z])", raw)
    parts = [p.strip(" -•") for p in parts if p and p.strip(" -•")]
    final = []
    for p in parts:
        if ":" in p:
            t, c = p.split(":", 1)
            final.extend([t.strip(), c.strip()])
        else:
            final.append(p)
    seen = set(); result = []
    for p in final:
        if p and p.lower() not in seen:
            seen.add(p.lower()); result.append(p)
    return result

def standardize_locations(val):
    if isinstance(val, list):
        arr = [normalize_text(x) for x in val if isinstance(x, str)]
    elif isinstance(val, str):
        arr = [normalize_text(val)]
    else:
        arr = []
    joined = "; ".join([x for x in arr if x])
    city = ""
    low = joined.lower()
    for canonical, variants in CITY_MAP.items():
        for v in variants:
            if v.lower() in low:
                city = canonical
                break
        if city: break
    if not city and "việt nam" in low:
        before = joined.split(",")
        if len(before) >= 2:
            city = normalize_text(before[-2])
    return joined, city

def parse_experience(s: str):
    s = normalize_text(s)
    if not s:
        return None, None
    if re.search(r"không yêu cầu|no\s+experience", s, re.I):
        return 0, 0
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return None, None
    if "-" in s or "–" in s:
        return nums[0], nums[1] if len(nums) > 1 else None
    if re.search(r"tối thiểu|min", s, re.I):
        return nums[0], None
    if len(nums) == 1:
        return nums[0], nums[0]
    return nums[0], (nums[1] if len(nums) > 1 else None)

def split_career(s: str):
    s = normalize_text(s)
    if not s:
        return "", ""
    parts = [p.strip() for p in s.split(">")]
    main = parts[0] if parts else ""
    sub = parts[1] if len(parts) > 1 else ""
    return main, sub

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="input", default="vietnamworks_test.json")
    ap.add_argument("--out", dest="output", default="jobs_preprocessed")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data.get("jobs", [])
    df = pd.DataFrame(jobs)

    text_cols = ["name","salary","upload_date","expiration_date","company","job_position","field",
                 "language_cv","minimum_years_of_experience","career","description","requirements","link_job"]
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].map(normalize_text)

    if "upload_date" in df.columns:
        df["upload_date_iso"] = df["upload_date"].map(parse_date_any)
    if "expiration_date" in df.columns:
        df["expiration_date_iso"] = df["expiration_date"].map(parse_date_any)

    if "salary" in df.columns:
        sal = df["salary"].map(parse_salary).apply(pd.Series)
        df = pd.concat([df, sal], axis=1)

    if "skill" in df.columns:
        df["skills"] = df["skill"].map(split_skills)

    if "benefits" in df.columns:
        df["benefits_list"] = df["benefits"].map(parse_benefits)

    if "locations" in df.columns:
        locs = df["locations"].map(standardize_locations).apply(pd.Series)
        locs.columns = ["locations_joined","city_guess"]
        df = pd.concat([df, locs], axis=1)

    if "career" in df.columns:
        career_split = df["career"].map(split_career).apply(pd.Series)
        career_split.columns = ["career_main","career_sub"]
        df = pd.concat([df, career_split], axis=1)

    if "minimum_years_of_experience" in df.columns:
        exp = df["minimum_years_of_experience"].map(parse_experience).apply(pd.Series)
        exp.columns = ["years_min","years_max"]
        df = pd.concat([df, exp], axis=1)

    if "link_job" in df.columns:
        df = df.drop_duplicates(subset=["link_job"])

    preferred = [
        "name","company","field","career","career_main","career_sub",
        "job_position","language_cv","minimum_years_of_experience","years_min","years_max",
        "salary","currency","min","max","period",
        "upload_date","upload_date_iso","expiration_date","expiration_date_iso",
        "locations","locations_joined","city_guess",
        "skills","benefits_list",
        "description","requirements","link_job"
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols]

    root = Path(args.output)
    df.to_parquet(str(root) + ".parquet", index=False)
    df.to_csv(str(root) + ".csv", index=False, encoding="utf-8-sig")
    df.to_json(str(root) + ".json", orient="records", force_ascii=False, indent=2)
    print(f"Saved {len(df)} rows -> {root}.parquet and {root}.csv and {root}.json")

if __name__ == "__main__":
    main()
