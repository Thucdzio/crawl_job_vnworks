
import json
import re
from groq import Groq

# Khởi tạo client Groq với API key
client = Groq(api_key="your_api_key")

# Danh sách các model khả dụng
models = [
    "gemma2-9b-it",
    "allam-2-7b",
    "llama-3.1-8b-instant",
    "meta-llama/llama-guard-4-12b",
    "meta-llama/llama-prompt-guard-2-22m",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-guard-4-12b",
    "meta-llama/llama-prompt-guard-2-86m"
]

# Mark
model_flags = [True] * len(models)

# Đọc dữ liệu từ file JSON
with open("../summarized_jobs_test.json", "r", encoding="utf-8") as file:
    data = json.load(file)

def guess_industry_from_summary(summary: str) -> str:
    """
    Dựa vào summary (chuỗi text), đoán ngành phù hợp.
    Trả về một trong các ngành trong taxonomy hoặc "Others" nếu không xác định được.
    """

    summary_lower = summary.lower()

    
    manufacturing_keywords = [
        "lubricant", "distributor", "manufacturing", "factory", "production",
        "industrial", "engineering", "assembly line", "quality control",
        "technical sales", "b2b", "supply chain"
    ]

   
    it_keywords = [
        "software", "developer", "engineer", "programming", "python",
        "java", "javascript", "it infrastructure", "devops", "qa", "data"
    ]

    
    finance_keywords = [
        "finance", "accounting", "audit", "banking", "investment",
        "tax", "financial analysis", "budgeting"
    ]

    
    marketing_keywords = [
        "marketing", "seo", "sem", "content", "brand", "advertising",
        "campaign", "social media", "digital marketing"
    ]

    
    hr_keywords = [
        "human resources", "recruitment", "talent acquisition",
        "employee relations", "payroll", "training"
    ]

    
    sales_keywords = [
        "sales", "customer", "account management", "client", "business development",
        "crm", "territory"
    ]

   
    education_keywords = [
        "teaching", "curriculum", "education", "trainer", "training",
        "lesson plan", "student"
    ]

   
    healthcare_keywords = [
        "nurse", "doctor", "healthcare", "medical", "patient", "clinic",
        "pharmaceutical", "hospital"
    ]

    
    logistics_keywords = [
        "logistics", "warehouse", "supply chain", "distribution",
        "freight", "shipping", "transportation"
    ]

   
    retail_keywords = [
        "retail", "store", "merchandise", "inventory", "cashier",
        "sales floor"
    ]

   
    industry_keywords = {
        "Manufacturing": manufacturing_keywords,
        "IT": it_keywords,
        "Finance": finance_keywords,
        "Marketing": marketing_keywords,
        "HR": hr_keywords,
        "Sales": sales_keywords,
        "Education": education_keywords,
        "Healthcare": healthcare_keywords,
        "Logistics": logistics_keywords,
        "Retail": retail_keywords
    }

    
    counts = {}
    for industry, keywords in industry_keywords.items():
        count = sum(1 for kw in keywords if kw in summary_lower)
        counts[industry] = count

   
    max_industry = max(counts, key=counts.get)
    max_count = counts[max_industry]

    if max_count > 0:
        return max_industry
    else:
        return "Others"

def extract_field(text, field, is_list=False, is_number=False):
    pattern = rf'"{field}"\s*:\s*(\[.*?\]|{{.*?}}|".*?"|-?\d+(?:\.\d+)?|\'.*?\')'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return [] if is_list else (0 if is_number else None)

    value = match.group(1).strip()

    if is_list:
        try:
            return json.loads(value.replace("'", '"'))  # đổi nháy đơn → kép
        except:
            return []
    elif is_number:
        try:
            return float(value) if '.' in value else int(value)
        except:
            return 0
    else:
        return value.strip('"').strip("'")

def parse_output_loose(text):
    # Chuẩn hóa nháy để tránh lỗi
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')

    result = {}
    result["industry"] = extract_field(text, "industry")
    result["role_family"] = extract_field(text, "role_family")
    result["seniority"] = extract_field(text, "seniority")
    result["education_required"] = extract_field(text, "education_required") or extract_field(text, "education_level_applicant")
    result["languages_required"] = extract_field(text, "languages_required", is_list=True) or extract_field(text, "languages", is_list=True)
    result["employment_type"] = extract_field(text, "employment_type")
    result["core_skills"] = extract_field(text, "core_skills", is_list=True) or extract_field(text, "required_specific_skills", is_list=True)
    # Xử lý experience_years
    exp_raw = extract_field(text, "experience_years")
    exp_nums = [int(x) for x in re.findall(r'\d+', str(exp_raw))]
    if len(exp_nums) >= 2:
        min_exp, max_exp = exp_nums[0], exp_nums[1]
    elif len(exp_nums) == 1:
        min_exp, max_exp = exp_nums[0], None
    else:
        min_exp, max_exp = None, None
    result["experience_years"] = {
        "min": min_exp,
        "max": max_exp
    }
    conf = extract_field(text, "confidence", is_number=True)
    result["confidence"] = conf if conf is not None else 0.6
    return result


classified_jobs = []

for index, job in enumerate(data, start=1):
    name = job.get("name", f"Job {index}")
    summary_for_llm = job.get("summary", "")
    skills = job.get("skills", "")

    prompt = f"""You are a recruitment analytics expert.

Task: Read the job posting (Vietnamese or English) and return ONLY a compact JSON object that classifies the role and extracts key attributes. 
Follow the taxonomy strictly. If you're uncertain, choose the **most likely** category from the list and lower the confidence score accordingly.
Only use "Others" if absolutely nothing fits.

Output schema (JSON only, no extra text):
{{
  "industry": "<one_of: IT (technology-related) | Finance (banking, accounting) | Marketing (advertising, digital) | HR (human resources) | Sales (B2B, B2C) | Manufacturing (production, factory) | Education (teaching, training) | Healthcare (medical, hospital) | Logistics (supply chain, transport) | Retail (store, consumer) | Others>",
  "role_family": "<one_of: Data | Software | QA | DevOps | Marketing | Sales | Operations | HR | Finance | Product | Design | Support | Others>",
  "seniority": "<one_of: Intern | Junior | Mid | Senior | Lead | Manager | Director>",
  "core_skills": ["skill1","skill2","..."], 
  "education_required": "<one_of: No requirement | College | Bachelor | Master | PhD>",
  "languages_required": ["English B1","Vietnamese","..."],
  "employment_type": "<one_of: Full-time | Part-time | Contract | Internship | Unknown>",
  "experience_years": {{"min": null, "max": null}},
  "confidence": <float 0..1>
}}

Guidelines:
- Rely more on responsibilities and requirements than general company descriptions.
- core_skills: 5–10 normalized keywords (e.g., "Excel", "SQL", "Python", "Ecommerce Operations").
- Only extract experience_years if explicitly stated. Otherwise use: {{"min": null, "max": null}}.
- Avoid "Others" unless there's no fit at all. If unsure, choose the closest match and adjust confidence.
- If the posting is ambiguous, pick the closest industry/role_family based on available keywords. Use "Others" only if no reasonable match exists.

Examples:

Input: Software Engineer - Develop backend systems in Python, requires knowledge of SQL and cloud platforms.
Output:
{{
  "industry": "IT",
  "role_family": "Software",
  "seniority": "Mid",
  "core_skills": ["Python", "SQL", "AWS", "Backend Development"],
  "education_required": "Bachelor",
  "languages_required": ["English B2"],
  "employment_type": "Full-time",
  "experience_years": {{"min": 2, "max": 4}},
  "confidence": 0.85
}}

Input: Nhân viên kế toán - quản lý sổ sách kế toán, hỗ trợ báo cáo tài chính.
Output:
{{
  "industry": "Finance",
  "role_family": "Finance",
  "seniority": "Junior",
  "core_skills": ["Kế toán", "Excel", "Lập báo cáo tài chính"],
  "education_required": "Bachelor",
  "languages_required": ["Vietnamese"],
  "employment_type": "Full-time",
  "experience_years": {{"min": null, "max": null}},
  "confidence": 0.75
}}

JOB INPUT
Name: {name}
Summary:
{summary_for_llm}
Skills (optional): {skills}
"""

    classification = None
    used_model = None

    for i, model in enumerate(models):
        if not model_flags[i]:
            continue

        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )

            classification = response.choices[0].message.content.strip()
            used_model = model
            print(f"Job {index} classified using model {used_model}")
            break

        except Exception as e:
            print(f"Model {model} lỗi: {e}")
            model_flags[i] = False

    if classification:
        try:
            parsed_result = parse_output_loose(classification)
            if parsed_result.get("industry") == "Others":
                summary = job.get("summary", "")
                guessed_industry = guess_industry_from_summary(summary)
                if guessed_industry != "Others":
                    parsed_result["industry"] = guessed_industry
                    parsed_result["confidence"] = max(parsed_result.get("confidence", 0.5), 0.7)
            print(f"Parsed result for job {index}: {parsed_result}")
        except Exception as e:
            print(f"Lỗi khi phân tích kết quả từ model: {e}")
            parsed_result = {}
    else:
        print(f"Không tóm tắt được job {index} bằng bất kỳ model nào.")
        parsed_result = {}

    classified_job = {
        "name": name,
        "industry": parsed_result.get("industry", "Unknown"),
        "role_family": parsed_result.get("role_family", "Unknown"),
        "seniority": parsed_result.get("seniority", "Unknown"),
        "core_skills": parsed_result.get("core_skills", []),
        "education_required": parsed_result.get("education_required", "Unknown"),
        "languages_required": parsed_result.get("languages_required", []),
        "employment_type": parsed_result.get("employment_type", "Unknown"),
        "experience_years": parsed_result.get("experience_years", {"min": None, "max": None}),
        "confidence": parsed_result.get("confidence", 0.0)
    }

    classified_jobs.append(classified_job)

# Ghi ra file kết quả
with open("classified_jobs.json", "w", encoding="utf-8") as outfile:
    json.dump(classified_jobs, outfile, ensure_ascii=False, indent=2)
