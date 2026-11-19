"""
Reputation as a belief: the probability that someone keeps their next promise.

Model. A user keeps each promise with probability theta. Across the population theta
follows Beta(a0, b0). A user's theta is not fixed for ever: between any two promises,
with probability h, their circumstances change and theta is drawn afresh from the
population. So a piece of evidence that is tau steps old is still about the present
user with probability (1 - h) ** tau.

Three predictors of the next outcome, vectorised over users (rows) and time (columns):

  - `static_predictive`: Beta-Bernoulli updating that never forgets (correct if h = 0);
  - `forgetting_predictive`: the counts decay towards the prior by a factor gamma per step.
    This is the cheap rule a contract could implement: two decaying counters per user;
  - `exact_predictive`: the exact Bayesian filter for the model above, which tracks a
    distribution over how long ago the last change happened.

See notes/bayesian-reputation.md for the derivation and experiments/bayes_decay for
how close the cheap rule comes to the exact one.
"""

from __future__ import annotations

import numpy as np


def forget(alpha, beta, a0: float, b0: float, gamma: float):
    """
    One step of forgetting: Beta(alpha, beta) -> Beta(a0 + gamma (alpha - a0), b0 + gamma (beta - b0)).
    This is the normalised geometric mean posterior**gamma * prior**(1 - gamma).
    """
    return a0 + gamma * (alpha - a0), b0 + gamma * (beta - b0)


def reliability(kept: float, broken: float, a0: float, b0: float) -> float:
    """Posterior mean probability of keeping the next promise, from (decayed) counts."""
    return (a0 + kept) / (a0 + b0 + kept + broken)


def static_predictive(outcomes: np.ndarray, a0: float, b0: float) -> np.ndarray:
    """P(outcome_t = 1 | outcomes before t), never forgetting."""
    return forgetting_predictive(outcomes, a0, b0, 1.0)


def forgetting_predictive(outcomes: np.ndarray, a0: float, b0: float, gamma: float) -> np.ndarray:
    """P(outcome_t = 1 | outcomes before t) with counts decayed by gamma before each new promise."""
    users, steps = outcomes.shape
    alpha, beta = np.full(users, float(a0)), np.full(users, float(b0))
    predictions = np.empty((users, steps))
    for t in range(steps):
        alpha, beta = forget(alpha, beta, a0, b0, gamma)
        predictions[:, t] = alpha / (alpha + beta)
        alpha = alpha + outcomes[:, t]
        beta = beta + 1 - outcomes[:, t]
    return predictions


def exact_predictive(outcomes: np.ndarray, a0: float, b0: float, hazard: float) -> np.ndarray:
    """
    The exact filter. weights[u, j] is the posterior probability that user u's current
    theta was drawn just before promise j; given that, the outcomes since j are the evidence.
    """
    users, steps = outcomes.shape
    kept_before = np.concatenate([np.zeros((users, 1)), np.cumsum(outcomes, axis=1)], axis=1)
    weights = np.zeros((users, steps))
    predictions = np.empty((users, steps))
    for t in range(steps):
        if t == 0:
            weights[:, 0] = 1.0
        else:
            weights[:, t] = hazard  # the weights sum to one, so this is hazard * total
            weights[:, :t] *= 1 - hazard
        births = np.arange(t + 1)
        kept = kept_before[:, [t]] - kept_before[:, : t + 1]  # kept since each possible birth
        seen = t - births
        p_keep = (a0 + kept) / (a0 + b0 + seen)
        predictions[:, t] = (weights[:, : t + 1] * p_keep).sum(axis=1)
        likelihood = np.where(outcomes[:, [t]] == 1, p_keep, 1 - p_keep)
        weights[:, : t + 1] *= likelihood
        weights[:, : t + 1] /= weights[:, : t + 1].sum(axis=1, keepdims=True)
    return predictions


def simulate_outcomes(rng: np.random.Generator, users: int, steps: int, a0: float, b0: float, hazard: float) -> np.ndarray:
    """Draws promise outcomes from the model: theta ~ Beta(a0, b0), redrawn with probability `hazard` before each promise."""
    theta = rng.beta(a0, b0, size=users)
    outcomes = np.empty((users, steps))
    for t in range(steps):
        if t > 0:
            changed = rng.random(users) < hazard
            theta = np.where(changed, rng.beta(a0, b0, size=users), theta)
        outcomes[:, t] = rng.random(users) < theta
    return outcomes


def log_loss(predictions: np.ndarray, outcomes: np.ndarray) -> float:
    p = np.clip(predictions, 1e-12, 1 - 1e-12)
    return float(-(outcomes * np.log(p) + (1 - outcomes) * np.log(1 - p)).mean())
