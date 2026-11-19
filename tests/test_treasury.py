"""
Treasury: fees in, dividends out.

Claims tested:
  - everything the Treasury receives goes into the payout fund, and a cycle shares out at
    most a fixed fraction of the fund, no more often than the cycle interval allows;
  - every unit of currency is reserved for a cycle, in the fund, or received and not yet counted;
  - a holder can claim exactly their leaf, once, before expiry, and a cycle never pays out
    more than it reserved;
  - the off-chain Merkle tree agrees with the on-chain verifier.

Most tests use a Treasury that shares out its whole fund each cycle with no waiting, so that
amounts are simple; the gradual release and the interval have their own tests at the end.
"""
import pytest
from helpers import E18, accounts, advance, deploy_treasury, ev, project, reverts

from rain.merkletree import OZMerkleTree, leaf_hash

CLAIM_PERIOD = 7 * 24 * 60 * 60
DAY = 24 * 60 * 60


@pytest.fixture(scope="function")
def usdc():
    token = project.CurrencyToken.deploy(sender=accounts[0])
    for i in range(4):
        token.mint(accounts[i], 1_000_000 * E18, sender=accounts[0])
    return token


@pytest.fixture(scope="function")
def treasury(usdc):
    return deploy_treasury(accounts[0], usdc, CLAIM_PERIOD, (E18, 0))  # release everything, no waiting


@pytest.fixture(scope="function")
def gradual(usdc):
    """A Treasury that shares out a tenth of its fund per cycle, at most once a day."""
    return deploy_treasury(accounts[0], usdc, CLAIM_PERIOD, (E18 // 10, DAY))


def make_cycle(treasury, usdc, rewards, fund=True):
    """Pays fees into the treasury and publishes a cycle for `rewards` ({account: amount}); returns (cycle_id, tree)."""
    manager = accounts[0]
    total = sum(rewards.values())
    if fund:
        usdc.transfer(treasury.address, total, sender=manager)
    tree = OZMerkleTree([leaf_hash(account.address, amount) for account, amount in rewards.items()])
    tx = treasury.createDividendCycle(tree.root, total, sender=manager)
    return ev(tx)['DividendCycleCreated']['cycleId'], tree


def claim(treasury, cycle_id, tree, account, amount):
    proof = tree.get_proof(leaf_hash(account.address, amount))
    return treasury.claimDividend(cycle_id, amount, proof, sender=account)


def books_balance(treasury, usdc):
    return usdc.balanceOf(treasury) == treasury.reservedForDividends() + treasury.payoutFund() + treasury.uncounted()


def test_deployment(gradual, usdc):
    admin = accounts[0]
    assert gradual.usdcToken() == usdc.address
    assert gradual.claimPeriodDuration() == CLAIM_PERIOD
    assert (gradual.releasePerCycle(), gradual.cycleInterval()) == (E18 // 10, DAY)
    assert gradual.hasRole(gradual.DEFAULT_ADMIN_ROLE(), admin)
    assert gradual.hasRole(gradual.MANAGER_ROLE(), admin)
    assert gradual.getNumberOfCycles() == 0
    assert (gradual.uncounted(), gradual.payoutFund(), gradual.distributable()) == (0, 0, 0)
    schedule = gradual.decaySchedule()
    with reverts("USDC token address cannot be zero"):
        project.Treasury.deploy("0x" + "00" * 20, CLAIM_PERIOD, schedule, sender=admin)
    with reverts("Decay schedule address cannot be zero"):
        project.Treasury.deploy(usdc.address, CLAIM_PERIOD, "0x" + "00" * 20, sender=admin)


def test_the_release_schedule_is_the_reputation_decay_and_cannot_be_changed(usdc):
    """One rate: the fund pays out the fraction reputation loses per period, once per period."""
    admin = accounts[0]
    rep = project.RainReputation.deploy(30 * DAY, 97 * E18 // 100, sender=admin)
    treasury = project.Treasury.deploy(usdc.address, CLAIM_PERIOD, rep.address, sender=admin)
    assert treasury.decaySchedule() == rep.address
    assert treasury.releasePerCycle() == E18 - rep.retentionPerPeriod() == 3 * E18 // 100
    assert treasury.cycleInterval() == rep.decayPeriod() == 30 * DAY
    assert not hasattr(treasury, "setRelease")

    # Reputation that never decayed would never be paid.
    everlasting = project.RainReputation.deploy(30 * DAY, E18, sender=admin)
    with reverts("Reputation must decay for fees to be paid out"):
        project.Treasury.deploy(usdc.address, CLAIM_PERIOD, everlasting.address, sender=admin)


def test_fees_received_join_the_fund_at_the_next_cycle(treasury, usdc):
    usdc.transfer(treasury.address, 500, sender=accounts[0])
    assert treasury.uncounted() == treasury.distributable() == 500 and treasury.payoutFund() == 0
    tx = make_cycle(treasury, usdc, {accounts[1]: 500}, fund=False)
    assert treasury.uncounted() == 0 and treasury.reservedForDividends() == 500 and treasury.payoutFund() == 0
    assert books_balance(treasury, usdc)


def test_dividend_cycle_full_lifecycle(treasury, usdc):
    manager, alice, bob, charlie = accounts[0], accounts[1], accounts[2], accounts[3]
    rewards = {alice: 1000 * E18, bob: 1500 * E18, charlie: 500 * E18}
    total_rewards = sum(rewards.values())

    cycle_id, tree = make_cycle(treasury, usdc, rewards)

    details = treasury.getCycleDetails(cycle_id)
    assert bytes(details['merkleRoot']) == tree.root
    assert details['totalAmount'] == total_rewards
    assert details['claimedAmount'] == 0
    assert details['expiryTimestamp'] == details['creationTimestamp'] + CLAIM_PERIOD
    assert treasury.getNumberOfCycles() == 1

    # --- Valid claims ---
    alice_initial_balance = usdc.balanceOf(alice)
    tx = claim(treasury, cycle_id, tree, alice, rewards[alice])
    assert usdc.balanceOf(alice) == alice_initial_balance + rewards[alice]
    assert treasury.hasUserClaimed(cycle_id, alice) == True
    assert treasury.hasUserClaimed(cycle_id, bob) == False
    event = ev(tx)['DividendClaimed']
    assert (event['cycleId'], event['user'], event['amountClaimed']) == (cycle_id, alice, rewards[alice])

    # Charlie (tests odd-numbered node logic)
    charlie_initial_balance = usdc.balanceOf(charlie)
    claim(treasury, cycle_id, tree, charlie, rewards[charlie])
    assert usdc.balanceOf(charlie) == charlie_initial_balance + rewards[charlie]
    assert treasury.getCycleDetails(cycle_id)['claimedAmount'] == rewards[alice] + rewards[charlie]
    assert books_balance(treasury, usdc)

    # --- Invalid claims ---
    alice_proof = tree.get_proof(leaf_hash(alice.address, rewards[alice]))
    with reverts("Dividend already claimed for this cycle"):
        treasury.claimDividend(cycle_id, rewards[alice], alice_proof, sender=alice)
    with reverts("Invalid Merkle proof"):
        treasury.claimDividend(cycle_id, rewards[bob], alice_proof, sender=bob)

    # --- Claiming after Expiry ---
    advance(CLAIM_PERIOD + 100)
    with reverts("Dividend cycle has expired"):
        claim(treasury, cycle_id, tree, bob, rewards[bob])


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_offchain_tree_matches_onchain_verifier_for_every_leaf(treasury, usdc, n):
    """Every participant of an n-leaf drop can claim: the Python tree agrees with MerkleProof.sol."""
    rewards = {accounts[i]: (i + 1) * E18 for i in range(n)}
    cycle_id, tree = make_cycle(treasury, usdc, rewards)
    for account, amount in rewards.items():
        before = usdc.balanceOf(account)
        claim(treasury, cycle_id, tree, account, amount)
        assert usdc.balanceOf(account) == before + amount
    assert treasury.getCycleDetails(cycle_id)['claimedAmount'] == sum(rewards.values())
    assert usdc.balanceOf(treasury) == 0


def test_claim_is_bound_to_sender_and_amount(treasury, usdc):
    alice, bob, mallory = accounts[1], accounts[2], accounts[5]
    rewards = {alice: 100, bob: 200}
    cycle_id, tree = make_cycle(treasury, usdc, rewards)
    alice_proof = tree.get_proof(leaf_hash(alice.address, 100))

    with reverts("Invalid Merkle proof"):  # someone else's proof
        treasury.claimDividend(cycle_id, 100, alice_proof, sender=mallory)
    with reverts("Invalid Merkle proof"):  # inflated amount
        treasury.claimDividend(cycle_id, 101, alice_proof, sender=alice)
    with reverts("Invalid Merkle proof"):  # empty proof
        treasury.claimDividend(cycle_id, 100, [], sender=alice)
    with reverts("Invalid cycle ID"):
        treasury.claimDividend(cycle_id + 1, 100, alice_proof, sender=alice)
    assert usdc.balanceOf(treasury) == 300


def test_cycles_are_independent(treasury, usdc):
    alice, bob = accounts[1], accounts[2]
    first, tree1 = make_cycle(treasury, usdc, {alice: 100, bob: 200})
    second, tree2 = make_cycle(treasury, usdc, {alice: 300, bob: 400})
    assert (first, second) == (0, 1)

    claim(treasury, second, tree2, alice, 300)
    assert treasury.hasUserClaimed(second, alice) and not treasury.hasUserClaimed(first, alice)

    # A proof from one cycle is useless in the other
    with reverts("Invalid Merkle proof"):
        treasury.claimDividend(first, 300, tree2.get_proof(leaf_hash(alice.address, 300)), sender=alice)
    claim(treasury, first, tree1, alice, 100)
    assert treasury.getCycleDetails(first)['claimedAmount'] == 100
    assert treasury.getCycleDetails(second)['claimedAmount'] == 300


def test_create_cycle_requirements(treasury, usdc):
    manager, alice = accounts[0], accounts[1]
    root = OZMerkleTree([leaf_hash(alice.address, 100)]).root
    with reverts("Manager only"):
        treasury.createDividendCycle(root, 100, sender=alice)
    with reverts("Total dividend amount must be positive"):
        treasury.createDividendCycle(root, 0, sender=manager)
    with reverts("Exceeds this cycle's release"):
        treasury.createDividendCycle(root, 100, sender=manager)
    usdc.transfer(treasury.address, 100, sender=manager)
    with reverts("Exceeds this cycle's release"):
        treasury.createDividendCycle(root, 101, sender=manager)
    assert treasury.getNumberOfCycles() == 0


def test_view_functions_reject_unknown_cycles(treasury):
    with reverts("Invalid cycle ID"):
        treasury.getCycleDetails(0)
    with reverts("Invalid cycle ID"):
        treasury.hasUserClaimed(0, accounts[1])


# --- Funds promised to a cycle are not available for anything else ---

def test_cycles_cannot_promise_the_same_funds_twice(treasury, usdc):
    alice, bob = accounts[1], accounts[2]
    make_cycle(treasury, usdc, {alice: 100})  # the treasury now holds exactly 100, all owed to Alice
    with reverts("Exceeds this cycle's release"):
        make_cycle(treasury, usdc, {bob: 100}, fund=False)
    assert treasury.getNumberOfCycles() == 1


def test_cycle_cannot_pay_out_more_than_its_total(treasury, usdc):
    """Even if the manager publishes a root whose leaves sum to more than the cycle's total."""
    manager, alice, bob, carol = accounts[0], accounts[1], accounts[2], accounts[3]
    make_cycle(treasury, usdc, {carol: 500})  # an honest cycle whose funds must stay safe
    usdc.transfer(treasury.address, 100, sender=manager)
    tree = OZMerkleTree([leaf_hash(alice.address, 200), leaf_hash(bob.address, 100)])
    treasury.createDividendCycle(tree.root, 100, sender=manager)  # leaves sum to 300, declared total 100

    with reverts("Claim exceeds cycle total"):
        claim(treasury, 1, tree, alice, 200)
    claim(treasury, 1, tree, bob, 100)
    with reverts("Claim exceeds cycle total"):
        claim(treasury, 1, tree, alice, 200)
    assert treasury.reservedForDividends() == 500 == usdc.balanceOf(treasury)


def test_recover_unclaimed_funds_returns_them_to_the_next_pool(treasury, usdc):
    manager, alice, bob = accounts[0], accounts[1], accounts[2]
    cycle_id, tree = make_cycle(treasury, usdc, {alice: 100, bob: 200})
    claim(treasury, cycle_id, tree, alice, 100)

    with reverts("Manager only"):
        treasury.recoverUnclaimedFunds(cycle_id, sender=alice)
    with reverts("Invalid cycle ID"):
        treasury.recoverUnclaimedFunds(cycle_id + 1, sender=manager)
    with reverts("Cannot recover funds from an active cycle"):
        treasury.recoverUnclaimedFunds(cycle_id, sender=manager)
    assert treasury.uncounted() == 0

    advance(CLAIM_PERIOD + 1)
    tx = treasury.recoverUnclaimedFunds(cycle_id, sender=manager)
    assert ev(tx)['FundsRecovered']['amountRecovered'] == 200
    details = treasury.getCycleDetails(cycle_id)
    assert details['claimedAmount'] == details['totalAmount'] == 300
    assert treasury.reservedForDividends() == 0
    assert treasury.uncounted() == 200 == usdc.balanceOf(treasury)  # Bob's share will be shared out again

    tx = treasury.recoverUnclaimedFunds(cycle_id, sender=manager)  # idempotent
    assert 'FundsRecovered' not in ev(tx)
    assert treasury.uncounted() == 200

    make_cycle(treasury, usdc, {alice: 200}, fund=False)
    assert books_balance(treasury, usdc)


# --- Gradual release ---

def cycle(treasury, account, amount):
    tree = OZMerkleTree([leaf_hash(account.address, amount)])
    return treasury.createDividendCycle(tree.root, amount, sender=accounts[0]), tree


def test_each_cycle_shares_out_a_fixed_fraction_of_the_fund(gradual, usdc):
    manager, alice = accounts[0], accounts[1]
    usdc.transfer(gradual.address, 1000, sender=manager)
    advance(DAY)
    assert gradual.distributable() == 100

    with reverts("Exceeds this cycle's release"):
        cycle(gradual, alice, 101)
    tx, tree = cycle(gradual, alice, 100)
    event = ev(tx)['PayoutFundChanged']
    assert (event['received'], event['paidOut'], event['payoutFund']) == (1000, 100, 900)
    assert (gradual.payoutFund(), gradual.reservedForDividends(), gradual.uncounted()) == (900, 100, 0)
    claim(gradual, 0, tree, alice, 100)

    # With no new fees the next cycle shares out a tenth of what is left; new fees add to the fund first
    advance(DAY)
    assert gradual.distributable() == 90
    usdc.transfer(gradual.address, 100, sender=manager)
    assert gradual.distributable() == 100  # (900 + 100) / 10
    cycle(gradual, alice, 100)
    assert gradual.payoutFund() == 900
    assert books_balance(gradual, usdc)


def test_in_steady_state_the_fund_pays_out_what_comes_in(gradual, usdc):
    """With 100 arriving per cycle the fund settles at 900 after each payout and pays 100 a cycle."""
    manager, alice = accounts[0], accounts[1]
    usdc.transfer(gradual.address, 1000, sender=manager)
    for _ in range(4):
        advance(DAY)
        assert gradual.distributable() == 100
        cycle(gradual, alice, 100)
        assert gradual.payoutFund() == 900
        usdc.transfer(gradual.address, 100, sender=manager)


def test_a_jump_in_fees_reaches_holders_gradually(gradual, usdc):
    manager, alice = accounts[0], accounts[1]
    usdc.transfer(gradual.address, 1000, sender=manager)
    advance(DAY)
    cycle(gradual, alice, 100)
    usdc.transfer(gradual.address, 1000, sender=manager)  # ten cycles' worth at once
    advance(DAY)
    assert gradual.distributable() == 190  # not 1000 + 90
    cycle(gradual, alice, 190)
    advance(DAY)
    assert gradual.distributable() == 171


def test_what_a_cycle_does_not_share_out_stays_in_the_fund(gradual, usdc):
    manager, alice = accounts[0], accounts[1]
    usdc.transfer(gradual.address, 1000, sender=manager)
    advance(DAY)
    cycle(gradual, alice, 30)  # the release was 100
    assert gradual.payoutFund() == 970 and gradual.uncounted() == 0
    assert books_balance(gradual, usdc)


def test_cycles_cannot_be_run_faster_than_the_interval(gradual, usdc):
    """Otherwise a manager could empty the fund by starting cycles back to back."""
    manager, alice = accounts[0], accounts[1]
    usdc.transfer(gradual.address, 1000, sender=manager)
    with reverts("Too soon for the next cycle"):
        cycle(gradual, alice, 100)  # the first cycle waits one interval after deployment
    advance(DAY)
    tx, _ = cycle(gradual, alice, 100)
    assert gradual.nextCycleTimestamp() == tx.timestamp + DAY
    with reverts("Too soon for the next cycle"):
        cycle(gradual, alice, 90)
    advance(DAY - 100)
    with reverts("Too soon for the next cycle"):
        cycle(gradual, alice, 90)
    advance(100)
    cycle(gradual, alice, 90)


def test_recovered_funds_rejoin_the_fund(gradual, usdc):
    manager, alice = accounts[0], accounts[1]
    usdc.transfer(gradual.address, 1000, sender=manager)
    advance(DAY)
    cycle(gradual, alice, 100)  # never claimed
    advance(CLAIM_PERIOD + 1)
    gradual.recoverUnclaimedFunds(0, sender=manager)
    assert gradual.uncounted() == 100 and gradual.distributable() == 100  # (900 + 100) / 10
    cycle(gradual, alice, 100)
    assert gradual.payoutFund() == 900 and books_balance(gradual, usdc)


# --- Admin ---

def test_set_claim_period(treasury, usdc):
    admin, alice = accounts[0], accounts[1]
    with reverts("Admin only"):
        treasury.setClaimPeriodDuration(1, sender=alice)
    with reverts("Claim period must be positive"):
        treasury.setClaimPeriodDuration(0, sender=admin)

    old_cycle, _ = make_cycle(treasury, usdc, {alice: 100})
    tx = treasury.setClaimPeriodDuration(60, sender=admin)
    assert ev(tx)['ClaimPeriodUpdated']['newDuration'] == 60
    new_cycle, _ = make_cycle(treasury, usdc, {alice: 100})

    old, new = treasury.getCycleDetails(old_cycle), treasury.getCycleDetails(new_cycle)
    assert old['expiryTimestamp'] - old['creationTimestamp'] == CLAIM_PERIOD  # existing cycles keep their expiry
    assert new['expiryTimestamp'] - new['creationTimestamp'] == 60


