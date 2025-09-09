# GitHub Activity Digest

A Flask-based web application that fetches recent GitHub repository activity, summarizes it using Google's Gemini AI, and sends a daily digest via email.

## Features

- **GitHub Activity Fetching**: Retrieves issues and pull requests from a specified GitHub repository for the last 24 hours using the GitHub API.
- **AI-Powered Summarization**: Uses Google's Gemini AI to generate a concise, human-readable summary of repository activity, grouped into categories like new issues, pull requests, and closed/merged items.
- **Email Notifications**: Sends the summarized digest to a specified email address using SMTP (configured for Gmail).
- **Web Interface**: Provides a simple web form to input a repository and email for on-demand digest generation.
- **Automated Daily Digest**: Supports triggering a daily digest for a pre-configured repository and recipient email.

## Prerequisites

- Python 3.8+
- A Google Gemini API key
- A Gmail account with an App Password for SMTP access
- A GitHub repository to monitor
- A `.env` file with the following environment variables:
  ```plaintext
  GEMINI_API_KEY=your_gemini_api_key
  SENDER_EMAIL=your_gmail_address
  SENDER_PASSWORD=your_gmail_app_password
  DEFAULT_REPO=owner/repo_name
  DEFAULT_RECIPIENT_EMAIL=recipient_email_address
  ```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/github-activity-digest.git
   cd github-activity-digest
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root and add the required environment variables (see above).

5. Create an `index.html` file in a `templates` folder for the web interface. Example:
   ```html
   <!DOCTYPE html>
   <html>
   <head>
       <title>GitHub Activity Digest</title>
   </head>
   <body>
       <h1>GitHub Activity Digest</h1>
       <form id="digestForm">
           <label>Repository (owner/repo):</label><br>
           <input type="text" name="repo" required><br>
           <label>Email:</label><br>
           <input type="email" name="email" required><br>
           <button type="submit">Generate Digest</button>
       </form>
       <script>
           document.getElementById('digestForm').addEventListener('submit', async (e) => {
               e.preventDefault();
               const repo = e.target.repo.value;
               const email = e.target.email.value;
               const response = await fetch('/generate-digest', {
                   method: 'POST',
                   headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify({ repo, email })
               });
               const result = await response.json();
               alert(result.message || result.error);
           });
       </script>
   </body>
   </html>
   ```

6. Run the application:
   ```bash
   python app.py
   ```

## Usage

- **Web Interface**: Navigate to `http://localhost:5000` to access the form. Enter a GitHub repository (e.g., `owner/repo_name`) and an email address, then submit to receive a digest.
- **Automated Digest**: Send a POST request to `http://localhost:5000/trigger-daily-digest` to generate and send a digest for the default repository and email configured in `.env`.
- **Manual Testing**: Use tools like `curl` or Postman to test the `/generate-digest` and `/trigger-daily-digest` endpoints.

## Endpoints

- **GET /**: Serves the web interface (`index.html`).
- **POST /generate-digest**: Generates and sends a digest for a specified repository and email.
  - Payload: `{ "repo": "owner/repo_name", "email": "recipient@example.com" }`
  - Response: JSON with `message` or `error`.
- **POST /trigger-daily-digest**: Triggers the automated digest for the default repository and email.
  - Response: JSON with `status` and `message`.

## Dependencies

- `flask`: Web framework for the application.
- `requests`: For making GitHub API calls.
- `google-generativeai`: For interacting with the Gemini API.
- `python-dotenv`: For loading environment variables.
- `smtplib`: For sending emails via SMTP.

Install dependencies using:
```bash
pip install flask requests google-generativeai python-dotenv
```

## Notes

- Ensure your Gmail account has an App Password if 2FA is enabled (see [Google's documentation](https://support.google.com/accounts/answer/185833)).
- The GitHub API may have rate limits; consider adding authentication for higher limits.
- The application runs in debug mode by default (`app.run(debug=True)`). Disable this in production.
- The Gemini model used is `gemini-1.5-flash`. Update the model name in the code if a different model is required.

## License

MIT License. See [LICENSE](LICENSE) for details.