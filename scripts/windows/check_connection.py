"""Local-only diagnostic; no Naver navigation or login verification."""
import json
import sys
from playwright.sync_api import sync_playwright

def main():
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)
            if len(browser.contexts) != 1:
                raise RuntimeError("Expected one existing Chrome context")
            page = browser.contexts[0].new_page()
            try:
                page.set_content("<h1>Autoblog connection check</h1>")
                if page.locator("h1").inner_text() != "Autoblog connection check":
                    raise RuntimeError("DOM check failed")
            finally:
                page.close()
        print(json.dumps({"status":"CDP_READY", "naver_login_verified":False,
                          "naver_network_verified":False, "profile_restart_verified":False}))
        return 0
    except Exception as e:
        print(json.dumps({"status":"BLOCKED_CDP", "error_type":type(e).__name__}))
        return 1

if __name__ == "__main__":
    sys.exit(main())
