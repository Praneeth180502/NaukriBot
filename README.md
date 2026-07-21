# AI Job Hunter Agent

Production-grade autonomous job discovery, matching, and tracking system for Naukri.com.

## Architecture

```
External Sources → Ingestion Layer → Intelligence Core → Action Layer → Storage
```

- **Profile Intelligence**: Auto-extracts skills from resume + Naukri profile
- **Job Discovery**: Crawls Naukri every 15 minutes via Playwright
- **Automated Chatbot Answering**: Intercepts and auto-answers job application questionnaires based on your profile
- **AI Matching**: sentence-transformers/all-MiniLM-L6-v2 for semantic similarity
- **Ranking Engine**: Weighted formula (40% resume + 20% skill + 15% location + 15% exp + 10% company)
- **Telegram Bot**: Real-time alerts + /commands
- **FastAPI Dashboard**: Analytics, trends, application tracking
- **Learning Engine**: Improves from apply/ignore signals

## Stack

| Layer | Tech |
|---|---|
| Scraping | Playwright, BeautifulSoup |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Vector Search | FAISS |
| Resume Parsing | PyMuPDF, spaCy |
| API | FastAPI, Uvicorn |
| Database | SQLite, SQLAlchemy |
| Scheduler | APScheduler |
| Bot | python-telegram-bot |
| Container | Docker, Docker Compose |

## Quick Start

```bash
cp config/config.example.yaml config/config.yaml
# Fill in Telegram bot token + Naukri credentials
docker compose up --build
```

## Configuration

See `config/config.example.yaml` for all settings.

## Dashboard

After startup: http://localhost:8000

## Telegram Commands

| Command | Description |
|---|---|
| /jobs | Latest matched jobs |
| /topjobs | Top 20 ranked jobs |
| /newjobs | Jobs in last 1 hour |
| /stats | Application statistics |
| /companies | Top hiring companies |
| /skillgaps | Your skill gaps |
