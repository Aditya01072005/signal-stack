# Signal Stack — Testing Evidence

**EDXSO AI Engineer Assignment | 25 November 2026**

## 1. Scope and environment

Windows local development, Python 3.11.9, Node.js 24.14.1, FastAPI, React/Vite, Neon PostgreSQL and Ollama llama3.2:3b. Live demonstrations used the dev-test database branch. Results below are historical developer-reported test runs and observed demonstration outputs, not a newly executed independent audit.

## 2. Automated testing

| Module | Reported passing tests |
|---|---:|
| Company management (earlier isolated run) | 8 |
| Ethical scraper | 63 |
| AI research | 58 |
| Adaptive interview | 46 |
| Monitoring pipeline | 64 |
| Signal analysis, monitoring and sources | 72 |
| Brief generation and related modules | 79 |
| Competitor intelligence | 38 |
| Scheduler | 25 |
| Latest focused brief regression | 12 |
| Internal document ingestion | 5 |

These runs overlap and must not be summed. The earlier full backend suite reported **286 passed, 0 failed, 8 errors, 13 warnings**. The eight errors were company-test setup errors caused by missing TEST_DATABASE_URL. The database safety guard prevented unsafe test execution. A complete regression run after the latest changes remains pending. Mocked tests do not establish live integration success.

Frontend production build passed; lint reported zero errors and seven warnings in the latest reported checks.

## 3. Live demonstration evidence

| Company | Industry | Registered sources | Web-derived signal records | Exported brief |
|---|---|---:|---:|---|
| MeetUniversity | Education services | 24 | 25 | PDF + Markdown |
| Stripe | Financial technology | 5 | 5 | PDF + Markdown |
| IKEA | Furniture and home retail | 5 | 5 | PDF + Markdown |
| Total | | 34 | 35 | 6 files |

One additional explicitly synthetic TXT document signal was created for MeetUniversity, bringing the total to 36 signal records. It is not counted as real business intelligence. Web-derived records are not necessarily distinct or strategically relevant events. Source registration does not prove that every source has been individually approved or that its terms permit crawling.

- Backend health endpoint returned a healthy database connection.
- Dashboard company switching and live source/signal retrieval were demonstrated.
- MeetUniversity had five active competitor profiles with stored verification flags and evidence URLs: IDP Education, ApplyBoard, Yocket, GradRight and AdmitKard. Independent verification of all claims was not performed.
- Public web monitoring created stored signal records with evidence links. A blocked source was deactivated rather than bypassed.
- TXT upload created a company-specific internal signal with an evidence reference and pending analysis status.
- Scheduler status displayed active jobs. Actual timed execution has not been observed.

## 4. Executive brief evidence

All three exported briefs contain the ten required sections and source references. Each relies on one unique signal.

| Company | PDF pages | Recommended actions | Observations |
|---|---:|---:|---|
| MeetUniversity | 4 | 0 | Market threat from PIE News; sparse summary |
| Stripe | 6 | 5 | Official Treasury blog; recommendations need stronger company perspective |
| IKEA | 5 | 0 | Official FRAKTA update; deterministic evidence-backed fallback |

See the six exported files in `reports/`. Public official company sources in the Stripe and IKEA briefs were classified as Internal; this is a known categorization limitation. The reports do not include the synthetic internal document.

The brief generator regression fix rejects invalid evidence quotations and uses a deterministic fallback based on stored verified analyzed signals. The IKEA demonstration exercised this fallback. Evidence validation establishes correspondence to stored source text, not independent truth of all source claims.

## 5. Reproduction commands

From the repository root, activate the existing Python environment and install pytest if needed. Before running database tests, configure TEST_DATABASE_URL with a separate disposable test database or branch, never the production or populated demonstration database. Confirm the database safety checks remain enabled.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install pytest
cd backend
python -m pytest tests -v --tb=short
```

From the repository root in another terminal:

```powershell
cd frontend
npm run lint
npm run build
```

These are reproduction instructions, not evidence of a fresh run. Additional test dependencies may be required by the repository's test harness.

## 6. Outstanding verification and limitations

- Complete live adaptive interview: answer, follow-up, skip, edit, persistence and company isolation.
- Full regression suite against a dedicated test database.
- Live PDF and CSV ingestion; scanned PDF OCR is not implemented.
- Observe actual weekly and monthly scheduled execution.
- Verify source terms, relevance and approval; improve event-level extraction and report coverage.
- Validate company-specific research and competitor discovery across all three demos.
- Improve source categorization and recommendation specificity.
- Verify independent source reliability, evidence strength and strategic relevance scoring requirements.
- Fresh installation and production deployment have not been independently tested.

## 7. Conclusion

The available evidence demonstrates a working local full-stack prototype with real web monitoring, stored evidence, multi-company records, local AI analysis, report generation and export. It does not establish that every assignment requirement has passed end-to-end verification. Historical test counts should be replaced or supplemented with fresh logs when available.

## Final Adaptive Interview Live Verification

- Company-specific question generation: PASS
- Answer submission: PASS
- Adaptive context memory: PASS
- Progress tracking: PASS
- Interview transcript: PASS
- Skip functionality: PASS
- Answer editing: PASS
- Persistence after refresh: PASS
- Company switching: PASS

Result: 9/9 targeted checks passed.
Evidence: UI screenshots and developer-confirmed live checks.
Interview answers used hypothetical demonstration context.
Full ten-question completion remains untested.
