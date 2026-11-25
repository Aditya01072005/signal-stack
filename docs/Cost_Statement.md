# Signal Stack — Cost Statement

**EDXSO AI Engineer Assignment | 25 November 2026**

## 1. Development and demonstration costs

| Component | Technology | Cost basis |
|---|---|---|
| Local AI inference | Ollama, llama3.2:3b | ₹0 paid inference API fees reported |
| Backend | Python, FastAPI, SQLAlchemy, Alembic | ₹0 software licence fees |
| Frontend | React, Vite, Tailwind CSS, Lucide React | ₹0 software licence fees |
| Database | Neon PostgreSQL | Free-tier usage intended; billing not independently verified |
| Web monitoring | HTTPX, Requests, BeautifulSoup, lxml | ₹0 paid scraping or search API fees reported |
| Document ingestion | pypdf, CSV and text processing | ₹0 software licence fees |
| Scheduling | APScheduler | ₹0 software licence fees |
| Development hosting | Existing local computer | No additional hosting expenditure reported |
| Report export | Markdown and browser Print to PDF | ₹0 additional software fees |

## 2. Cost summary

The application was developed to operate without paid AI, search or scraping APIs. The reported incremental paid application-service expenditure for the demonstration is ₹0, subject to confirmation of the Neon account's billing status. This is not an independently audited total.

Existing hardware, electricity, internet connectivity, development time and any optional coding-assistant subscriptions are excluded from this application-runtime estimate. These costs were not measured.

## 3. Cost-control design

- Local Ollama inference avoids per-token external LLM charges.
- Content hashing reduces duplicate signal storage and processing.
- Scraper timeouts, text-length limits and politeness delays constrain resource consumption.
- Brief generation uses a limited selection of eligible ranked signals.
- In-process scheduling avoids a separate paid orchestration service.

## 4. Future operating costs and limitations

The local demonstration is not a hosted production deployment. Larger workloads may require additional compute, database storage, hosting, backups or monitoring. Neon free-tier limits and billing terms should be checked before deployment. Local model inference consumes hardware resources and electricity, and scheduled jobs require the backend to remain running.

**Conclusion:** Signal Stack is designed for a low-cost demonstration using local inference and freely available development tools. Zero future operating cost is not guaranteed.
