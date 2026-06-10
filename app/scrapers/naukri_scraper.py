"""
Naukri Scraper — Playwright-based automation.
Handles: login, profile scraping, job search, job detail extraction.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
    TimeoutError as PWTimeout,
)
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

from app.core.config import settings
from app.core.logging import logger


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RawJob:
    external_id: str
    title: str
    company: str
    location: str
    experience: str
    description: str
    required_skills: List[str]
    salary: str
    posted_date: Optional[str]
    apply_url: str
    job_type: str = "full_time"
    source: str = "naukri"


@dataclass
class NaukriProfileData:
    name: str = ""
    email: str = ""
    phone: str = ""
    headline: str = ""
    total_experience: str = ""
    skills: List[str] = field(default_factory=list)
    current_company: str = ""
    current_role: str = ""
    education: List[dict] = field(default_factory=list)
    preferred_locations: List[str] = field(default_factory=list)
    scraped_at: datetime = field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Scraper
# ─────────────────────────────────────────────────────────────────────────────

class NaukriScraper:
    BASE_URL = "https://www.naukri.com"
    LOGIN_URL = "https://www.naukri.com/nlogin/login"
    PROFILE_URL = "https://www.naukri.com/mnjuser/profile"
    SESSION_FILE = Path("data/cache/naukri_session.json")

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._pw = None
        self._logged_in = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    # JS to inject into every page to spoof fingerprint
    _STEALTH_JS = """
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Spoof plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Spoof languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Spoof platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
        });

        // Hide automation in chrome object
        window.chrome = { runtime: {} };

        // Spoof permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);
    """

    async def start(self):
        self._pw = await async_playwright().start()

        # Use the real installed Chrome if available, else fall back to Chromium
        try:
            self._browser = await self._pw.chromium.launch(
                channel="chrome",
                headless=settings.naukri.headless,  # use configured headless option
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1366,768",
                    "--start-maximized",
                ],
            )
            logger.info("Browser launched: real Chrome channel")
        except Exception:
            logger.warning("Real Chrome not found — falling back to Chromium (stealth only)")
            self._browser = await self._pw.chromium.launch(
                headless=settings.naukri.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1366,768",
                ],
            )

        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )

        # Inject stealth JS into every new page
        await self._context.add_init_script(self._STEALTH_JS)

        # Also apply playwright-stealth library if available
        if HAS_STEALTH:
            logger.info("playwright-stealth active")

        # Try to restore session
        if await self._restore_session():
            logger.info("Naukri session restored from cache")
        else:
            await self.login()

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Naukri scraper stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.stop()

    async def _new_page(self) -> Page:
        """Create a new page with stealth applied."""
        page = await self._context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)
        return page

    # ── Session management ────────────────────────────────────────────────

    async def _save_session(self):
        self.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cookies = await self._context.cookies()
        self.SESSION_FILE.write_text(json.dumps(cookies))
        logger.debug("Session saved")

    async def _restore_session(self) -> bool:
        if not self.SESSION_FILE.exists():
            return False
        try:
            cookies = json.loads(self.SESSION_FILE.read_text())
            await self._context.add_cookies(cookies)
            page = await self._new_page()
            await page.goto(self.PROFILE_URL, wait_until="domcontentloaded", timeout=20_000)
            if "login" not in page.url.lower():
                self._page = page
                self._logged_in = True
                return True
            await page.close()
            return False
        except Exception as e:
            logger.warning(f"Session restore failed: {e}")
            return False

    # ── Login ─────────────────────────────────────────────────────────────

    # All known Naukri email/password input selectors (site changes them often)
    _EMAIL_SELECTORS = [
        "input[placeholder*='Email']",
        "input[placeholder*='email']",
        "input[placeholder*='Username']",
        "input[type='email']",
        "input[id*='email' i]",
        "input[name*='email' i]",
        "input[id='usernameField']",
        "input[id='login_Layer'] input[type='text']",
        ".login-form input[type='text']",
        "form input[type='text']:first-of-type",
        "input[data-testid*='email' i]",
    ]

    _PASSWORD_SELECTORS = [
        "input[type='password']",
        "input[placeholder*='Password']",
        "input[placeholder*='password']",
        "input[id*='password' i]",
        "input[name*='password' i]",
        "input[data-testid*='password' i]",
    ]

    _SUBMIT_SELECTORS = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        ".loginButton",
        "[data-testid*='login' i]",
        "form button",
    ]

    async def login(self) -> bool:
        logger.info("Logging into Naukri...")
        page = await self._new_page()
        debug_dir = Path("data/cache")
        debug_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Load login page — try both known URLs
            for login_url in [self.LOGIN_URL, "https://www.naukri.com/login"]:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(3)  # let JS render
                if "login" in page.url.lower() or "nlogin" in page.url.lower():
                    break

            logger.debug(f"Login page loaded: {page.url}")

            # Screenshot for debugging
            await page.screenshot(path=str(debug_dir / "login_page.png"), full_page=True)
            logger.info(f"Login page screenshot saved to {debug_dir}/login_page.png")

            # Dismiss any popups / overlays
            await self._dismiss_popups(page)

            # Find email field
            email_el = await self._find_element(page, self._EMAIL_SELECTORS, "email input")
            if not email_el:
                # Last resort: dump all inputs for debugging
                inputs = await page.query_selector_all("input")
                logger.error(f"Could not find email input. Found {len(inputs)} inputs on page:")
                for inp in inputs:
                    attrs = await page.evaluate(
                        "(el) => ({ type: el.type, id: el.id, name: el.name, placeholder: el.placeholder, class: el.className })",
                        inp,
                    )
                    logger.error(f"  input: {attrs}")
                await page.screenshot(path=str(debug_dir / "login_failed.png"), full_page=True)
                self._page = page
                return False

            await email_el.click()
            await asyncio.sleep(0.3)
            await email_el.fill(settings.naukri.email)
            logger.debug("Email filled")
            await asyncio.sleep(0.5)

            # Find password field
            pass_el = await self._find_element(page, self._PASSWORD_SELECTORS, "password input")
            if not pass_el:
                logger.error("Could not find password input")
                await page.screenshot(path=str(debug_dir / "login_no_pass.png"), full_page=True)
                self._page = page
                return False

            await pass_el.click()
            await asyncio.sleep(0.3)
            await pass_el.fill(settings.naukri.password)
            logger.debug("Password filled")
            await asyncio.sleep(0.5)

            # Screenshot before submit
            await page.screenshot(path=str(debug_dir / "login_before_submit.png"))

            # Submit
            submit_el = await self._find_element(page, self._SUBMIT_SELECTORS, "submit button")
            if submit_el:
                await submit_el.click()
            else:
                # Fallback: press Enter on password field
                logger.warning("Submit button not found — pressing Enter")
                await pass_el.press("Enter")

            # Wait for navigation away from login page
            try:
                await page.wait_for_function(
                    "() => !window.location.href.includes('login')",
                    timeout=20_000,
                )
            except PWTimeout:
                logger.warning("Navigation timeout after submit — checking current URL")

            await asyncio.sleep(2)
            current_url = page.url
            logger.debug(f"Post-login URL: {current_url}")
            await page.screenshot(path=str(debug_dir / "login_after_submit.png"))

            # Verify success — we should be away from the login page
            if "login" not in current_url.lower() and "nlogin" not in current_url.lower():
                logger.success(f"Naukri login successful — at {current_url}")
                self._page = page
                self._logged_in = True
                await self._save_session()
                return True
            else:
                # Check for error message on page
                error_text = await self._safe_text(page, ".error-msg, .errorMsg, [class*='error']")
                logger.error(f"Login failed — still at {current_url}. Error: {error_text or 'unknown'}")
                self._page = page
                self._logged_in = False
                return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            try:
                await page.screenshot(path=str(debug_dir / "login_exception.png"), full_page=True)
            except Exception:
                pass
            self._page = page
            return False

    async def _find_element(self, page, selectors: list[str], label: str):
        """Try selectors in parallel using combined CSS query, with a sequential fallback if it fails."""
        try:
            combined_sel = ", ".join(selectors)
            el = await page.wait_for_selector(combined_sel, timeout=5_000, state="visible")
            if el:
                # Find which selector matched for logging and return it
                for sel in selectors:
                    try:
                        matched_el = await page.query_selector(sel)
                        if matched_el and await matched_el.is_visible():
                            logger.debug(f"Found {label} via: {sel}")
                            return matched_el
                    except Exception:
                        continue
                logger.debug(f"Found {label} via combined selector")
                return el
        except Exception as e:
            logger.debug(f"Combined selector search failed or timed out: {e}. Falling back to sequential search.")

        # Sequential fallback
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=1_000, state="visible")
                if el:
                    logger.debug(f"Found {label} via sequential fallback: {sel}")
                    return el
            except Exception:
                continue
        logger.warning(f"No selector matched for {label}")
        return None


    async def _dismiss_popups(self, page):
        """Close cookie banners, login prompts, overlays."""
        close_selectors = [
            "button[aria-label*='close' i]",
            "button[aria-label*='dismiss' i]",
            ".close-btn",
            ".modal-close",
            "[data-testid='cross']",
            "button.crossIcon",
            ".login-layer .close",
        ]
        for sel in close_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.5)
                    logger.debug(f"Dismissed popup via: {sel}")
            except Exception:
                pass

    # ── Profile scraping ──────────────────────────────────────────────────

    async def scrape_profile(self) -> NaukriProfileData:
        logger.info("Scraping Naukri profile...")
        profile = NaukriProfileData()

        if not self._logged_in:
            await self.login()

        page = await self._context.new_page()
        try:
            await page.goto(self.PROFILE_URL, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(2)

            # Name
            profile.name = await self._safe_text(page, "span.user-name, h1.profileName, .nameInfo h1")
            # Headline
            profile.headline = await self._safe_text(page, ".designation, .profileSummary span")
            # Experience
            profile.total_experience = await self._safe_text(page, ".exp-info, .experienceInfo")

            # Skills
            skill_els = await page.query_selector_all(".chipsWrapper .chip, .keySkills .tag")
            for el in skill_els:
                skill = (await el.inner_text()).strip()
                if skill:
                    profile.skills.append(skill)

            # Current company / role
            exp_blocks = await page.query_selector_all(".resume-exp-block, .experienceBlock")
            if exp_blocks:
                profile.current_role = await self._safe_text(exp_blocks[0], ".desig, .designation")
                profile.current_company = await self._safe_text(exp_blocks[0], ".org, .company")

            logger.success(f"Profile scraped: {profile.name}, {len(profile.skills)} skills")
        except Exception as e:
            logger.error(f"Profile scrape error: {e}")
        finally:
            await page.close()

        return profile

    # ── Job search ────────────────────────────────────────────────────────

    async def search_jobs(
        self, role: str, location: str, exp_min: int = 0, exp_max: int = 2
    ) -> List[RawJob]:
        """Search Naukri for a specific role + location."""
        if not self._logged_in:
            await self.login()

        page = await self._context.new_page()
        jobs: List[RawJob] = []

        try:
            search_url = self._build_search_url(role, location, exp_min, exp_max)
            logger.info(f"Searching: {role} in {location}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            # Handle login redirect
            if "login" in page.url.lower():
                await page.close()
                await self.login()
                page = await self._context.new_page()
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(2)

            # Collect job cards
            job_cards = await page.query_selector_all("article.jobTuple, .srp-jobtuple-wrapper")
            logger.debug(f"Found {len(job_cards)} job cards")

            for card in job_cards[:settings.naukri.max_jobs_per_cycle]:
                try:
                    job = await self._parse_job_card(page, card)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Card parse error: {e}")
                    continue

        except Exception as e:
            logger.error(f"Search error for {role}/{location}: {e}")
        finally:
            await page.close()

        logger.info(f"Collected {len(jobs)} jobs for {role} in {location}")
        return jobs

    async def get_job_detail(self, job_url: str) -> Optional[str]:
        """Fetch full job description from detail page."""
        page = await self._context.new_page()
        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(1)

            description = await self._safe_text(
                page,
                ".job-desc, .jobDescriptionText, #job-desc, .description",
            )
            return description
        except Exception as e:
            logger.debug(f"Job detail fetch error: {e}")
            return None
        finally:
            await page.close()

    # Bug 1 fix: layered fallback apply-button selectors (same pattern as login)
    _APPLY_SELECTORS = [
        "#apply-button",
        "button.apply-button",
        "a.apply-button",
        "button[id*='apply' i]",
        "a[id*='apply' i]",
        ".apply-section button",
        ".apply-widget button",
        "[data-testid*='apply' i]",
        "button:has-text('Apply Now')",
        "button:has-text('1-Click Apply')",
        "button:has-text('Easy Apply')",
        "button:has-text('Apply')",
        "a:has-text('Apply Now')",
        "a:has-text('Apply')",
        "[role='button']:has-text('Apply Now')",
        "[role='button']:has-text('Apply')",
        "div.apply-button",
        "span.apply-button",
        "[class*='apply-button' i]",
        "[class*='applyButton' i]",
    ]

    # Bug 2 fix: correct external-site keywords used by Naukri
    _EXTERNAL_APPLY_KEYWORDS = [
        "company website", "company site", "external",
        "careers page", "apply on", "visit company",
    ]
    _DIRECT_APPLY_KEYWORDS = [
        "apply now", "1-click", "easy apply", "apply",
    ]

    async def auto_apply(self, job_url: str) -> bool:
        """
        Attempts to automatically apply to a job if:
        1. It has a direct Naukri apply button (not redirecting to company site).
        2. Profile match ticks are present (at least 1 tick found).
        Freshness is logged but no longer a hard gate.
        """
        if not self._logged_in:
            await self.login()

        page = await self._new_page()
        try:
            logger.info(f"Checking auto-apply conditions for {job_url}")

            # Navigate to job URL (domcontentloaded is faster and more reliable)
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            # Handle login redirect or session expiration
            if "login" in page.url.lower() or "register" in page.url.lower() or "login" in (await page.title()).lower():
                logger.warning(f"Session expired or redirected to login page on {job_url}. Re-authenticating...")
                await page.close()
                await self.login()
                page = await self._new_page()
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            # Also wait explicitly for an apply button to be visible
            try:
                await page.wait_for_selector(
                    "#apply-button, button.apply-button, [id*='apply' i], [class*='apply' i] button, [class*='apply' i]",
                    timeout=10_000,
                    state="visible",
                )
            except PWTimeout:
                logger.debug("Apply button did not appear after page load — continuing anyway")

            # Bug 1 fix: use layered fallback selectors
            apply_btn = await self._find_element(page, self._APPLY_SELECTORS, "apply button")
            if not apply_btn:
                logger.debug("No apply button found after all selectors exhausted.")
                return False

            btn_text = (await apply_btn.inner_text()).strip().lower()
            logger.debug(f"Apply button text: {btn_text!r}")

            # Check if button text indicates we are logged out
            if any(kw in btn_text for kw in ["login to apply", "register to apply", "login", "register", "sign in"]):
                logger.warning(f"Apply button indicates login required ({btn_text!r}). Re-authenticating...")
                await page.close()
                await self.login()
                page = await self._new_page()
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
                apply_btn = await self._find_element(page, self._APPLY_SELECTORS, "apply button")
                if not apply_btn:
                    logger.debug("No apply button found after re-login.")
                    return False
                btn_text = (await apply_btn.inner_text()).strip().lower()
                logger.debug(f"Apply button text after re-login: {btn_text!r}")

            # Check if already applied
            if "applied" in btn_text or "already applied" in btn_text:
                logger.info(f"Already applied to job {job_url} based on button text. Marking success.")
                return True

            # Bug 2 fix: correct external-site keywords
            if any(kw in btn_text for kw in self._EXTERNAL_APPLY_KEYWORDS):
                logger.debug(f"Redirects to external site ({btn_text!r}). Skipping auto-apply.")
                return False

            if not any(kw in btn_text for kw in self._DIRECT_APPLY_KEYWORDS):
                logger.debug(f"Button text not a recognised apply action: {btn_text!r}")
                return False

            # Bug 3 fix: freshness is now an informational log, NOT a hard gate
            posted_text = await self._safe_text(
                page,
                ".jd-top-head .stat .date, .jd-header-content .posted-date, "
                "[class*='posted' i], [class*='freshness' i], .stat-item, "
                ".jd-stats span, .job-post-day, .stat .type",
            )
            is_early = any(
                kw in posted_text.lower()
                for kw in ["today", "just now", "1 day", "2 day", "hour", "early", "few"]
            )
            logger.debug(f"Freshness text: {posted_text!r} | is_early={is_early}")

            # Bug 4 fix: broader tick selectors, threshold relaxed from 2 → 1
            tick_icons = await page.query_selector_all(
                "i.icon-tick, i.icon-check, i[class*='tick' i], i[class*='check' i], "
                ".match-icon, .criteria-match, [class*='matched' i], [class*='eligible' i], "
                ".green-tick, svg[class*='check'], .checkmark, .tick"
            )
            has_ticks = len(tick_icons) >= 1
            logger.debug(f"Match tick icons found: {len(tick_icons)} | has_ticks={has_ticks}")

            # Proceed with apply (ticks are preferred but not mandatory if score was already high enough)
            logger.success(f"Clicking apply for {job_url} (is_early={is_early}, has_ticks={has_ticks})")

            # Click Apply — use plain click then immediately watch what appears
            await apply_btn.click()

            # Short wait then check for chatbot BEFORE anything else
            await asyncio.sleep(1.5)
            if await self._detect_chatbot(page):
                logger.info(f"Chatbot questionnaire detected for {job_url} — skipping (requires manual answers).")
                return False

            # Give page a little more time to navigate or update
            await asyncio.sleep(2)

            # Check if chatbot appeared after the additional wait
            if await self._detect_chatbot(page):
                logger.info(f"Chatbot questionnaire detected (delayed) for {job_url} — skipping.")
                return False

            # Check if page navigated to an applied/confirmation URL
            current_url = page.url.lower()
            if any(kw in current_url for kw in ["applied", "application", "thankyou", "thank-you", "success", "confirm"]):
                logger.success(f"Apply confirmed by URL navigation: {page.url}")
                return True

            # Check re-apply button text → if button now says 'Applied', we succeeded
            try:
                updated_btn = await self._find_element(page, self._APPLY_SELECTORS, "updated apply button")
                if updated_btn:
                    updated_text = (await updated_btn.inner_text()).strip().lower()
                    logger.debug(f"Apply button text after click: {updated_text!r}")
                    if "applied" in updated_text or "already applied" in updated_text:
                        logger.success(f"Apply confirmed — button now reads: {updated_text!r}")
                        return True
                    # Final chatbot check after _find_element (which takes a few seconds)
                    if await self._detect_chatbot(page):
                        logger.info(f"Chatbot detected after button search for {job_url} — skipping.")
                        return False
            except Exception:
                pass

            # Bug 5 fix: handle the apply modal / chatbot Naukri opens for simple applies
            modal_selectors = [
                ".apply-modal",
                ".apply-layer",
                "#chatbot-ifr",
                "[class*='apply-modal']",
                "[class*='applyModal']",
                ".popup-apply",
            ]
            for modal_sel in modal_selectors:
                modal = await page.query_selector(modal_sel)
                if modal and await modal.is_visible():
                    logger.debug(f"Apply modal detected: {modal_sel}")
                    # Try to click Submit / Confirm inside the modal
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
                        f"{modal_sel} [class*='button' i]",
                    ]
                    confirm_btn = await self._find_element(page, confirm_selectors, "modal confirm")
                    if confirm_btn:
                        try:
                            async with page.expect_navigation(wait_until="domcontentloaded", timeout=5_000):
                                await confirm_btn.click()
                        except PWTimeout:
                            pass
                        await asyncio.sleep(2)
                        logger.debug(f"Modal confirm clicked — URL now: {page.url}")
                    break

            # Check success message with broadened selectors
            success_msg = await self._safe_text(
                page,
                ".success-msg, .apply-message, .applied-status, "
                "[class*='success' i], [class*='applied' i], .application-success",
            )
            if success_msg and (
                "applied" in success_msg.lower() or "success" in success_msg.lower()
            ):
                logger.success(f"Apply confirmed by success message: {success_msg!r}")
                return True

            # Final URL check after any modal interactions
            current_url = page.url.lower()
            if any(kw in current_url for kw in ["applied", "application", "thankyou", "thank-you", "success", "confirm"]):
                logger.success(f"Apply confirmed by URL after modal: {page.url}")
                return True

            # Optimistic success: if we clicked apply and no error page appeared, treat as success
            logger.info(f"Apply clicked — no explicit confirmation detected at {page.url}; treating as optimistic success.")
            return True

        except Exception as e:
            logger.error(f"Auto-apply error for {job_url}: {e}")
            return False
        finally:
            await page.close()

    # ── Chatbot detection ─────────────────────────────────────────────────

    async def _detect_chatbot(self, page) -> bool:
        """
        Detect whether Naukri opened a chatbot/questionnaire panel after Apply was clicked.
        Returns True if a chatbot panel is visible — caller should skip this job.
        Does NOT interact with the chatbot at all.
        """
        CHATBOT_SIGNALS = [
            # Panel/container selectors
            ".chatbot-container",
            "[class*='chatbot' i]",
            "[class*='ChatBot' i]",
            ".apply-chatbot",
            "[class*='apply-chat' i]",
            ".naukri-chat",
            # Text input inside a panel (strong indicator of a questionnaire)
            "input[placeholder*='Type message' i]",
            "textarea[placeholder*='Type message' i]",
        ]
        for sel in CHATBOT_SIGNALS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    logger.debug(f"Chatbot panel detected via: {sel}")
                    return True
            except Exception:
                continue
        return False



    def _build_search_url(self, role: str, location: str, exp_min: int, exp_max: int) -> str:
        role_encoded = role.replace(" ", "-").lower()
        loc_encoded = location.lower()
        return (
            f"{self.BASE_URL}/{role_encoded}-jobs-in-{loc_encoded}"
            f"?experience={exp_min}to{exp_max}"
            f"&nignBefer=0&k={role.replace(' ', '%20')}&l={location}"
        )

    async def _parse_job_card(self, page: Page, card) -> Optional[RawJob]:
        title_el = await card.query_selector("a.title, .jobTitle a, h2 a")
        if not title_el:
            return None

        title = (await title_el.inner_text()).strip()
        job_url = await title_el.get_attribute("href") or ""
        if not job_url.startswith("http"):
            job_url = self.BASE_URL + job_url

        company = await self._safe_text(card, ".comp-name, .companyName, a.comp-name")
        location = await self._safe_text(card, ".locWdth, .location, .jobLocation")
        experience = await self._safe_text(card, ".experience, .expwdth")
        salary = await self._safe_text(card, ".salary, .package")
        posted_date = await self._safe_text(card, ".jobAge, .type")

        # Skills from card
        skill_tags = await card.query_selector_all(".techStack span, .tags li")
        skills = []
        for tag in skill_tags:
            s = (await tag.inner_text()).strip()
            if s:
                skills.append(s)

        # Generate stable ID from URL
        external_id = re.sub(r"[^a-zA-Z0-9]", "", job_url[-30:]) or str(abs(hash(job_url)))[:12]

        return RawJob(
            external_id=external_id,
            title=title,
            company=company,
            location=location,
            experience=experience,
            description="",  # Fetched separately if needed
            required_skills=skills,
            salary=salary,
            posted_date=posted_date,
            apply_url=job_url,
        )

    async def _safe_text(self, container, selector: str) -> str:
        try:
            el = await container.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""