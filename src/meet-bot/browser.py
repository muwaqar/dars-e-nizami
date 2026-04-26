from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
import time
import logging
import os

logger = logging.getLogger(__name__)


class MeetBrowser:
    """Playwright-based browser automation for Google Meet."""

    def __init__(self, headless: bool = True, storage_state: str = None, strict_media: bool = True, debug: bool = False):
        self.headless = headless
        self.storage_state = storage_state or os.environ.get("CHROME_SESSION_FILE")
        self.strict_media = strict_media
        self.debug = debug
        self.playwright = None
        self.browser: Browser = None
        self.page: Page = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )
        context_options = {}
        if self.storage_state:
            context_options["storage_state"] = self.storage_state

        self.context = self.browser.new_context(
            **context_options,
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            permissions=["geolocation"],
        )
        
        self.context.clear_permissions()
        
        self.page = self.context.new_page()
        
        self.page.on("dialog", self._handle_dialog)
        
        return self

    def _handle_dialog(self, dialog):
        """Handle any browser dialogs (permissions, alerts, etc.)."""
        dialog_text = dialog.message
        logger.debug(f"Dialog detected: {dialog_text}")
        
        if "camera" in dialog_text.lower() or "microphone" in dialog_text.lower() or "media" in dialog_text.lower():
            dialog.dismiss()
            logger.info("Dismissed permission dialog")
        else:
            dialog.accept()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _debug_screenshot(self, name: str) -> None:
        """Take a debug screenshot for troubleshooting."""
        if not self.debug:
            return
        try:
            self.page.screenshot(path=f"debug_{name}.png")
            logger.debug(f"Saved debug_{name}.png")
        except Exception:
            pass

    def join_meeting(self, meet_link: str) -> None:
        """
        Join a Google Meet meeting.

        Args:
            meet_link: The Google Meet URL to join
        """
        logger.info(f"Joining meeting: {meet_link}")
        self.page.goto(meet_link)

        time.sleep(3)

        self._debug_screenshot("01_after_load")

        self._dismiss_popups()

        self._debug_screenshot("02_before_controls")

        camera_off = False
        mic_off = False

        try:
            self._turn_off_camera()
            logger.info("Camera turned off")
            camera_off = True
        except Exception as e:
            logger.error(f"Could not turn off camera: {e}")
            if self.strict_media:
                raise RuntimeError("Failed to turn off camera (strict mode)")

        try:
            self._turn_off_mic()
            logger.info("Microphone turned off")
            mic_off = True
        except Exception as e:
            logger.error(f"Could not turn off microphone: {e}")
            if self.strict_media:
                raise RuntimeError("Failed to turn off microphone (strict mode)")

        self._debug_screenshot("03_controls_toggled")

        time.sleep(1)

        try:
            self._click_join_button()
            self._debug_screenshot("04_joined")
        except Exception as e:
            logger.error(f"Failed to join meeting: {e}")
            self._debug_screenshot("error_join_failed")
            raise

        logger.info("Successfully joined meeting")

    def _dismiss_popups(self) -> None:
        """Dismiss any popups that appear on load."""
        time.sleep(2)
        
        try:
            got_it_button = self.page.wait_for_selector(
                'button:has-text("Got it")',
                timeout=3000,
            )
            if got_it_button:
                logger.info("Dismissing 'Got it' popup")
                got_it_button.click()
                time.sleep(1)
        except PlaywrightTimeout:
            pass

        try:
            dismiss_button = self.page.wait_for_selector(
                'button[aria-label="Dismiss"]',
                timeout=3000,
            )
            if dismiss_button:
                logger.info("Dismissing popup")
                dismiss_button.click()
                time.sleep(1)
        except PlaywrightTimeout:
            pass

    def _turn_off_camera(self) -> None:
        """Turn off camera by clicking the camera toggle button."""
        self.page.wait_for_selector(
            'button[aria-label="Turn off camera"]',
            timeout=5000,
        )
        self.page.click('button[aria-label="Turn off camera"]')

    def _turn_off_mic(self) -> None:
        """Turn off microphone by clicking the mic toggle button."""
        self.page.wait_for_selector(
            'button[aria-label="Turn off microphone"]',
            timeout=5000,
        )
        self.page.click('button[aria-label="Turn off microphone"]')

    def _click_join_button(self) -> None:
        """Click the join button (handles both 'Join now' and 'Ask to join')."""
        time.sleep(2)

        join_selectors = [
            'button[aria-label="Join now"]',
            'button[aria-label="Ask to join"]',
            'button:has-text("Join now")',
            'button:has-text("Ask to join")',
            'button:has-text("Join")',
            'div[role="button"]:has-text("Join now")',
            'div[role="button"]:has-text("Join")',
            'span:has-text("Join now")',
            'span:has-text("Ask to join")',
        ]

        page_text = self.page.content()
        logger.debug(f"Page content preview: {page_text[:1000]}")

        for selector in join_selectors:
            try:
                logger.debug(f"Trying selector: {selector}")
                element = self.page.wait_for_selector(selector, timeout=5000)
                if element:
                    element.click()
                    logger.info(f"Clicked join button with selector: {selector}")
                    time.sleep(3)
                    return
            except PlaywrightTimeout:
                continue

        raise RuntimeError("Could not find join button")

    def save_session(self, path: str) -> None:
        """Save browser session state for reuse."""
        if self.context:
            self.context.storage_state(path=path)
            logger.info(f"Saved session to {path}")

    @staticmethod
    def create_signed_in_browser(headless: bool = False) -> "MeetBrowser":
        """Create a browser that you can use to sign in manually first."""
        browser = MeetBrowser(headless=headless)
        browser.__enter__()
        return browser

    def send_chat_message(self, message: str) -> bool:
        """
        Send a message to the meeting chat.

        Args:
            message: The message to send

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            self._open_chat_panel()
            time.sleep(2)

            chat_selectors = [
                'textarea[aria-label="Send a message to everyone"]',
                'textarea[aria-label="Chat, @mentions"]',
                'textarea[placeholder*="Send a message"]',
                'div[contenteditable="true"][role="textbox"]',
                'input[aria-label*="chat"]',
            ]

            chat_input = None
            for selector in chat_selectors:
                try:
                    chat_input = self.page.wait_for_selector(selector, timeout=3000)
                    if chat_input:
                        logger.debug(f"Found chat input with: {selector}")
                        break
                except PlaywrightTimeout:
                    continue

            if not chat_input:
                logger.error("Could not find chat input")
                return False

            chat_input.fill(message)
            time.sleep(0.5)

            chat_input.press("Enter")
            logger.info(f"Sent chat message: {message}")
            time.sleep(1)

            return True

        except Exception as e:
            logger.error(f"Failed to send chat message: {e}")
            return False

    def _open_chat_panel(self) -> None:
        """Open the chat panel if not already open."""
        chat_input_selectors = [
            'textarea[aria-label="Send a message to everyone"]',
            'textarea[aria-label="Chat, @mentions"]',
            'textarea[placeholder*="Send a message"]',
            'div[contenteditable="true"][role="textbox"]',
        ]
        
        for selector in chat_input_selectors:
            try:
                if self.page.wait_for_selector(selector, timeout=500):
                    logger.debug("Chat input already visible, panel is open")
                    return
            except PlaywrightTimeout:
                continue
        
        logger.debug("Looking for chat button...")
        chat_button_selectors = [
            'button[aria-label="Open chat"]',
            'button[aria-label="Chat"]',
            'button[aria-label="Show chat"]',
            'div[aria-label="Chat, press to open chat panel"]',
            'span:has-text("Chat")',
        ]

        for selector in chat_button_selectors:
            try:
                chat_button = self.page.wait_for_selector(selector, timeout=2000)
                if chat_button:
                    logger.debug(f"Found chat button with: {selector}")
                    chat_button.click()
                    time.sleep(1)
                    return
            except PlaywrightTimeout:
                continue
        
        logger.debug("No chat button found")

    def is_in_meeting(self) -> bool:
        """Check if still in the meeting."""
        try:
            page_url = self.page.url
            logger.debug(f"Current URL: {page_url}")
            
            if "meet.google.com" in page_url and "ended" not in page_url.lower():
                leave_selectors = [
                    '[aria-label="Leave the call"]',
                    '[aria-label="Leave call"]',
                    'button:has-text("Leave")]',
                ]
                
                for selector in leave_selectors:
                    try:
                        element = self.page.wait_for_selector(selector, timeout=1000)
                        if element:
                            return True
                    except PlaywrightTimeout:
                        continue
                
                return True
            
            if "left" in page_url.lower() or "ended" in page_url.lower():
                return False
            
            return False
        except Exception as e:
            logger.debug(f"Error checking meeting status: {e}")
            return False