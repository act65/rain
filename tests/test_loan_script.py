"""
LoanScript: the reference application built on the Rain primitives.

Claims tested, taken from the notes and the blog post:
  - the script holds no protocol role; it can only do what the borrower and lender allowed;
  - the borrower's reputation bond is locked until the loan is cancelled, repaid or defaulted,
    and only the script can unlock it;
  - the promise to repay (and its fee) exists only once the loan is funded, and the term
    starts at funding;
  - repayment fulfils the promise, makes the lender whole and returns the bond;
  - default is only possible after the deadline; it marks the promise Defaulted, destroys
    the bond, mints an RCT for the full amount owed to the lender and makes the borrower
    delinquent at once ("circuit breaker");
  - a delinquent user cannot borrow;
  - a defaulter clears their name only by re-acquiring and burning the RCT.
"""
import pytest
from helpers import accounts, action_id_of, advance, chain, ev, project, promise_id_of, reverts, token_id_of

E18 = 10**18
START_REP = 1_000 * E18
PRINCIPAL = 1_000 * E18
INTEREST = 50 * E18
STAKE = 200 * E18
DURATION = 30 * 24 * 60 * 60
NONE, REQUESTED, ACTIVE, REPAID, DEFAULTED, CANCELLED = range(6)  # LoanScript.Status
P_PENDING, P_FULFILLED, P_DEFAULTED = 0, 1, 2  # CalculusEngine.PromiseStatus


def purpose(loan_id):
    return loan_id.to_bytes(32, "big")


def request(s, borrower=None, lender=None, principal=PRINCIPAL, interest=INTEREST, duration=DURATION, stake=STAKE):
    borrower = borrower or s.bob
    lender = lender or s.alice
    tx = s.loan.requestLoan(lender, principal, interest, duration, stake, sender=borrower)
    return ev(tx)['LoanRequested']['loanId'], tx


def funded(s, **kwargs):
    loan_id, _ = request(s, **kwargs)
    s.loan.fundLoan(loan_id, sender=kwargs.get("lender") or s.alice)
    return loan_id


def defaulted(s, **kwargs):
    loan_id = funded(s, **kwargs)
    advance(kwargs.get("duration", DURATION) + 1)
    tx = s.loan.claimDefault(loan_id, sender=kwargs.get("lender") or s.alice)
    return loan_id, ev(tx)['LoanDefaulted']['rctId']


def test_script_holds_no_protocol_role(system):
    s = system
    for contract in (s.engine, s.rep, s.treasury, s.updater):
        assert not contract.hasRole(contract.DEFAULT_ADMIN_ROLE(), s.loan)
    assert not s.rep.hasRole(s.rep.UPDATER_ROLE(), s.loan)


# --- requestLoan ---

def test_request_bonds_reputation_and_costs_nothing_else(system):
    s = system
    bob_before, alice_before = s.usdc.balanceOf(s.bob), s.usdc.balanceOf(s.alice)
    loan_id, tx = request(s)

    assert loan_id == s.loan.loanCount() == 1
    loan = s.loan.loans(loan_id)
    assert (loan['borrower'], loan['lender'], loan['principal'], loan['interest']) == (s.bob, s.alice, PRINCIPAL, INTEREST)
    assert (loan['reputationStake'], loan['duration'], loan['deadline'], loan['promiseId'], loan['status']) == (
        STAKE, DURATION, 0, 0, REQUESTED)

    # The bond is held by the script
    assert s.rep.stakedReputation(s.bob) == STAKE
    assert s.rep.getLiquidReputation(s.bob) == START_REP - STAKE
    assert s.rep.getStake(s.loan, purpose(loan_id)) == (s.bob, STAKE, True, False)

    # No promise, no fee, no money moved yet
    assert 'PromiseCreated' not in ev(tx)
    assert s.usdc.balanceOf(s.treasury) == 0
    assert (s.usdc.balanceOf(s.bob), s.usdc.balanceOf(s.alice)) == (bob_before, alice_before)

    event = ev(tx)['LoanRequested']
    assert (event['borrower'], event['lender'], event['principal']) == (s.bob, s.alice, PRINCIPAL)


def test_request_requires_enough_liquid_reputation(system):
    s = system
    with reverts("Insufficient liquid reputation"):
        request(s, stake=START_REP + 1)
    request(s, stake=600 * E18)
    with reverts("Insufficient liquid reputation"):
        request(s, stake=401 * E18)  # only 400 left


def test_request_requires_the_borrowers_stake_allowance(system):
    s = system
    s.rep.approveStake(s.loan, STAKE - 1, sender=s.bob)
    with reverts("Insufficient stake allowance"):
        request(s)
    assert s.rep.stakedReputation(s.bob) == 0


def test_cannot_borrow_from_yourself(system):
    with reverts("LoanScript: Cannot borrow from yourself"):
        request(system, borrower=system.bob, lender=system.bob)


def test_user_without_reputation_cannot_bond(system):
    s = system
    s.rep.approveStake(s.loan, 1, sender=s.outsider)
    with reverts("Insufficient liquid reputation"):
        request(s, borrower=s.outsider, stake=1)


# --- cancelLoan ---

def test_borrower_can_cancel_an_unfunded_request_and_recover_the_bond(system):
    s = system
    loan_id, _ = request(s)
    advance(10 * DURATION)  # however long the lender ignores it
    chain.mine()

    for caller in (s.alice, s.carol):
        with reverts("Not the borrower"):
            s.loan.cancelLoan(loan_id, sender=caller)

    tx = s.loan.cancelLoan(loan_id, sender=s.bob)
    assert s.loan.loans(loan_id)['status'] == CANCELLED
    assert s.rep.stakedReputation(s.bob) == 0
    assert ev(tx)['LoanCancelled']['loanId'] == loan_id

    with reverts("Loan not requested"):
        s.loan.cancelLoan(loan_id, sender=s.bob)
    with reverts("Loan not requested"):
        s.loan.fundLoan(loan_id, sender=s.alice)


def test_funded_loan_cannot_be_cancelled(system):
    s = system
    loan_id = funded(s)
    with reverts("Loan not requested"):
        s.loan.cancelLoan(loan_id, sender=s.bob)
    assert s.rep.stakedReputation(s.bob) == STAKE


# --- fundLoan ---

def test_fund_creates_the_promise_charges_the_fee_and_pays_the_principal(system):
    s = system
    loan_id, _ = request(s)
    advance(5 * 24 * 60 * 60)  # the lender takes five days to decide
    chain.mine()
    alice_before, bob_before = s.usdc.balanceOf(s.alice), s.usdc.balanceOf(s.bob)

    tx = s.loan.fundLoan(loan_id, sender=s.alice)

    loan = s.loan.loans(loan_id)
    assert loan['status'] == ACTIVE
    assert loan['deadline'] == tx.timestamp + DURATION  # the full term starts now

    # One promise: the borrower's, for principal + interest
    promise = s.engine.promises(loan['promiseId'])
    assert (promise['promisor'], promise['promisee'], promise['asset'], promise['amount'], promise['deadline'], promise['status']) == (
        s.bob, s.alice, s.usdc.address, PRINCIPAL + INTEREST, loan['deadline'], P_PENDING)
    assert s.engine.actions(promise['actionId']) == (s.bob, s.loan.address)
    assert s.loan.loanForPromise(loan['promiseId']) == loan_id
    assert len(ev(tx)['PromiseCreated']) == 1

    # Money: principal lender -> borrower; one fee borrower -> treasury
    assert s.usdc.balanceOf(s.alice) == alice_before - PRINCIPAL
    assert s.usdc.balanceOf(s.bob) == bob_before + PRINCIPAL - s.fee
    assert s.usdc.balanceOf(s.treasury) == s.fee
    event = ev(tx)['LoanFunded']
    assert (event['loanId'], event['promiseId'], event['deadline']) == (loan_id, loan['promiseId'], loan['deadline'])


def test_only_the_named_lender_can_fund_and_only_once(system):
    s = system
    loan_id, _ = request(s)
    for caller in (s.bob, s.carol):
        with reverts("Not the lender"):
            s.loan.fundLoan(loan_id, sender=caller)
    s.loan.fundLoan(loan_id, sender=s.alice)
    with reverts("Loan not requested"):
        s.loan.fundLoan(loan_id, sender=s.alice)
    with reverts("Not the lender"):
        s.loan.fundLoan(999, sender=s.alice)  # unknown loan


def test_fund_needs_the_lenders_allowance_for_this_script(system):
    s = system
    loan_id, _ = request(s)
    s.engine.approveScript(s.loan, s.usdc, PRINCIPAL - 1, sender=s.alice)
    with reverts("CalculusEngine: Insufficient script allowance"):
        s.loan.fundLoan(loan_id, sender=s.alice)
    assert s.loan.loans(loan_id)['status'] == REQUESTED
    assert s.usdc.balanceOf(s.treasury) == 0  # the whole funding reverted, fee included


def test_fund_needs_the_borrowers_authorization_and_fee_allowance(system):
    s = system
    loan_id, _ = request(s)
    s.engine.setScriptAuthorization(s.loan, False, sender=s.bob)
    with reverts("CalculusEngine: Script not authorized by user"):
        s.loan.fundLoan(loan_id, sender=s.alice)

    s.engine.setScriptAuthorization(s.loan, True, sender=s.bob)
    s.engine.approveScript(s.loan, s.usdc, s.fee - 1, sender=s.bob)
    with reverts("CalculusEngine: Insufficient script allowance"):
        s.loan.fundLoan(loan_id, sender=s.alice)

    s.loan.cancelLoan(loan_id, sender=s.bob)  # the borrower can always back out
    assert s.rep.stakedReputation(s.bob) == 0


def test_cannot_fund_a_borrower_who_became_delinquent(system):
    s = system
    pending, _ = request(s, lender=s.carol)
    defaulted(s)
    with reverts("LoanScript: Borrower is delinquent"):
        s.loan.fundLoan(pending, sender=s.carol)


# --- repayLoan ---

def test_repay_makes_lender_whole_and_returns_the_bond(system):
    s = system
    alice_start, bob_start = s.usdc.balanceOf(s.alice), s.usdc.balanceOf(s.bob)
    loan_id = funded(s)

    tx = s.loan.repayLoan(loan_id, sender=s.bob)

    assert s.usdc.balanceOf(s.alice) == alice_start + INTEREST
    assert s.usdc.balanceOf(s.bob) == bob_start - INTEREST - s.fee
    assert s.usdc.balanceOf(s.treasury) == s.fee  # conservation: only the fee left the two parties
    loan = s.loan.loans(loan_id)
    assert loan['status'] == REPAID
    assert s.engine.promises(loan['promiseId'])['status'] == P_FULFILLED
    assert s.rep.stakedReputation(s.bob) == 0
    assert s.rep.getStake(s.loan, purpose(loan_id)) == (s.bob, STAKE, True, True)
    assert s.rep.reputationScores(s.bob) == START_REP  # the bond came back whole
    assert not s.rep.isDelinquent(s.bob)
    assert ev(tx)['LoanRepaid']['loanId'] == loan_id
    assert ev(tx)['ValueTransferred']['amount'] == PRINCIPAL + INTEREST


def test_lender_earns_no_reputation_for_lending(system):
    """Only the borrower made a promise, so only the borrower's promise is in the log."""
    s = system
    loan_id = funded(s)
    tx = s.loan.repayLoan(loan_id, sender=s.bob)
    assert ev(tx)['PromiseFulfilled']['promiseId'] == s.loan.loans(loan_id)['promiseId']
    assert s.engine.promises(2)['promisor'] == "0x" + "00" * 20  # there is no second promise


def test_only_borrower_can_repay_and_only_an_active_loan(system):
    s = system
    loan_id, _ = request(s)
    with reverts("Loan not active"):
        s.loan.repayLoan(loan_id, sender=s.bob)  # not yet funded
    s.loan.fundLoan(loan_id, sender=s.alice)
    for caller in (s.alice, s.carol):
        with reverts("Not the borrower"):
            s.loan.repayLoan(loan_id, sender=caller)
    s.loan.repayLoan(loan_id, sender=s.bob)
    with reverts("Loan not active"):
        s.loan.repayLoan(loan_id, sender=s.bob)


def test_repay_right_up_to_the_deadline_but_not_after(system):
    s = system
    on_time, late = funded(s, stake=10 * E18), funded(s, lender=s.carol, stake=10 * E18)
    advance(DURATION - 60)
    s.loan.repayLoan(on_time, sender=s.bob)
    advance(120)
    with reverts("Loan past due"):
        s.loan.repayLoan(late, sender=s.bob)


def test_repay_fails_without_funds_and_leaves_loan_active(system):
    s = system
    loan_id = funded(s)
    s.usdc.transfer(s.carol, s.usdc.balanceOf(s.bob), sender=s.bob)  # Bob spends everything
    with reverts("ERC20: transfer amount exceeds balance"):
        s.loan.repayLoan(loan_id, sender=s.bob)
    assert s.loan.loans(loan_id)['status'] == ACTIVE
    assert s.rep.stakedReputation(s.bob) == STAKE


def test_loan_without_a_reputation_bond_works(system):
    s = system
    loan_id = funded(s, stake=0)
    s.loan.repayLoan(loan_id, sender=s.bob)
    assert s.loan.loans(loan_id)['status'] == REPAID


# --- The bond cannot be freed behind the script's back ---

def test_borrower_cannot_release_their_bond_while_the_loan_is_active(system):
    s = system
    loan_id = funded(s)
    for caller in (s.bob, s.alice, s.outsider):
        with reverts("Stake does not exist"):
            s.rep.releaseStake(purpose(loan_id), sender=caller)
    assert s.rep.stakedReputation(s.bob) == STAKE
    with reverts("Insufficient liquid reputation"):
        request(s, lender=s.carol, stake=START_REP - STAKE + 1)  # the bonded part cannot be bonded again


# --- claimDefault ---

def test_cannot_claim_default_before_deadline_or_on_inactive_loan(system):
    s = system
    loan_id, _ = request(s)
    advance(DURATION + 1)
    with reverts("Loan not active"):
        s.loan.claimDefault(loan_id, sender=s.alice)  # never funded: nothing was promised
    s.loan.fundLoan(loan_id, sender=s.alice)
    with reverts("Deadline not passed"):
        s.loan.claimDefault(loan_id, sender=s.alice)

    repaid = funded(s, lender=s.carol)
    s.loan.repayLoan(repaid, sender=s.bob)
    advance(DURATION + 1)
    with reverts("Loan not active"):
        s.loan.claimDefault(repaid, sender=s.carol)


def test_default_forfeits_the_bond_mints_rct_and_trips_the_circuit_breaker(system):
    s = system
    loan_id = funded(s)
    promise_id = s.loan.loans(loan_id)['promiseId']
    total_before = s.rep.totalReputation()
    advance(DURATION + 1)

    tx = s.loan.claimDefault(loan_id, sender=s.alice)
    rct_id = ev(tx)['LoanDefaulted']['rctId']

    assert s.loan.loans(loan_id)['status'] == DEFAULTED
    assert s.engine.promises(promise_id)['status'] == P_DEFAULTED
    assert ev(tx)['PromiseDefaulted']['promiseId'] == promise_id

    # The bond is destroyed immediately, without waiting for the oracle
    assert s.rep.reputationScores(s.bob) == START_REP - STAKE
    assert s.rep.stakedReputation(s.bob) == 0
    assert s.rep.totalReputation() == total_before - STAKE
    assert ev(tx)['StakeForfeited']['reputationBurned'] == STAKE
    assert s.rep.reputationScores(s.alice) == START_REP  # nobody receives it

    # The lender holds a claim for everything that was promised
    assert s.rct.ownerOf(rct_id) == s.alice
    c = s.rct.claims(rct_id)
    assert (c['promiseId'], c['defaulterAddress'], c['originalLenderAddress'], c['loanContractAddress']) == (
        promise_id, s.bob, s.alice, s.loan.address)
    assert c['shortfallAmount'] == PRINCIPAL + INTEREST == s.engine.promises(promise_id)['amount']
    assert s.rct.debtCount(s.bob) == 1
    assert s.rep.isDelinquent(s.bob)

    with reverts("Loan not active"):
        s.loan.claimDefault(loan_id, sender=s.alice)


@pytest.mark.parametrize("stake", [0, 50 * E18, 900 * E18])
def test_the_penalty_scales_with_the_bond(system, stake):
    s = system
    defaulted(s, stake=stake)
    assert s.rep.reputationScores(s.bob) == START_REP - stake


def test_anyone_can_trigger_a_default_after_the_deadline(system):
    """Characterisation: claimDefault is permissionless; the RCT still goes to the lender."""
    s = system
    loan_id = funded(s)
    advance(DURATION + 1)
    tx = s.loan.claimDefault(loan_id, sender=s.outsider)
    assert s.rct.ownerOf(ev(tx)['LoanDefaulted']['rctId']) == s.alice


def test_delinquent_borrower_cannot_open_new_loans(system):
    s = system
    defaulted(s)
    with reverts("LoanScript: Borrower is delinquent"):
        request(s, lender=s.carol)
    # ...but can still be a lender
    loan_id, _ = request(s, borrower=s.carol, lender=s.bob)
    s.loan.fundLoan(loan_id, sender=s.bob)


def test_delinquent_borrower_can_still_repay_other_loans(system):
    s = system
    long_loan = funded(s, lender=s.carol, duration=10 * DURATION)
    defaulted(s)  # a second, shorter loan from Alice goes bad
    assert s.rep.isDelinquent(s.bob)
    s.loan.repayLoan(long_loan, sender=s.bob)
    assert s.loan.loans(long_loan)['status'] == REPAID
    assert s.rep.isDelinquent(s.bob)  # repaying another loan does not clear the default
    assert s.rep.reputationScores(s.bob) == START_REP - STAKE  # only the defaulted loan's bond was lost


def test_bonds_bound_what_concurrent_defaults_can_cost_and_each_is_lost(system):
    s = system
    first = funded(s, stake=400 * E18)
    second = funded(s, lender=s.carol, stake=600 * E18)
    with reverts("Insufficient liquid reputation"):
        request(s, lender=s.carol, stake=1)  # everything is bonded
    advance(DURATION + 1)
    s.loan.claimDefault(first, sender=s.alice)
    s.loan.claimDefault(second, sender=s.carol)
    assert s.rep.reputationScores(s.bob) == 0
    assert s.rct.debtCount(s.bob) == 2


# --- resolveDefault ---

def test_resolve_default_burns_rct_and_clears_delinquency_but_not_the_penalty(system):
    s = system
    loan_id, rct_id = defaulted(s)
    s.rct.transferFrom(s.alice, s.bob, rct_id, sender=s.alice)  # settled off-chain
    s.rct.approve(s.loan.address, rct_id, sender=s.bob)

    tx = s.loan.resolveDefault(rct_id, sender=s.bob)

    with reverts("ERC721: invalid token ID"):
        s.rct.ownerOf(rct_id)
    assert s.rct.debtCount(s.bob) == 0
    assert not s.rep.isDelinquent(s.bob)
    event = ev(tx)['LoanResolved']
    assert (event['loanId'], event['rctId']) == (loan_id, rct_id)
    # The history is not rewritten
    assert s.engine.promises(s.loan.loans(loan_id)['promiseId'])['status'] == P_DEFAULTED
    assert s.loan.loans(loan_id)['status'] == DEFAULTED
    assert s.rep.reputationScores(s.bob) == START_REP - STAKE
    # and the borrower can borrow again
    request(s)


def test_resolve_default_requirements(system):
    s = system
    _, rct_id = defaulted(s)

    with reverts("Only the original defaulter can resolve their own debt"):
        s.loan.resolveDefault(rct_id, sender=s.alice)  # the holder is not the defaulter
    with reverts("You must own the RCT to resolve the default"):
        s.loan.resolveDefault(rct_id, sender=s.bob)  # the defaulter does not hold it

    s.rct.transferFrom(s.alice, s.bob, rct_id, sender=s.alice)
    with reverts("ERC721: burn caller is not owner nor approved"):
        s.loan.resolveDefault(rct_id, sender=s.bob)  # LoanScript not approved to burn
    assert s.rep.isDelinquent(s.bob)


def test_multiple_defaults_need_multiple_resolutions(system):
    s = system
    first = funded(s, stake=100 * E18)
    second = funded(s, lender=s.carol, stake=100 * E18)
    advance(DURATION + 1)
    rct1 = ev(s.loan.claimDefault(first, sender=s.alice))['LoanDefaulted']['rctId']
    rct2 = ev(s.loan.claimDefault(second, sender=s.carol))['LoanDefaulted']['rctId']

    s.rct.transferFrom(s.alice, s.bob, rct1, sender=s.alice)
    s.rct.approve(s.loan.address, rct1, sender=s.bob)
    s.loan.resolveDefault(rct1, sender=s.bob)
    assert s.rep.isDelinquent(s.bob)

    s.rct.transferFrom(s.carol, s.bob, rct2, sender=s.carol)
    s.rct.approve(s.loan.address, rct2, sender=s.bob)
    s.loan.resolveDefault(rct2, sender=s.bob)
    assert not s.rep.isDelinquent(s.bob)


def test_rct_can_be_traded_before_resolution(system):
    s = system
    _, rct_id = defaulted(s)
    s.rct.transferFrom(s.alice, s.carol, rct_id, sender=s.alice)  # Alice sells the claim
    assert s.rep.isDelinquent(s.bob)
    s.rct.transferFrom(s.carol, s.bob, rct_id, sender=s.carol)  # Bob buys it back
    s.rct.approve(s.loan.address, rct_id, sender=s.bob)
    s.loan.resolveDefault(rct_id, sender=s.bob)
    assert not s.rep.isDelinquent(s.bob)


def test_lender_can_forgive_the_debt_leaving_nothing_locked(system):
    s = system
    _, rct_id = defaulted(s)
    s.rct.burn(rct_id, sender=s.alice)
    assert not s.rep.isDelinquent(s.bob)
    assert s.rep.stakedReputation(s.bob) == 0
    assert s.rep.getLiquidReputation(s.bob) == START_REP - STAKE
