# GitHub Activity Digest AI Agent

A Flask-based web application that fetches recent GitHub repository activity, synthesizes executive summaries using Google's Gemini AI, and delivers daily digests via a live web dashboard or email.

## Features

- **GitHub Activity Fetching**: Retrieves issues and pull requests from any public repository for the last 24 hours via GitHub REST API v3.
- **AI-Powered Summarization**: Uses Google Gemini (`gemini-2.5-flash` by default with fallback support) via the official `google-genai` SDK to generate readable, categorized executive digests (🚀 Pull Requests, 🐛 Issues & Bugs, 🏁 Merged/Closed).
- **Graceful Unconfigured Fallback**: Functions cleanly even before an API key is added by presenting structured raw activity logs with setup guidance.
- **Email Delivery (SMTP)**: Dispatches digests with both plain text and styled rich HTML formatting via SMTP (configured for Gmail or custom hosts).
- **Modern Interactive Dashboard**: Dark/Light mode UI with live web preview, markdown rendering, clipboard copying, file download (`.md`), activity statistics, preset repositories, and search history.
- **Automated Digest Trigger**: Supports scheduled/cron triggers via `/trigger-daily-digest` for automated workflows.
- **Robust Input Handling**: Accepts clean `owner/repo` formats, full GitHub URLs, `.git` clone URLs, and issues/PR sublinks.

## Prerequisites

- Python 3.8+ (Python 3.11 recommended)
- A Google Gemini API key (from [Google AI Studio](https://aistudio.google.com/))
- *(Optional)* A Gmail account with an App Password for SMTP email delivery
- *(Optional)* A GitHub Personal Access Token to raise API rate limits from 60 to 5,000 req/hr

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/github-activity-digest.git
   cd github-activity-digest
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows
   py -3.11 -m venv venv
   venv\Scripts\activate

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy the `.env.example` template:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your credentials:
   ```plaintext
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-2.5-flash
   GITHUB_TOKEN=your_optional_github_token
   SENDER_EMAIL=your_email@gmail.com
   SENDER_PASSWORD=your_gmail_app_password
   DEFAULT_REPO=pallets/flask
   DEFAULT_RECIPIENT_EMAIL=recipient@example.com
   ```

## Running the Application

Start the Flask server:
```bash
python app.py
# or on Windows with Python 3.11:
py -3.11 app.py
```
Open your browser and navigate to `http://127.0.0.1:5000`.

## Testing

Run the automated test suite with:
```bash
python -m unittest discover tests
# or on Windows:
py -3.11 -m unittest discover tests
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the interactive web dashboard. |
| `GET` | `/api/health` | Health probe returning service readiness and timestamp. |
| `GET` | `/api/status` | Reports system readiness (`gemini_configured`, `smtp_configured`, `github_token_configured`). |
| `POST` | `/generate-digest` | Synthesizes activity digest for a repo (live web preview or email dispatch). |
| `POST` | `/trigger-daily-digest` | Runs the automated digest task for the configured default repository and recipient. |

### Sample Payload: `/generate-digest`
```json
{
  "repo": "pallets/flask",
  "send_email": false,
  "email": "user@example.com"
}
```

## License

MIT License. See [LICENSE](LICENSE) for details.
