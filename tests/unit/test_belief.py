"""
Claims tested: the three predictors in rain.belief are what they say they are. The exact
filter is checked against brute-force enumeration of every change pattern.
"""
import itertools

import numpy as np
import pytest

from rain import belief

A0, B0 = 8.0, 2.0


def brute_force_predictive(outcomes, a0, b0, hazard):
    """P(x_t = 1 | x_<t) by summing over every pattern of changes (exponential; tiny inputs only)."""
    from math import lgamma, exp

    def log_marginal(kept, broken):  # Beta-Bernoulli evidence of one segment
        return (lgamma(a0 + kept) + lgamma(b0 + broken) - lgamma(a0 + b0 + kept + broken)
                - lgamma(a0) - lgamma(b0) + lgamma(a0 + b0))

    def joint(sequence):
        n = len(sequence)
        total = 0.0
        for changes in itertools.product([0, 1], repeat=n - 1):  # change before promise 1..n-1
            logp, start = 0.0, 0
            cuts = [i + 1 for i, c in enumerate(changes) if c] + [n]
            for cut in cuts:
                segment = sequence[start:cut]
                logp += log_marginal(sum(segment), len(segment) - sum(segment))
                start = cut
            prior = hazard ** sum(changes) * (1 - hazard) ** (n - 1 - sum(changes))
            total += prior * exp(logp)
        return total

    predictions = []
    for t in range(len(outcomes)):
        history = list(outcomes[:t])
        predictions.append(joint(history + [1]) / (joint(history + [1]) + joint(history + [0])))
    return predictions


@pytest.mark.parametrize("hazard", [0.0, 0.1, 0.4])
@pytest.mark.parametrize("sequence", [[1, 1, 0, 1, 1, 1, 0, 0], [0, 0, 0, 1, 1, 1, 1, 1], [1, 0, 1, 0, 1, 0, 1, 0]])
def test_exact_filter_matches_brute_force(hazard, sequence):
    outcomes = np.array([sequence], dtype=float)
    exact = belief.exact_predictive(outcomes, A0, B0, hazard)[0]
    assert exact == pytest.approx(brute_force_predictive(sequence, A0, B0, hazard), abs=1e-10)


def test_without_change_all_three_predictors_coincide():
    rng = np.random.default_rng(0)
    outcomes = belief.simulate_outcomes(rng, 50, 40, A0, B0, 0.0)
    static = belief.static_predictive(outcomes, A0, B0)
    assert belief.exact_predictive(outcomes, A0, B0, 0.0) == pytest.approx(static, abs=1e-12)
    assert belief.forgetting_predictive(outcomes, A0, B0, 1.0) == pytest.approx(static, abs=1e-12)


def test_static_predictive_is_beta_bernoulli():
    outcomes = np.array([[1, 1, 0, 1]], dtype=float)
    assert belief.static_predictive(outcomes, A0, B0)[0] == pytest.approx([8 / 10, 9 / 11, 10 / 12, 10 / 13])


def test_forgetting_is_the_geometric_mean_of_posterior_and_prior():
    alpha, beta, gamma = 20.0, 5.0, 0.7
    a, b = belief.forget(alpha, beta, A0, B0, gamma)
    theta = np.linspace(0.01, 0.99, 99)
    pooled = (theta ** (alpha - 1) * (1 - theta) ** (beta - 1)) ** gamma * (theta ** (A0 - 1) * (1 - theta) ** (B0 - 1)) ** (1 - gamma)
    forgotten = theta ** (a - 1) * (1 - theta) ** (b - 1)
    assert pooled / pooled.sum() == pytest.approx(forgotten / forgotten.sum(), rel=1e-9)


def test_forgetting_regresses_to_the_prior_with_no_new_evidence():
    alpha, beta = 100.0, 1.0
    for _ in range(2000):
        alpha, beta = belief.forget(alpha, beta, A0, B0, 0.99)
    assert (alpha, beta) == pytest.approx((A0, B0), abs=1e-6)


def test_reliability():
    assert belief.reliability(0, 0, A0, B0) == 0.8
    assert belief.reliability(90, 0, A0, B0) == 0.98
    assert belief.reliability(0, 10, A0, B0) == 0.4


def test_simulated_outcomes_have_the_population_mean():
    rng = np.random.default_rng(1)
    outcomes = belief.simulate_outcomes(rng, 4000, 50, A0, B0, 0.05)
    assert outcomes.mean() == pytest.approx(0.8, abs=0.01)


def test_exact_filter_is_calibrated_on_data_from_the_model():
    rng = np.random.default_rng(2)
    outcomes = belief.simulate_outcomes(rng, 3000, 60, A0, B0, 0.05)
    predictions = belief.exact_predictive(outcomes, A0, B0, 0.05)
    for lo, hi in [(0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]:
        mask = (predictions >= lo) & (predictions < hi)
        assert outcomes[mask].mean() == pytest.approx(predictions[mask].mean(), abs=0.015)
