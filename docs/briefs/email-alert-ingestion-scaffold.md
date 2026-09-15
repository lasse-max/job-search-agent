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

## Owner Prerequisite

Create a separate mailbox used only for job alerts. Subscribe to Google, Apple,
Amazon, Uber, Netflix and Atlassian career alerts. Forward account-bound alerts
there if needed; do not grant this agent personal-inbox access. Let representative
alerts accumulate, then confirm the dedicated account and provide sanitized sample
formats privately. Never commit real email bodies, addresses or OAuth tokens.

## Next Implementation Slice

1. Bind read-only access to the confirmed dedicated account and verify identity.
2. Build format-specific MIME/HTML parsers against sanitized examples. Preserve
   source provenance, ignore unsubscribe/tracking links, and fail loudly for
   unsupported formats. No LinkedIn scraping.
3. Resolve public job URLs through the existing URL/text intake path. Use the same
   normalization, material deduplication, recency gate and evaluator; email is
   discovery provenance, not a second scorer. Extraction failures request JD text.
4. Add durable per-message/link receipts and retries before scheduling. Unknown
   senders, spoofed metadata, changed formats and repeated alerts need tests.
5. Review privacy, owner gating and end-to-end replay with Cato before activation.
