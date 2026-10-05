# Nokri Baz Scraper 🕷️💼

A high-performance Python web scraper designed to extract job listings and detailed requirements from the Punjab Government Jobs portal [jobs.punjab.gov.pk](jobs.punjab.gov.pk). 

The scraper utilizes concurrent network requests for speed and bulk UPSERT operations to efficiently synchronize active job postings into a Supabase PostgreSQL database.

---

## 📋 Prerequisites

Before you begin, ensure you have the following installed on your machine:
* **Python 3.8 or higher**
* **Git**
* A **Supabase** account (or any PostgreSQL database with the `vector` extension enabled for future hybrid search capabilities).

---

## 🚀 Getting Started

Follow these steps to set up and run the project locally.

### 1. Clone the Repository
Open your terminal and clone the repository to your local machine:
```bash
git clone https://github.com/hanzzlah/nokri-baz.git
cd nokri-baz-scraper
```

### 2. Create a Virtual Environment
It is highly recommended to use a virtual environment to manage project dependencies.

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS and Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
With your virtual environment activated, install the required Python packages:
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
The project uses environment variables to securely connect to your Supabase database. 

1. Copy the provided example template:
   ```bash
   cp .env.example .env
   ```
2. Open the `.env` file in your code editor and fill in your Supabase connection details. 

*Note: It is highly recommended to use the **IPv4 Transaction Pooler** (Port `6543`) provided by Supabase to avoid DNS resolution issues (`ENOTFOUND`). Check `.env.example` for detailed inline instructions.*

### 5. Database Setup (Supabase)
Before running the scraper, you must ensure the target table exists in your database. 

Go to your Supabase SQL Editor and execute the following schema to create the `jobs` table:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    education_level_years INT,
    degree_area TEXT[],
    district TEXT,
    division TEXT,
    industry TEXT,
    project TEXT,
    total_positions INT,
    employment_status TEXT,
    role TEXT,
    job_posted DATE,
    last_date_to_apply DATE,
    level TEXT,
    years_of_experience JSONB,
    age_min INT,
    age_max INT,
    gender TEXT,
    monthly_salary_min INT,
    monthly_salary_max INT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_filters ON jobs (education_level_years, age_min, age_max, gender, district);
CREATE INDEX idx_jobs_embedding ON jobs USING hnsw (embedding vector_cosine_ops);
```

### 6. Run the Scraper
Once your database is ready and `.env` is configured, execute the scraper:

```bash
python nokri-baz-scraper.py
```

## 🛠️ How it Works
1. **Fetch IDs:** Reads existing job IDs from the database to avoid redundant network/database calls.
2. **Scrape Listings:** Fetches all currently active job URLs from the main portal.
3. **Concurrent Parsing:** Uses `ThreadPoolExecutor` (with retry logic and rate-limit delays) to fetch details only for newly posted jobs.
4. **Bulk Upsert:** Formats the extracted data and performs a bulk `INSERT ... ON CONFLICT DO UPDATE` into your Supabase database, ensuring updated deadlines and open positions are captured safely.
