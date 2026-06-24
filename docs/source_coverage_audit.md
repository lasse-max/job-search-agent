# Stage 0 Source-Coverage Audit

Date: 2026-06-23

Scope: 91 companies from `Owner_Tracker.xlsx`, using the Company Watchlist sheet as the source of truth for tiers, locations, careers URLs, and role-family notes. Public feed probes checked Greenhouse, Lever, and Ashby endpoints only.

## Summary

- Supported public feed found: 44
- Needs configuration: 30
- Manual fallback: 17
- Unsupported: 0 explicitly marked; misses remain usable through manual URL/text intake unless the owner approves a custom exception.

## First Automated Coverage Candidates

These are the first Tier 1/2 companies selected for Stage 1 coverage because they have supported public feeds and strong priority signal.

| Company | Tier | ATS | Source key | Probe jobs | Why first |
|---|---:|---|---|---:|---|
| Databricks | 1 | greenhouse | databricks | 757 | Warm path and active Deployment Strategist roles. |
| OpenAI | 1 | ashby | openai | 709 | Top strategic company and clean S&O target lane. |
| Stripe | 1 | greenhouse | stripe | 496 | High-priority Tier 1/2 company with supported feed. |
| Airbnb | 1 | greenhouse | airbnb | 218 | High-priority Tier 1/2 company with supported feed. |
| Airwallex | 1 | ashby | airwallex | 582 | High-priority Tier 1/2 company with supported feed. |
| Sierra | 1 | ashby | sierra | 135 | High-priority Tier 1/2 company with supported feed. |
| Mistral AI | 1 | lever | mistral | 172 | Direct Lever source and active AI deployment roles. |
| Palantir | 1 | lever | palantir | 237 | High-priority Tier 1/2 company with supported feed. |
| Helsing | 1 | greenhouse | helsing | 132 | High-priority Tier 1/2 company with supported feed. |
| Anthropic | 1 | greenhouse | anthropic | 375 | High-priority Tier 1/2 company with supported feed. |
| Xero | 2 | ashby | xero | 104 | High-priority Tier 1/2 company with supported feed. |
| Spotify | 2 | lever | spotify | 134 | High-priority Tier 1/2 company with supported feed. |
| Checkout.com | 2 | ashby | checkout.com | 208 | Ashby source and explicit AI accelerator role in tracker. |
| Snowflake | 2 | ashby | snowflake | 413 | High-priority Tier 1/2 company with supported feed. |
| Harvey | 2 | ashby | harvey | 292 | High-priority Tier 1/2 company with supported feed. |

## Proposed First Vertical Slice

Recommended: Databricks via the Greenhouse feed (`source_key: databricks`). It is Tier 1, has a warm path in the tracker, and currently contains active Deployment Strategist roles in the target geographies. The one-source slice should fetch Databricks, normalize postings, deduplicate by source job ID plus canonical key, filter Sydney/London Deployment Strategist roles, persist to SQLite, run one structured evaluation, and write a local digest.

Backup if the large Databricks feed is noisy: Mistral AI via Lever (`source_key: mistral`), because the tracker already points directly at `jobs.lever.co/mistral` and the feed shape is simple.

## Full Matrix

| Company | Tier | Careers URL | ATS | Source key | Adapter supported | Status | Fallback |
|---|---:|---|---|---|---|---|---|
| Google | 1 | https://careers.google.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Databricks | 1 | https://www.databricks.com/company/careers | greenhouse | databricks | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| OpenAI | 1 | https://openai.com/careers/ | ashby | openai | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Stripe | 1 | https://stripe.com/jobs | greenhouse | stripe | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Airbnb | 1 | https://careers.airbnb.com/ | greenhouse | airbnb | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| DoorDash | 1 | https://careersatdoordash.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Uber | 1 | https://www.uber.com/global/en/careers/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Canva | 1 | https://www.lifeatcanva.com/en/jobs/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Atlassian | 1 | https://www.atlassian.com/company/careers | lever | atlassian | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Airwallex | 1 | https://careers.airwallex.com/ | ashby | airwallex | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Sierra | 1 | https://sierra.ai/careers | ashby | sierra | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Mistral AI | 1 | https://jobs.lever.co/mistral | lever | mistral | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Palantir | 1 | https://www.palantir.com/careers/ | lever | palantir | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Amazon / AWS | 1 | https://www.amazon.jobs/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Apple | 1 | https://jobs.apple.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Netflix | 1 | https://jobs.netflix.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| SafetyCulture | 1 | https://safetyculture.com/careers/ | ashby | safetyculture | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| NEURA Robotics | 1 | https://jobs.neura-robotics.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Helsing | 1 | https://helsing.ai/careers | greenhouse | helsing | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Anthropic | 1 | https://www.anthropic.com/careers | greenhouse | anthropic | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Xero | 2 | https://careers.xero.com/ | ashby | xero | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Rokt | 2 | https://www.rokt.com/company/careers | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Wise | 2 | https://wise.jobs/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Spotify | 2 | https://www.lifeatspotify.com/jobs | lever | spotify | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Checkout.com | 2 | https://jobs.ashbyhq.com/checkout.com | ashby | checkout.com | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Grab | 2 | https://www.grab.careers/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Salesforce | 2 | https://careers.salesforce.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Snowflake | 2 | https://careers.snowflake.com/ | ashby | snowflake | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| ServiceNow / Moveworks | 2 | https://careers.servicenow.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Meta | 2 | https://www.metacareers.com/jobs/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Microsoft | 2 | https://jobs.careers.microsoft.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| LinkedIn | 2 | https://careers.linkedin.com/ | lever | linkedin | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Disney | 2 | https://jobs.disneycareers.com/ | greenhouse | disney | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| OutSystems | 2 | https://www.outsystems.com/careers/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Celonis | 2 | https://careers.celonis.com/ | greenhouse | celonis | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Harvey | 2 | https://www.harvey.ai/careers | ashby | harvey | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Glean | 2 | https://www.glean.com/careers | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Cohere | 2 | https://cohere.com/careers | ashby | cohere | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| ElevenLabs | 2 | https://elevenlabs.io/careers | ashby | elevenlabs | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Pigment | 2 | https://www.pigment.com/careers | lever | pigment | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Personio | 2 | https://www.personio.com/careers/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| N26 | 2 | https://n26.com/en-eu/careers | greenhouse | n26 | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| TikTok | 2 | https://careers.tiktok.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Booking.com | 2 | https://careers.booking.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Deliveroo | 2 | https://careers.deliveroo.co.uk/ | ashby | deliveroo | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Block | 2 | https://block.xyz/careers | greenhouse | block | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| DeepL | 2 | https://www.deepl.com/en/jobs | ashby | deepl | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Parloa | 2 | https://www.parloa.com/careers | greenhouse | parloa | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| SAP | 2 | https://jobs.sap.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Expedia Group | 2 | https://careers.expediagroup.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Adobe | 2 | https://careers.adobe.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Visa | 2 | https://corporate.visa.com/en/jobs/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Mastercard | 2 | https://careers.mastercard.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Revolut | 2 | https://www.revolut.com/careers/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Vercel | 2 | https://vercel.com/careers | ashby | vercel | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Quantexa | 2 | https://www.quantexa.com/careers/ | ashby | quantexa | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Synthesia | 2 | https://www.synthesia.io/careers | ashby | synthesia | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Encord | 2 | https://encord.com/careers/ | ashby | encord | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Lovable | 2 | https://lovable.dev/careers | ashby | lovable | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Magentic | 2 | https://www.magentic.ai/careers | ashby | magentic | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Aleph Alpha | 2 | https://aleph-alpha.com/careers/ | ashby | alephalpha | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Decagon | 2 | https://jobs.ashbyhq.com/decagon | ashby | decagon | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Cognition | 2 | https://cognition.ai/careers | ashby | cognition | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Fortescue | 2 | https://careers.fortescue.com/ | unknown |  | no | Needs configuration | Confirm ATS/source key, then use manual URL/text intake until configured. |
| Zendesk | 3 | https://jobs.zendesk.com/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Deputy | 3 | https://www.deputy.com/careers | lever | deputy | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Culture Amp | 3 | https://www.cultureamp.com/careers | greenhouse | cultureamp | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Harrison.ai | 3 | https://harrison.ai/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Quantium | 3 | https://www.quantium.com/careers/ | greenhouse | quantium | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Nearmap | 3 | https://www.nearmap.com/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Macquarie Group | 3 | https://www.macquarie.com/au/en/careers.html | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Woodside Energy | 3 | https://www.woodside.com/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| BHP | 3 | https://www.bhp.com/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Rio Tinto | 3 | https://www.riotinto.com/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Wesfarmers | 3 | https://www.wesfarmers.com.au/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Klarna | 3 | https://www.klarna.com/careers/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Zalando | 3 | https://jobs.zalando.com/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Trade Republic | 3 | https://traderepublic.com/careers | greenhouse | traderepublic | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Delivery Hero | 3 | https://careers.deliveryhero.com/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| HelloFresh | 3 | https://careers.hellofresh.com/ | greenhouse | hellofresh | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Flix | 3 | https://flix.careers/ | greenhouse | flix | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Skyscanner | 3 | https://www.skyscanner.net/jobs | ashby | skyscanner | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Plaid | 3 | https://plaid.com/careers/ | ashby | plaid | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| Waymo | 3 | https://waymo.com/joinus/ | greenhouse | waymo | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| X, the Moonshot Factory | 3 | https://x.company/careers/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Noah Labs | 3 | https://www.noah-labs.com/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Roblox | 3 | https://careers.roblox.com/ | greenhouse | roblox | yes | Supported | Manual URL/text intake if feed fails or a role is missing from the feed. |
| BCG / BCG X | 3 | https://careers.bcg.com/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| McKinsey / QuantumBlack | 3 | https://www.mckinsey.com/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Bain / Vector | 3 | https://www.bain.com/careers/ | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
| Accenture | 3 | https://www.accenture.com/us-en/careers | unknown |  | no | Manual fallback | Manual careers-page check plus add-url/add-text intake; no Stage 1 adapter selected. |
