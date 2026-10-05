import os
import re
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import requests as req
from dotenv import load_dotenv
from bs4 import BeautifulSoup as bs
from psycopg2.extras import execute_values

load_dotenv()

def fetch_job_listings(
    url: str = "https://jobs.punjab.gov.pk/new_recruit/jobs",
) -> list[dict[str, str]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }

    response = req.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = bs(response.content, "html.parser")
    rows = soup.select("table tbody tr")

    jobs_data = []
    for row in rows:
        a_tag = row.select_one('td[data-label="Job Title"] strong a')
        if a_tag:
            title = a_tag.get_text(strip=True)
            href = str(a_tag.get("href") or "").strip()
            if href:
                jobs_data.append({"title": title, "href": href})

    return jobs_data

def parse_job_details(html_content: str, url: str | None = None) -> dict:
    soup = bs(html_content, "html.parser")

    # 1. Job ID (from URL or fallback to saveJob onclick function in HTML)
    job_id = None
    if url:
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
    if not job_id:
        save_btn = soup.select_one("a[onclick*='saveJob']")
        if save_btn:
            match = re.search(r"saveJob\((\d+)\)", str(save_btn.get("onclick", "") or ""))
            if match:
                job_id = match.group(1)

    # 2. Title
    title_input = soup.find("input", id="jobTitle")
    title = None

    if title_input:
        val = title_input.get("value")
        if isinstance(val, str):
            title = val.strip()

    if not title:
        title_a = soup.select_one("h6.title a")
        if title_a:
            title = title_a.get_text(strip=True)

    # 3. Sidebar Table Fields Extraction
    sidebar_data = {}
    for row in soup.select("div.candidates-single-widget table tr"):
        cols = row.find_all("td")
        if len(cols) == 2:
            key = cols[0].text.strip().rstrip(":")
            val = cols[1].text.strip()
            sidebar_data[key] = val

    # Field Mappings from Sidebar
    division = sidebar_data.get("Division") or None
    district = sidebar_data.get("District") or None
    industry = sidebar_data.get("Industry") or None
    project = sidebar_data.get("Project") or None
    employment_status = sidebar_data.get("Employment Status") or None
    role = sidebar_data.get("Role") or None
    level = sidebar_data.get("Level") or None
    gender = sidebar_data.get("Gender") or None

    # Total Positions
    tot_pos = sidebar_data.get("Total Positions")
    total_positions = int(tot_pos) if tot_pos and tot_pos.isdigit() else None

    # Dates
    def parse_date(date_str):
        if not date_str or date_str == "-":
            return None
        try:
            return datetime.strptime(date_str, "%d-%m-%Y")
        except ValueError:
            return None

    job_posted = parse_date(sidebar_data.get("Job Posted"))
    last_date_to_apply = parse_date(sidebar_data.get("Last Date to Apply"))

    # Age Min/Max
    age_str = sidebar_data.get("Age")
    age_min, age_max = None, None
    if age_str:
        age_match = re.search(r"(\d+)\s*-\s*(\d+)", age_str)
        if age_match:
            age_min = int(age_match.group(1))
            age_max = int(age_match.group(2))

    # Salary Min/Max
    salary_str = sidebar_data.get("Monthly Salary") or sidebar_data.get(
        "Salary"
    )
    salary_min, salary_max = None, None
    if salary_str:
        sal_match = re.search(r"(\d+)\s*-\s*(\d+)", salary_str.replace(",", ""))
        if sal_match:
            salary_min = int(sal_match.group(1))
            salary_max = int(sal_match.group(2))

    # 4. Years of Experience (Array of objects: {edu_years: exp_years})
    years_of_experience = []
    for row in soup.select("div.candidates-single-widget table tr"):
        cols = row.find_all("td")
        if len(cols) == 2:
            label = cols[0].text.strip()
            val = cols[1].text.strip()

            edu_match = re.search(r"(\d+)\s*years?", label, re.IGNORECASE)
            exp_match = re.search(r"(\d+)", val)

            if edu_match and exp_match:
                edu_yrs = int(edu_match.group(1))
                exp_yrs = int(exp_match.group(1))
                years_of_experience.append({edu_yrs: exp_yrs})

    # 5. Job Description
    desc_heading = soup.find(
        lambda tag: tag.name == "h6" and "Job Description" in tag.text
    )
    description = None
    if desc_heading:
        desc_parts = []
        curr = desc_heading.find_next_sibling()
        while curr and curr.name not in ["h6", "hr"]:
            text = curr.get_text(separator=" ", strip=True)
            if text:
                desc_parts.append(text)
            curr = curr.find_next_sibling()
        description = "\n".join(desc_parts) if desc_parts else None

    # 6. Education Level (in years)
    deg_level_heading = soup.find(
        lambda tag: tag.name == "h6" and "Degree Level" in tag.text
    )
    edu_years_list = []
    if deg_level_heading:
        ul = deg_level_heading.find_next_sibling("ul")
        if ul:
            for li in ul.find_all("li"):
                match = re.search(r"(\d+)\s*years?", li.text, re.IGNORECASE)
                if match:
                    edu_years_list.append(int(match.group(1)))

    education_level_years = min(edu_years_list) if edu_years_list else None

    # 7. Degree Area
    deg_area_heading = soup.find(
        lambda tag: tag.name == "h6" and "Degree Area" in tag.text
    )
    degree_area = []
    if deg_area_heading:
        ul = deg_area_heading.find_next_sibling("ul")
        if ul:
            degree_area = [
                li.text.strip() for li in ul.find_all("li") if li.text.strip()
            ]

    return {
        "id": job_id,
        "title": title,
        "description": description,
        "education_level_years": education_level_years,
        "degree_area": degree_area,
        "district": district,
        "division": division,
        "industry": industry,
        "project": project,
        "total_positions": total_positions,
        "employment_status": employment_status,
        "role": role,
        "job_posted": job_posted,
        "last_date_to_apply": last_date_to_apply,
        "level": level,
        "years_of_experience": years_of_experience,
        "age_min": age_min,
        "age_max": age_max,
        "gender": gender,
        "monthly_salary_min": salary_min,
        "monthly_salary_max": salary_max,
    }

def fetch_single_detail(job_id, url):
    """Worker function for threading: fetches and parses a single detail page."""
    time.sleep(0.5)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    resp = req.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    
    # parse_job_details was defined in the earlier steps
    parsed_data = parse_job_details(resp.text, url)
    parsed_data["id"] = job_id  # Enforce ID from main page
    return parsed_data

def sync_jobs_to_db():
    # 1. Establish Database Connection
    pg_set = os.getenv("DB_HOST") and os.getenv("DB_PORT") and os.getenv("DB_NAME") and os.getenv("DB_USER") and os.getenv("DB_PASS")
    if not pg_set:
        raise ValueError("One or more database environment variables are missing.")
        
    with psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        sslmode="require"
    ) as conn:
        with conn.cursor() as cursor:
            
            # 2. Fetch existing job IDs into a local set for O(1) lookups
            cursor.execute("SELECT id FROM RAW.punjab_jobs_portal;")
            existing_ids = {row[0] for row in cursor.fetchall()}
            
            # 3. Fetch current listings from the main portal (using previous function)
            all_listings = fetch_job_listings()
            
            new_jobs = []
            for job in all_listings:
                # Extract ID directly from the trailing end of the URL
                job_id = job["href"].rstrip("/").rsplit("/", 1)[-1]
                if job_id not in existing_ids:
                    new_jobs.append((job_id, job["href"]))
            
            if not new_jobs:
                print("No new jobs to sync.")
                return
            
            # 4. Fetch detail pages concurrently to maximize network performance
            parsed_records = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_job = {
                    executor.submit(fetch_single_detail, j_id, href): href 
                    for j_id, href in new_jobs
                }
                
                for future in as_completed(future_to_job):
                    try:
                        parsed_records.append(future.result())
                    except Exception as exc:
                        href = future_to_job[future]
                        print(f"Failed parsing {href}: {exc}")
            
            if not parsed_records:
                return

            # 5. Prepare data for Bulk Insert
            columns = [
                "id", "title", "description", "education_level_years", "degree_area",
                "district", "division", "industry", "project", "total_positions",
                "employment_status", "role", "job_posted", "last_date_to_apply",
                "level", "years_of_experience", "age_min", "age_max", "gender",
                "monthly_salary_min", "monthly_salary_max"
            ]
            
            values_list = []
            for r in parsed_records:
                values_list.append((
                    r["id"], r["title"], r["description"], r["education_level_years"],
                    r["degree_area"], r["district"], r["division"], r["industry"],
                    r["project"], r["total_positions"], r["employment_status"],
                    r["role"], r["job_posted"], r["last_date_to_apply"], r["level"],
                    json.dumps(r["years_of_experience"]) if r["years_of_experience"] else None,
                    r["age_min"], r["age_max"], r["gender"],
                    r["monthly_salary_min"], r["monthly_salary_max"]
                ))
            
            # 6. Execute Bulk UPSERT (Safeguard for modified records)
            cursor.execute("""
                CREATE TEMP TABLE staging_jobs 
                (LIKE RAW.punjab_jobs_portal INCLUDING DEFAULTS) 
                ON COMMIT DROP;
            """)

            # 2. Bulk insert scraped batch into staging
            insert_staging_query = f"""
                INSERT INTO staging_jobs ({', '.join(columns)})
                VALUES %s;
            """
            execute_values(cursor, insert_staging_query, values_list)

            # 3. Execute atomic MERGE
            merge_query = f"""
                MERGE INTO RAW.punjab_jobs_portal AS target
                USING staging_jobs AS source
                ON target.id = source.id
                WHEN MATCHED THEN
                    UPDATE SET 
                        title = source.title,
                        description = source.description,
                        total_positions = source.total_positions,
                        last_date_to_apply = source.last_date_to_apply,
                        is_active = TRUE
                WHEN NOT MATCHED BY TARGET THEN
                    INSERT ({', '.join(columns)})
                    VALUES ({', '.join(['source.' + col for col in columns])})
                WHEN NOT MATCHED BY SOURCE THEN
                    UPDATE SET is_active = FALSE;
            """
            cursor.execute(merge_query)
            print(f"Successfully synced {len(values_list)} new jobs.")
            
        conn.commit()

if __name__ == "__main__":
    sync_jobs_to_db()