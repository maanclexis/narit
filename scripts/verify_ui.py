import time
import os
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\mohit\narit\screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # 1. Initial page
        print("1. Initial page load...")
        page.goto("http://localhost:8000/")
        page.wait_for_selector(".brand-title")
        time.sleep(0.5)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_initial_page.png"), full_page=False)

        # 2. Skeleton Loader State
        print("2. Capturing skeleton loading state...")
        # Route /analyze with artificial delay to screenshot the skeleton loader
        def delayed_handler(route):
            time.sleep(1.0)
            route.continue_()

        page.route("**/analyze", delayed_handler)
        page.click(".quick-fills button:has-text('Motorcycle theft')")
        time.sleep(0.1)
        page.click("#analyze-btn")
        page.wait_for_selector(".skeleton-panel")
        time.sleep(0.2)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_skeleton_loader.png"), full_page=False)

        # Unroute delay and wait for results
        page.unroute("**/analyze")
        page.wait_for_selector(".section-card")
        time.sleep(0.5)

        # 3. Motorcycle theft results + expand reasoning path
        print("3. Capturing Motorcycle theft results...")
        page.click(".section-card summary")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_motorcycle_theft_results.png"), full_page=False)

        # Card closeup
        first_card = page.locator(".section-card").first
        first_card.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_theft_card_closeup.png"))

        # 4. Assault with stick
        print("4. Testing Assault with stick...")
        page.click(".quick-fills button:has-text('Assault with stick')")
        time.sleep(0.1)
        page.click("#analyze-btn")
        page.wait_for_selector(".section-card")
        time.sleep(0.5)
        page.click(".section-card summary")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_assault_results.png"), full_page=False)

        # 5. Cheating for money
        print("5. Testing Cheating for money...")
        page.click(".quick-fills button:has-text('Cheating for money')")
        time.sleep(0.1)
        page.click("#analyze-btn")
        page.wait_for_selector(".section-card")
        time.sleep(0.5)
        page.click(".section-card summary")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_cheating_results.png"), full_page=False)

        # 6. Empty input
        print("6. Testing empty input...")
        page.fill("#facts-input", "")
        time.sleep(0.1)
        page.click("#analyze-btn")
        page.wait_for_selector(".empty-state-card:has-text('No specific sections matched')")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "06_empty_input.png"), full_page=False)

        # 7. Non-legal prompt (bake a cake)
        print("7. Testing 'bake a cake'...")
        page.fill("#facts-input", "I want to bake a cake")
        time.sleep(0.1)
        page.click("#analyze-btn")
        page.wait_for_selector(".empty-state-card:has-text('No specific sections matched')")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "07_bake_cake_no_match.png"), full_page=False)

        # 8. Mobile responsive view
        print("8. Testing mobile view...")
        mobile_page = context.new_page()
        mobile_page.set_viewport_size({"width": 390, "height": 844})
        mobile_page.goto("http://localhost:8000/")
        mobile_page.click(".quick-fills button:has-text('Motorcycle theft')")
        mobile_page.click("#analyze-btn")
        mobile_page.wait_for_selector(".section-card")
        time.sleep(0.5)
        mobile_page.click(".section-card summary")
        time.sleep(0.3)
        mobile_page.screenshot(path=os.path.join(SCREENSHOT_DIR, "08_mobile_view.png"), full_page=False)

        browser.close()
        print("All verification steps completed!")

if __name__ == "__main__":
    main()
