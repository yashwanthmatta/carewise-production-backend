# Before real patient data: Business Associate Agreements (BAAs)

DocBridge stays pilot-only (de-identified or sample labs) until every service that
could touch patient health information has a signed BAA, or is switched off or
replaced. Confirm each vendor's current terms and plan requirements yourself; they
change, and this list is a starting point, not legal advice.

| Service | What it touches | What to do |
|---|---|---|
| Render (API + Postgres) | Every stored lab, summary and question | Ask Render about its HIPAA option and which plan it needs; move the API and database there, or to a host that signs a BAA. |
| Anthropic (help chat, patient questions) | Questions and approved summaries sent to the model | Ask Anthropic sales for a BAA covering API use (usually with zero data retention). Until then keep patient questions off. |
| Cloudflare Email Routing (lab intake) | Forwarded lab PDFs | Not for real patient data. Switch intake to Amazon SES (AWS signs a BAA); the API already accepts SES via SNS. |
| Google Workspace (founder email) | Any patient email that reaches the inbox | Sign Google's BAA in the Admin console and use only covered services. |
| Twilio (reminder calls) | Phone numbers and medicine names in calls | Twilio offers a BAA on eligible plans; sign it before calling real patients. |
| OpenAI (server-side photo reading, if the key is set) | Images of reports | Leave the key unset (photos are read on the device), or get a BAA first. |
| Stripe (billing) | Names and payment only, no health data | No BAA needed if no health information is sent to it. |

Also before real data:
- A written privacy and security policy, an incident-response plan, and a designated privacy officer (the founder, at first).
- Clinic-side agreement: each clinic signs a BAA with FollowThrough Health.
- A lawyer reviews all of the above.
