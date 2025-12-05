import os
import json
from groq import Groq

# Khởi tạo client Groq với API key
client = Groq(api_key="your_api)ey")

# Danh sách các model khả dụng
models = [
    "groq/compound",
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
with open("vietnamworks.json", "r", encoding="utf-8") as file:
    data = json.load(file)

summarized_jobs = []

for index, job in enumerate(data["jobs"], start=1):
    description = job.get("description", "")
    requirements = job.get("requirements", "")
    combined_text = f"{description}\n\n{requirements}"

    prompt = f"""Summarize the following job posting into 6–10 bullet points focusing ONLY on:
- Core responsibilities
- Required skills/tools/technologies
- Required years of experience
- Required education/certifications
- Required languages
- Any employment type info

Do NOT include company marketing/introduction text.
Return bullets only (no prose before/after).

TEXT:
{combined_text}"""

    summary = None
    used_model = None

    for i, model in enumerate(models):
        if not model_flags[i]:
            continue 

        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )

            summary = response.choices[0].message.content.strip()
            used_model = model
            print(f"Job {index} summarized using model {used_model}")
            break  

        except Exception as e:
            print(f"Model {model} lỗi: {e}")
            model_flags[i] = False 

    if summary:
        summarized_job = {
            "name": job.get("name", f"Job {index}"),
            "company": job.get("company", ""),
            "location": job.get("locations", ""),
            "skills": job.get("skill", ""),
            "summary": summary
        }
        summarized_jobs.append(summarized_job)
    else:
        print(f"Không tóm tắt được job {index} bằng bất kỳ model nào.")

# Ghi ra file kết quả
with open("summarized_jobs1.json", "w", encoding="utf-8") as outfile:
    json.dump(summarized_jobs, outfile, ensure_ascii=False, indent=2)


