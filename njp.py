import re
import os
from datetime import datetime

import psycopg2
import cloudscraper
from lxml import html
from dotenv import load_dotenv
from bs4 import BeautifulSoup as bs
from psycopg2.extras import execute_values

load_dotenv()

scraper = cloudscraper.create_scraper()
URL = "https://www.njp.gov.pk/jobs/live"

def get_job_links(url):
    i = 1
    links = []
    while True:
        resp = scraper.get(f"{url}?page={i}")
        soup = bs(resp.content, "html.parser")
        divs = soup.find_all("div", class_="job-card-actions")
        if not divs:
            break
        for div in divs:
            if (a_tag := div.select_one("a")) and a_tag.has_attr("href"):
                links.append(a_tag["href"])
        i += 1
    return links

def get_job_details(link):
    resp = scraper.get(link)
    if resp.status_code == 200:
        tree = html.fromstring(resp.content)

        # ID
        id = link.split("/")[-1]

        # Title
        h1 = tree.xpath("/html/body/div[2]/div[1]/div[2]/h1")
        title = h1[0].text.strip() if h1 else None
        
        # Employer
        employer_tag = tree.xpath("/html/body/div[2]/div[1]/div[2]/div[1]/div/p[1]")
        employer = employer_tag[0].text.strip() if employer_tag else None
        
        # Grade
        grade_tag = tree.xpath("/html/body/div[2]/div[1]/div[2]/div[2]/div[1]/div/p[2]")
        grade = grade_tag[0].text.strip() if grade_tag else None
        
        # Employment Type
        employment_type_tag = tree.xpath("/html/body/div[2]/div[1]/div[2]/div[2]/div[2]/div/p[2]")
        employment_type = employment_type_tag[0].text.strip() if employment_type_tag else None
        
        # Vacancies
        vacancies_tag = tree.xpath("/html/body/div[2]/div[1]/div[2]/div[2]/div[3]/div/p[2]")
        vacancies = match.group() if vacancies_tag and (match := re.search(r'\d+', vacancies_tag[0].text_content())) else None
        
        # Description
        description_tag = tree.xpath('//*[@id="job-description-container"]')
        description = description_tag[0].text_content().strip() if description_tag else None
        
        # Qualifications
        qual_spans = tree.xpath('//h4[normalize-space(text())="Qualifications"]/following-sibling::div[1]//span/text()')
        qualifications = [text.strip() for text in qual_spans if text.strip()]
        
        # Experience
        exp_spans = tree.xpath('//h4[normalize-space(text())="Experience"]/following-sibling::div[1]//span')
        experience = match.group() if exp_spans and (match := re.search(r'\d+', exp_spans[0].text_content())) else None

        # Age Limit
        max_age_spans = tree.xpath('//h4[normalize-space(text())="Age Limit"]/following-sibling::div[1]//span')
        age_limit_max = match.group() if max_age_spans and (match := re.search(r'\d+', max_age_spans[0].text_content())) else None
        
        # Minimum Age Limit
        min_age_spans = tree.xpath('//h4[normalize-space(text())="Minimum Age Limit"]/following-sibling::div[1]//span')
        age_limit_min = match.group() if min_age_spans and (match := re.search(r'\d+', min_age_spans[0].text_content())) else None
        
        # Last Date to Apply
        last_date_div = tree.xpath("/html/body/div[2]/div[2]/div[2]/div[1]/div[2]/text()")
        last_date = last_date_div[0].strip() if last_date_div else None
        last_date = datetime.strptime(last_date, "%d %b %Y").strftime("%Y-%m-%d") if last_date else None
        
        # Date posted
        date_posted_span = tree.xpath("/html/body/div[2]/div[2]/div[2]/div[2]/div/div[1]/span[2]")
        date_posted = date_posted_span[0].text.strip() if date_posted_span else None
        date_posted = datetime.strptime(date_posted, "%d %b %Y").strftime("%Y-%m-%d") if date_posted else None
        
        return {
            'id': id,
            'title': title,
            'employer': employer,
            'grade': grade,
            'employment_type': employment_type,
            'vacancies': vacancies,
            'description': description,
            'qualifications': qualifications,
            'experience': experience,
            'age_limit_max': age_limit_max,
            'age_limit_min': age_limit_min,
            'last_date': last_date,
            'date_posted': date_posted
        }

def main():
    links = get_job_links(URL)
    current_scraped_ids = {link.rstrip('/').split('/')[-1] for link in links}
    new_data = []

    with psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT", "6543"),
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS")
        ) as conn:
        with conn.cursor() as cursor:

            cursor.execute("SELECT id FROM RAW.njp_jobs")
            db_ids = {row[0] for row in cursor.fetchall()}

            for link in links:
                job_id = link.rstrip('/').split('/')[-1]
                if job_id in db_ids:
                    continue
                    
                job_details = get_job_details(link)
                if job_details:
                    new_data.append(job_details)

            if new_data:
                columns = [
                    'id', 'title', 'employer', 'grade', 'employment_type', 
                    'vacancies', 'description', 'qualifications', 'experience', 
                    'age_limit_max', 'age_limit_min', 'last_date', 'date_posted'
                ]
                values_list = [tuple(r[col] for col in columns) for r in new_data]
                
                insert_query = f"""
                    INSERT INTO RAW.njp_jobs ({', '.join(columns)})
                    VALUES %s;
                """
                execute_values(cursor, insert_query, values_list)
                print(f"Inserted {len(new_data)} new records into the database.")

            ids_to_deactivate = db_ids - current_scraped_ids
            if ids_to_deactivate:
                cursor.execute(
                    "UPDATE RAW.njp_jobs SET is_active = FALSE WHERE id = ANY(%s)",
                    (list(ids_to_deactivate),)
                )
                print(f"Deactivated {len(ids_to_deactivate)} records.")

    conn.close()


if __name__ == "__main__":
    main()