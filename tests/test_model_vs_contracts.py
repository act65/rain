"""
The pure-Python Economy model against the real contracts.

One scenario is replayed through both: proportional fees, reputation earned in proportion to
the fee, a default with a clamped penalty, a reward lost to delinquency, decay of scores and of
an open bond, resolution, and two dividend cycles from the payout fund. The experiments in
`experiments/` rely on the model, so this is the evidence that the model describes the protocol.
"""
import pytest
from helpers import E18, PERIOD, advance, chain, deploy_system, ev

from rain.dividends import calculate_dividend_shares, get_reputation_holders
from rain.model import Economy
from rain.reputation import process_promise_log, to_update_tuples

DURATION = 20 * 24 * 60 * 60  # shorter than a decay period
FEE_RATE, MIN_FEE, POINT_PRICE, DECAY, RELEASE = 0.01, 0.1, 0.04, 0.03, 0.10
START = 1_000
NAMES = ("alice", "bob", "carol")
TOLERANCE = 1e-9  # the chain rounds down in 18-decimal fixed point; the model uses floats


def chain_loan(s, borrower, lender, principal, interest, bond, duration=DURATION):
    tx = s.loan.requestLoan(lender, int(principal * E18), int(interest * E18), duration, int(bond * E18), sender=borrower)
    loan_id = ev(tx)['LoanRequested']['loanId']
    s.loan.fundLoan(loan_id, sender=lender)
    return loan_id


def run_oracle(s):
    increases, decreases, _ = process_promise_log(s.engine, s.rep, 0, chain.blocks.height)
    s.updater.applyReputationChanges(to_update_tuples(increases), to_update_tuples(decreases), sender=s.oracle)


def assert_same_state(s, eco):
    for name in NAMES:
        user, agent = getattr(s, name), eco.agents[name]
        assert s.usdc.balanceOf(user) / E18 == pytest.approx(agent.money, abs=TOLERANCE), f"{name}: money"
        assert s.rep.reputationScores(user) / E18 == pytest.approx(agent.reputation, abs=TOLERANCE), f"{name}: reputation"
        assert s.rep.stakedReputation(user) / E18 == pytest.approx(agent.staked, abs=TOLERANCE), f"{name}: staked"
        assert s.rep.isDelinquent(user) == agent.delinquent, f"{name}: delinquent"
    assert s.rep.totalReputation() / E18 == pytest.approx(eco.total_reputation, abs=TOLERANCE)
    assert s.treasury.uncounted() / E18 == pytest.approx(eco.fee_pool, abs=TOLERANCE), "fees not yet in the fund"
    assert s.treasury.payoutFund() / E18 == pytest.approx(eco.reserve_fund, abs=TOLERANCE), "payout fund"


def dividend_cycle(s, eco):
    """Runs one cycle on both sides and checks the pool and every share."""
    pool = s.treasury.distributable()
    shares, root, _ = calculate_dividend_shares(s.rep, get_reputation_holders(s.rep), pool)
    to_holders = sum(share["amount"] for share in shares)
    s.treasury.createDividendCycle(root, to_holders, sender=s.admin)

    received_before = {name: eco.agents[name].dividends_received for name in NAMES}
    fund_before = eco.reserve_fund + eco.fee_pool
    paid = eco.pay_dividend(decay=False)  # on the chain decay follows the clock, not the dividend

    assert pool / E18 == pytest.approx(paid, abs=TOLERANCE), "pool"
    assert paid == pytest.approx(RELEASE * fund_before)
    by_account = {share["account"]: share["amount"] for share in shares}
    for name in NAMES:
        model_share = eco.agents[name].dividends_received - received_before[name]
        assert by_account.get(getattr(s, name).address, 0) / E18 == pytest.approx(model_share, abs=TOLERANCE), f"{name}: dividend"
        # the model pays at once; on the chain the money waits in the Treasury to be claimed
        eco.agents[name].money -= model_share
    # the chain keeps its rounding dust in the fund
    assert s.treasury.payoutFund() / E18 == pytest.approx(eco.reserve_fund, abs=TOLERANCE)
    return paid


def test_model_reproduces_the_contracts():
    s = deploy_system(
        retention=int((1 - DECAY) * 100) * E18 // 100, fee_bps=int(FEE_RATE * 10_000), min_fee=int(MIN_FEE * E18),
        point_price=int(POINT_PRICE * 100) * E18 // 100, starting_reputation=START * E18,
        release=int(RELEASE * 100) * E18 // 100,
    )
    eco = Economy.current_rules(min_fee=MIN_FEE, fee_rate=FEE_RATE, point_price=POINT_PRICE, decay_rate=DECAY, release=RELEASE)
    eco.add_agent("lender_of_last_resort")  # unused; shows other agents do not disturb the comparison
    for name in NAMES:
        eco.add_agent(name, money=10_000, reputation=START)
    assert s.rep.currentPeriod() == 0
    assert_same_state(s, eco)

    # 1. Bob borrows from Alice and repays: fee 1% of 105, reward fee / 0.04.
    a = chain_loan(s, s.bob, s.alice, 100, 5, 200)
    s.loan.repayLoan(a, sender=s.bob)
    eco.repay_loan(eco.loan("bob", "alice", 100, 5, 200))
    assert eco.agents["bob"].fees_paid == pytest.approx(1.05)

    # 2. Carol takes a long loan from Bob (minimum fee), then a short one from Alice which she
    #    defaults on (bond 950: the flat penalty is clamped), then repays the long one while delinquent.
    long_loan = chain_loan(s, s.carol, s.bob, 5, 1, 10, duration=10 * DURATION)
    short_loan = chain_loan(s, s.carol, s.alice, 300, 15, 950)
    advance(DURATION + 1)
    assert s.rep.currentPeriod() == 0  # still within the first decay period
    rct_id = ev(s.loan.claimDefault(short_loan, sender=s.alice))['LoanDefaulted']['rctId']
    s.loan.repayLoan(long_loan, sender=s.carol)

    m_long = eco.loan("carol", "bob", 5, 1, 10)
    m_short = eco.loan("carol", "alice", 300, 15, 950)
    eco.default_loan(m_short)
    eco.repay_loan(m_long)

    run_oracle(s)  # the model's oracle is instantaneous; the chain's runs here
    assert_same_state(s, eco)
    assert eco.agents["carol"].reputation == 0
    assert eco.agents["bob"].reputation == pytest.approx(START + 1.05 / POINT_PRICE)

    # 3. Alice requests a loan with a bond, and two decay periods pass before it is cancelled:
    #    scores, the total and the open bond all shrink by 0.97 ** 2.
    tx = s.loan.requestLoan(s.bob, 10 * E18, 0, DURATION, 100 * E18, sender=s.alice)
    chain_request = ev(tx)['LoanRequested']['loanId']
    model_request = eco.request_loan("alice", "bob", 10, bond=100)
    advance(2 * PERIOD)
    assert s.rep.currentPeriod() == 2
    eco.decay()
    eco.decay()
    assert eco.agents["alice"].staked == pytest.approx(100 * 0.97**2)
    assert_same_state(s, eco)
    s.loan.cancelLoan(chain_request, sender=s.alice)
    eco.cancel_loan(model_request)
    assert_same_state(s, eco)

    # 4. Carol settles: buys the claim back from Alice for the amount owed and burns it.
    owed = s.rct.claims(rct_id)['shortfallAmount']
    assert owed == 315 * E18
    s.usdc.transfer(s.alice, owed, sender=s.carol)
    s.rct.transferFrom(s.alice, s.carol, rct_id, sender=s.alice)
    s.rct.approve(s.loan, rct_id, sender=s.carol)
    s.loan.resolveDefault(rct_id, sender=s.carol)
    eco.resolve_default(m_short)
    run_oracle(s)  # a replay: nothing new
    assert_same_state(s, eco)

    # 5. A dividend cycle: a tenth of all fees so far, split pro rata; the rest stays in the fund.
    fees = 1.05 + 0.1 + 3.15  # the three promises' fees
    paid = dividend_cycle(s, eco)
    assert paid == pytest.approx(RELEASE * fees)
    assert eco.reserve_fund == pytest.approx((1 - RELEASE) * fees)
    assert_same_state(s, eco)

    # 6. More activity, then a second cycle: a tenth of (what was left + the new fee).
    b = chain_loan(s, s.bob, s.alice, 400, 20, 50)
    s.loan.repayLoan(b, sender=s.bob)
    eco.repay_loan(eco.loan("bob", "alice", 400, 20, 50))
    run_oracle(s)
    paid = dividend_cycle(s, eco)
    assert paid == pytest.approx(RELEASE * ((1 - RELEASE) * fees + 4.2))
    assert_same_state(s, eco)
