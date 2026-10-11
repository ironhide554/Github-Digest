import os
import requests
import smtplib
import ssl
from flask import Flask, render_template, request, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "").strip()
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()
DEFAULT_RECIPIENT_EMAIL = os.getenv("DEFAULT_RECIPIENT_EMAIL", "").strip()

# Initialize Gemini safely
model = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"Warning: Failed to configure Gemini client: {e}")
        model = None


def sanitize_repo_name(repo: str) -> str:
    """Cleans up repository input, stripping URLs and trailing slashes."""
    cleaned = repo.strip()
    prefixes = [
        "https://github.com/",
        "http://github.com/",
        "github.com/",
        "git@github.com:"
    ]
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned.strip("/")


def fetch_github_activity(repo: str):
    """
    Fetches GitHub issues and pull requests for the past 24 hours.
    Returns (activity_log: str, issues_list: list, stats: dict)
    """
    clean_repo = sanitize_repo_name(repo)
    print(f"Fetching activity for {clean_repo}...")
    
    since_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    api_url = f"https://api.github.com/repos/{clean_repo}/issues?since={since_time}&state=all&per_page=100"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-Digest-Agent/2.0"
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=12)
        response.raise_for_status()
        issues = response.json()
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else None
        if status_code == 404:
            err_msg = f"Repository '{clean_repo}' was not found. Please verify the owner/repo name and ensure it is public."
        elif status_code == 403:
            err_msg = "GitHub API rate limit exceeded. Please wait a few minutes before trying again."
        else:
            err_msg = f"GitHub API error ({status_code}): {e}"
        return err_msg, [], {"total": 0, "prs": 0, "issues": 0, "open": 0, "closed": 0}
    except requests.exceptions.RequestException as e:
        return f"Unable to connect to GitHub API: {e}", [], {"total": 0, "prs": 0, "issues": 0, "open": 0, "closed": 0}

    stats = {
        "total": len(issues),
        "prs": sum(1 for item in issues if "pull_request" in item),
        "issues": sum(1 for item in issues if "pull_request" not in item),
        "open": sum(1 for item in issues if item.get("state") == "open"),
        "closed": sum(1 for item in issues if item.get("state") == "closed")
    }

    if not issues:
        empty_msg = f"No new activity (issues or pull requests) detected in '{clean_repo}' in the last 24 hours."
        return empty_msg, [], stats

    activity_log = f"GitHub Activity Digest for {clean_repo} - Last 24 Hours\n"
    activity_log += f"Total events: {len(issues)} (PRs: {stats['prs']}, Issues: {stats['issues']})\n\n"

    for item in issues:
        item_type = "Pull Request" if "pull_request" in item else "Issue"
        author = item.get("user", {}).get("login", "unknown")
        activity_log += f"- {item_type} #{item.get('number')}: {item.get('title')}\n"
        activity_log += f"  State: {item.get('state')} | Author: @{author}\n"
        activity_log += f"  URL: {item.get('html_url')}\n\n"
        
    return activity_log, issues, stats


def summarize_activity_with_gemini(raw_log: str, repo: str = "") -> str:
    """Summarizes raw activity using Gemini 1.5 Flash."""
    if "No new activity" in raw_log or "Unable to connect" in raw_log or "not found" in raw_log or "rate limit" in raw_log:
        return raw_log
        
    print(f"Summarizing activity for {repo} with Gemini...")

    if not GEMINI_API_KEY:
        # Fallback informative digest if user has not set API key yet
        return (
            f"### ⚠️ Gemini API Key Not Configured\n\n"
            f"Here is the structured activity log for **`{repo}`** in the past 24 hours:\n\n"
            f"{raw_log}\n\n"
            f"> **Tip**: To enable AI narrative summarization, set `GEMINI_API_KEY=your_key` in your `.env` file."
        )

    prompt = (
        "You are an expert tech lead and project manager AI assistant. "
        "Summarize the following raw GitHub activity log into an executive, highly readable daily digest.\n\n"
        "Guidelines:\n"
        "1. Start with a 1-2 sentence high-level executive summary of repository momentum.\n"
        "2. Group items into clear sections with emojis:\n"
        "   - 🚀 **Pull Requests** (Highlight features, fixes, or breaking changes)\n"
        "   - 🐛 **Issues & Bug Reports** (Group by user friction, questions, or bugs)\n"
        "   - 🏁 **Closed & Merged Items**\n"
        "3. Include clickable markdown links to PRs/issues when URL is provided.\n"
        "4. Keep it concise, engaging, and beautifully formatted in GitHub Markdown.\n\n"
        f"Raw Activity Log:\n{raw_log}"
    )
    
    try:
        if model is None:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            current_model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            current_model = model

        response = current_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API generation error: {e}")
        return f"Could not generate AI summary due to an error: {e}\n\n### Raw Activity Log\n{raw_log}"


def send_email_digest(summary: str, recipient_email: str, repo: str):
    """Sends the generated digest to the specified email address via SMTP."""
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("SMTP credentials missing in .env")
        return False, "SMTP sender credentials are not configured in .env."

    print(f"Sending digest email to {recipient_email}...")
    
    message = MIMEMultipart("alternative")
    clean_repo = sanitize_repo_name(repo)
    message["Subject"] = f"GitHub Daily Digest: {clean_repo} ({datetime.now(timezone.utc).strftime('%b %d, %Y')})"
    message["From"] = SENDER_EMAIL
    message["To"] = recipient_email
    message.attach(MIMEText(summary, "plain"))

    context = ssl.create_default_context()
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=10) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, recipient_email, message.as_string())
        print("Email sent successfully!")
        return True, "Email sent successfully."
    except Exception as e:
        print(f"Error sending email: {e}")
        return False, str(e)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def system_status():
    """Returns current environment readiness status."""
    return jsonify({
        "gemini_configured": bool(GEMINI_API_KEY),
        "smtp_configured": bool(SENDER_EMAIL and SENDER_PASSWORD),
        "default_repo": DEFAULT_REPO,
        "default_recipient": DEFAULT_RECIPIENT_EMAIL
    })


@app.route('/generate-digest', methods=['POST'])
def generate_digest():
    """
    Generates a digest for a given repo.
    Allows both in-browser preview (email optional) and direct email delivery.
    """
    data = request.json or {}
    repo = data.get('repo', '').strip()
    email = data.get('email', '').strip()
    send_email = data.get('send_email', bool(email))

    if not repo:
        return jsonify({"error": "Repository name is required (e.g. facebook/react)."}), 400

    clean_repo = sanitize_repo_name(repo)
    raw_activity, issues, stats = fetch_github_activity(clean_repo)
    
    if "not found" in raw_activity or "Unable to connect" in raw_activity:
        return jsonify({
            "error": raw_activity,
            "repo": clean_repo,
            "stats": stats
        }), 400

    ai_summary = summarize_activity_with_gemini(raw_activity, clean_repo)
    
    email_status = "skipped"
    email_error_detail = None

    if send_email:
        if not email:
            return jsonify({
                "error": "Email address is required to send the digest via email.",
                "summary": ai_summary,
                "stats": stats
            }), 400

        sent_ok, detail = send_email_digest(ai_summary, email, clean_repo)
        if sent_ok:
            email_status = "sent"
        else:
            email_status = "failed"
            email_error_detail = detail

    response_payload = {
        "status": "success",
        "message": f"Digest for {clean_repo} generated successfully!" + 
                   (f" Sent to {email}." if email_status == "sent" else ""),
        "repo": clean_repo,
        "summary": ai_summary,
        "raw_activity": raw_activity,
        "stats": stats,
        "email_status": email_status,
        "email_recipient": email if email else None,
        "email_error": email_error_detail,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    return jsonify(response_payload)


@app.route('/trigger-daily-digest', methods=['POST'])
def trigger_daily_digest():
    """Triggers the automated digest for the default repository and email."""
    target_repo = DEFAULT_REPO or "pallets/flask"
    target_email = DEFAULT_RECIPIENT_EMAIL

    print(f"--- Running Automated Daily Digest for {target_repo} ---")
    raw_activity, issues, stats = fetch_github_activity(target_repo)
    ai_summary = summarize_activity_with_gemini(raw_activity, target_repo)
    
    if target_email:
        sent_ok, detail = send_email_digest(ai_summary, target_email, target_repo)
        if sent_ok:
            return jsonify({
                "status": "success",
                "message": f"Daily digest for {target_repo} sent to {target_email}.",
                "summary": ai_summary,
                "stats": stats
            })
        else:
            return jsonify({
                "status": "warning",
                "message": f"Digest generated but email delivery failed: {detail}",
                "summary": ai_summary,
                "stats": stats
            }), 500
    else:
        return jsonify({
            "status": "success",
            "message": f"Daily digest generated for {target_repo} (no recipient email configured).",
            "summary": ai_summary,
            "stats": stats
        })


if __name__ == '__main__':
    app.run(debug=True)