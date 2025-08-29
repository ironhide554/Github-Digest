import os
import requests
import smtplib
import ssl
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dotenv import load_dotenv


load_dotenv()
app = Flask(__name__)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
DEFAULT_REPO = os.getenv("DEFAULT_REPO")
DEFAULT_RECIPIENT_EMAIL = os.getenv("DEFAULT_RECIPIENT_EMAIL")

try:
    genai.configure(api_key=GEMINI_API_KEY)
   
    model = genai.GenerativeModel('gemini-1.5-flash') 
except Exception as e:
  
    raise RuntimeError(f"Error:Not able to configure Gemini client. Check API key. Details: {e}")


def fetch_github_activity(repo: str) -> str:

    print(f"Fetching activity for {repo}...")
    since_time = (datetime.now(datetime.timezone.utc) - timedelta(days=1)).isoformat()
    api_url = f"https://api.github.com/repos/{repo}/issues?since={since_time}&state=all"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        issues = response.json()
    except requests.exceptions.RequestException as e:
        return f"Error!! Unable to fetch data from GitHub: {e}"

    if not issues:
        return f"No new activity in {repo} in the last 24 hours."

    activity_log = f"GitHub Activity Digest for {repo} - Last 24 Hours\n\n"
    for item in issues:
        item_type = "Pull Request" if "pull_request" in item else "Issue"
        activity_log += f"- {item_type} #{item['number']}: {item['title']}\n"
        activity_log += f"  State: {item['state']}\n  URL: {item['html_url']}\n\n"
        
    return activity_log

def summarize_activity_with_gemini(raw_log: str) -> str:
    
    if "No new activity" in raw_log or "Error fetching" in raw_log:
        return raw_log
        
    print("Summarizing activity with Gemini...")
    prompt = (
        "You are an expert project manager AI. Summarize the following raw GitHub "
        "activity log into a clear, human-readable daily digest. Group items logically "
        "(e.g., 'New Pull Requests', 'New Issues', 'Closed/Merged Items'). "
        "Focus on the key changes. Use markdown for formatting.\n\n"
        f"Here is the raw log:\n{raw_log}"
    )
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Could not generate AI summary due to an error: {e}"

def send_email_digest(summary: str, recipient_email: str, repo: str):
    """Sends the generated digest to the specified email address."""
    print(f"Sending email to {recipient_email}...")
    
    message = MIMEMultipart("alternative")
    message["Subject"] = f"GitHub Daily Digest: {repo}"
    message["From"] = SENDER_EMAIL
    message["To"] = recipient_email
    message.attach(MIMEText(summary, "plain"))

    context = ssl.create_default_context()
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, recipient_email, message.as_string())
        print("Email sent successfully!")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route('/')
def index():

    return render_template('index.html')

@app.route('/generate-digest', methods=['POST'])
def generate_digest():

    data = request.json
    repo = data.get('repo')
    email = data.get('email')

    if not repo or not email:
        return jsonify({"error": "Repository and email are required."}), 400

    raw_activity = fetch_github_activity(repo)
    ai_summary = summarize_activity_with_gemini(raw_activity)
    
    if send_email_digest(ai_summary, email, repo):
        return jsonify({"message": f"Digest for {repo} sent successfully to {email}!"})
    else:
        return jsonify({"error": "Failed to send the email digest."}), 500

@app.route('/trigger-daily-digest', methods=['POST'])
def trigger_daily_digest():
 
    print("--- Running Automated Daily Digest ---")
    raw_activity = fetch_github_activity(DEFAULT_REPO)
    ai_summary = summarize_activity_with_gemini(raw_activity)
    
    if send_email_digest(ai_summary, DEFAULT_RECIPIENT_EMAIL, DEFAULT_REPO):
        return jsonify({"status": "success", "message": "Daily digest sent."})
    else:
        return jsonify({"status": "error", "message": "Failed to send daily digest."}), 500

if __name__ == '__main__':
    app.run(debug=True)