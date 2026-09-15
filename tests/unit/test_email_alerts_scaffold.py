from dataclasses import replace
from unittest.mock import Mock
import unittest

from app.services.email_alerts import (
    AlertCandidate,
    AlertMessage,
    EmailAlertSetupRequired,
    collect_alert_candidates,
)


class EmailAlertScaffoldTest(unittest.TestCase):
    def test_unconfigured_and_wrong_mailboxes_never_read_messages(self) -> None:
        mailbox, parser = Mock(), Mock()
        with self.assertRaises(EmailAlertSetupRequired):
            collect_alert_candidates(mailbox, parser)
        mailbox.account_id.assert_not_called()
        mailbox.account_id.return_value = "different-account"
        with self.assertRaises(EmailAlertSetupRequired):
            collect_alert_candidates(mailbox, parser, expected_account_id="approved-account",
                                     owner_confirmed_dedicated=True)
        mailbox.messages.assert_not_called()
        parser.parse.assert_not_called()

    def test_synthetic_contract_and_fail_loud_parser(self) -> None:
        mailbox, parser = Mock(), Mock()
        mailbox.account_id.return_value = "approved-account"
        message = AlertMessage("synthetic-1", "Synthetic job alert; no real email content.")
        mailbox.messages.return_value = [message]
        candidate = AlertCandidate("ExampleCo", "Program Manager", "London",
                                   "https://example.com/job", message.message_id)
        parser.parse.return_value = [candidate]
        kwargs = {"expected_account_id": "approved-account", "owner_confirmed_dedicated": True}
        self.assertEqual(collect_alert_candidates(mailbox, parser, **kwargs), [candidate])
        parser.parse.side_effect = ValueError("unsupported alert format")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            collect_alert_candidates(mailbox, parser, **kwargs)
        parser.parse.side_effect = None
        for url in ("javascript:alert(1)", "file:///private/example", "https://user:pass@example.com"):
            parser.parse.return_value = [replace(candidate, source_url=url)]
            with self.assertRaises(ValueError):
                collect_alert_candidates(mailbox, parser, **kwargs)
