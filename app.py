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


def get_config():
    """Dynamically reads environment variables, ensuring latest values from .env."""
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        "github_token": os.getenv("GITHUB_TOKEN", "").strip(),
        "sender_email": os.getenv("SENDER_EMAIL", "").strip(),
        "sender_password": os.getenv("SENDER_PASSWORD", "").strip(),
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "smtp_port": int(os.getenv("SMTP_PORT", "465").strip() or 465),
        "default_repo": os.getenv("DEFAULT_REPO", "pallets/flask").strip(),
        "default_recipient_email": os.getenv("DEFAULT_RECIPIENT_EMAIL", "").strip()
    }


def sanitize_repo_name(repo: str) -> str:
    """
    Cleans up repository input, stripping URLs, .git suffixes, deep subpaths, and whitespace.
    Returns clean 'owner/repo' format.
    """
    if not repo:
        return ""
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
            break

    # Strip any trailing .git
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    cleaned = cleaned.strip("/")

    # If the user pasted a deep link (e.g. owner/repo/issues or owner/repo/pull/123),
    # extract the first two path segments (owner and repo)
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) >= 2:
        cleaned = f"{parts[0]}/{parts[1]}"

    return cleaned


def fetch_github_activity(repo: str):
    """
    Fetches GitHub issues and pull requests for the past 24 hours.
    Returns (success: bool, activity_log_or_error: str, issues_list: list, stats: dict)
    """
    clean_repo = sanitize_repo_name(repo)
    empty_stats = {"total": 0, "prs": 0, "issues": 0, "open": 0, "closed": 0}

    if not clean_repo or "/" not in clean_repo:
        err_msg = f"Invalid repository format '{repo}'. Please provide an 'owner/repo' format (e.g. pallets/flask)."
        return False, err_msg, [], empty_stats

    config = get_config()
    print(f"Fetching activity for {clean_repo}...")

    since_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    api_url = f"https://api.github.com/repos/{clean_repo}/issues?since={since_time}&state=all&per_page=100"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-Digest-Agent/2.0"
    }
    if config["github_token"]:
        headers["Authorization"] = f"token {config['github_token']}"

    try:
        response = requests.get(api_url, headers=headers, timeout=12)
        response.raise_for_status()
        issues = response.json()
    except requests.exceptions.HTTPError as e:
        # Note: Do NOT use `if e.response:`, because requests.Response.__bool__
        # evaluates to False for 4xx/5xx status codes! Always check `is not None`.
        status_code = e.response.status_code if e.response is not None else None
        if status_code == 404:
            err_msg = f"Repository '{clean_repo}' was not found. Please verify the owner/repo name and ensure it is public."
        elif status_code == 403:
            err_msg = "GitHub API rate limit exceeded. Please wait a few minutes before trying again or configure GITHUB_TOKEN in .env."
        else:
            err_msg = f"GitHub API error ({status_code}): {e}"
        return False, err_msg, [], empty_stats
    except requests.exceptions.RequestException as e:
        return False, f"Unable to connect to GitHub API: {e}", [], empty_stats

    if not isinstance(issues, list):
        return False, f"Unexpected response format from GitHub API for {clean_repo}.", [], empty_stats

    stats = {
        "total": len(issues),
        "prs": sum(1 for item in issues if isinstance(item, dict) and "pull_request" in item),
        "issues": sum(1 for item in issues if isinstance(item, dict) and "pull_request" not in item),
        "open": sum(1 for item in issues if isinstance(item, dict) and item.get("state") == "open"),
        "closed": sum(1 for item in issues if isinstance(item, dict) and item.get("state") == "closed")
    }

    if not issues:
        empty_msg = f"No new activity (issues or pull requests) detected in '{clean_repo}' in the last 24 hours."
        return True, empty_msg, [], stats

    activity_log = f"GitHub Activity Digest for {clean_repo} - Last 24 Hours\n"
    activity_log += f"Total events: {len(issues)} (PRs: {stats['prs']}, Issues: {stats['issues']})\n\n"

    for item in issues:
        if not isinstance(item, dict):
            continue
        item_type = "Pull Request" if "pull_request" in item else "Issue"
        # Safe lookup for deleted or ghost users
        user_data = item.get("user") or {}
        author = user_data.get("login", "unknown")
        activity_log += f"- {item_type} #{item.get('number')}: {item.get('title')}\n"
        activity_log += f"  State: {item.get('state')} | Author: @{author}\n"
        activity_log += f"  URL: {item.get('html_url')}\n\n"

    return True, activity_log, issues, stats


def summarize_activity_with_gemini(raw_log: str, repo: str = "") -> str:
    """Summarizes raw activity using Google Gemini AI."""
    if "No new activity" in raw_log or "Unable to connect" in raw_log:
        return raw_log

    config = get_config()
    api_key = config["gemini_api_key"]
    model_name = config["gemini_model"]

    if not api_key:
        return (
            f"### ⚠️ Gemini API Key Not Configured\n\n"
            f"Here is the structured activity log for **`{repo}`** in the past 24 hours:\n\n"
            f"{raw_log}\n\n"
            f"> **Tip**: To enable AI narrative summarization, set `GEMINI_API_KEY=your_key` in your `.env` file."
        )

    print(f"Summarizing activity for {repo} with Gemini ({model_name})...")

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

    # 1. Try modern google-genai SDK first
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        if response and response.text:
            return response.text
    except Exception as e_genai:
        print(f"google-genai attempt encountered: {e_genai}. Falling back to google.generativeai...")

    # 2. Fall back to google.generativeai SDK if modern SDK is unavailable
    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=api_key)
        # Fall back to 1.5-flash if 2.5-flash is not mapped in older SDK version
        fallback_model_name = 'gemini-1.5-flash' if '2.5' in model_name else model_name
        current_model = legacy_genai.GenerativeModel(fallback_model_name)
        response = current_model.generate_content(prompt)
        if response and response.text:
            return response.text
    except Exception as e_legacy:
        print(f"Gemini API generation error: {e_legacy}")
        return f"Could not generate AI summary due to an error: {e_legacy}\n\n### Raw Activity Log\n{raw_log}"

    return f"### Activity Log for {repo}\n\n{raw_log}"


def send_email_digest(summary: str, recipient_email: str, repo: str):
    """Sends the generated digest to the specified email address via SMTP."""
    config = get_config()
    sender_email = config["sender_email"]
    sender_password = config["sender_password"]
    smtp_host = config["smtp_host"]
    smtp_port = config["smtp_port"]

    if not sender_email or not sender_password:
        print("SMTP credentials missing in .env")
        return False, "SMTP sender credentials (SENDER_EMAIL, SENDER_PASSWORD) are not configured in .env."

    print(f"Sending digest email to {recipient_email}...")

    clean_repo = sanitize_repo_name(repo)
    message = MIMEMultipart("alternative")
    message["Subject"] = f"GitHub Daily Digest: {clean_repo} ({datetime.now(timezone.utc).strftime('%b %d, %Y')})"
    message["From"] = sender_email
    message["To"] = recipient_email

    # Plain text version (UTF-8 encoded)
    message.attach(MIMEText(summary, "plain", "utf-8"))

    # HTML rich email version
    try:
        import markdown
        html_content = markdown.markdown(summary, extensions=['extra', 'nl2br'])
    except Exception:
        html_content = f"<pre style='font-family: monospace; white-space: pre-wrap;'>{summary}</pre>"

    html_wrapper = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; padding: 24px; }}
        .card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; max-width: 680px; margin: 0 auto; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
        .header {{ border-bottom: 2px solid #6366f1; padding-bottom: 12px; margin-bottom: 20px; }}
        h1, h2, h3 {{ color: #0f172a; }}
        a {{ color: #4f46e5; text-decoration: underline; }}
        code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
        blockquote {{ border-left: 3px solid #6366f1; margin: 12px 0; padding-left: 12px; color: #64748b; font-style: italic; }}
        .footer {{ margin-top: 24px; pt: 16px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h2 style="margin: 0; color: #4f46e5;">GitHub Daily Digest: {clean_repo}</h2>
          <div style="font-size: 12px; color: #64748b; margin-top: 4px;">
            Generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}
          </div>
        </div>
        <div class="content">
          {html_content}
        </div>
        <div class="footer">
          Sent by GitHub Activity Digest Agent &bull; Powered by Gemini AI
        </div>
      </div>
    </body>
    </html>
    """
    message.attach(MIMEText(html_wrapper, "html", "utf-8"))

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=12) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, message.as_string())
        print("Email sent successfully!")
        return True, "Email sent successfully."
    except Exception as e:
        print(f"Error sending email: {e}")
        return False, str(e)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health probe for monitoring."""
    return jsonify({
        "status": "healthy",
        "service": "GitHub Digest Agent",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route('/api/status', methods=['GET'])
def system_status():
    """Returns current environment readiness status."""
    config = get_config()
    return jsonify({
        "gemini_configured": bool(config["gemini_api_key"]),
        "gemini_model": config["gemini_model"],
        "github_token_configured": bool(config["github_token"]),
        "smtp_configured": bool(config["sender_email"] and config["sender_password"]),
        "default_repo": config["default_repo"],
        "default_recipient": config["default_recipient_email"]
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
    success, raw_activity, issues, stats = fetch_github_activity(clean_repo)

    if not success:
        return jsonify({
            "status": "error",
            "error": raw_activity,
            "repo": clean_repo or repo,
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
    config = get_config()
    target_repo = config["default_repo"] or "pallets/flask"
    target_email = config["default_recipient_email"]

    print(f"--- Running Automated Daily Digest for {target_repo} ---")
    success, raw_activity, issues, stats = fetch_github_activity(target_repo)

    if not success:
        return jsonify({
            "status": "error",
            "error": raw_activity,
            "message": f"Failed to fetch activity for default repo '{target_repo}': {raw_activity}",
            "stats": stats
        }), 400

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
