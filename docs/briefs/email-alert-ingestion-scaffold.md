# B-14: Dedicated Alerts Mailbox Scaffold

Status: **owner setup pending; no live integration shipped**.

The mailbox has not been confirmed in this task. Do not use the owner's personal
inbox, do not request Gmail write scopes, and do not count this scaffold as company
coverage. No OAuth flow, credentials, scheduler wiring, production format parser,
database migration or email content is included.

`app/services/email_alerts.py` defines a read-only mailbox boundary, parser contract
and candidate shape. The collector refuses to read messages without explicit
dedicated-account confirmation and checks the actual account ID before reading.
Synthetic unit tests check setup/mismatch rejection, parser errors and unsafe URLs.
This is contract scaffolding only, not a parser validated against real alerts.

## Owner Boundary (2026-09-21)

The alerts pipeline has two addresses: an owner-managed domain forwarder feeds a
dedicated Gmail inbox. B-14 integrates with the Gmail inbox only. The domain
forwarder is never accessible to application code; do not integrate with or manage
it. The subscription address is reference-only and must not appear in code.

Read the dedicated inbox address from the `ALERTS_INBOX_EMAIL` secret, with no
hardcoded address or fallback. Request only `gmail.readonly` Gmail access and bind
it to that dedicated account. This is inbound-only: never send, reply, delete or
modify messages. Ignore the Spam folder by design, including during sample
collection and parser validation.

**Parser work is held until the owner confirms 20-30 real alerts have accumulated
in the dedicated Gmail inbox.** Do not infer that readiness from mailbox setup or
write a production parser against assumed formats. Keep real addresses, email
bodies and OAuth tokens out of the repository and logs.

## Owner Prerequisite

Set up the domain forwarder and dedicated Gmail inbox outside the application.
Subscribe to Google, Apple, Amazon, Uber, Netflix and Atlassian career alerts using
the reference-only subscription address. Confirm the dedicated account and that
20-30 real non-Spam alerts have accumulated, then provide sanitized sample formats
privately. Never grant this agent personal-inbox or forwarder access.

## Next Implementation Slice

1. Bind `gmail.readonly` access to the dedicated account specified by the
   `ALERTS_INBOX_EMAIL` secret and verify identity; exclude Spam explicitly.
2. Only after the owner's 20-30-alert confirmation, build format-specific MIME/HTML
   parsers against sanitized examples of those alerts. Preserve
   source provenance, ignore unsubscribe/tracking links, and fail loudly for
   unsupported formats. No LinkedIn scraping.
3. Resolve public job URLs through the existing URL/text intake path. Use the same
   normalization, material deduplication, recency gate and evaluator; email is
   discovery provenance, not a second scorer. Extraction failures request JD text.
4. Add durable per-message/link receipts and retries before scheduling. Unknown
   senders, spoofed metadata, changed formats and repeated alerts need tests.
5. Review privacy, owner gating and end-to-end replay with Cato before activation.
