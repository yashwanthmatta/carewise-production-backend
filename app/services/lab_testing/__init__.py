"""Lab testing foundation (stage 1 of docs/lab-testing-architecture.md).

Code only: no database tables, no partner connections, no payments, no orders leave this service.
Everything here runs on synthetic data until the owner approves a lab partner, an ordering
clinician arrangement, legal review and a production migration.

LIVE is a code constant, not an environment setting, so lab testing cannot be switched on by
changing configuration: turning it on needs a reviewed code change.
"""

LIVE = False
