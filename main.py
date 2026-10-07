from njp import main as njp_jobs_scraper
from punjab_jobs_portal import sync_jobs_to_db as punjab_jobs_scraper

def main():
    print("="*50)

    print("Starting NJP jobs scraping...")
    njp_jobs_scraper()
    print("NJP jobs scraping completed.")

    print("="*50)

    print("Starting Punjab Jobs Portal scraping...")
    punjab_jobs_scraper()
    print("Punjab Jobs Portal scraping completed.")

    print("="*50)

if __name__ == "__main__":
    main()