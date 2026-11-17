"""Whether a test may be ordered for someone in a given place, by a given pathway.

Default deny. A request is allowed only when an explicit rule says so. No real rules ship with
this code: direct-access testing, clinician-order requirements and lab licensing differ by state
and must come from legal review of the actual partner and ordering arrangement. Until then every
real request is refused with a reason, which the website can show honestly.
"""

from dataclasses import dataclass

DIRECT_ACCESS = "direct_access"  # the person orders without a clinician, where the law allows it
CLINICIAN_ORDER = "clinician_order"  # a licensed clinician reviews and orders


@dataclass(frozen=True)
class Rule:
    state: str
    test_key: str
    pathway: str
    min_age: int = 18
    reviewed_by: str = ""  # who approved this rule (legal review); required
    synthetic: bool = False


@dataclass(frozen=True)
class Decision:
    allowed: bool
    pathway: str = ""
    reasons: tuple[str, ...] = ()


def decide(rules: list[Rule], *, state: str, test_key: str, age: int, partner_live: bool, allow_synthetic: bool = False) -> Decision:
    reasons = []
    if not partner_live:
        reasons.append("No lab partner is live for this test yet.")
    matches = [r for r in rules if r.state == state.upper() and r.test_key == test_key and (allow_synthetic or not r.synthetic)]
    approved = [r for r in matches if r.reviewed_by]
    if not matches:
        reasons.append("There is no approved ordering rule for this test in this state yet.")
    elif not approved:
        reasons.append("The ordering rule for this state has not been through legal review.")
    usable = [r for r in approved if age >= r.min_age]
    if approved and not usable:
        reasons.append("This test can't be ordered for this age through FollowThrough Health.")
    if reasons:
        return Decision(allowed=False, reasons=tuple(reasons))
    # Prefer a clinician-ordered pathway when both exist: it is the safer route.
    pathways = {r.pathway for r in usable}
    pathway = CLINICIAN_ORDER if CLINICIAN_ORDER in pathways else DIRECT_ACCESS
    return Decision(allowed=True, pathway=pathway)
