from dataclasses import dataclass
from typing import Optional
from google.auth.transport.requests import AuthorizedSession
from google.auth.credentials import Credentials


MEET_API_BASE = "https://meet.googleapis.com/v2"


@dataclass
class Participant:
    """Represents a participant in a Google Meet."""
    name: str
    display_name: str
    email: Optional[str] = None
    joined_time: Optional[str] = None
    ended_time: Optional[str] = None


@dataclass
class ConferenceRecord:
    """Represents a conference record."""
    name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class MeetClient:
    """Client for Google Meet REST API."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._session = AuthorizedSession(credentials)

    def get_space(self, meeting_code: str) -> dict:
        """
        Get meeting space info by meeting code.

        Args:
            meeting_code: The 10-character meeting code (e.g., 'abc-mnop-xyz')

        Returns:
            Space resource dict
        """
        response = self._session.get(f"{MEET_API_BASE}/spaces/{meeting_code}")
        response.raise_for_status()
        return response.json()

    def list_conferences(self, space_name: str) -> list[ConferenceRecord]:
        """
        List conference records for a space.

        Args:
            space_name: The space name (e.g., 'spaces/abc123')

        Returns:
            List of ConferenceRecord objects
        """
        response = self._session.get(
            f"{MEET_API_BASE}/spaces/{space_name.split('/')[-1]}/conferences"
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()

        conferences = []
        for conf in data.get("conferences", []):
            conferences.append(ConferenceRecord(
                name=conf.get("name"),
                start_time=conf.get("startTime"),
                end_time=conf.get("endTime"),
            ))
        return conferences

    def list_conference_records(self) -> list[ConferenceRecord]:
        """List all conference records the user has access to."""
        response = self._session.get(f"{MEET_API_BASE}/conferenceRecords")
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()

        conferences = []
        for conf in data.get("conferenceRecords", []):
            conferences.append(ConferenceRecord(
                name=conf.get("name"),
                start_time=conf.get("startTime"),
                end_time=conf.get("endTime"),
            ))
        return conferences

    def get_conference_record_by_space(self, space_name: str) -> Optional[ConferenceRecord]:
        """Get active conference record for a space from conferenceRecords list."""
        all_conferences = self.list_conference_records()

        for conf in all_conferences:
            if conf.start_time and not conf.end_time:
                return conf
        return None

    def get_active_conference(self, space_name: str) -> Optional[ConferenceRecord]:
        """
        Get the currently active conference for a space.

        Args:
            space_name: The space name

        Returns:
            ConferenceRecord if active conference exists, None otherwise
        """
        conferences = self.list_conferences(space_name)
        for conf in conferences:
            if conf.start_time and not conf.end_time:
                return conf
        return None

    def list_participants(self, conference_name: str) -> list[Participant]:
        """
        List participants in a conference.

        Args:
            conference_name: The conference name (e.g., 'conferenceRecords/abc123')

        Returns:
            List of Participant objects
        """
        import logging
        logger = logging.getLogger(__name__)

        response = self._session.get(
            f"{MEET_API_BASE}/{conference_name}/participants"
        )
        logger.info(f"participants API status: {response.status_code}")
        if response.status_code == 200:
            logger.info(f"participants API response: {response.text[:500]}")
        response.raise_for_status()
        data = response.json()

        participants = []
        for p in data.get("participants", []):
            display = p.get("signedinUser", {}).get("displayName") or p.get("displayName") or p.get("anonymousUser", {}).get("displayName") or "Unknown"
            participant = Participant(
                name=p.get("name", ""),
                display_name=display,
                email=p.get("signedinUser", {}).get("email") if p.get("signedinUser") else None,
                joined_time=p.get("earliestStartTime"),
                ended_time=p.get("latestEndTime"),
            )
            if not participant.email:
                participant.email = p.get("anonymousUser", {}).get("displayName")
            participants.append(participant)

        return participants

    def get_participant_count(self, conference_name: str) -> int:
        """Get count of active (joined, not left) participants."""
        participants = self.list_participants(conference_name)
        return len([p for p in participants if p.name])

    def get_participant_ids(self, conference_name: str) -> set[str]:
        """Get set of participant IDs currently in the conference."""
        participants = self.list_participants(conference_name)
        return {p.name for p in participants if p.name and not p.ended_time}

    def get_all_participant_ids(self, conference_name: str) -> set[str]:
        """Get set of all participant IDs who've ever joined (including left)."""
        participants = self.list_participants(conference_name)
        return {p.name for p in participants if p.name}

    def list_participant_sessions(self, conference_name: str) -> list[dict]:
        """List all participant sessions for each participant in the conference."""
        import logging
        logger = logging.getLogger(__name__)

        all_sessions = []

        participants = self.list_participants(conference_name)

        for participant in participants:
            parts = participant.name.split("/participants/")
            if len(parts) < 2:
                continue

            participant_id = parts[1]
            parent = f"{conference_name}/participants/{participant_id}"

            response = self._session.get(
                f"{MEET_API_BASE}/{parent}/participantSessions"
            )

            if response.status_code == 200:
                data = response.json()
                sessions = data.get("participantSessions", [])
                for s in sessions:
                    s["participant_name"] = participant.name
                    s["display_name"] = participant.display_name
                all_sessions.extend(sessions)
                logger.info(f"Sessions for {participant.display_name}: {len(sessions)}")

        return all_sessions

    def get_all_participant_session_ids(self, conference_name: str) -> set[str]:
        """Get ALL participant session IDs (including ended sessions)."""
        sessions = self.list_participant_sessions(conference_name)
        return {s.get("name") for s in sessions if s.get("name")}

    def get_active_participant_session_ids(self, conference_name: str) -> set[str]:
        """Get set of active participant session IDs (unique device/session)."""
        sessions = self.list_participant_sessions(conference_name)
        active_sessions = [
            s.get("name") for s in sessions
            if s.get("startTime") and not s.get("endTime")
        ]
        return set(active_sessions)
