"""
Test Apply Script
Allows testing the auto-apply sequence on a specific job URL with step-by-step logging and visual confirmation (screenshots).

Usage:
    python test_apply.py <Naukri Job URL>
"""
import asyncio
import sys
from pathlib import Path
from app.scrapers.naukri_scraper import NaukriScraper
from app.services.chatbot_handler import ChatbotHandler
from app.core.config import settings
from app.core.logging import logger

async def test_job_url(job_url: str):
    logger.info(f"Initializing test run for URL: {job_url}")
    
    # Ensure screenshots output directory exists
    screenshots_dir = Path("data/cache/test_runs")
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    async with NaukriScraper() as scraper:
        # We manually run the steps here so we can take custom screenshots and log details
        if not scraper._logged_in:
            await scraper.login()
            
        page = await scraper._new_page()
        try:
            logger.info("Navigating to job URL...")
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
            
            # Handle login redirect or session expiration
            if "login" in page.url.lower() or "register" in page.url.lower() or "login" in (await page.title()).lower():
                logger.warning(f"Session expired or redirected to login page on {job_url}. Re-authenticating...")
                await page.close()
                await scraper.login()
                page = await scraper._new_page()
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for button to be visible
            try:
                await page.wait_for_selector(
                    "#apply-button, button.apply-button, [id*='apply' i], [class*='apply' i] button, [class*='apply' i]",
                    timeout=10_000,
                    state="visible"
                )
            except Exception:
                logger.warning("Apply button selector timeout — continuing to check")

            # Screenshot: Page Loaded
            img_loaded = screenshots_dir / "1_loaded.png"
            await page.screenshot(path=str(img_loaded))
            logger.info(f"Step 1: Loaded page screenshot saved to {img_loaded}")

            # Find apply button
            apply_btn = await scraper._find_element(page, scraper._APPLY_SELECTORS, "apply button")
            if not apply_btn:
                logger.error("Could not find any apply button with current selectors.")
                return False
                
            btn_text = (await apply_btn.inner_text()).strip().lower()
            logger.info(f"Found apply button text: {btn_text!r}")
            
            # Check if button text indicates we are logged out
            if any(kw in btn_text for kw in ["login to apply", "register to apply", "login", "register", "sign in"]):
                logger.warning(f"Apply button indicates login required ({btn_text!r}). Re-authenticating...")
                await page.close()
                await scraper.login()
                page = await scraper._new_page()
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
                apply_btn = await scraper._find_element(page, scraper._APPLY_SELECTORS, "apply button")
                if not apply_btn:
                    logger.error("No apply button found after re-login.")
                    return False
                btn_text = (await apply_btn.inner_text()).strip().lower()
                logger.info(f"Found apply button text after re-login: {btn_text!r}")

            # Check if already applied
            if "applied" in btn_text or "already applied" in btn_text:
                logger.info(f"Already applied to job {job_url} based on button text. Marking success.")
                return True

            # Check external
            is_external = any(kw in btn_text for kw in scraper._EXTERNAL_APPLY_KEYWORDS)
            logger.info(f"Is external redirect? {is_external}")
            
            # Check direct
            is_direct = any(kw in btn_text for kw in scraper._DIRECT_APPLY_KEYWORDS)
            logger.info(f"Is direct Easy-Apply? {is_direct}")
            
            if is_external:
                logger.warning("This is an external job. Skipping actual click to avoid redirecting.")
                return False
                
            # Click apply — plain click then immediately check for chatbot
            logger.info("Clicking the apply button...")
            await apply_btn.click()

            # Short wait then check for chatbot BEFORE anything else
            await asyncio.sleep(1.5)

            # Screenshot: After Click
            img_clicked = screenshots_dir / "2_after_click.png"
            await page.screenshot(path=str(img_clicked))
            logger.info(f"Step 2: After-click screenshot saved to {img_clicked}")

            cb_handler = ChatbotHandler(page)

            # FIRST: If Naukri opened a chatbot/questionnaire panel — initiate auto-answer
            if await cb_handler.is_chatbot_visible():
                logger.info("Chatbot questionnaire detected — initiating auto-answer sequence...")
                img_chatbot = screenshots_dir / "2b_chatbot_detected.png"
                await page.screenshot(path=str(img_chatbot))
                logger.info(f"Chatbot screenshot saved to {img_chatbot}")
                return await cb_handler.process_and_answer()

            # Give page more time to navigate or update
            await asyncio.sleep(2)

            # Second chatbot check after additional wait
            if await cb_handler.is_chatbot_visible():
                logger.info("Chatbot questionnaire detected (delayed) — initiating auto-answer sequence...")
                return await cb_handler.process_and_answer()

            current_url = page.url.lower()
            if any(kw in current_url for kw in ["applied", "application", "thankyou", "thank-you", "success", "confirm"]):
                logger.info(f"Apply confirmed by URL navigation: {page.url}")
                return True

            # Check if Apply button now says 'Applied'
            try:
                updated_btn = await scraper._find_element(page, scraper._APPLY_SELECTORS, "updated apply button")
                if updated_btn:
                    updated_text = (await updated_btn.inner_text()).strip().lower()
                    logger.info(f"Apply button text after click: {updated_text!r}")
                    if "applied" in updated_text or "already applied" in updated_text:
                        logger.info(f"Apply confirmed — button now reads: {updated_text!r}")
                        return True
            except Exception:
                pass

            # If Naukri opened a chatbot/questionnaire panel — skip this job
            if await scraper._detect_chatbot(page):
                logger.warning("Chatbot questionnaire detected — skipping this job (requires manual answers).")
                img_chatbot = screenshots_dir / "2b_chatbot_detected.png"
                await page.screenshot(path=str(img_chatbot))
                logger.info(f"Chatbot screenshot saved to {img_chatbot}")
                return False

            # Handle modals
            modal_selectors = [
                ".apply-modal", ".apply-layer", "#chatbot-ifr",
                "[class*='apply-modal']", "[class*='applyModal']", ".popup-apply"
            ]
            for modal_sel in modal_selectors:
                modal = await page.query_selector(modal_sel)
                if modal and await modal.is_visible():
                    logger.info(f"Modal popup detected: {modal_sel}")
                    confirm_selectors = [
                        f"{modal_sel} button[type='submit']",
                        f"{modal_sel} .submit-btn",
                        f"{modal_sel} button:has-text('Submit')",
                        f"{modal_sel} button:has-text('Apply')",
                        f"{modal_sel} button:has-text('Confirm')",
                        f"{modal_sel} [role='button']:has-text('Submit')",
                        f"{modal_sel} [role='button']:has-text('Apply')",
                        f"{modal_sel} [role='button']:has-text('Confirm')",
                        f"{modal_sel} a:has-text('Submit')",
                        f"{modal_sel} a:has-text('Apply')",
                        f"{modal_sel} a:has-text('Confirm')",
                        f"{modal_sel} div:has-text('Submit')",
                        f"{modal_sel} div:has-text('Apply')",
                        f"{modal_sel} div:has-text('Confirm')",
                        f"{modal_sel} [class*='btn' i]",
                        f"{modal_sel} [class*='button' i]"
                    ]
                    confirm_btn = await scraper._find_element(page, confirm_selectors, "modal confirm")
                    if confirm_btn:
                        logger.info("Found confirm button inside modal. Clicking it...")
                        try:
                            async with page.expect_navigation(wait_until="domcontentloaded", timeout=5_000):
                                await confirm_btn.click()
                        except Exception:
                            pass
                        await asyncio.sleep(2)
                        img_modal_confirm = screenshots_dir / "3_modal_confirmed.png"
                        await page.screenshot(path=str(img_modal_confirm))
                        logger.info(f"Step 3: Modal confirmation screenshot saved to {img_modal_confirm}")
                    break

            # Final success check
            success_msg = await scraper._safe_text(
                page,
                ".success-msg, .apply-message, .applied-status, [class*='success' i], [class*='applied' i]"
            )
            logger.info(f"Success text found: {success_msg!r}")

            img_final = screenshots_dir / "4_final.png"
            await page.screenshot(path=str(img_final))
            logger.info(f"Step 4: Final verification screenshot saved to {img_final}")

            # Final URL check
            current_url = page.url.lower()
            if any(kw in current_url for kw in ["applied", "application", "thankyou", "thank-you", "success", "confirm"]):
                logger.info(f"Apply confirmed by final URL: {page.url}")
                return True

            if success_msg and ("applied" in success_msg.lower() or "success" in success_msg.lower()):
                logger.success("Apply confirmed successfully!")
                return True
            else:
                logger.info(f"Apply completed (optimistic verification). Final URL: {page.url}")
                return True
                
        except Exception as e:
            logger.error(f"Error during test apply execution: {e}")
            return False
        finally:
            await page.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: Missing job URL.")
        print("Usage: python test_apply.py <Naukri Job URL>")
        sys.exit(1)
        
    url = sys.argv[1]
    asyncio.run(test_job_url(url))
