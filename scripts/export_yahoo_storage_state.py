from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]

BROWSER_PROFILE_DIR = PROJECT_ROOT / ".browser-profile"
STORAGE_STATE_PATH = PROJECT_ROOT / ".yahoo-storage-state.json"

YAHOO_FANTASY_URL = "https://football.fantasysports.yahoo.com/"
YAHOO_PROFILE_URL = (
    "https://pub-api-ro.fantasysports.yahoo.com/"
    "fantasy/v2/users;use_login=1/profile?format=json"
)


def check_auth(page):
    result = page.evaluate(
        """async (url) => {
            const response = await fetch(url, {
                credentials: 'include'
            });

            return {
                status: response.status,
                body: await response.text()
            };
        }""",
        YAHOO_PROFILE_URL,
    )

    return result


def main():
    with sync_playwright() as playwright:
        print("Opening existing Yahoo browser profile...")

        persistent_context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            channel="chrome",
            headless=True,
        )

        page = (
            persistent_context.pages[0]
            if persistent_context.pages
            else persistent_context.new_page()
        )

        page.goto(
            YAHOO_FANTASY_URL,
            wait_until="commit",
            timeout=60000,
        )

        result = check_auth(page)

        if result["status"] != 200:
            persistent_context.close()
            raise RuntimeError(
                "Existing Yahoo browser profile is not authenticated. "
                f"HTTP status: {result['status']}"
            )

        print("Existing Yahoo session authenticated.")

        persistent_context.storage_state(
            path=str(STORAGE_STATE_PATH)
        )

        persistent_context.close()

        print(f"Saved storage state to: {STORAGE_STATE_PATH}")
        print()
        print("Testing storage state in a completely fresh browser...")

        browser = playwright.chromium.launch(
            channel="chrome",
            headless=True,
        )

        context = browser.new_context(
            storage_state=str(STORAGE_STATE_PATH)
        )

        page = context.new_page()

        page.goto(
            YAHOO_FANTASY_URL,
            wait_until="commit",
            timeout=60000,
        )

        result = check_auth(page)

        browser.close()

        if result["status"] != 200:
            raise RuntimeError(
                "Storage-state authentication failed. "
                f"HTTP status: {result['status']}"
            )

        print("SUCCESS")
        print("Yahoo authentication works from storage state alone.")


if __name__ == "__main__":
    main()