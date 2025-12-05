import argparse
import json
import re
from pathlib import Path
import pandas as pd

def normalize_whitespace(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.replace("\xa0"," ")).strip()

def norm_name_key(s: str) -> str:
    s = normalize_whitespace(s).lower()
    s = re.sub(r"[“”\"'’‘\-\–\—]", "", s)
    return s

def to_list(val):
    if isinstance(val, list):
        return [normalize_whitespace(x) for x in val if isinstance(x, str)]
    if isinstance(val, str):
        s = normalize_whitespace(val)
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [normalize_whitespace(x) for x in arr]
            except Exception:
                pass
        parts = [p.strip() for p in re.split(r",|;|\|", s) if p.strip()]
        return parts
    return []

ROLE_MAP = {
    "operational":"Operations",
    "operation":"Operations",
    "ops":"Operations",
    "engineering":"Engineering",
    "dev ops":"DevOps","dev-ops":"DevOps","devop":"DevOps",
    "sw":"Software","software engineering":"Software",
    "qa":"QA","quality assurance":"QA",
    "hr":"HR",
}
SENIORITY_SET = {"Intern","Junior","Mid","Senior","Lead","Manager","Director"}

def normalize_llm_row(d: dict) -> dict:
    out = dict(d)
    role = out.get("role_family") or out.get("role") or out.get("role_type")
    if role:
        k = normalize_whitespace(role).lower()
        out["role_family"] = ROLE_MAP.get(k, out.get("role_family", role))
    sen = out.get("seniority")
    if sen and sen not in SENIORITY_SET:
        m = sen.lower()
        if "manager" in m: out["seniority"] = "Manager"
        elif "lead" in m: out["seniority"] = "Lead"
        elif "senior" in m: out["seniority"] = "Senior"
        elif "junior" in m: out["seniority"] = "Junior"
        elif "intern" in m: out["seniority"] = "Intern"
        elif "director" in m: out["seniority"] = "Director"
        else: out["seniority"] = "Mid"
    out["core_skills"] = to_list(out.get("core_skills",""))
    out["languages_required"] = to_list(out.get("languages_required",""))
    exp = out.get("experience_years") or {}
    if isinstance(exp, dict):
        out["years_min"] = exp.get("min")
        out["years_max"] = exp.get("max")
    else:
        out["years_min"] = None
        out["years_max"] = None
    for k in ["industry","employment_type","education_required","name"]:
        if k in out: out[k] = normalize_whitespace(out[k])
    try:
        out["confidence"] = float(out.get("confidence", 0.0))
    except Exception:
        out["confidence"] = 0.0
    return out

def normalize_summary_row(d: dict) -> dict:
    out = dict(d)
    out["name"] = normalize_whitespace(out.get("name",""))
    print("Name:", end=" ") 
    print(out.get("name",""))
    out["company"] = normalize_whitespace(out.get("company",""))
    print("Company:", end=" ")
    print(out.get("company",""))
    out["summary"] = out.get("summary","").strip()
    loc_list = to_list(out.get("location",""))
    out["locations_joined"] = "; ".join(loc_list)
    out["city_guess"] = guess_city(out.get("locations_joined",""))
    out["skills"] = to_list(out.get("skills",""))
    return out

CITY_MAP = {
    "Hồ Chí Minh": ["Hồ Chí Minh", "TP.HCM", "TP HCM", "Thủ Đức", "Quận 1", "Quận 3", "Bình Thạnh", "Tân Bình", "Gò Vấp", "Phú Nhuận"],
    "Hà Nội": ["Hà Nội", "Ha Noi", "Cầu Giấy", "Đống Đa", "Ba Đình", "Thanh Xuân", "Hoàng Mai", "Hà Đông", "Long Biên", "Nam Từ Liêm", "Bắc Từ Liêm","Ngô Quyền"],
    "Đà Nẵng": ["Đà Nẵng", "Da Nang", "Hải Châu", "Sơn Trà", "Liên Chiểu", "Ngũ Hành Sơn", "Thanh Khê"]
}

def guess_city(s: str) -> str:
    low = s.lower()
    for canon, variants in CITY_MAP.items():
        for v in variants:
            if v.lower() in low:
                return canon
    if "việt nam" in low or "vietnam" in low:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) >= 2:
            return parts[-2]
    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cls", required=True, help="Classifications JSON (array)")
    ap.add_argument("--sum", required=True, help="Summaries JSON (array)")
    ap.add_argument("--out", default="jobs_with_llm", help="Output file root (without extension)")
    args = ap.parse_args()

    with open(args.cls, "r", encoding="utf-8") as f:
        cls = json.load(f)
    with open(args.sum, "r", encoding="utf-8") as f:
        sums = json.load(f)

    cls_rows = [normalize_llm_row(r) for r in cls]
    sum_rows = [normalize_summary_row(r) for r in sums]

    df_cls = pd.DataFrame(cls_rows)
    df_sum = pd.DataFrame(sum_rows)

    df_cls["name_key"] = df_cls["name"].map(norm_name_key)
    df_sum["name_key"] = df_sum["name"].map(norm_name_key)

    merged = pd.merge(df_sum, df_cls, on="name_key", how="left", suffixes=("","_llm"))
   
   
    # Reorder
    preferred = [
        "name","company","locations_joined","city_guess",
        "industry","role_family","seniority","employment_type",
        "years_min","years_max","education_required","languages_required","core_skills",
        "summary","confidence","name_key"
    ]
    merged = merged[[c for c in merged.columns if c in preferred]]

    # cols = [c for c in preferred if c in merged.columns] + [c for c in merged.columns if c not in preferred]
    # merged = merged[cols]

    out_root = Path(args.out)
    merged.to_csv(out_root.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    try:
        merged.to_parquet(out_root.with_suffix(".parquet"), index=False)
    except Exception:
        pass

    total = len(merged)
    matched = merged["industry"].notna().sum() if "industry" in merged.columns else 0
   
    print(f"Merged {total} jobs. LLM fields matched: {matched}.")
    print(f"Saved -> {out_root.with_suffix('.csv')}")

if __name__ == "__main__":
    main()
#python merge_llm_and_summaries.py --cls classified_jobs.json --sum summarized_jobs_test.json