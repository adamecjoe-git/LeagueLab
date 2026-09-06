from playwright.sync_api import sync_playwright


PROFILE_URL = (
    "https://pub-api-ro.fantasysports.yahoo.com/"
    "fantasy/v2/users;use_login=1/profile?format=json"
)

YAHOO_URL = "https://football.fantasysports.yahoo.com/"

BROWSER_PROFILE_DIR = (
    r"C:\Users\jadamec\source\FantasyFootball\.browser-profile"
)


def fetch_profile(page):
    return page.evaluate(
        """async (url) => {
            const response = await fetch(url, {
                credentials: 'include'
            });

            return {
                status: response.status,
                body: await response.text()
            };
        }""",
        PROFILE_URL,
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            channel="chrome",
            headless=False,
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        page.goto(
            YAHOO_URL,
            wait_until="commit",
            timeout=60000,
        )

        result = fetch_profile(page)

        if result["status"] == 401:
            print()
            print("Yahoo login is required.")
            print()
            print("Log into Yahoo in the browser window that just opened.")
            print("Once you can see your fantasy league, come back here.")
            print()

            input("Press Enter after you have logged into Yahoo...")

            # Do NOT navigate again here.
            # Yahoo may still be finishing its redirect from login.yahoo.com.
            print()
            print("Waiting for Yahoo Fantasy page...")

            page.wait_for_url(
                "**football.fantasysports.yahoo.com/**",
                timeout=60000,
            )

            # Give the authenticated page a moment to finish initializing.
            page.wait_for_timeout(2000)

            result = fetch_profile(page)

        print()
        print(f"Status: {result['status']}")
        print()
        print(result["body"])
        print()

        if result["status"] == 200:
            print("SUCCESS: Yahoo session is authenticated.")
        else:
            print("Yahoo authentication test failed.")

        print()
        input("Press Enter to close the browser...")

        browser.close()


if __name__ == "__main__":
    main()