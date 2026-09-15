"""B-14 contracts only: no mailbox connector, format parser, or persistence yet."""

from dataclasses import dataclass
from typing import Iterable, Protocol
from urllib.parse import urlsplit


class EmailAlertSetupRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class AlertMessage:
    message_id: str
    body: str


@dataclass(frozen=True)
class AlertCandidate:
    company: str
    title: str
    location: str
    source_url: str
    message_id: str


class ReadOnlyAlertsMailbox(Protocol):
    def account_id(self) -> str: ...

    def messages(self) -> Iterable[AlertMessage]: ...


class JobAlertParser(Protocol):
    def parse(self, message: AlertMessage) -> list[AlertCandidate]:
        """Raise on unknown/malformed alert formats; never silently drop an alert."""
        ...


def collect_alert_candidates(
    mailbox: ReadOnlyAlertsMailbox,
    parser: JobAlertParser,
    *,
    expected_account_id: str | None = None,
    owner_confirmed_dedicated: bool = False,
) -> list[AlertCandidate]:
    """Testable boundary for future dedicated-mailbox discovery, not live ingestion.

    No implementation of either protocol is shipped in this slice. Candidates
    still need the existing intake normalization/gates/evaluator before storage.
    """
    if not owner_confirmed_dedicated or not expected_account_id:
        raise EmailAlertSetupRequired("Dedicated alerts mailbox requires owner setup and approval.")
    if mailbox.account_id() != expected_account_id:
        raise EmailAlertSetupRequired("Connected account is not the approved alerts mailbox.")
    candidates: list[AlertCandidate] = []
    for message in mailbox.messages():
        for candidate in parser.parse(message):
            url = urlsplit(candidate.source_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or not candidate.company.strip()
                or not candidate.title.strip()
                or candidate.message_id != message.message_id
            ):
                raise ValueError("Invalid parsed job-alert candidate; intake was not performed.")
            candidates.append(candidate)
    return candidates
