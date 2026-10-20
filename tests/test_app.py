import os
import sys
import unittest

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import (
    app,
    sanitize_repo_name,
    fetch_github_activity,
    summarize_activity_with_gemini,
    send_email_digest,
    get_config
)


class TestGithubDigestApp(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.testing = True
        self.client = self.app.test_client()

    def test_homepage(self):
        """Root GET request should serve index.html with HTTP 200."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'GitHub Digest', response.data)

    def test_health_check(self):
        """GET /api/health should return a healthy status JSON."""
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "healthy")

    def test_system_status(self):
        """GET /api/status should report environment configuration flags."""
        response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('gemini_configured', data)
        self.assertIn('smtp_configured', data)
        self.assertIn('github_token_configured', data)
        self.assertIn('default_repo', data)
        self.assertIn('default_recipient', data)

    def test_sanitize_repo_name_variants(self):
        """Sanitizer should clean various URL schemas, prefixes, suffixes, and paths."""
        cases = {
            'facebook/react': 'facebook/react',
            'https://github.com/facebook/react': 'facebook/react',
            'https://github.com/facebook/react/': 'facebook/react',
            'https://github.com/facebook/react.git': 'facebook/react',
            'http://github.com/facebook/react': 'facebook/react',
            'github.com/facebook/react': 'facebook/react',
            'git@github.com:facebook/react.git': 'facebook/react',
            'https://github.com/facebook/react/issues/100': 'facebook/react',
            'https://github.com/facebook/react/pull/200': 'facebook/react',
            '  pallets/flask  ': 'pallets/flask',
            '': '',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(sanitize_repo_name(raw), expected)

    def test_fetch_github_activity_invalid_format(self):
        """Invalid repository names without owner/repo format should return False cleanly."""
        success, err_msg, issues, stats = fetch_github_activity('invalidformat')
        self.assertFalse(success)
        self.assertIn('Invalid repository format', err_msg)
        self.assertEqual(len(issues), 0)

    def test_fetch_github_activity_nonexistent_repo(self):
        """Non-existent repositories should return False with a 404 message."""
        success, err_msg, issues, stats = fetch_github_activity('fake-owner-12345/fake-repo-98765')
        self.assertFalse(success)
        self.assertIn('was not found', err_msg)
        self.assertEqual(len(issues), 0)

    def test_fetch_github_activity_valid_repo(self):
        """A valid public repository should return True and a valid issues list."""
        success, log, issues, stats = fetch_github_activity('pallets/flask')
        self.assertTrue(success)
        self.assertIsInstance(issues, list)
        self.assertIn('total', stats)
        self.assertIn('prs', stats)

    def test_generate_digest_missing_repo_payload(self):
        """Calling /generate-digest without repo should return 400 Bad Request."""
        response = self.client.post('/generate-digest', json={'repo': ''})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.get_json())

    def test_generate_digest_invalid_repo(self):
        """Calling /generate-digest with invalid repo should return 400 with error message."""
        response = self.client.post('/generate-digest', json={'repo': 'nonexistent-user-12345/nonexistent-repo-987654', 'send_email': False})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'error')
        self.assertIn('error', data)

    def test_generate_digest_missing_email_in_email_mode(self):
        """Calling /generate-digest in email mode without email should return 400."""
        response = self.client.post('/generate-digest', json={'repo': 'pallets/flask', 'send_email': True, 'email': ''})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.get_json())

    def test_generate_digest_valid_preview(self):
        """Valid repo in preview mode should generate digest with HTTP 200."""
        response = self.client.post('/generate-digest', json={'repo': 'pallets/flask', 'send_email': False})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('email_status'), 'skipped')
        self.assertIn('summary', data)
        self.assertIn('raw_activity', data)

    def test_trigger_daily_digest(self):
        """Automated daily digest route should run cleanly for configured default repo."""
        response = self.client.post('/trigger-daily-digest')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('summary', data)

    def test_gemini_fallback_when_unconfigured(self):
        """When GEMINI_API_KEY is unset, summarizer should return structured log with setup tip."""
        # Test fallback function directly
        raw_log = "GitHub Activity Digest for pallets/flask\nTotal events: 1\n- Issue #1: Test"
        summary = summarize_activity_with_gemini(raw_log, "pallets/flask")
        self.assertIn("pallets/flask", summary)

    def test_send_email_digest_missing_credentials(self):
        """When SMTP credentials are not configured, email sender should fail gracefully."""
        success, message = send_email_digest("test summary", "recipient@example.com", "pallets/flask")
        self.assertFalse(success)
        self.assertIn("SMTP sender credentials", message)


if __name__ == '__main__':
    unittest.main()
