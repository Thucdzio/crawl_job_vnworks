
# -*- coding: utf-8 -*-
import argparse
import math
from pathlib import Path
import pandas as pd
import numpy as np
import json
import re
import unidecode
from rapidfuzz import process, fuzz

CITIES_REF = [
    "Hà Nội", "Hồ Chí Minh", "Hải Phòng", "Đà Nẵng", "Cần Thơ", "An Giang",
    "Bà Rịa - Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu", "Bắc Ninh",
    "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước", "Bình Thuận",
    "Cà Mau", "Cao Bằng", "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Nai",
    "Đồng Tháp", "Gia Lai", "Hà Giang", "Hà Nam", "Hà Tĩnh", "Hải Dương",
    "Hậu Giang", "Hòa Bình", "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum",
    "Lai Châu", "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An", "Nam Định",
    "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên", "Quảng Bình",
    "Quảng Nam", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sóc Trăng",
    "Sơn La", "Tây Ninh", "Thái Bình", "Thái Nguyên", "Thanh Hóa",
    "Thừa Thiên Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang", "Vĩnh Long",
    "Vĩnh Phúc", "Yên Bái"
]

# Chuẩn hóa reference (không dấu, lowercase)
CITIES_REF_ASCII = [unidecode.unidecode(c).lower() for c in CITIES_REF]
INVALID_VALUES = {"unknown", "n/a", "na", "none", ""}

def normalize_city_auto(city: str, threshold: int = 80):
    if not isinstance(city, str) or city.strip() == "":
        return []

    # Tách nhiều city theo ; hoặc ,
    parts = re.split(r"[;,]", city)
    results = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        city_ascii = unidecode.unidecode(part).lower().strip()
        if city_ascii in INVALID_VALUES:
            continue

        # Fuzzy match với danh sách tham chiếu
        best_match = process.extractOne(city_ascii, CITIES_REF_ASCII, scorer=fuzz.ratio)

        if best_match:
            _, score, idx = best_match
            if score >= threshold:
                results.append(CITIES_REF[idx])
            else:
                results.append(part.title())

    return results

def clean_employment_type(x: str) -> str:
    if not isinstance(x, str):
        return "Unknown"
    x = x.lower().strip()

    if any(sym in x for sym in ["{", "[", "<"]):
        return "Unknown"

    if "full" in x and "time" in x:
        return "Full-time"
    if "part" in x and "time" in x:
        return "Part-time"
    if "contract" in x:
        return "Contract"
    if "intern" in x:
        return "Internship"
    if "temporary" in x:
        return "Temporary"
    if "manager" in x:
        return "Managerial"
    if "permanent" in x:
        return "Permanent"
    if "shift" in x:
        return "Shift work"

    return "Unknown"

def to_list(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                import json
                arr = json.loads(s)
                if isinstance(arr, list): return arr
            except Exception:
                pass
        return [x.strip() for x in s.split(",") if x.strip()]
    return []

def clean_languages(val):
    if pd.isna(val):
        return None
    s = str(val).strip()

    # Bỏ ngoặc vuông [ ] và dấu nháy '
    s = re.sub(r"[\[\]']", "", s).strip()

    # Loại bỏ giá trị rác
    bad_values = {"none","na","n/a","other",""}
    if s.lower() in bad_values:
        return None

    # Chuẩn hóa một số pattern phổ biến
    s = s.replace("English (fluent)", "English Fluent")
    s = s.replace("English B2+", "English B2")
    s = s.replace("Good Writing and Speaking English", "English")
    # Nếu chứa English + level thì rút gọn
    match = re.search(r"(English).*?(A1|A2|B1|B2|C1|C2)", s, flags=re.I)
    if match:
        return f"English {match.group(2).upper()}"

    # Nếu chỉ ghi English
    if "english" in s.lower():
        return "English"
    if "vietnamese" in s.lower():
        return "Vietnamese"

    return s

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Loại bỏ industry rác
    bad_industries = {"#Other", "<--OTHER-->", "<career>","Others","Unknown"}
    df = df[~df["industry"].isin(bad_industries)].copy()

    # 2 Loại bỏ languages_required
    if "languages_required" in df.columns:
        df["languages_required"] = df["languages_required"].apply(clean_languages)
        df = df.dropna(subset=["languages_required"])

    # 3. Chuẩn hóa core_skills thành list
    def parse_skills(val):
        if pd.isna(val): 
            return []
        s = str(val).strip()
        # Nếu là dạng list string
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s.replace("'", '"'))
                return arr if isinstance(arr, list) else [s]
            except Exception:
                return re.findall(r"'([^']+)'", s)  # fallback parse
        # Nếu là dạng 'Skill'
        return [s.strip("'")]

    df["core_skills"] = df["core_skills"].apply(parse_skills)

    # 4. Làm phẳng (explode)
    df = df.explode("core_skills")
    df["core_skills"] = df["core_skills"].str.strip()

    # 5. Chuẩn hóa city_guess :
    df["city_guess"] = df["city_guess"].apply(normalize_city_auto)
    df = df.explode("city_guess")
    df = df.dropna(subset=["city_guess"])
    df["city_guess"] = df["city_guess"].astype(str).str.strip()   

    return df
def safe_mean(series):
    s = pd.to_numeric(series, errors="coerce")
    return float(s.mean()) if s.notna().any() else np.nan

def make_report(df: pd.DataFrame, out_xlsx: Path, out_txt: Path):
    for c in ["industry","role_family","seniority","employment_type","company","name"]:
        if c in df.columns:
            df[c] = df[c].fillna("Unknown")
    
    for c in ["min","max","years_min","years_max","confidence"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    n_jobs = len(df)
    n_industries = df["industry"].nunique() if "industry" in df.columns else 0
    n_companies = df["company"].nunique() if "company" in df.columns else 0
    n_city = df["city_guess"].nunique() if "city_guess" in df.columns else 0
    avg_years_min = safe_mean(df["years_min"]) if "years_min" in df.columns else np.nan
    avg_years_max = safe_mean(df["years_max"]) if "years_max" in df.columns else np.nan
    # avg_salary_min = safe_mean(df["min"]) if "min" in df.columns else np.nan
    # avg_salary_max = safe_mean(df["max"]) if "max" in df.columns else np.nan
    # avg_conf = safe_mean(df["confidence"]) if "confidence" in df.columns else np.nan

    agg = {}
    if "name" in df.columns: agg["posts"] = ("name","count")
    if "years_min" in df.columns: agg["avg_exp_min"] = ("years_min","mean")
    if "years_max" in df.columns: agg["avg_exp_max"] = ("years_max","mean")
    # if "min" in df.columns: agg["avg_salary_min"] = ("min","mean")
    # if "max" in df.columns: agg["avg_salary_max"] = ("max","mean")
    # if "confidence" in df.columns: agg["avg_confidence"] = ("confidence","mean")

    by_industry = (df.groupby("industry", dropna=False)
                     .agg(**agg)
                     .sort_values("posts", ascending=False) if agg else pd.DataFrame())

    if {"industry","seniority"}.issubset(df.columns):
        piv_sen = pd.pivot_table(df, index="industry", columns="seniority", values="name", aggfunc="count", fill_value=0)
        piv_sen = piv_sen.reindex(piv_sen.sum(axis=1).sort_values(ascending=False).index)
    else:
        piv_sen = pd.DataFrame()

    if {"industry","city_guess"}.issubset(df.columns):
        piv_city = pd.pivot_table(df, index="industry", columns="city_guess", values="name", aggfunc="count", fill_value=0)
        piv_city = piv_city.reindex(piv_city.sum(axis=1).sort_values(ascending=False).index)
    else:
        piv_city = pd.DataFrame()

    if "core_skills" in df.columns:
        tmp = df.copy()
        tmp["core_skills"] = tmp["core_skills"].apply(to_list)
        skills = tmp.explode("core_skills")
        skills = skills.dropna(subset=["core_skills"])
        top_skills = (skills.groupby(["industry","core_skills"]).size()
                      .reset_index(name="count")
                      .sort_values(["industry","count"], ascending=[True, False]))
    else:
        top_skills = pd.DataFrame()

    if "languages_required" in df.columns:
        tmp2 = df.copy()
        tmp2["languages_required"] = tmp2["languages_required"].apply(to_list)
        langs = tmp2.explode("languages_required").dropna(subset=["languages_required"])
        lang_stats = (langs.groupby(["industry","languages_required"]).size()
                      .reset_index(name="count")
                      .sort_values(["industry","count"], ascending=[True, False]))
    else:
        lang_stats = pd.DataFrame()

    low_conf = pd.DataFrame()
    if "confidence" in df.columns:
        low_conf = df[df["confidence"] < 0.5].copy()

    if "company" in df.columns:
        company_stats = (
            df.groupby("company")
            .agg(posts=("name", "count"))
            .sort_values("posts", ascending=False)
            .head(10)
        )
    else:
        company_stats = pd.DataFrame()


   
    if "employment_type" in df.columns:
        df["employment_type"] = df["employment_type"].map(clean_employment_type)
        employment_counts = df["employment_type"].value_counts(normalize=True).mul(100).round(2)
        employment_df = employment_counts.rename_axis("employment_type").reset_index(name="percent")
    else:
        employment_df = pd.DataFrame()

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as xw:
        overview = pd.DataFrame({
            "metric": ["jobs","industries","companies","city","avg_years_min","avg_years_max"],
            "value": [n_jobs, n_industries, n_companies, n_city, avg_years_min, avg_years_max]
        })
        overview.to_excel(xw, index=False, sheet_name="00_Overview")

        if not by_industry.empty:
            by_industry.to_excel(xw, sheet_name="01_ByIndustry")
            ws = xw.sheets["01_ByIndustry"]
            wb = xw.book
            chart = wb.add_chart({"type":"column"})
            n = len(by_industry)
            chart.add_series({
                "name": "Posts",
                "categories": ["01_ByIndustry", 1, 0, n, 0],
                "values":     ["01_ByIndustry", 1, 1, n, 1],
            })
            chart.set_title({"name":"Posts by Industry"})
            chart.set_x_axis({"name":"Industry"})
            chart.set_y_axis({"name":"Posts"})
            ws.insert_chart("H2", chart)

        if not piv_sen.empty:
            piv_sen.to_excel(xw, sheet_name="02_SeniorityPivot")
            ws2 = xw.sheets["02_SeniorityPivot"]
            wb = xw.book
            chart2 = wb.add_chart({"type":"column", "subtype": "stacked"})
            n_rows = len(piv_sen)
            for idx, col in enumerate(piv_sen.columns, start=1):
                chart2.add_series({
                    "name": col,
                    "categories": ["02_SeniorityPivot", 1, 0, n_rows, 0],
                    "values":     ["02_SeniorityPivot", 1, idx, n_rows, idx],
                })
            chart2.set_title({"name":"Seniority Distribution by Industry"})
            chart2.set_x_axis({"name":"Industry"})
            chart2.set_y_axis({"name":"Posts"})
            ws2.insert_chart("H2", chart2)

        if not piv_city.empty:

            piv_city.to_excel(xw, sheet_name="03_CityPivot")
            ws3 = xw.sheets["03_CityPivot"]
            n_rows, n_cols = piv_city.shape
            city_totals = piv_city.sum(axis=0).sort_values(ascending=False).head(10)

            # Xuất ra sheet 
            city_totals.to_frame("TotalJobs").to_excel(xw, sheet_name="03_CityPivot", startrow=1, startcol=n_cols+2)

            # Vẽ chart dựa vào city_totals
            chart3 = wb.add_chart({"type": "column"})
            chart3.add_series({
                "name": "Top 10 Cities",
                "categories": ["03_CityPivot", 2, n_cols+2, len(city_totals)+1, n_cols+2], # city names
                "values":     ["03_CityPivot", 2, n_cols+3, len(city_totals)+1, n_cols+3], # job counts
            })
            chart3.set_title({"name": "Top 10 Cities by Job Count"})
            chart3.set_x_axis({"name": "City"})
            chart3.set_y_axis({"name": "Job Count"})
            ws3.insert_chart("H20", chart3)

            # Giữ lại conditional format cho pivot gốc
            if n_rows and n_cols:
                from xlsxwriter.utility import xl_rowcol_to_cell
                start_row, start_col = 1, 1
                end_row, end_col = n_rows, n_cols
                start_cell = xl_rowcol_to_cell(start_row, start_col)
                end_cell = xl_rowcol_to_cell(end_row, end_col)
                ws3.conditional_format(f"{start_cell}:{end_cell}", {"type":"3_color_scale"})
                
        if not top_skills.empty:
            top_skills.to_excel(xw, index=False, sheet_name="04_TopSkillsByIndustry")
        if not lang_stats.empty:
            lang_stats.to_excel(xw, index=False, sheet_name="05_LanguagesByIndustry")
        if not low_conf.empty:
            low_conf_cols = [c for c in ["name","company","industry","role_family","seniority","confidence","summary"] if c in low_conf.columns]
            low_conf[low_conf_cols].to_excel(xw, index=False, sheet_name="06_LowConfidence")
        # if not company_stats.empty:
        #     company_stats.to_excel(xw, sheet_name="07_TopCompanies")

        #     ws7 = xw.sheets["07_TopCompanies"]
        #     wb = xw.book
        #     chart_comp = wb.add_chart({"type": "column"})
        #     n = len(company_stats)
        #     chart_comp.add_series({
        #         "name": "Job Posts",
        #         "categories": ["07_TopCompanies", 1, 0, n, 0],
        #         "values": ["07_TopCompanies", 1, 1, n, 1],
        #     })
        #     chart_comp.set_title({"name": "Top 10 Companies by Job Posts"})
        #     chart_comp.set_x_axis({"name": "Company"})
        #     chart_comp.set_y_axis({"name": "Number of Posts"})
        #     ws7.insert_chart("E2", chart_comp)

       
        if not employment_df.empty:
            employment_df.to_excel(xw, sheet_name="08_EmploymentType", index=False)

            ws8 = xw.sheets["08_EmploymentType"]
            wb = xw.book
            chart_emp = wb.add_chart({"type": "pie"})
            chart_emp.add_series({
                "name": "Employment Type Distribution",
                "categories": ["08_EmploymentType", 1, 0, len(employment_df), 0],
                "values": ["08_EmploymentType", 1, 1, len(employment_df), 1],
            })
            chart_emp.set_title({"name": "Employment Type Percentage"})
            ws8.insert_chart("D2", chart_emp)

    with open(out_txt, "w", encoding="utf-8") as w:
        w.write("=== INDUSTRY HIRING REPORT SUMMARY ===\n")
        w.write(f"Total jobs: {n_jobs}\n")
        w.write(f"Industries: {n_industries}\n")
        w.write(f"Companies: {n_companies}\n")
        if not math.isnan(avg_years_min): w.write(f"Avg years min: {avg_years_min:.2f}\n")
        if not math.isnan(avg_years_max): w.write(f"Avg years max: {avg_years_max:.2f}\n")
        # if not math.isnan(avg_salary_min): w.write(f"Avg salary min: {avg_salary_min:,.0f}\n")
        # if not math.isnan(avg_salary_max): w.write(f"Avg salary max: {avg_salary_max:,.0f}\n")
        # if not math.isnan(avg_conf): w.write(f"Avg confidence: {avg_conf:.2f}\n")
        if "industry" in df.columns:
            top = df["industry"].value_counts().head(5)
            w.write("\nTop industries by posts:\n")
            for k,v in top.items():
                w.write(f" - {k}: {v}\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", required=True, help="Merged CSV (jobs_with_llm.csv)")
    ap.add_argument("--out", default="jobs_industry_report", help="Output file root")
    args = ap.parse_args()

    df = pd.read_csv(args.merged)
    df = clean_data(df)
    out_root = Path(args.out)
    make_report(df, out_root.with_suffix(".xlsx"), out_root.with_suffix(".txt"))
    print(f"Saved: {out_root.with_suffix('.xlsx')} and {out_root.with_suffix('.txt')}")

if __name__ == "__main__":
    main()
#  python industry_report.py --merged jobs_with_llm.csv --out jobs_industry_report