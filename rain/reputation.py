"""
The rules engine of the Rain Reputation Oracle.

It turns the CalculusEngine's promise log into reputation changes:

  - a kept promise earns its promisor `fee paid / point price` points, so reputation has
    a fixed price and is a record of fees paid on promises that were kept;
  - a broken promise costs its promisor a flat penalty (on top of the bond the script
    forfeits on-chain);
  - a promise kept while its promisor was delinquent earns nothing.
"""

from typing import Any, Dict, Iterable, List, Tuple

POINT = 10**18  # reputation is stored with 18 decimals
REP_LOSS_ON_DEFAULT = 100 * POINT  # Flat penalty for breaking a promise

Change = Dict[str, Any]  # {"user": address, "amount": int, "reason": str}


def reward(fee_paid: int, point_price: int) -> int:
    """
    Reputation (in base units) earned by a kept promise on which `fee_paid` currency base
    units were paid, when a whole point costs `point_price` currency base units. Rounded down.
    """
    if point_price <= 0:
        raise ValueError("point_price must be positive")
    if fee_paid < 0:
        raise ValueError("fee_paid must be non-negative")
    return fee_paid * POINT // point_price


def reputation_changes(
    fulfilled: Iterable[Tuple[int, str, int]],
    defaulted: Iterable[Tuple[int, str]],
    point_price: int,
    rep_loss: int = REP_LOSS_ON_DEFAULT,
) -> Tuple[List[Change], List[Change]]:
    """
    The pure rules. `fulfilled` holds `(promise_id, promisor, fee_paid)` and `defaulted`
    holds `(promise_id, promisor)`.

    Returns `(increases, decreases)`. Each resolved promise yields at most one change,
    whose `reason` names the promise so that changes can be audited against the log
    (and so that the updater applies each one only once). A kept promise that paid no
    fee earns nothing and yields no change.
    """
    increases = []
    for promise_id, promisor, fee_paid in fulfilled:
        amount = reward(fee_paid, point_price)
        if amount > 0:
            increases.append({"user": promisor, "amount": amount, "reason": f"PROMISE_FULFILLED:{promise_id}"})
    decreases = [
        {"user": promisor, "amount": rep_loss, "reason": f"PROMISE_DEFAULTED:{promise_id}"}
        for promise_id, promisor, *_ in defaulted
    ]
    return increases, decreases


def _resolved_promises(engine_contract: Any, event_type: str, start_block: int, end_block: int):
    """`(promise_id, promisor, fee_paid, block, log_index)` for each promise resolved in the block range, in chain order."""
    # Ape's `range` excludes its stop block; our block ranges are inclusive.
    events = getattr(engine_contract, event_type).range(start_block, end_block + 1)
    events = sorted(events, key=lambda e: (e.block_number, e.log_index))
    resolved = []
    for event in events:
        promise_id = event.event_arguments["promiseId"]
        promise = engine_contract.promises(promise_id)
        resolved.append((promise_id, promise[1], promise[7], event.block_number, event.log_index))  # promisor, feePaid
    return resolved


def process_promise_events(
    engine_contract: Any, start_block: int, end_block: int
) -> Tuple[List[Change], List[Change]]:
    """
    Reads `PromiseFulfilled` / `PromiseDefaulted` events from the CalculusEngine in
    the (inclusive) block range and applies the rules, at the engine's current point
    price. Returns `(increases, decreases)`.

    This is the promise log alone: it does not know who was delinquent. The oracle
    uses `process_promise_log`, which does.
    """
    fulfilled = _resolved_promises(engine_contract, "PromiseFulfilled", start_block, end_block)
    defaulted = _resolved_promises(engine_contract, "PromiseDefaulted", start_block, end_block)
    return reputation_changes([f[:3] for f in fulfilled], defaulted, engine_contract.pointPrice())


# --- Delinquency: a promise kept while delinquent earns nothing ---

Timeline = Dict[str, List[Tuple[int, int, bool]]]  # user -> [(block, log_index, is_delinquent)], in chain order


def delinquency_timeline(rain_reputation_contract: Any, to_block: int) -> Timeline:
    """Every change of delinquent status up to `to_block`, per user, read from the reputation contract's events."""
    timeline: Timeline = {}
    events = rain_reputation_contract.DelinquentStatusChanged.range(0, to_block + 1)
    for event in sorted(events, key=lambda e: (e.block_number, e.log_index)):
        args = event.event_arguments
        timeline.setdefault(str(args["user"]), []).append((event.block_number, event.log_index, bool(args["isDelinquent"])))
    return timeline


def was_delinquent(timeline: Timeline, user: str, block: int, log_index: int) -> bool:
    """Whether `user` was delinquent just before the log at `(block, log_index)`."""
    status = False
    for change_block, change_index, is_delinquent in timeline.get(str(user), []):
        if (change_block, change_index) >= (block, log_index):
            break
        status = is_delinquent
    return status


def process_promise_log(
    engine_contract: Any, rain_reputation_contract: Any, start_block: int, end_block: int
) -> Tuple[List[Change], List[Change], List[Change]]:
    """
    The oracle's full rule for a block range. Returns `(increases, decreases, withheld)`.

    A kept promise is rewarded unless its promisor was delinquent at the moment it was
    kept; those rewards are returned in `withheld` and never submitted. Status is read
    from the event log as of the promise's own position in the chain, so the result does
    not depend on when the oracle runs: someone who keeps a promise and defaults on
    another before the oracle has caught up still earns the first one's reward.
    """
    fulfilled = _resolved_promises(engine_contract, "PromiseFulfilled", start_block, end_block)
    defaulted = _resolved_promises(engine_contract, "PromiseDefaulted", start_block, end_block)
    timeline = delinquency_timeline(rain_reputation_contract, end_block)

    earned, lost = [], []
    for promise in fulfilled:
        _, promisor, _, block, log_index = promise
        (lost if was_delinquent(timeline, promisor, block, log_index) else earned).append(promise[:3])
    point_price = engine_contract.pointPrice()
    increases, decreases = reputation_changes(earned, defaulted, point_price)
    withheld, _ = reputation_changes(lost, [], point_price)
    return increases, decreases, withheld


def to_update_tuples(changes: List[Change]) -> List[Tuple[str, int, str]]:
    """Formats changes as the `ReputationUpdate` struct tuples the updater expects."""
    return [(c["user"], c["amount"], c["reason"]) for c in changes]
