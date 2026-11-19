"""
Reputation decay.

Claims tested: every `decayPeriod`, scores, bonds and the total are all multiplied by
`retentionPerPeriod`; this happens whether or not anyone touches the account; reputation
earned later is not decayed retroactively; and no amount of elapsed time can break the contract.
"""
import pytest
from helpers import E18, PERIOD, accounts, advance, deploy_reputation, ev, project, reverts

RETENTION = 97 * E18 // 100
START = 1_000 * E18


def purpose(n):
    return n.to_bytes(32, "big")


def kept(amount, periods):
    """What the contract leaves of `amount` after `periods`: retention applied one period at a time in fixed point."""
    factor = E18
    base = RETENTION
    n = periods
    while n > 0:  # the same square-and-multiply the contract uses
        if n & 1:
            factor = factor * base // E18
        base = base * base // E18
        n >>= 1
    return amount * factor // E18


@pytest.fixture
def rep():
    """Alice (accounts[2]) and Bob (accounts[3]) hold 1,000 points each; accounts[1] is the updater."""
    admin, updater = accounts[0], accounts[1]
    contract = deploy_reputation(admin, retention=RETENTION)
    contract.grantRole(contract.UPDATER_ROLE(), updater, sender=admin)
    for user in (accounts[2], accounts[3]):
        contract.increaseReputation(user, START, "seed", sender=updater)
    return contract


def test_parameters(rep):
    assert (rep.decayPeriod(), rep.retentionPerPeriod(), rep.currentPeriod()) == (PERIOD, RETENTION, 0)
    for bad_period, bad_retention in [(0, RETENTION), (PERIOD, 0), (PERIOD, E18 + 1)]:
        with reverts():
            project.RainReputation.deploy(bad_period, bad_retention, sender=accounts[0])


def test_kept_helper_matches_floating_point():
    assert kept(START, 0) == START
    assert kept(START, 1) == 970 * E18
    assert kept(START, 10) / E18 == pytest.approx(1000 * 0.97**10, rel=1e-12)
    assert kept(START, 500) / E18 == pytest.approx(1000 * 0.97**500, rel=1e-9)


def test_nothing_decays_within_a_period(rep):
    alice = accounts[2]
    advance(PERIOD // 2)
    assert rep.currentPeriod() == 0
    assert rep.reputationScores(alice) == START and rep.totalReputation() == 2 * START


@pytest.mark.parametrize("periods", [1, 2, 7, 24, 100])
def test_score_and_total_decay_without_anyone_touching_them(rep, periods):
    alice = accounts[2]
    advance(periods * PERIOD)
    assert rep.currentPeriod() == periods
    assert rep.reputationScores(alice) == kept(START, periods)
    assert rep.totalReputation() == kept(2 * START, periods)
    # The total is the sum of the scores, up to rounding of one unit per account
    assert abs(rep.totalReputation() - 2 * rep.reputationScores(alice)) <= 2


def test_half_life_is_about_two_years_at_three_percent_a_month(rep):
    advance(23 * PERIOD)
    assert rep.reputationScores(accounts[2]) / START == pytest.approx(0.5, abs=0.01)


def test_decay_in_steps_equals_decay_at_once(rep):
    """Touching an account part-way (which stores the decayed value) must not change where it ends up."""
    updater, alice, bob = accounts[1], accounts[2], accounts[3]
    for _ in range(6):
        advance(PERIOD)
        rep.increaseReputation(alice, 0, "touch", sender=updater)  # writes Alice's account every period
    # Bob was never touched. Rounding differs by at most one unit per step.
    assert abs(rep.reputationScores(alice) - rep.reputationScores(bob)) <= 6
    assert rep.reputationScores(bob) == kept(START, 6)


def test_reputation_earned_later_is_not_decayed_retroactively(rep):
    updater, alice = accounts[1], accounts[2]
    advance(3 * PERIOD)
    rep.increaseReputation(alice, 500 * E18, "later", sender=updater)
    assert rep.reputationScores(alice) == kept(START, 3) + 500 * E18
    advance(2 * PERIOD)
    assert rep.reputationScores(alice) == kept(kept(START, 3) + 500 * E18, 2)
    assert abs(rep.totalReputation() - rep.reputationScores(alice) - rep.reputationScores(accounts[3])) <= 4


def test_penalties_apply_to_the_decayed_score(rep):
    updater, alice = accounts[1], accounts[2]
    advance(PERIOD)
    tx = rep.slash(alice, 2_000 * E18, sender=updater)  # more than is left
    assert ev(tx)['ReputationSlashed']['amount'] == 970 * E18
    assert rep.reputationScores(alice) == 0
    assert rep.totalReputation() == 970 * E18  # Bob's


def test_the_broken_promise_counter_fades_at_the_same_rate(rep):
    updater, alice = accounts[1], accounts[2]
    rep.recordBroken(alice, 400 * E18, "first", sender=updater)
    advance(3 * PERIOD)
    assert rep.brokenScores(alice) == kept(400 * E18, 3)
    rep.recordBroken(alice, 100 * E18, "second", sender=updater)
    advance(2 * PERIOD)
    assert rep.brokenScores(alice) == kept(kept(400 * E18, 3) + 100 * E18, 2)
    # Both counters fade together, so with no prior the belief does not move with time alone...
    assert abs(rep.reliability(alice, 0, 0) - rep.reputationScores(alice) * E18 // (rep.reputationScores(alice) + rep.brokenScores(alice))) <= 1
    # ...and with a prior it drifts towards the prior as the evidence fades.
    prior = (30 * E18, 10 * E18)  # 0.75
    before = rep.reliability(alice, *prior)
    advance(60 * PERIOD)
    after = rep.reliability(alice, *prior)
    assert abs(after - 75 * E18 // 100) < abs(before - 75 * E18 // 100)


def test_bond_decays_with_the_score_it_is_part_of(rep):
    alice, script = accounts[2], accounts[5]
    rep.approveStake(script, 400 * E18, sender=alice)
    rep.stake(alice, 400 * E18, purpose(1), sender=script)
    advance(5 * PERIOD)

    assert rep.stakedReputation(alice) == kept(400 * E18, 5)
    assert rep.getStake(script, purpose(1)) == (alice, kept(400 * E18, 5), True, False)
    assert rep.getLiquidReputation(alice) == kept(START, 5) - kept(400 * E18, 5)

    tx = rep.releaseStake(purpose(1), sender=script)
    assert ev(tx)['StakeReleased']['amount'] == kept(400 * E18, 5)
    assert rep.stakedReputation(alice) == 0
    assert rep.reputationScores(alice) == kept(START, 5)  # releasing a bond does not change the score


def test_forfeit_destroys_what_is_left_of_the_bond(rep):
    alice, script = accounts[2], accounts[5]
    rep.approveStake(script, 400 * E18, sender=alice)
    rep.stake(alice, 400 * E18, purpose(1), sender=script)
    advance(5 * PERIOD)

    tx = rep.forfeitStake(purpose(1), sender=script)

    left = kept(400 * E18, 5)
    assert ev(tx)['StakeForfeited']['reputationBurned'] == left
    assert rep.reputationScores(alice) == kept(START, 5) - left
    assert rep.stakedReputation(alice) == 0
    assert abs(rep.totalReputation() - (kept(2 * START, 5) - left)) <= 2


def test_liquid_reputation_cannot_be_overstaked_after_decay(rep):
    alice = accounts[2]
    rep.stake(alice, 900 * E18, purpose(1), sender=alice)
    advance(PERIOD)
    liquid = rep.getLiquidReputation(alice)
    assert liquid == 970 * E18 - 873 * E18
    with reverts("Insufficient liquid reputation"):
        rep.stake(alice, liquid + 1, purpose(2), sender=alice)
    rep.stake(alice, liquid, purpose(2), sender=alice)
    assert rep.getLiquidReputation(alice) == 0


def test_stakes_made_in_different_periods_resolve_cleanly(rep):
    alice = accounts[2]
    rep.stake(alice, 300 * E18, purpose(1), sender=alice)
    advance(2 * PERIOD)
    rep.stake(alice, 200 * E18, purpose(2), sender=alice)
    advance(3 * PERIOD)
    assert abs(rep.stakedReputation(alice) - (kept(300 * E18, 5) + kept(200 * E18, 3))) <= 2
    rep.releaseStake(purpose(1), sender=alice)
    rep.releaseStake(purpose(2), sender=alice)
    assert rep.stakedReputation(alice) <= 2  # at most rounding dust is left locked
    assert rep.getLiquidReputation(alice) >= rep.reputationScores(alice) - 2


def test_a_very_long_time_cannot_break_the_contract(rep):
    """Decay tends to zero. There is no growing index that could overflow."""
    updater, alice = accounts[1], accounts[2]
    rep.stake(alice, 100 * E18, purpose(1), sender=alice)
    advance(5_000 * PERIOD)  # four centuries
    assert rep.reputationScores(alice) == 0 and rep.totalReputation() == 0
    rep.releaseStake(purpose(1), sender=alice)
    rep.increaseReputation(alice, 5, "still works", sender=updater)
    assert rep.reputationScores(alice) == 5 == rep.totalReputation()


def test_without_decay_nothing_ever_changes():
    updater, alice = accounts[1], accounts[2]
    contract = deploy_reputation(accounts[0])  # retention 1
    contract.grantRole(contract.UPDATER_ROLE(), updater, sender=accounts[0])
    contract.increaseReputation(alice, START, "seed", sender=updater)
    advance(1_000 * PERIOD)
    assert contract.reputationScores(alice) == contract.totalReputation() == START
