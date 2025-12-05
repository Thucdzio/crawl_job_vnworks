

import json
import re
import time
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager


NOTICE = 'Information is missed'

# ------------ Firefox options ------------
options = webdriver.FirefoxOptions()
# Headless mode (comment this line if you want to see the browser)
options.add_argument("-headless")
# Private/incognito for Firefox
options.add_argument("-private")
# Disable notifications just in case
options.set_preference("dom.webnotifications.enabled", False)

# ------------ Driver init (Selenium 4) ------------
service = Service(GeckoDriverManager().install())
driver = webdriver.Firefox(service=service, options=options)
driver.set_window_size(1920, 1080)

wait = WebDriverWait(driver, 15)

def safe_text(elem, default=NOTICE):
    try:
        if elem is None:
            return default
        txt = elem.get_text(separator=" ", strip=True)
        return txt if txt else default
    except Exception:
        return default

def login():
    driver.get("https://secure.vietnamworks.com/login/vi?client_id=3")
    try:
        wait.until(EC.presence_of_element_located((By.ID, "email")))
        # TODO: Fill your credentials here
        driver.find_element(By.ID, "email").send_keys("youremails")
        driver.find_element(By.ID, "login__password").send_keys("yourpassword")
        driver.find_element(By.ID, "button-login").click()
        # Optional: wait for redirect or some logged-in indicator
        time.sleep(3)
    except TimeoutException:
        print("Login page did not load in time. Continuing without login...")

def collect_listing_links(num_pages):
    all_links = []
    page_num = 1
    while page_num <= num_pages:
        url = f'https://www.vietnamworks.com/viec-lam?page={page_num}'
        driver.get(url)
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        block_job_list = soup.find_all("div", {"class": "block-job-list"})
        for block in block_job_list:
            link_catalogue = block.find_all("div", {"class": "search_list"})
            for item in link_catalogue:
                a = item.find("a")
                if a and a.get("href"):
                    href = a.get("href")
                    if href.startswith("http"):
                        all_links.append(href)
                    else:
                        all_links.append("https://www.vietnamworks.com" + href)
        print(f"Collected links from page {page_num}")
        page_num += 1
        time.sleep(1)
            
    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for x in all_links:
        if x not in seen:
            unique_links.append(x)
            seen.add(x)
    return unique_links
    
def get_section_text_by_title(title, soup):
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == title:
            # Lấy div kế tiếp chứa nội dung
            content_div = h2.find_next_sibling("div")
            if content_div:
                return content_div.get_text(separator="\n", strip=True)
    return None
def parse_job(url):
    driver.get(url)
    # Let dynamic content load a bit
    time.sleep(1.5)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Title
    name_job = safe_text(soup.find("h1", {"name": "title"}))

    # Company
    link_company = soup.find_all("a", {"name": "label"})
    name_company = safe_text(link_company[0]) if link_company else None

    # Location
    location_header = next(
        (h2 for h2 in soup.find_all("h2", {"name": "title"}) 
        if "địa điểm làm việc" in h2.get_text(strip=True).lower()),
        None
    )
    locations = []
    if location_header:
        container = location_header.find_next_sibling()
        while container:
            
            paragraphs = container.find_all("p", {"name": "paragraph"})
            if paragraphs:
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text:
                        locations.append(text)
                break  
            container = container.find_next_sibling()

    if not locations:
        locations = [NOTICE]
    # Salary
    salary = safe_text(soup.find("span", {"name": "label"}))

    # Benefits
    benefits = []
    benefit_blocks = soup.find_all("div", {"data-benefit-name": True})

    for block in benefit_blocks:
        # Lấy tiêu đề benefit
        title_tag = block.find("p", {"name": "title"})
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Tìm tất cả thẻ div bên trong block
        all_divs = block.find_all("div")
        
        # Lấy div cuối cùng có text
        description = ""
        for div in reversed(all_divs):
            text = div.get_text(strip=True)
            if text:
                description = text
                break

        benefits.append(f"{title}: {description}" if title else description)

    # Description
    description = NOTICE
    desc = get_section_text_by_title("Mô tả công việc", soup)
    if desc:
        description = desc

    # Requirements
    requirements = NOTICE
    req = get_section_text_by_title("Yêu cầu công việc", soup)
    if req:
        requirements = req

    # Summary items
    content = []
    summary_header = next(
        (h2 for h2 in soup.find_all("h2", {"name": "title"}) 
        if "thông tin việc làm" in h2.get_text(strip=True).lower()),
        None
    )
    if summary_header:
        summary_row = summary_header.find_next("div", {"id": "vnwLayout__row"})
        if summary_row:
            summary_cols = summary_row.find_all("div", {"id": "vnwLayout__col"})
            for summary_col in summary_cols:
                items = summary_col.find_all("p")
                for item in items:
                    text = item.get_text(strip=True)
                    content.append(text)
    def get_or(idx, default=NOTICE):
        try:
            return content[idx] if content[idx] and content[idx] != NOTICE else default
        except Exception:
            return default

    upload_date = get_or(0)
    position = get_or(1)
    career = get_or(2)
    skill = get_or(3)
    field = get_or(4)
    language_of_cv = get_or(5)
    minimum_years_of_experience = get_or(6)

    # Expiry/expiration date extraction
    expiration_date = NOTICE
    expiry_span = soup.find("span", {"name": "paragraph"})
    if expiry_span and upload_date != NOTICE:
        try:
            expiration_str = safe_text(expiry_span)
            number_days = re.findall(r"\d+", expiration_str)
            if number_days:
                days = int(number_days[0])
                expiration_date = (datetime.strptime(upload_date, "%d/%m/%Y").date() + timedelta(days=days)).strftime("%d/%m/%y")
        except Exception:
            pass

    data = {
        "name": name_job,
        "salary": salary,
        "upload_date": upload_date,
        "expiration_date": expiration_date,
        "locations": locations,
        "skill": skill,
        "career": career,
        "company": name_company,
        "job_position": position,
        "field": field,
        "language_cv": language_of_cv,
        "minimum_years_of_experience": minimum_years_of_experience,
        "benefits": benefits,
        "description": description,
        "requirements": requirements,
        "link_job": url,
    }
    return data

def main():
    try:
        login()
        max_pages = 150
        links = collect_listing_links(max_pages)

        results = {"jobs": []}
        for idx, link in enumerate(links, 1):
            try:
                job = parse_job(link)
                results["jobs"].append(job)
            except Exception as e:
                print(f"Failed to parse {link}: {e}")
        with open("vietnamworks.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"Total jobs collected: {len(results['jobs'])}")
        print("Saved to vietnamworks.json")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
