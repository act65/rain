"""
The off-chain `rain` library against the real contracts: the oracle, the dividend
Merkle drop and the fee keeper, exercised the way the scripts use them.
"""
import pytest
from helpers import E18, action_id_of, advance, chain, deploy_system, ev, reverts

from rain.dividends import calculate_dividend_shares, get_merkle_proof, get_reputation_holders
from rain.reputation import (
    process_promise_events,
    process_promise_log,
    to_update_tuples,
)

START_REP = 1_000 * E18
DURATION = 30 * 24 * 60 * 60
STAKE = 10 * E18


def loan(s, borrower, lender, principal=100 * E18, interest=5 * E18, duration=DURATION, stake=STAKE):
    tx = s.loan.requestLoan(lender, principal, interest, duration, stake, sender=borrower)
    loan_id = ev(tx)['LoanRequested']['loanId']
    s.loan.fundLoan(loan_id, sender=lender)
    return loan_id


def promise_of(s, loan_id):
    return s.loan.loans(loan_id)['promiseId']


def run_oracle(s, from_block=0):
    """One oracle run, as scripts/run_reputation_oracle.py does it. Returns (increases, decreases, withheld)."""
    increases, decreases, withheld = process_promise_log(s.engine, s.rep, from_block, chain.blocks.height)
    if increases or decreases:
        s.updater.applyReputationChanges(to_update_tuples(increases), to_update_tuples(decreases), sender=s.oracle)
    return increases, decreases, withheld


# --- Oracle ---

def test_oracle_rewards_kept_promises_and_records_broken_ones(system):
    s = system
    repaid = loan(s, s.bob, s.alice)
    s.loan.repayLoan(repaid, sender=s.bob)
    broken = loan(s, s.carol, s.alice)
    advance(DURATION + 1)
    s.loan.claimDefault(broken, sender=s.alice)

    increases, decreases, skipped = run_oracle(s)

    assert [(c["user"], c["reason"]) for c in increases] == [(s.bob.address, f"PROMISE_FULFILLED:{promise_of(s, repaid)}")]
    assert [(c["user"], c["reason"]) for c in decreases] == [(s.carol.address, f"PROMISE_DEFAULTED:{promise_of(s, broken)}")]
    assert skipped == []

    assert s.rep.reputationScores(s.alice) == START_REP  # lending is not a promise
    assert s.rep.reputationScores(s.bob) == START_REP + s.reward
    # Carol lost her bond at the moment of default. The oracle adds the promise to her broken
    # counter with the weight it would have earned; it takes no further reputation.
    assert s.rep.reputationScores(s.carol) == START_REP - STAKE
    assert s.rep.brokenScores(s.carol) == s.reward
    assert s.rep.brokenScores(s.bob) == s.rep.brokenScores(s.alice) == 0
    assert s.rep.totalReputation() == sum(s.rep.reputationScores(u) for u in (s.alice, s.bob, s.carol))


def test_oracle_ignores_requests_and_pending_promises(system):
    s = system
    s.loan.requestLoan(s.alice, 100 * E18, 0, DURATION, STAKE, sender=s.bob)  # never funded
    loan(s, s.carol, s.alice)  # funded, not yet repaid
    assert process_promise_events(s.engine, 0, chain.blocks.height) == ([], [])


def test_oracle_block_ranges_partition_the_log(system):
    """Processing [0, k] then [k+1, head] finds each event exactly once."""
    s = system
    first = loan(s, s.bob, s.alice)
    s.loan.repayLoan(first, sender=s.bob)
    checkpoint = chain.blocks.height
    second = loan(s, s.carol, s.alice)
    s.loan.repayLoan(second, sender=s.carol)

    whole, _ = process_promise_events(s.engine, 0, chain.blocks.height)
    early, _ = process_promise_events(s.engine, 0, checkpoint)
    late, _ = process_promise_events(s.engine, checkpoint + 1, chain.blocks.height)
    assert early + late == whole
    assert [c["user"] for c in whole] == [s.bob.address, s.carol.address]


def test_only_the_oracle_can_commit(system):
    s = system
    update = [(s.bob.address, 10**30, "free reputation")]
    for caller in (s.admin, s.bob, s.outsider):
        with reverts("Caller is not a trusted updater"):
            s.updater.applyReputationChanges(update, [], sender=caller)
    for caller in (s.oracle, s.admin):  # the ledger only listens to the updater contract
        with reverts("Caller is not a trusted updater"):
            s.rep.increaseReputation(s.bob, 10**30, "free reputation", sender=caller)


def test_promise_kept_while_delinquent_earns_nothing_and_blocks_nobody(system):
    """Bob defaults on one loan and then repays another, in the same batch as Carol's repayment."""
    s = system
    long_loan = loan(s, s.bob, s.carol, duration=10 * DURATION)
    short_loan = loan(s, s.bob, s.alice)
    carols = loan(s, s.carol, s.alice, duration=10 * DURATION)
    advance(DURATION + 1)
    rct_id = ev(s.loan.claimDefault(short_loan, sender=s.alice))['LoanDefaulted']['rctId']
    s.loan.repayLoan(long_loan, sender=s.bob)  # kept while delinquent
    s.loan.repayLoan(carols, sender=s.carol)

    _, _, withheld = run_oracle(s)

    assert [c["reason"] for c in withheld] == [f"PROMISE_FULFILLED:{promise_of(s, long_loan)}"]
    assert s.rep.reputationScores(s.bob) == START_REP - STAKE
    assert s.rep.reputationScores(s.carol) == START_REP + s.reward

    # Settling the debt later does not bring that reward back, even if the oracle re-reads the log
    s.rct.transferFrom(s.alice, s.bob, rct_id, sender=s.alice)
    s.rct.approve(s.loan.address, rct_id, sender=s.bob)
    s.loan.resolveDefault(rct_id, sender=s.bob)
    assert run_oracle(s)[2] == withheld
    assert s.rep.reputationScores(s.bob) == START_REP - STAKE


def test_promise_kept_before_a_default_is_rewarded_however_late_the_oracle_runs(system):
    """
    Bob repays one loan and afterwards defaults on another. The oracle only runs after the
    default, when Bob is delinquent. He still earns the reward for the promise he kept.
    """
    s = system
    kept = loan(s, s.bob, s.carol)
    broken = loan(s, s.bob, s.alice)
    s.loan.repayLoan(kept, sender=s.bob)
    advance(DURATION + 1)
    s.loan.claimDefault(broken, sender=s.alice)
    assert s.rep.isDelinquent(s.bob)

    increases, decreases, withheld = run_oracle(s)

    assert [c["reason"] for c in increases] == [f"PROMISE_FULFILLED:{promise_of(s, kept)}"]
    assert withheld == []
    assert s.rep.reputationScores(s.bob) == START_REP + s.reward - STAKE


def test_oracle_result_is_the_same_run_promptly_or_late():
    """The same history, with the oracle run after every step or once at the end, ends in the same scores."""
    def history(s, oracle_after_each_step):
        kept = loan(s, s.bob, s.carol)
        broken = loan(s, s.bob, s.alice)
        other = loan(s, s.bob, s.carol, duration=10 * DURATION)
        steps = [
            lambda: s.loan.repayLoan(kept, sender=s.bob),
            lambda: (advance(DURATION + 1), s.loan.claimDefault(broken, sender=s.alice)),
            lambda: s.loan.repayLoan(other, sender=s.bob),  # while delinquent
        ]
        seen = 0
        for step in steps:
            step()
            if oracle_after_each_step:
                run_oracle(s, from_block=seen)
                seen = chain.blocks.height + 1
        run_oracle(s)
        return s.rep.reputationScores(s.bob), s.rep.brokenScores(s.bob)

    prompt = history(deploy_system(), oracle_after_each_step=True)
    late = history(deploy_system(), oracle_after_each_step=False)
    assert prompt == late == (START_REP + 25 * E18 - STAKE, 25 * E18)


def test_a_default_is_recorded_once_and_resolution_does_not_erase_it(system):
    s = system
    broken = loan(s, s.bob, s.alice)
    advance(DURATION + 1)
    rct_id = ev(s.loan.claimDefault(broken, sender=s.alice))['LoanDefaulted']['rctId']
    run_oracle(s)
    checkpoint = chain.blocks.height

    s.rct.transferFrom(s.alice, s.bob, rct_id, sender=s.alice)
    s.rct.approve(s.loan.address, rct_id, sender=s.bob)
    s.loan.resolveDefault(rct_id, sender=s.bob)

    assert run_oracle(s, from_block=checkpoint + 1) == ([], [], [])
    assert run_oracle(s)[1] != []  # re-reading the whole log finds the default again; the updater skips it
    assert s.rep.reputationScores(s.bob) == START_REP - STAKE  # the bond does not come back
    assert s.rep.brokenScores(s.bob) == s.reward  # and the record stays (it fades with time)


def test_replaying_the_log_does_not_double_count(system):
    """The oracle crashed before saving its state and re-reads the same blocks."""
    s = system
    s.loan.repayLoan(loan(s, s.bob, s.alice), sender=s.bob)
    broken = loan(s, s.carol, s.alice)
    advance(DURATION + 1)
    s.loan.claimDefault(broken, sender=s.alice)

    run_oracle(s)
    scores = [s.rep.reputationScores(u) for u in (s.alice, s.bob, s.carol)]
    run_oracle(s)
    run_oracle(s)
    assert [s.rep.reputationScores(u) for u in (s.alice, s.bob, s.carol)] == scores


# --- The fee model ---

def test_every_reputation_reward_was_paid_for_with_one_fee(system):
    """
    The anti-farming invariant: reputation is only minted for fulfilled promises, and
    every promise paid the protocol fee. So fees collected == fee x promises, and
    reputation minted == fees / point price, whatever a script does.
    """
    s = system
    for borrower, lender in [(s.bob, s.alice), (s.carol, s.bob), (s.alice, s.carol), (s.bob, s.carol)]:
        s.loan.repayLoan(loan(s, borrower, lender), sender=borrower)
    total_before = s.rep.totalReputation()
    run_oracle(s)

    promises = 4
    assert s.usdc.balanceOf(s.treasury) == promises * s.fee
    assert s.rep.totalReputation() - total_before == promises * s.reward


def test_a_colluding_pair_pays_a_fee_for_every_reward(system):
    """Wash loans of nothing between two accounts are possible, but each reward costs one fee."""
    s = system
    spent_before = s.usdc.balanceOf(s.bob) + s.usdc.balanceOf(s.carol)
    for borrower, lender in [(s.bob, s.carol), (s.carol, s.bob)] * 3:
        s.loan.repayLoan(loan(s, borrower, lender, principal=0, interest=0, stake=0), sender=borrower)
    run_oracle(s)

    gained = s.rep.reputationScores(s.bob) + s.rep.reputationScores(s.carol) - 2 * START_REP
    spent = spent_before - s.usdc.balanceOf(s.bob) - s.usdc.balanceOf(s.carol)
    assert gained == 6 * s.reward
    assert spent == 6 * s.fee


def test_cannot_farm_with_a_loan_to_yourself(system):
    s = system
    with reverts("LoanScript: Cannot borrow from yourself"):
        s.loan.requestLoan(s.bob, 0, 0, DURATION, 0, sender=s.bob)
    # ...nor by writing your own script: the engine itself refuses a promise to yourself
    action_id = action_id_of(s.engine.monitoredAction(s.bob, sender=s.bob))
    with reverts("CalculusEngine: Cannot promise to yourself"):
        s.engine.monitoredPromise(action_id, s.bob, s.bob, s.usdc, 0, chain.pending_timestamp + 10, sender=s.bob)


def test_reward_is_proportional_to_the_fee_paid():
    """With a 1% fee, a loan ten times larger pays ten times the fee and earns ten times the reputation."""
    s = deploy_system(fee_bps=100, min_fee=E18 // 10, point_price=E18 // 25, starting_reputation=0)
    small = loan(s, s.bob, s.alice, principal=100 * E18, interest=0, stake=0)
    large = loan(s, s.carol, s.alice, principal=1_000 * E18, interest=0, stake=0)
    tiny = loan(s, s.alice, s.bob, principal=1 * E18, interest=0, stake=0)  # pays the minimum fee
    for loan_id, borrower in ((small, s.bob), (large, s.carol), (tiny, s.alice)):
        s.loan.repayLoan(loan_id, sender=borrower)
    assert [s.engine.promises(promise_of(s, l))['feePaid'] for l in (small, large, tiny)] == [E18, 10 * E18, E18 // 10]
    assert s.usdc.balanceOf(s.treasury) == 11 * E18 + E18 // 10

    run_oracle(s)

    assert s.rep.reputationScores(s.bob) == 25 * E18
    assert s.rep.reputationScores(s.carol) == 250 * E18
    assert s.rep.reputationScores(s.alice) == 25 * E18 // 10
    # Reputation in existence is exactly the fees collected divided by the point price
    assert s.rep.totalReputation() * (E18 // 25) // E18 == s.usdc.balanceOf(s.treasury)


def test_new_identities_start_with_nothing_and_earn_only_by_keeping_promises():
    s = deploy_system(starting_reputation=0)
    assert [s.rep.reputationScores(u) for u in (s.alice, s.bob, s.carol)] == [0, 0, 0]
    with reverts("Insufficient liquid reputation"):
        s.loan.requestLoan(s.alice, E18, 0, DURATION, 1, sender=s.bob)  # nothing to bond yet
    first = loan(s, s.bob, s.alice, stake=0)  # the first rung is unbonded
    s.loan.repayLoan(first, sender=s.bob)
    run_oracle(s)
    assert s.rep.reputationScores(s.bob) == s.reward
    loan(s, s.bob, s.alice, stake=s.reward)  # and now there is something to bond


# --- Dividends ---

def test_reputation_holders_are_discovered_from_mint_events(system):
    s = system
    assert get_reputation_holders(s.rep) == [s.alice.address, s.bob.address, s.carol.address]


def test_dividend_drop_end_to_end(system):
    s = system
    # Give the three users different reputations through real activity
    s.loan.repayLoan(loan(s, s.bob, s.alice), sender=s.bob)
    broken = loan(s, s.carol, s.alice)
    advance(DURATION + 1)
    s.loan.claimDefault(broken, sender=s.alice)
    run_oracle(s)

    pool = s.treasury.distributable()  # this Treasury shares out its whole fund: the two protocol fees
    assert pool == 2 * s.fee == s.usdc.balanceOf(s.treasury)
    holders = get_reputation_holders(s.rep)
    shares, root, total_rep = calculate_dividend_shares(s.rep, holders, pool)

    assert total_rep == s.rep.totalReputation()
    to_holders = sum(share["amount"] for share in shares)
    assert pool - len(shares) < to_holders <= pool
    by_account = {share["account"]: share["amount"] for share in shares}
    assert by_account[s.bob.address] > by_account[s.alice.address] > by_account[s.carol.address] > 0
    for share in shares:  # pro rata, rounded down
        assert share["amount"] == share["reputation"] * pool // total_rep

    s.treasury.createDividendCycle(root, to_holders, sender=s.admin)
    cycle_id = s.treasury.getNumberOfCycles() - 1

    for user in (s.alice, s.bob, s.carol):
        amount = by_account[user.address]
        proof = get_merkle_proof(shares, user.address, amount)
        with reverts("Invalid Merkle proof"):
            s.treasury.claimDividend(cycle_id, amount + 1, proof, sender=user)
        before = s.usdc.balanceOf(user)
        s.treasury.claimDividend(cycle_id, amount, proof, sender=user)
        assert s.usdc.balanceOf(user) == before + amount

    dust = pool - to_holders
    assert s.usdc.balanceOf(s.treasury) == dust == s.treasury.payoutFund()  # carried to the next cycle
    assert s.treasury.reservedForDividends() == 0


def test_user_with_no_reputation_gets_no_dividend_leaf(system):
    s = system
    # A broken promise on the record does not change anyone's share: dividends follow reputation alone.
    s.updater.applyReputationChanges([], [(s.carol.address, START_REP, "PROMISE_DEFAULTED:99")], sender=s.oracle)
    shares, _, _ = calculate_dividend_shares(s.rep, get_reputation_holders(s.rep), 90 * E18)
    assert [share["amount"] for share in shares] == [30 * E18] * 3

    s.rep.grantRole(s.rep.UPDATER_ROLE(), s.admin, sender=s.admin)
    s.rep.slash(s.carol, START_REP, sender=s.admin)  # wiped out
    shares, _, _ = calculate_dividend_shares(s.rep, get_reputation_holders(s.rep), 100 * E18)
    assert [share["account"] for share in shares] == [s.alice.address, s.bob.address]
    assert [share["amount"] for share in shares] == [50 * E18, 50 * E18]


def test_first_users_do_not_collect_all_the_early_fees():
    """
    With the Treasury releasing a tenth of its fund per cycle, the first holder of reputation
    receives the early fees gradually, not all at once.
    """
    s = deploy_system(starting_reputation=0, release=E18 // 10, cycle_interval=DURATION)
    for _ in range(4):  # Bob is the only user with reputation: 100 points, 4 DMD of fees paid
        s.loan.repayLoan(loan(s, s.bob, s.alice, stake=0), sender=s.bob)
    run_oracle(s)
    advance(DURATION)

    def run_cycle():
        pool = s.treasury.distributable()
        shares, root, _ = calculate_dividend_shares(s.rep, get_reputation_holders(s.rep), pool)
        s.treasury.createDividendCycle(root, sum(share["amount"] for share in shares), sender=s.admin)
        return pool, shares

    pool, shares = run_cycle()
    assert pool == 4 * s.fee // 10
    assert [(share["account"], share["amount"]) for share in shares] == [(s.bob.address, pool)]
    assert s.treasury.payoutFund() == 4 * s.fee - pool

    advance(DURATION)
    pool2, _ = run_cycle()
    assert pool2 == (4 * s.fee - pool) // 10  # a tenth of what was left
    assert s.usdc.balanceOf(s.treasury) == (
        s.treasury.reservedForDividends() + s.treasury.payoutFund() + s.treasury.uncounted())


# --- A lender's tool (not part of the protocol): reading a borrower's record from the log ---

def test_repayment_history_is_read_from_the_promise_log(system):
    from rain.ladder import repayment_history
    s = system
    for principal in (100, 400, 250):
        s.loan.repayLoan(loan(s, s.bob, s.alice, principal=principal * E18, interest=0), sender=s.bob)
    broken = loan(s, s.bob, s.alice, principal=900 * E18, interest=0)
    s.loan.repayLoan(loan(s, s.carol, s.alice, principal=700 * E18, interest=0), sender=s.carol)
    advance(DURATION + 1)
    s.loan.claimDefault(broken, sender=s.alice)

    assert repayment_history(s.engine, s.bob.address) == dict(kept=3, broken=1, largest_kept=400 * E18)
    assert repayment_history(s.engine, s.carol.address, asset=s.usdc.address) == dict(kept=1, broken=0, largest_kept=700 * E18)
    assert repayment_history(s.engine, s.alice.address) == dict(kept=0, broken=0, largest_kept=0)  # lending is not a promise
    assert repayment_history(s.engine, s.bob.address, asset=s.rct.address) == dict(kept=0, broken=0, largest_kept=0)
