# Billing architecture: one account, three stores

Last updated: 2026-10-23. Status: **foundation built; no live charges.** Prices in this document are
proposals to test, not approved offers. Nothing here turns on billing, charges anyone, or publishes a
paid plan. Each of those needs the owner's approval.

## 1. Audit of what existed (before this change)

| Area | What was there | Gap found |
|---|---|---|
| Plans | `SUBSCRIPTION_PLANS` in `app/api/routes/subscriptions.py`: Free, Plus $7, Family $12 | Prices are placeholders; the owner is considering $6.99 / $11.99 (not changed) |
| Website checkout | Stripe Checkout session from `/subscriptions/checkout`; the site only redirects to `checkout.stripe.com`. With no Stripe key it says "payments open soon" | A person could start a second paid plan while one was active → **fixed: 409** |
| Stripe webhook | Signature checked (HMAC, 5-minute tolerance); handled `checkout.session.completed`, `invoice.payment_failed`, `customer.subscription.deleted` | Retried events were re-applied, so an old failure could undo a later payment → **fixed: events recorded once**. Renewals and recovered payments never set the plan back to active → **fixed**. `customer.subscription.updated` was ignored → **fixed**. Newer Stripe API invoices nest the subscription id → **handled** |
| Entitlements | `/subscriptions/me` returns the latest current row | No shared "which features" answer, no expiry for store plans → **added** |
| Feature locks | None. Every feature is free everywhere | Paid plans currently unlock nothing (owner decision) |
| Phone app | Sells nothing since carewise-mobile-app PR #44 | Needs StoreKit / Play Billing before selling in the app |
| Card data | Never touches our servers (Stripe-hosted checkout) | ✅ |
| Health data in billing | Billing rows hold plan, status and provider ids only; audit details hold plan and event type | ✅ |

## 2. Design

```
               one FollowThrough account (email login)
                              │
     ┌────────────────────────┼─────────────────────────┐
  Website (Stripe)     iPhone (StoreKit)      Android (Play Billing)     Clinics (Stripe invoices)
     │ webhook                │ App Store Server        │ Real-time developer     │ admin/contract
     │                        │ Notifications V2        │ notifications            │
     └──────────────┬─────────┴────────────┬────────────┴────────────┬──────────┘
                    ▼                      ▼                         ▼
          subscriptions table (one row per purchase, payment_provider = stripe|apple|google|organization)
                    │  status, plan_code, provider_reference, expires_at
                    ▼
          app/services/entitlements.py → GET /subscriptions/entitlements
                    ▼
          the same features on web, iPhone and Android
```

- **One entitlement answer.** `entitlements_for()` takes the highest current plan from any provider.
  "Current" means status `active` or `past_due` (grace period) and not past `expires_at`.
- **Always free.** `ALWAYS_FREE` covers report explanations, doctor brief, safety messages, health record
  and appointment questions. Tests fail if a paid plan ever lists one of these.
- **Locks are off.** `CAREWISE_ENTITLEMENT_ENFORCEMENT` defaults to false, so every account gets every
  feature. Turning it on is a pricing decision; it then needs the website and app to check
  `has_feature()` (not yet wired to any screen).
- **Idempotent events.** `billing_events` stores (provider, event id) with a unique constraint. A repeat,
  or two deliveries racing each other, is acknowledged without changing anything.
- **One paid plan per account.** Checkout returns 409 if a paid plan is current. Upgrades and downgrades
  go through Stripe's billing page once it is configured to allow plan switching. Until then the
  website shows a generic "Checkout could not open" message for a second plan. Showing the 409 message
  is part of PR 1 below.
- **Secrets stay server-side.** Stripe keys (and later Apple/Google keys) live only in Render
  environment variables.

## 3. Still to build (proposed PRs, in order)

1. **Website subscription page polish:** show plan source and renewal or expiry date from
   `/subscriptions/entitlements`; "Manage plan" opens the Stripe billing page only for Stripe plans, and
   tells Apple/Google subscribers to manage the plan in their phone's settings.
2. **Apple (StoreKit 2):** `POST /subscriptions/apple/verify` takes the signed transaction from the app,
   verifies the JWS chain against Apple's root certificate, and creates or updates a row with
   `payment_provider=apple`, `provider_reference=originalTransactionId`, `expires_at`. Add an
   App Store Server Notifications V2 endpoint for renewals, refunds (`REFUND`) and expiry. Pass
   `appAccountToken` (our user id as a UUID) so purchases attach to the right account.
3. **Google (Play Billing 7+):** `POST /subscriptions/google/verify` takes the purchase token and checks it
   with the Play Developer API (`purchases.subscriptionsv2.get`) using a service account. Acknowledge
   the purchase within 3 days. Add a Pub/Sub real-time developer notification endpoint.
4. **Mobile:** use `react-native-iap` or RevenueCat. RevenueCat's webhooks can feed the same
   `subscriptions` table and save building parts 2 and 3. Add Restore purchases.
5. **Clinics (DocBridge):** Stripe invoices or subscriptions per clinic, with `payment_provider=organization`
   on clinic members or a clinic-level entitlement. Only after clinical, legal and security sign-off,
   and BAAs where real patient data is involved.
6. **Sandbox tests:** Stripe test mode (`stripe trigger`), StoreKit testing in Xcode and TestFlight, Play
   license testers. These need the owner's accounts.

## 4. Store policy checklist (check current rules before each release)

- [ ] Apple 3.1.1: digital subscriptions bought **in** the iPhone app use In-App Purchase. Apple
      3.1.3(b) multiplatform: a plan bought on the web may unlock the same features in the app, as
      long as in-app purchase is offered too when the app sells it.
- [ ] US storefront: court rulings have allowed link-outs to web purchase. These rules have been
      changing, so confirm the current guideline text before adding any link.
- [ ] Google Play Payments policy: Play Billing for digital goods in the app, except the programmes
      Google publishes (for example user-choice or alternative billing, by region).
- [ ] No feature that's important to safety or understanding is paywalled (`ALWAYS_FREE`).
- [ ] Account deletion explains how to cancel a store subscription (Apple 5.1.1(v)).
- [ ] No health-data-based advertising and no sale of health data.

## 5. Owner setup steps (cannot be done from code)

1. Stripe: create the account, products and prices (test mode first). Set `CAREWISE_STRIPE_SECRET_KEY`
   and `CAREWISE_STRIPE_WEBHOOK_SECRET` in Render. Point the webhook at
   `https://carewise-api.onrender.com/subscriptions/webhook` with these events: `checkout.session.completed`,
   `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`,
   `customer.subscription.deleted`.
2. Apple: Developer Program, then in App Store Connect create a subscription group with Plus and Family
   auto-renewable subscriptions; set up an App Store Server API key; sign the Paid Apps agreement;
   enrol in the Small Business Program (15% fee).
3. Google: Play Console, subscriptions with base plans, a service account with financial-data access,
   Pub/Sub topic for notifications, payments profile.
4. Decide what Plus and Family unlock, and approve final prices.
