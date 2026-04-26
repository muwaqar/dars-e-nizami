import logging
import sys
import time
from pathlib import Path

from config import parse_args, extract_meeting_code, Config
from auth import get_credentials
from meet_client import MeetClient
from browser import MeetBrowser


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_space_name(meet_client: MeetClient, meeting_code: str) -> str:
    """Get the space name from meeting code."""
    logger.info(f"Getting space info for meeting code: {meeting_code}")
    space = meet_client.get_space(meeting_code)
    space_name = space.get("name")
    logger.info(f"Space name: {space_name}")
    return space_name


def create_session(session_path: Path) -> None:
    """Create a browser session by having user log in."""
    logger.info("Creating new browser session...")
    logger.info("Opening browser for login - please sign into your Google account")
    
    with MeetBrowser(headless=False, strict_media=False) as browser:
        browser.page.goto("https://meet.google.com/")
        logger.info("Please sign into your Google account in the browser window")
        logger.info("Press Enter when done...")
        input()
        
        browser.save_session(str(session_path))
        logger.info(f"Session saved to {session_path}")


def wait_for_conference_start(
    meet_client: MeetClient,
    space_name: str,
    timeout: int = 120,
) -> str:
    """Wait for a conference to start and return the conference name."""
    logger.info("Waiting for conference to start...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        conference = meet_client.get_conference_record_by_space(space_name)
        if conference:
            logger.info(f"Conference started: {conference.name}")
            return conference.name
        time.sleep(2)
    
    raise TimeoutError("Conference did not start within timeout")


def poll_participants(
    meet_client: MeetClient,
    conference_name: str,
    known_participants: set[str],
    poll_interval: int,
) -> tuple[set[str], list[str]]:
    """
    Poll for new participant sessions.
    Uses sessions so same user joining from different device is detected as new.
    
    Returns:
        Tuple of (updated session set, list of new session IDs)
    """
    logger.info("Calling API to get participant sessions...")
    current_participants = meet_client.get_all_participant_session_ids(conference_name)
    logger.info(f"Got sessions: {current_participants}")
    
    new_participants = current_participants - known_participants
    
    if new_participants:
        logger.info(f"New sessions detected: {new_participants}")
        return current_participants, list(new_participants)
    
    return current_participants, []


def run_bot(config: Config) -> None:
    """Main bot execution."""
    if not config.debug:
        logging.getLogger().setLevel(logging.INFO)
    
    logger.info("Starting Google Meet Bot")
    logger.info(f"Meeting link: {config.meet_link}")
    logger.info(f"Welcome message: {config.message}")
    logger.info(f"Poll interval: {config.poll_interval}s")
    logger.info(f"Headless: {config.headless}")
    logger.info(f"Strict media: {config.strict_media}")
    logger.info(f"Debug: {config.debug}")
    logger.info(f"Session: {config.session_path}")
    logger.info(f"New session: {config.new_session}")
    
    needs_session = config.new_session or not config.session_path.exists()
    if needs_session:
        if config.new_session and config.session_path.exists():
            logger.info("--new-session specified, removing old session file")
        create_session(config.session_path)

    meeting_code = extract_meeting_code(config.meet_link)
    
    logger.info("Authenticating with Google...")
    credentials = get_credentials(
        token_path=config.token_path,
        client_secret_path=config.client_secret_path,
    )
    
    meet_client = MeetClient(credentials)
    space_name = get_space_name(meet_client, meeting_code)
    
    logger.info("Launching browser...")
    with MeetBrowser(
        headless=config.headless,
        storage_state=str(config.session_path) if config.session_path else None,
        strict_media=config.strict_media,
        debug=config.debug,
    ) as browser:
        browser.join_meeting(config.meet_link)
        
        logger.info("Waiting for conference to be detected...")
        time.sleep(5)
        
        conference_name = wait_for_conference_start(meet_client, space_name, timeout=60)
        
        initial_participants = meet_client.get_all_participant_session_ids(conference_name)
        logger.info(f"Initial sessions: {initial_participants}")
        known_participants = initial_participants.copy()
        
        logger.info("Sending initial welcome message...")
        browser.send_chat_message(config.message)
        
        logger.info(f"Starting polling loop (interval: {config.poll_interval}s)")
        
        while True:
            try:
                logger.info("Polling for participants...")
                current_participants, new_participant_ids = poll_participants(
                    meet_client,
                    conference_name,
                    known_participants,
                    config.poll_interval,
                )
                
                logger.info(f"Current: {current_participants}, Known: {known_participants}, New: {new_participant_ids}")
                
                if new_participant_ids:
                    participants = meet_client.list_participants(conference_name)
                    participant_map = {p.name: p for p in participants}
                    
                    for session_id in new_participant_ids:
                        display_name = "Someone"
                        
                        if "/participantSessions/" in session_id:
                            parts = session_id.split("/participantSessions/")
                            participant_id = parts[0]
                            participant = participant_map.get(participant_id)
                            if participant:
                                display_name = participant.display_name
                        
                        logger.info(f"New joiner detected: {display_name}")
                        
                        message = f"{config.message} Welcome {display_name}!"
                        
                        success = browser.send_chat_message(message)
                        if success:
                            logger.info(f"Sent welcome message to {display_name}")
                        else:
                            logger.warning(f"Failed to send message to {display_name}")
                    
                    known_participants = current_participants
                
                logger.info("Checking if still in meeting...")
                in_meeting = browser.is_in_meeting()
                logger.info(f"In meeting: {in_meeting}")
                
                if not in_meeting:
                    logger.info("Bot has left the meeting")
                    break
                    
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                logger.info("Continuing after error...")
            
            logger.info(f"Sleeping for {config.poll_interval}s...")
            time.sleep(config.poll_interval)
            logger.info("Woke up, starting next poll...")
    
    logger.info("Bot stopped")


def main() -> None:
    """Entry point."""
    config = parse_args()
    
    try:
        run_bot(config)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()