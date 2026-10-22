import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()
from api.db import get_driver

SCREENSHOT_DIR = r"C:\Users\mohit\narit\screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def verify_hitl():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print("1. Opening http://localhost:8000/ ...")
        page.goto("http://localhost:8000/")
        page.wait_for_selector(".brand-title")
        time.sleep(0.5)

        print("2. Switching to [ Contribute ] tab ...")
        page.click("#tab-contribute")
        page.wait_for_selector("#view-contribute", state="visible")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "hitl_01_contribute_tab.png"), full_page=False)

        print("3. Pasting text into Contribute textarea ...")
        test_text = "In the case of State v. Sharma, the court ruled on murder under section 302."
        page.fill("#contribute-input", test_text)
        time.sleep(0.2)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "hitl_02_text_entered.png"), full_page=False)

        print("4. Clicking [ Process & Connect → ] ...")
        page.click("#process-btn")
        page.wait_for_selector(".review-proposal-card")
        time.sleep(0.5)

        # Verify card elements
        heading = page.locator(".proposal-heading").inner_text()
        print("Proposal Heading:", heading)
        assert "Proposed Graph Addition" in heading

        card_text = page.locator(".review-proposal-card").inner_text()
        print("Card Text Summary:\n", card_text)
        assert "Case" in card_text
        assert "State v. Sharma" in card_text
        assert "INTERPRETS" in card_text
        assert "IPC 302" in card_text
        assert "Approve & Save" in card_text
        assert "Edit" in card_text
        assert "Discard" in card_text

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "hitl_03_proposal_card.png"), full_page=False)

        print("5. Testing [ Edit ] toggle ...")
        page.click("#btn-edit-toggle")
        page.wait_for_selector("#edit-fields-box", state="visible")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "hitl_04_edit_mode.png"), full_page=False)

        # Edit the title field
        page.fill("#input-edit-title", "Ruling on Murder under Section 302")
        time.sleep(0.2)
        page.click("#btn-edit-toggle") # Done editing
        time.sleep(0.3)

        print("6. Clicking [ Approve & Save ] ...")
        page.click("#btn-approve-save")
        page.wait_for_selector(".success-toast-card")
        time.sleep(0.5)

        success_text = page.locator(".success-toast-card").inner_text()
        print("Success Toast:\n", success_text)
        assert "Graph Updated Permanently" in success_text
        assert "State v. Sharma" in success_text

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "hitl_05_commit_success.png"), full_page=False)

        print("7. Testing [ Discard ] flow ...")
        page.fill("#contribute-input", "State of Maharashtra v. Mayer Hans George (1965) concerning foreign exchange.")
        page.click("#process-btn")
        page.wait_for_selector(".review-proposal-card")
        time.sleep(0.3)
        page.click("#btn-discard-proposal")
        page.wait_for_selector(".empty-state-card:has-text('Human-in-the-Loop')")
        time.sleep(0.3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "hitl_06_discard_success.png"), full_page=False)

        browser.close()

    print("8. Verifying node and relationship in Neo4j Aura ...")
    driver = get_driver()
    with driver.session() as s:
        res = s.run(
            "MATCH (c:Case {citation: 'State v. Sharma'})-[r:INTERPRETS]->(sec:Section {number: '302'}) RETURN c.citation AS cite, c.title AS title, type(r) AS rel, sec.code AS code, sec.number AS num"
        ).data()
        print("Neo4j Verification Query Result:", res)
        assert len(res) > 0, "Expected Case node State v. Sharma to exist in Neo4j!"
        assert res[0]["cite"] == "State v. Sharma"
        assert res[0]["rel"] == "INTERPRETS"
        assert res[0]["num"] == "302"
        print("Verified in Neo4j Aura successfully!")

if __name__ == "__main__":
    verify_hitl()
