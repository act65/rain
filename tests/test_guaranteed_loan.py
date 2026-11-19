"""
GuaranteedLoanScript: a loan that a guarantor answers for (vouching), built on the Rain primitives.

Claims tested:
  - nothing happens without each party's own act: the borrower asks, the guarantor agrees, the lender funds;
  - the loan is two promises of the amount due (borrower to guarantor, guarantor to lender), each paying its fee;
  - a repayment goes straight to the lender and keeps both promises;
  - if the borrower defaults, the claim on them goes to the guarantor, who has the grace period to pay the lender;
  - if the guarantor pays, the lender is whole and the guarantor's promise is kept;
  - if not, the guarantor's promise is broken too and the lender holds a claim on the guarantor;
  - on the log, the borrower's promise was to the guarantor: a reader who trusts only the lender learns
    nothing about the borrower from it, and learns about the guarantor from the promise made to the lender;
  - the model (rain.model.Economy.guaranteed_loan) reproduces the contracts on all three paths.
"""
import pytest
from helpers import MAX_UINT, E18, advance, chain, deploy_system, ev, project, reverts

from rain.model import Economy
from rain.record import read_entries, weigh
from rain.reputation import process_promise_log, to_update_tuples

PRINCIPAL, INTEREST, DUE = 1_000 * E18, 50 * E18, 1_050 * E18
DURATION, GRACE = 30 * 24 * 60 * 60, 7 * 24 * 60 * 60
START_REP = 1_000 * E18
NONE, REQUESTED, GUARANTEED, ACTIVE, REPAID, CALLED, COVERED, GUARANTOR_DEFAULTED, CANCELLED = range(9)
P_PENDING, P_FULFILLED, P_DEFAULTED = 0, 1, 2


@pytest.fixture
def s():
    """Alice lends, Bob borrows, Carol guarantees. All three have set the script up."""
    s = deploy_system()
    s.gloan = project.GuaranteedLoanScript.deploy(s.engine.address, s.rep.address, s.rct.address, s.usdc.address, sender=s.admin)
    for user in (s.alice, s.bob, s.carol):
        s.engine.setScriptAuthorization(s.gloan.address, True, sender=user)
        s.engine.approveScript(s.gloan.address, s.usdc.address, MAX_UINT, sender=user)
    return s


def requested(s):
    tx = s.gloan.requestLoan(s.alice, s.carol, PRINCIPAL, INTEREST, DURATION, GRACE, sender=s.bob)
    return ev(tx)['LoanRequested']['loanId']


def funded(s):
    loan_id = requested(s)
    s.gloan.guarantee(loan_id, sender=s.carol)
    s.gloan.fundLoan(loan_id, sender=s.alice)
    return loan_id


def called(s):
    loan_id = funded(s)
    advance(DURATION + 1)
    tx = s.gloan.claimDefault(loan_id, sender=s.outsider)  # anyone can
    return loan_id, ev(tx)['GuaranteeCalled']['rctId']


def run_oracle(s):
    increases, broken, _ = process_promise_log(s.engine, s.rep, 0, chain.blocks.height)
    s.updater.applyReputationChanges(to_update_tuples(increases), to_update_tuples(broken), sender=s.oracle)


def balances(s):
    return [s.usdc.balanceOf(u) for u in (s.alice, s.bob, s.carol)]


def test_each_party_must_act_for_themselves(s):
    with reverts("GuaranteedLoan: Needs three parties"):
        s.gloan.requestLoan(s.alice, s.alice, PRINCIPAL, INTEREST, DURATION, GRACE, sender=s.bob)
    with reverts("GuaranteedLoan: Needs three parties"):
        s.gloan.requestLoan(s.alice, s.bob, PRINCIPAL, INTEREST, DURATION, GRACE, sender=s.bob)
    loan_id = requested(s)
    assert s.gloan.loans(loan_id)['status'] == REQUESTED
    with reverts("Loan not guaranteed"):
        s.gloan.fundLoan(loan_id, sender=s.alice)  # nobody is bound until the guarantor agrees
    for other in (s.alice, s.bob, s.outsider):
        with reverts("Not the guarantor"):
            s.gloan.guarantee(loan_id, sender=other)
    s.gloan.guarantee(loan_id, sender=s.carol)
    with reverts("Not the lender"):
        s.gloan.fundLoan(loan_id, sender=s.carol)
    before = balances(s)
    assert s.engine.promises(1)['promisor'] == "0x" + "00" * 20  # no promise exists yet
    assert before == [10_000 * E18] * 3


def test_borrower_or_guarantor_can_withdraw_before_funding(s):
    for who in (s.bob, s.carol):
        loan_id = requested(s)
        s.gloan.guarantee(loan_id, sender=s.carol)
        with reverts("Not the borrower or the guarantor"):
            s.gloan.cancelLoan(loan_id, sender=s.alice)
        s.gloan.cancelLoan(loan_id, sender=who)
        assert s.gloan.loans(loan_id)['status'] == CANCELLED
        with reverts("Loan not guaranteed"):
            s.gloan.fundLoan(loan_id, sender=s.alice)
    with reverts("Loan already funded or closed"):
        s.gloan.cancelLoan(funded(s), sender=s.carol)  # too late once the lender has paid


def test_funding_records_two_promises_and_each_promisor_pays_the_fee(s):
    loan_id = funded(s)
    loan = s.gloan.loans(loan_id)
    assert loan['status'] == ACTIVE
    borrowers, guarantors = s.engine.promises(loan['borrowerPromiseId']), s.engine.promises(loan['guarantorPromiseId'])
    assert (borrowers['promisor'], borrowers['promisee'], borrowers['amount']) == (s.bob, s.carol, DUE)
    assert (guarantors['promisor'], guarantors['promisee'], guarantors['amount']) == (s.carol, s.alice, DUE)
    assert guarantors['deadline'] - borrowers['deadline'] == GRACE
    assert borrowers['feePaid'] == guarantors['feePaid'] == s.fee
    assert balances(s) == [10_000 * E18 - PRINCIPAL, 10_000 * E18 + PRINCIPAL - s.fee, 10_000 * E18 - s.fee]
    assert s.gloan.loanForPromise(loan['borrowerPromiseId']) == s.gloan.loanForPromise(loan['guarantorPromiseId']) == loan_id


def test_repayment_goes_to_the_lender_and_keeps_both_promises(s):
    loan_id = funded(s)
    with reverts("Not the borrower"):
        s.gloan.repayLoan(loan_id, sender=s.carol)
    s.gloan.repayLoan(loan_id, sender=s.bob)
    loan = s.gloan.loans(loan_id)
    assert loan['status'] == REPAID
    assert s.engine.promises(loan['borrowerPromiseId'])['status'] == P_FULFILLED
    assert s.engine.promises(loan['guarantorPromiseId'])['status'] == P_FULFILLED
    assert balances(s) == [10_000 * E18 + INTEREST, 10_000 * E18 - INTEREST - s.fee, 10_000 * E18 - s.fee]
    run_oracle(s)
    assert s.rep.reputationScores(s.bob) == s.rep.reputationScores(s.carol) == START_REP + s.reward
    with reverts("Loan not active"):
        s.gloan.claimDefault(loan_id, sender=s.alice)


def test_a_default_calls_the_guarantor_who_receives_the_claim(s):
    loan_id = funded(s)
    with reverts("Deadline not passed"):
        s.gloan.claimDefault(loan_id, sender=s.alice)
    with reverts("Guarantee not called"):
        s.gloan.coverLoan(loan_id, sender=s.carol)
    advance(DURATION + 1)
    with reverts("Loan past due"):
        s.gloan.repayLoan(loan_id, sender=s.bob)
    rct_id = ev(s.gloan.claimDefault(loan_id, sender=s.outsider))['GuaranteeCalled']['rctId']
    loan = s.gloan.loans(loan_id)
    assert loan['status'] == CALLED
    assert s.engine.promises(loan['borrowerPromiseId'])['status'] == P_DEFAULTED
    assert s.engine.promises(loan['guarantorPromiseId'])['status'] == P_PENDING
    assert s.rct.ownerOf(rct_id) == s.carol  # the guarantor holds the claim on the borrower
    assert s.rct.claims(rct_id)['shortfallAmount'] == DUE
    assert s.rep.isDelinquent(s.bob) and not s.rep.isDelinquent(s.carol)


def test_the_guarantor_covers_and_the_lender_is_whole(s):
    loan_id, rct_id = called(s)
    with reverts("Not the guarantor"):
        s.gloan.coverLoan(loan_id, sender=s.bob)
    with reverts("Grace period not over"):
        s.gloan.claimGuarantorDefault(loan_id, sender=s.alice)
    s.gloan.coverLoan(loan_id, sender=s.carol)
    loan = s.gloan.loans(loan_id)
    assert loan['status'] == COVERED
    assert s.engine.promises(loan['guarantorPromiseId'])['status'] == P_FULFILLED
    assert balances(s) == [10_000 * E18 + INTEREST, 10_000 * E18 + PRINCIPAL - s.fee, 10_000 * E18 - DUE - s.fee]
    assert not s.rep.isDelinquent(s.carol) and s.rep.isDelinquent(s.bob)
    advance(GRACE + 1)
    with reverts("Guarantee not called"):
        s.gloan.claimGuarantorDefault(loan_id, sender=s.alice)  # it was honoured

    run_oracle(s)
    assert s.rep.reputationScores(s.carol) == START_REP + s.reward  # the guarantor kept their promise
    assert (s.rep.reputationScores(s.bob), s.rep.brokenScores(s.bob)) == (START_REP, s.reward)

    # The borrower settles with the guarantor and clears their name
    s.usdc.transfer(s.carol, DUE, sender=s.bob)
    s.rct.transferFrom(s.carol, s.bob, rct_id, sender=s.carol)
    s.rct.approve(s.gloan.address, rct_id, sender=s.bob)
    tx = s.gloan.resolveDefault(rct_id, sender=s.bob)
    assert ev(tx)['DefaultResolved']['loanId'] == loan_id
    assert not s.rep.isDelinquent(s.bob)


def test_a_guarantor_who_does_not_pay_is_the_lenders_defaulter(s):
    loan_id, borrowers_rct = called(s)
    advance(GRACE + 1)
    with reverts("Grace period over"):
        s.gloan.coverLoan(loan_id, sender=s.carol)
    tx = s.gloan.claimGuarantorDefault(loan_id, sender=s.outsider)
    rct_id = ev(tx)['GuarantorDefaulted']['rctId']
    loan = s.gloan.loans(loan_id)
    assert loan['status'] == GUARANTOR_DEFAULTED
    assert s.engine.promises(loan['guarantorPromiseId'])['status'] == P_DEFAULTED
    assert s.rct.ownerOf(rct_id) == s.alice and s.rct.claims(rct_id)['defaulterAddress'] == s.carol
    assert s.rct.ownerOf(borrowers_rct) == s.carol
    assert s.rep.isDelinquent(s.carol) and s.rep.isDelinquent(s.bob)
    assert balances(s) == [10_000 * E18 - PRINCIPAL, 10_000 * E18 + PRINCIPAL - s.fee, 10_000 * E18 - s.fee]
    run_oracle(s)
    assert s.rep.brokenScores(s.carol) == s.rep.brokenScores(s.bob) == s.reward
    with reverts("Only the original defaulter can resolve their own debt"):
        s.gloan.resolveDefault(rct_id, sender=s.alice)


def test_a_delinquent_guarantor_or_borrower_cannot_start_a_loan(s):
    called(s)  # Bob is now delinquent
    with reverts("GuaranteedLoan: Borrower is delinquent"):
        s.gloan.requestLoan(s.alice, s.carol, PRINCIPAL, INTEREST, DURATION, GRACE, sender=s.bob)
    # Bob as a guarantor for Carol
    tx = s.gloan.requestLoan(s.alice, s.bob, PRINCIPAL, INTEREST, DURATION, GRACE, sender=s.carol)
    loan_id = ev(tx)['LoanRequested']['loanId']
    s.gloan.guarantee(loan_id, sender=s.bob)
    with reverts("GuaranteedLoan: Guarantor is delinquent"):
        s.gloan.fundLoan(loan_id, sender=s.alice)


def test_what_a_reader_learns_from_a_guaranteed_loan(s):
    s.gloan.repayLoan(funded(s), sender=s.bob)
    entries = read_entries(s.engine)
    assert [(e.promisor, e.promisee, e.kept) for e in entries] == [
        (s.bob.address, s.carol.address, True), (s.carol.address, s.alice.address, True)]
    # Alice, reading as a lender who trusts only her own dealings:
    alices = {s.alice.address: 1.0}
    assert weigh(entries, s.bob.address, trust=alices).largest_repaid == 0  # Bob's promise was to his guarantor
    assert weigh(entries, s.carol.address, trust=alices).largest_repaid == DUE  # Carol's was to her


@pytest.mark.parametrize("path", ["repaid", "covered", "guarantor defaulted"])
def test_the_model_reproduces_the_contracts(path):
    s = deploy_system(fee_bps=100, min_fee=E18 // 10, point_price=E18 // 25)
    s.gloan = project.GuaranteedLoanScript.deploy(s.engine.address, s.rep.address, s.rct.address, s.usdc.address, sender=s.admin)
    for user in (s.alice, s.bob, s.carol):
        s.engine.setScriptAuthorization(s.gloan.address, True, sender=user)
        s.engine.approveScript(s.gloan.address, s.usdc.address, MAX_UINT, sender=user)
    eco = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.03)
    for name in ("alice", "bob", "carol"):
        eco.add_agent(name, money=10_000, reputation=1_000)

    loan_id = funded(s)
    model_loan = eco.guaranteed_loan("bob", "carol", "alice", 1_000, 50)
    if path == "repaid":
        s.gloan.repayLoan(loan_id, sender=s.bob)
        eco.repay_loan(model_loan)
    else:
        advance(DURATION + 1)
        s.gloan.claimDefault(loan_id, sender=s.alice)
        eco.default_loan(model_loan)
        if path == "covered":
            s.gloan.coverLoan(loan_id, sender=s.carol)
            eco.cover_loan(model_loan)
        else:
            advance(GRACE + 1)
            s.gloan.claimGuarantorDefault(loan_id, sender=s.alice)
            eco.guarantor_default(model_loan)
    run_oracle(s)

    for name in ("alice", "bob", "carol"):
        user, agent = getattr(s, name), eco.agents[name]
        assert s.usdc.balanceOf(user) / E18 == pytest.approx(agent.money, abs=1e-9), name
        assert s.rep.reputationScores(user) / E18 == pytest.approx(agent.reputation, abs=1e-9), name
        assert s.rep.brokenScores(user) / E18 == pytest.approx(agent.broken, abs=1e-9), name
        assert s.rep.isDelinquent(user) == agent.delinquent, name
    chain_log = [(e.promisor, e.promisee, e.amount / E18, e.kept) for e in read_entries(s.engine)]
    names = {s.alice.address: "alice", s.bob.address: "bob", s.carol.address: "carol"}
    assert sorted((names[a], names[b], amount, kept) for a, b, amount, kept in chain_log) == sorted(
        (e.promisor, e.promisee, e.amount, e.kept) for e in eco.log)
