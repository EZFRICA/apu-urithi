"""The meter: no costly call runs without a budget granted to it (docs/decisions/0007).

    grant = meter().grant(capability, estimate)    # refuses plainly, or grants
    result = call(...)
    meter().record(grant, actual)                    # what it really cost

Who is spending is the person a request acts as, in the organisation they act in, set once
per request (`acting_as`) by the side that identified them; a call with nobody acting (a
script, the server starting) is the platform's own and counts against the platform alone.

Counted, each against a quota per organisation, role and period with a warning level and a
stop level: questions to the tutor, characters read aloud, seconds transcribed, illustrations,
source checks, bytes deposited. Model cost, in the currency of the price table, against four
ceilings: one request, one person in a day, one organisation in a month, the platform in a day.
The policy is data (registries/policy.json): set by the platform, and an organisation may only
narrow it, never widen it.

Nearing a ceiling the service steps down rather than stops; `level()` says how near, and the
caller chooses its step (learner.tutor.answer). Never counted: a reply to distress, which never
reaches a costly call, and anything served from an offline package, which never reaches the
server. A refusal names the person's own limit, never another person's or organisation's usage.

The counts themselves live in a store (exchange/counters.py, wired by server.py): this module
holds the rules and no data.
"""

import contextvars
import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from apu import config
from apu.logger import get_logger

logger = get_logger(__name__)

CAPABILITIES = ("questions", "speech_chars", "transcribed_seconds", "illustrations",
                "source_checks", "deposited_bytes", "model_cost")
PLATFORM = "platform"


@dataclass(frozen=True)
class Principal:
    """Who is spending: a person in an organisation, with their role there; or the platform."""

    organisation: str
    person_id: str
    role: str


PLATFORM_PRINCIPAL = Principal(PLATFORM, "", "system")


class Refused(PermissionError):
    """No budget: said plainly, in the person's own terms."""

    def __init__(self, capability: str, reason: str):
        super().__init__(reason)
        self.capability = capability
        self.reason = reason


@dataclass(frozen=True)
class Grant:
    grant_id: str
    principal: Principal
    capability: str
    estimate: float
    warning: str = ""      # set when a warning level is crossed: the caller may say it


class Counters(Protocol):
    def add(self, organisation: str, person_id: str, role: str, capability: str, amount: float,
            at: datetime) -> None: ...
    def total(self, capability: str, *, since: datetime, organisation: str | None = None,
              person_id: str | None = None) -> float: ...


# ── who is acting, per request ────────────────────────────────────────────────

_acting: contextvars.ContextVar[Principal | None] = contextvars.ContextVar("urithi_acting", default=None)


def act_as(principal: Principal) -> None:
    """For the rest of this request: set by the side that identified the person."""
    _acting.set(principal)


@contextmanager
def acting_as(principal: Principal):
    token = _acting.set(principal)
    try:
        yield
    finally:
        _acting.reset(token)


def acting() -> Principal:
    return _acting.get() or PLATFORM_PRINCIPAL


# ── policy and prices, as data ────────────────────────────────────────────────

def _policy() -> dict:
    """Read on every grant: a small file, and a change to it applies at once."""
    return json.loads(Path(config.POLICY_PATH).read_text(encoding="utf-8"))


def _narrowed(platform: float | None, organisation: float | None) -> float | None:
    """An organisation narrows the platform's limit, never widens it."""
    if platform is None:
        return organisation
    if organisation is None:
        return platform
    return min(platform, organisation)


def quota(principal: Principal, capability: str) -> dict | None:
    """{period, warn, stop} for this role and capability, as the organisation narrows it."""
    policy = _policy()
    base = policy.get("quotas", {}).get(principal.role, {}).get(capability)
    own = policy.get("organisations", {}).get(principal.organisation, {}).get("quotas", {}) \
        .get(principal.role, {}).get(capability)
    if not base and not own:
        return None
    base, own = base or {}, own or {}
    period = base.get("period") or own.get("period") or "day"
    return {"period": period, "warn": _narrowed(base.get("warn"), own.get("warn")),
            "stop": _narrowed(base.get("stop"), own.get("stop"))}


def ceilings(principal: Principal) -> dict:
    """Model cost ceilings: per request, per person and day, per organisation and month, platform per day."""
    policy = _policy()
    base = policy.get("ceilings", {})
    own = policy.get("organisations", {}).get(principal.organisation, {}).get("ceilings", {})
    return {key: _narrowed(base.get(key), own.get(key))
            for key in ("request", "person_day", "organisation_month", "platform_day")}


def price(role: str) -> dict:
    """The price of a model role, per million tokens in and out, from configuration. No
    provider returns a price (docs/urithi-measured.md, docs/measured-a-and-an.md); without one, a call is costed at zero
    and said once in the log."""
    found = config.MODEL_PRICES.get(role)
    if not found:
        if role not in _unpriced:
            _unpriced.add(role)
            logger.warning("No price is set for the %s role: its calls are costed at zero.", role)
        return {"input": 0.0, "output": 0.0}
    return found


_unpriced: set[str] = set()


def cost(role: str, prompt_tokens: int, output_tokens: int) -> float:
    """What a call cost: output includes the thinking billed with it (decision 0012)."""
    p = price(role)
    return (prompt_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ── the meter ─────────────────────────────────────────────────────────────────

def _start(period: str, now: datetime) -> datetime:
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


WORDS = {
    "questions": "questions to the tutor", "speech_chars": "listening", "transcribed_seconds": "speaking",
    "illustrations": "illustrations", "source_checks": "source checks", "deposited_bytes": "deposits",
    "model_cost": "answers worded by a model",
}


class Meter:
    def __init__(self, counters: Counters):
        self.counters = counters

    def _used(self, principal: Principal, capability: str, period: str, now: datetime, *, person: bool) -> float:
        return self.counters.total(capability, since=_start(period, now), organisation=principal.organisation,
                                   person_id=principal.person_id if person else None)

    def grant(self, capability: str, estimate: float = 1.0, principal: Principal | None = None,
              now: datetime | None = None, *, never_refuse: bool = False) -> Grant:
        """A budget for one call, or Refused. `never_refuse`: counted, never stopped; the guard
        reads every message before it knows one is distress, and a reply to distress is never
        stopped by a quota (docs/decisions/0007)."""
        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown capability {capability!r}.")
        principal = principal or acting()
        now = now or datetime.now(UTC)
        warning = ""
        if never_refuse:
            return Grant(str(uuid.uuid4()), principal, capability, estimate)
        if capability == "model_cost":
            warning = self._check_ceilings(principal, estimate, now)
        elif principal.organisation != PLATFORM:
            limits = quota(principal, capability)
            if limits:
                used = self._used(principal, capability, limits["period"], now, person=True)
                stop, warn = limits["stop"], limits["warn"]
                when = "today" if limits["period"] == "day" else "this month"
                if stop is not None and used + estimate > stop:
                    raise Refused(capability, f"You have reached your limit for {WORDS[capability]} {when}. "
                                              f"It starts again {'tomorrow' if limits['period'] == 'day' else 'next month'}.")
                if warn is not None and used + estimate > warn:
                    warning = f"You are close to your limit for {WORDS[capability]} {when}."
        return Grant(str(uuid.uuid4()), principal, capability, estimate, warning)

    def _check_ceilings(self, principal: Principal, estimate: float, now: datetime) -> str:
        limits = ceilings(principal)
        if limits["request"] is not None and estimate > limits["request"]:
            raise Refused("model_cost", "This request would cost more than one request may.")
        if limits["platform_day"] is not None:
            used = self.counters.total("model_cost", since=_start("day", now))
            if used + estimate > limits["platform_day"]:
                raise Refused("model_cost", "The service has reached its spending limit for today.")
        if principal.organisation == PLATFORM:
            return ""
        if limits["organisation_month"] is not None:
            used = self._used(principal, "model_cost", "month", now, person=False)
            if used + estimate > limits["organisation_month"]:
                raise Refused("model_cost", "Your organisation has reached its spending limit for this month.")
        if limits["person_day"] is not None:
            used = self._used(principal, "model_cost", "day", now, person=True)
            if used + estimate > limits["person_day"]:
                raise Refused("model_cost", "You have reached your limit for answers worded by a model today.")
        return ""

    def record(self, grant: Grant, actual: float | None = None, now: datetime | None = None) -> None:
        amount = grant.estimate if actual is None else actual
        if amount:
            p = grant.principal
            self.counters.add(p.organisation, p.person_id, p.role, grant.capability, amount, now or datetime.now(UTC))

    def level(self, principal: Principal | None = None, now: datetime | None = None) -> str:
        """How near the model ceilings this principal is: "ok", "near" (past 80%), or "stop".
        The step-down reads it: near, a cheaper model and deferred work; stop, the guardian's words."""
        principal = principal or acting()
        now = now or datetime.now(UTC)
        limits = ceilings(principal)
        ratios = []
        if limits["platform_day"]:
            ratios.append(self.counters.total("model_cost", since=_start("day", now)) / limits["platform_day"])
        if principal.organisation != PLATFORM:
            if limits["organisation_month"]:
                ratios.append(self._used(principal, "model_cost", "month", now, person=False) / limits["organisation_month"])
            if limits["person_day"]:
                ratios.append(self._used(principal, "model_cost", "day", now, person=True) / limits["person_day"])
        worst = max(ratios, default=0.0)
        return "stop" if worst >= 1.0 else "near" if worst >= 0.8 else "ok"


_meter: Meter | None = None


def meter() -> Meter:
    if _meter is None:
        raise RuntimeError("No counters: the server wires them at start (server.py), the tests in conftest.")
    return _meter


def set_counters(counters: Counters | None) -> None:
    global _meter
    _meter = Meter(counters) if counters is not None else None
