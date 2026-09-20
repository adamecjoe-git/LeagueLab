"""Yahoo transport checks without credentials or network access."""
import unittest
from unittest.mock import Mock, patch

from leaguelab.yahoo.client import BASE_URL, YahooFantasyClient


class YahooClientTests(unittest.TestCase):
    def client(self, status=200, body='{"league_key": "470.l.197909"}'):
        client = YahooFantasyClient()
        client.browser = Mock()
        client.page = Mock()
        client.page.url = "https://login.yahoo.com/manage_account"
        response = Mock(status=status)
        response.text.return_value = body
        client.browser.request.get.return_value = response
        return client, response

    def test_valid_session_works_from_account_management_page(self):
        client, response = self.client()
        self.assertEqual(client.get("/leagues?format=json"),
                         {"league_key": "470.l.197909"})
        client.browser.request.get.assert_called_once_with(
            BASE_URL + "/leagues?format=json", timeout=30000, max_redirects=0)
        client.page.evaluate.assert_not_called()
        response.dispose.assert_called_once_with()

    def test_transient_network_failure_retries(self):
        client, response = self.client()
        client.browser.request.get.side_effect = [RuntimeError("network"), response]
        with patch("leaguelab.yahoo.client.time.sleep"):
            self.assertIn("league_key", client.get("/leagues", retries=2))
        self.assertEqual(client.browser.request.get.call_count, 2)

    def test_authentication_failure_is_not_success(self):
        for status in (401, 403):
            with self.subTest(status=status):
                client, response = self.client(status, "unauthorized")
                with self.assertRaisesRegex(RuntimeError, "Yahoo authentication failed"):
                    client.get("/leagues", retries=1)
                response.dispose.assert_called_once_with()

    def test_redirect_or_html_is_not_success(self):
        for status in (302, 200):
            with self.subTest(status=status):
                client, response = self.client(status, "<html>Sign in</html>")
                with self.assertRaises(RuntimeError):
                    client.get("/leagues", retries=1)
                response.dispose.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
