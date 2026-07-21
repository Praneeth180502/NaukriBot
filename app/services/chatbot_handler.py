"""
Naukri Chatbot Auto-Answer Handler.
Handles chatbot questionnaires/popups that appear when applying for jobs on Naukri.com.
Dynamically detects questions, options, inputs, and submits answers based on user profile/config.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional, List, Union
from playwright.async_api import Page, Frame, ElementHandle

from app.core.config import settings
from app.core.logging import logger


class ChatbotHandler:
    """
    Automated solver for Naukri apply chatbot questionnaires.
    """

    CHATBOT_CONTAINER_SELECTORS = [
        "#chatbot-ifr",
        "iframe[src*='chatbot' i]",
        ".chatbot-container",
        "[class*='chatbot' i]",
        "[class*='ChatBot' i]",
        ".apply-chatbot",
        "[class*='apply-chat' i]",
        ".naukri-chat",
        "div[class*='bot-container' i]",
        "div[class*='drawer-container' i]",
        ".chat-wrapper",
        ".qs-container",
    ]

    QUESTION_SELECTORS = [
        ".bot-msg",
        ".bot-question",
        "[class*='botMsg' i]",
        "[class*='bot-msg' i]",
        "[class*='question' i]",
        ".qs-question",
        ".chat-message",
        "[class*='chat-message' i]",
        ".msg-text",
        ".msg",
    ]

    OPTION_BUTTON_SELECTORS = [
        "button[class*='option' i]",
        "div[class*='option' i]",
        "span[class*='chip' i]",
        "button[class*='chip' i]",
        "div[class*='chip' i]",
        ".bot-options button",
        ".options-container button",
        "[class*='bot-msg' i] button",
        "button[class*='radio' i]",
        "label[class*='radio' i]",
        "div[class*='choice' i]",
        "button[class*='pill' i]",
        "ul.options li",
        "[class*='button-group' i] button",
        "[class*='options' i] button",
        "[class*='options' i] div[role='button']",
    ]

    INPUT_SELECTORS = [
        "input[placeholder*='message' i]",
        "input[placeholder*='type' i]",
        "input[placeholder*='answer' i]",
        "input[placeholder*='enter' i]",
        "input[type='text']",
        "input[type='number']",
        "textarea",
    ]

    SEND_SELECTORS = [
        "button:has-text('Send')",
        "button:has-text('Next')",
        "button:has-text('Submit')",
        "button:has-text('Continue')",
        ".send-btn",
        "button[type='submit']",
        "i[class*='send' i]",
        "svg[class*='send' i]",
        "[class*='send-icon' i]",
        "span:has-text('Send')",
        "span:has-text('Next')",
        "[role='button']:has-text('Send')",
        "[role='button']:has-text('Next')",
    ]

    FINAL_SUBMIT_SELECTORS = [
        "button:has-text('Submit Application')",
        "button:has-text('Apply Now')",
        "button:has-text('Submit')",
        "button:has-text('Finish')",
        "button:has-text('Done')",
        "button:has-text('Confirm')",
        "button.apply-btn",
    ]

    def __init__(self, page: Page, profile_data=None):
        self.page = page
        self.profile = profile_data
        self.cb_config = getattr(settings.naukri, "chatbot_answers", None)

    async def is_chatbot_visible(self) -> bool:
        """Check if any chatbot container or active prompt is visible."""
        # 1. Check in main page
        for sel in self.CHATBOT_CONTAINER_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue

        # 2. Check frames (if iframe exists)
        for frame in self.page.frames:
            if any(kw in (frame.name or "").lower() or kw in frame.url.lower() for kw in ["chatbot", "apply"]):
                return True

        # 3. Check for specific question inputs
        for input_sel in self.INPUT_SELECTORS:
            try:
                el = await self.page.query_selector(input_sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue

        return False

    async def get_target_context(self) -> Union[Page, Frame]:
        """Returns the page or iframe where chatbot elements live."""
        for frame in self.page.frames:
            if any(kw in (frame.name or "").lower() or kw in frame.url.lower() for kw in ["chatbot", "apply"]):
                return frame
        # Check if iframe element exists
        iframe_el = await self.page.query_selector("#chatbot-ifr, iframe[src*='chatbot' i]")
        if iframe_el:
            content_frame = await iframe_el.content_frame()
            if content_frame:
                return content_frame
        return self.page

    async def process_and_answer(self, max_turns: int = 15) -> bool:
        """
        Main loop to answer questions sequentially until chatbot completes or closes.
        """
        logger.info("Starting automated chatbot answer sequence...")
        
        for turn in range(1, max_turns + 1):
            await asyncio.sleep(1.2)  # Give DOM time to update after previous turn

            context = await self.get_target_context()

            # Check if chatbot is still active / visible
            if not await self.is_chatbot_visible():
                logger.info("Chatbot container no longer visible. Questionnaire completed or closed.")
                return True

            # Check for final submit or success indicators first
            if await self._check_success_or_final_submit(context):
                logger.success("Chatbot application submitted successfully!")
                return True

            # Extract latest question text
            q_text = await self._extract_latest_question(context)
            logger.info(f"[Chatbot Turn {turn}/{max_turns}] Question detected: {q_text!r}")

            # Try answering option buttons / pills / radios
            answered = await self._handle_options(context, q_text)
            if answered:
                logger.info(f"[Chatbot Turn {turn}] Answered via option button selection.")
                await asyncio.sleep(1.5)
                continue

            # Try text inputs
            answered = await self._handle_text_input(context, q_text)
            if answered:
                logger.info(f"[Chatbot Turn {turn}] Answered via text input.")
                await asyncio.sleep(1.5)
                continue

            # Try clicking Next/Submit if no inputs or options were clicked but button is present
            if await self._click_next_or_send(context):
                logger.info(f"[Chatbot Turn {turn}] Clicked Next/Continue button.")
                await asyncio.sleep(1.5)
                continue

            logger.warning(f"[Chatbot Turn {turn}] No interactive elements or match found for question: {q_text!r}")
            # Short pause before next iteration
            await asyncio.sleep(1.5)

        logger.info("Chatbot interaction loop completed maximum turns.")
        return True

    async def _extract_latest_question(self, context: Union[Page, Frame]) -> str:
        """Find the latest question text rendered by the bot."""
        for sel in self.QUESTION_SELECTORS:
            try:
                els = await context.query_selector_all(sel)
                if els:
                    for el in reversed(els):
                        if await el.is_visible():
                            txt = (await el.inner_text()).strip()
                            if txt and len(txt) > 3:
                                return txt
            except Exception:
                continue

        # Fallback: find any visible text block inside chatbot container
        try:
            container = await context.query_selector(".chatbot-container, [class*='chatbot' i], #chatbot-ifr")
            if container:
                txt = (await container.inner_text()).strip()
                lines = [line.strip() for line in txt.split("\n") if len(line.strip()) > 5]
                if lines:
                    return lines[-1]
        except Exception:
            pass

        return ""

    async def _handle_options(self, context: Union[Page, Frame], q_text: str) -> bool:
        """Find option buttons/chips, determine best match, and click."""
        option_els: List[ElementHandle] = []
        for sel in self.OPTION_BUTTON_SELECTORS:
            try:
                els = await context.query_selector_all(sel)
                visible_els = [el for el in els if await el.is_visible()]
                if visible_els:
                    option_els = visible_els
                    break
            except Exception:
                continue

        if not option_els:
            return False

        # Gather text of all visible options
        options_info = []
        for el in option_els:
            txt = (await el.inner_text()).strip()
            if txt:
                options_info.append((txt, el))

        if not options_info:
            return False

        logger.debug(f"Available options for chatbot question: {[o[0] for o in options_info]}")

        # Choose best option based on question context & profile/config
        best_index = self._select_best_option([o[0] for o in options_info], q_text)
        chosen_txt, chosen_el = options_info[best_index]

        logger.info(f"Selecting chatbot option: {chosen_txt!r}")
        try:
            await chosen_el.click()
            return True
        except Exception as e:
            logger.warning(f"Failed to click option {chosen_txt!r}: {e}")
            return False

    def _select_best_option(self, options: List[str], q_text: str) -> int:
        """
        Determines the index of the best option based on question context & profile data.
        """
        q_lower = q_text.lower()
        opts_lower = [o.lower() for o in options]

        # 1. Experience Questions
        if any(kw in q_lower for kw in ["experience", "years", "exp"]):
            user_exp = getattr(self.profile, "total_experience_years", 1.0)
            if self.cb_config:
                user_exp = getattr(self.cb_config, "total_experience_years", user_exp)

            # Match numeric range or value closest to user_exp
            for idx, opt in enumerate(opts_lower):
                if f"{int(user_exp)}" in opt or "1 year" in opt or "0-1" in opt or "1-2" in opt or "fresher" in opt:
                    return idx
            # Default to first non-zero experience option if available
            for idx, opt in enumerate(opts_lower):
                if any(num in opt for num in ["0", "1", "2"]):
                    return idx

        # 2. Notice Period Questions
        if any(kw in q_lower for kw in ["notice", "serving", "join", "availability"]):
            notice_keywords = ["immediate", "0 day", "15 day", "1 month", "30 day", "yes"]
            for kw in notice_keywords:
                for idx, opt in enumerate(opts_lower):
                    if kw in opt:
                        return idx

        # 3. Location / Relocation Questions
        if any(kw in q_lower for kw in ["relocate", "relocation", "location", "city"]):
            for idx, opt in enumerate(opts_lower):
                if any(kw in opt for kw in ["yes", "willing", "ready", "hyderabad", "bangalore", "any"]):
                    return idx

        # 4. CTC / Salary Questions
        if any(kw in q_lower for kw in ["ctc", "salary", "lpa", "package", "compensation"]):
            # Pick mid-range or entry level band
            for idx, opt in enumerate(opts_lower):
                if any(kw in opt for kw in ["3-6", "4-7", "3", "4", "5", "6", "lpa"]):
                    return idx

        # 5. Education Questions
        if any(kw in q_lower for kw in ["education", "degree", "qualification", "graduate"]):
            for idx, opt in enumerate(opts_lower):
                if any(kw in opt for kw in ["b.tech", "btech", "bachelor", "graduate", "engineering", "yes", "full time"]):
                    return idx

        # 6. General Yes / No Questions
        for idx, opt in enumerate(opts_lower):
            if opt in ["yes", "yep", "yeah", "sure", "agree", "accept"]:
                return idx

        # Default fallback: pick positive option or first option
        for idx, opt in enumerate(opts_lower):
            if any(w in opt for w in ["yes", "immediate", "ready", "full-time", "b.tech", "agree"]):
                return idx

        return 0  # Fallback to first available option

    async def _handle_text_input(self, context: Union[Page, Frame], q_text: str) -> bool:
        """Find visible text input/textarea, type appropriate answer, and click send/submit."""
        input_el: Optional[ElementHandle] = None
        for sel in self.INPUT_SELECTORS:
            try:
                el = await context.query_selector(sel)
                if el and await el.is_visible() and await el.is_enabled():
                    input_el = el
                    break
            except Exception:
                continue

        if not input_el:
            return False

        # Formulate answer text based on question & profile/config
        answer_text = self._generate_text_answer(q_text)
        logger.info(f"Typing chatbot answer: {answer_text!r} for question: {q_text!r}")

        try:
            await input_el.click()
            await input_el.fill(answer_text)
            await asyncio.sleep(0.3)

            # Try clicking Send/Submit button or press Enter
            sent = await self._click_next_or_send(context)
            if not sent:
                await input_el.press("Enter")

            return True
        except Exception as e:
            logger.warning(f"Error answering via text input: {e}")
            return False

    def _generate_text_answer(self, q_text: str) -> str:
        """Generates smart text response matching question context."""
        q_lower = q_text.lower()

        # Notice period
        if any(kw in q_lower for kw in ["notice", "serving", "availability", "join"]):
            np_days = getattr(self.cb_config, "notice_period_days", 0) if self.cb_config else 0
            if np_days == 0:
                return "Immediate (0 days)"
            return f"{np_days} days"

        # Experience
        if any(kw in q_lower for kw in ["experience", "years", "exp"]):
            exp = getattr(self.profile, "total_experience_years", 1.0)
            if self.cb_config:
                exp = getattr(self.cb_config, "total_experience_years", exp)
            return f"{exp} year" if exp == 1.0 else f"{exp} years"

        # Current CTC
        if "current" in q_lower and any(kw in q_lower for kw in ["ctc", "salary", "package", "lpa"]):
            ctc = getattr(self.cb_config, "current_ctc_lpa", "4") if self.cb_config else "4"
            return f"{ctc} LPA"

        # Expected CTC
        if any(kw in q_lower for kw in ["expected", "expectation", "desire"]) and any(kw in q_lower for kw in ["ctc", "salary", "package", "lpa"]):
            ctc = getattr(self.cb_config, "expected_ctc_lpa", "6") if self.cb_config else "6"
            return f"{ctc} LPA"

        # Location
        if any(kw in q_lower for kw in ["location", "city", "where do you live"]):
            loc = getattr(self.cb_config, "current_location", "Hyderabad") if self.cb_config else "Hyderabad"
            return loc

        # Qualification / Degree
        if any(kw in q_lower for kw in ["education", "degree", "qualification", "college"]):
            deg = getattr(self.cb_config, "highest_qualification", "B.Tech") if self.cb_config else "B.Tech"
            return deg

        # Default fallback
        if self.cb_config and getattr(self.cb_config, "default_text", None):
            return getattr(self.cb_config, "default_text")

        return "Yes"

    async def _click_next_or_send(self, context: Union[Page, Frame]) -> bool:
        """Click Send / Next / Submit button if present."""
        for sel in self.SEND_SELECTORS:
            try:
                el = await context.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    return True
            except Exception:
                continue
        return False

    async def _check_success_or_final_submit(self, context: Union[Page, Frame]) -> bool:
        """Checks if final submit button is present and clicks it, or if success message appeared."""
        # Check success text
        try:
            container = await context.query_selector(".chatbot-container, [class*='chatbot' i]")
            if container:
                txt = (await container.inner_text()).lower()
                if any(kw in txt for kw in ["application submitted", "applied successfully", "thank you for applying", "application received"]):
                    return True
        except Exception:
            pass

        # Check final submit button
        for sel in self.FINAL_SUBMIT_SELECTORS:
            try:
                el = await context.query_selector(sel)
                if el and await el.is_visible():
                    btn_text = (await el.inner_text()).strip().lower()
                    logger.info(f"Found final submit button: {btn_text!r}. Clicking to finalize application...")
                    await el.click()
                    await asyncio.sleep(2)
                    return True
            except Exception:
                continue

        return False
