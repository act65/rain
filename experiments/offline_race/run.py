"""
Claim under test: a double spender's take is bounded by what the shops share. With no sharing it grows
with the market; with gossip it grows with the market's logarithm; through the chain it is the number of
shops reachable while news gets there and back, whatever the market's size. See README.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from rain.offline import split_limit
from rain.provenance import run_provenance

HERE = Path(__file__).parent
GUESS = 5  # the shops' guess m of how many places a payer could be
SEEDS = 20
LIMIT = 1.0  # everything is counted in limits


def summary(takes):
    takes = np.asarray(takes, dtype=float)
    return dict(mean=float(takes.mean()), standard_error=float(takes.std(ddof=1) / math.sqrt(len(takes))),
                largest=float(takes.max()))


# --- A and B: nothing shared ---

def take_without_news(market, per_shop):
    """Every shop accepts `per_shop` and the attacker visits them all."""
    return market * per_shop / LIMIT


# --- C: gossip between shops ---

def gossip_take(market, rate, seed, patience=30):
    """
    Limits taken when shops refuse a payer whose notes they know of already total the limit, and every
    shop that knows of a note swaps all it knows with a random shop `rate` times per unit of time.
    Knowledge is a bit set of note numbers. Stops after `patience` refusals in a row.
    """
    rng = np.random.default_rng(seed)
    knows = [0] * market
    order = rng.permutation(market)
    accepted = refused_in_a_row = 0
    for shop in order:
        if bin(knows[shop]).count("1") >= GUESS:
            refused_in_a_row += 1
            if refused_in_a_row >= patience:
                break
        else:
            knows[shop] |= 1 << accepted
            accepted += 1
            refused_in_a_row = 0
        informed = [i for i in range(market) if knows[i]]
        for i in rng.permutation(informed):
            for other in rng.integers(0, market, size=rng.poisson(rate)):
                knows[i] = knows[other] = knows[i] | knows[other]
    return accepted * split_limit(LIMIT, GUESS)


# --- D: news goes to the chain and comes back when a shop syncs ---

def chain_take(market, delay, sync_rate, seed, helpers=1, fresh_within=None):
    """
    Limits taken when a shop refuses a payer whose notes on the chain, at the shop's last sync, totalled the
    limit. A note reaches the chain `delay` after it is signed. The attacker (with helpers) visits `helpers`
    shops per unit of time. With `fresh_within`, a shop whose last sync is older than that refuses everyone.
    """
    rng = np.random.default_rng(seed)
    on_chain_at = []  # when each accepted note reaches the chain, in order
    accepted = 0
    for step in range(1, market + 1):
        now = step / helpers
        since_sync = rng.exponential(1 / sync_rate)  # each shop is visited once, so this is independent per visit
        if fresh_within is not None and since_sync > fresh_within:
            continue
        seen = sum(1 for t in on_chain_at if t <= now - since_sync)
        if seen < GUESS:
            accepted += 1
            on_chain_at.append(now + delay)
    return accepted * split_limit(LIMIT, GUESS)


def chain_formula(delay, sync_rate, helpers=1):
    d, rho = delay * helpers, sync_rate / helpers  # in the attacker's steps
    return 1 + (d + 1 / (math.exp(rho) - 1)) / GUESS


def main():
    out = dict(provenance=run_provenance(), parameters=dict(guess=GUESS, seeds=SEEDS))
    out["nothing_shared"] = {str(M): dict(guess=take_without_news(M, split_limit(LIMIT, GUESS)),
                                          divide_by_market=take_without_news(M, split_limit(LIMIT, M)),
                                          per_shop_when_divided_by_market=split_limit(LIMIT, M)) for M in (100, 1_000)}
    out["gossip"] = {str(g): {str(M): dict(**summary([gossip_take(M, g, seed) for seed in range(SEEDS)]),
                                           rough_prediction=1 + math.log(M) / g / GUESS)
                              for M in (100, 1_000, 10_000)} for g in (0.1, 0.3, 1.0, 3.0)}
    out["chain"] = {f"d={d}, rho={rho}": {str(M): dict(**summary([chain_take(M, d, rho, seed) for seed in range(SEEDS)]),
                                                        predicted=chain_formula(d, rho))
                                          for M in (100, 1_000)} for d, rho in ((1, 1.0), (5, 0.2), (20, 0.05))}
    T = 2.0
    out["freshness"] = dict(fresh_within=T, cap=1 + (5 + T) / GUESS, available=1 - math.exp(-0.2 * T),
                            **summary([chain_take(1_000, 5, 0.2, seed, fresh_within=T) for seed in range(SEEDS)]))
    out["helpers"] = dict(helpers=10, predicted=chain_formula(5, 0.2, helpers=10),
                          **summary([chain_take(1_000, 5, 0.2, seed, helpers=10) for seed in range(SEEDS)]))
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(json.dumps(out, indent=1))

    p = out["provenance"]
    L = ["# Offline, racing the news: results", "", f"Commit `{p['commit_short']}` (dirty: {p['dirty']}), {p['utc']}.", "",
         f"The take is in limits. Shops guess {GUESS} places. Means over {SEEDS} seeds, with standard errors.", "",
         "## A and B: nothing shared", "", "| shops in the market | each accepts the limit / 5 | each accepts the limit / the market | ...and then accepts, of the limit |",
         "|---|---|---|---|"]
    L += [f"| {M} | {r['guess']:.0f} | {r['divide_by_market']:.0f} | {100 * r['per_shop_when_divided_by_market']:.1f}% |" for M, r in out["nothing_shared"].items()]
    L += ["", "## C: gossip between shops", "", "| swaps per shop per attacker's visit | 100 shops | 1,000 | 10,000 | rough prediction at 1,000 |", "|---|---|---|---|---|"]
    for g, row in out["gossip"].items():
        L.append(f"| {g} | " + " | ".join(f"{row[M]['mean']:.2f} ({row[M]['standard_error']:.2f})" for M in ("100", "1000", "10000"))
                 + f" | {row['1000']['rough_prediction']:.2f} |")
    L += ["", "## D: through the chain", "", "| carriers' delay, shops' sync rate | 100 shops | 1,000 | predicted |", "|---|---|---|---|"]
    for name, row in out["chain"].items():
        L.append(f"| {name} | " + " | ".join(f"{row[M]['mean']:.2f} ({row[M]['standard_error']:.2f})" for M in ("100", "1000"))
                 + f" | {row['1000']['predicted']:.2f} |")
    f, h = out["freshness"], out["helpers"]
    L += ["", f"## D': shops refuse when their last sync is older than {T:g} (d=5, rho=0.2, 1,000 shops)", "",
          f"Take {f['mean']:.2f} ({f['standard_error']:.2f}); largest in any run {f['largest']:.2f}; cap {f['cap']:.2f}. "
          f"A shop is willing to deal {100 * f['available']:.0f}% of the time.", "",
          "## E: ten helpers (d=5, rho=0.2, 1,000 shops)", "",
          f"Take {h['mean']:.2f} ({h['standard_error']:.2f}); predicted {h['predicted']:.2f}."]
    (HERE / "results" / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
