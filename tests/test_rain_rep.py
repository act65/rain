import pytest
from helpers import PERIOD, accounts, advance, chain, deploy_reputation, ev, project, reverts

# A pytest fixture to deploy a fresh contract instance for each test.
# This runs before each test function that includes it as an argument.
@pytest.fixture
def reputation_contract():
    """
    Deploys a new RainReputation contract.
    The deployer (accounts[0]) is automatically granted DEFAULT_ADMIN_ROLE.
    """
    # The contract is deployed by accounts[0] by default
    return deploy_reputation(accounts[0])  # no decay: see tests/test_reputation_decay.py for decay

def test_deployment(reputation_contract):
    """
    Tests the initial state of the contract after deployment.
    """
    # Check the ERC721 name and symbol
    assert reputation_contract.name() == "Rain Reputation Token"
    assert reputation_contract.symbol() == "RAIN"

    # Check that the deployer has the DEFAULT_ADMIN_ROLE
    admin_role = reputation_contract.DEFAULT_ADMIN_ROLE()
    assert reputation_contract.hasRole(admin_role, accounts[0]) == True
    assert reputation_contract.hasRole(admin_role, accounts[1]) == False

def test_minting(reputation_contract):
    """
    An identity token is minted; it carries no reputation.
    """
    admin = accounts[0]
    alice = accounts[1]

    tx = reputation_contract.mint(alice, sender=admin)

    assert reputation_contract.ownerOf(1) == alice
    assert reputation_contract.balanceOf(alice) == 1
    assert reputation_contract.reputationScores(alice) == 0
    assert reputation_contract.totalReputation() == 0

    assert 'Transfer' in ev(tx)
    assert ev(tx)['Transfer']['to'] == alice
    assert ev(tx)['Transfer']['tokenId'] == 1


def test_mint_permissions(reputation_contract):
    """
    Ensures only an account with DEFAULT_ADMIN_ROLE can mint tokens.
    """
    # Arrange: Define a non-admin account and a recipient
    non_admin = accounts[1]
    bob = accounts[2]

    # Act & Assert: Attempt to mint from a non-admin account, expecting it to fail.
    # The 'with reverts(...)' block passes only if the code inside it fails with the expected message.
    with reverts("Admin only"):
        reputation_contract.mint(bob, sender=non_admin)

def test_non_transferable(reputation_contract):
    """
    Tests that the token is a non-transferable Soul-Bound Token (SBT).
    """
    # Arrange: Mint a token for Alice
    admin = accounts[0]
    alice = accounts[1]
    bob = accounts[2]
    reputation_contract.mint(alice, sender=admin)

    # Act & Assert: Alice attempts to transfer her token to Bob, which should be blocked.
    with reverts("RAIN: This token is non-transferable"):
        reputation_contract.transferFrom(alice, bob, 1, sender=alice)

# =====================================================================================
# Reputation ledger: updates, delinquency and staking
# =====================================================================================

@pytest.fixture
def ledger(reputation_contract):
    """
    RainReputation with: admin = accounts[0], updater = accounts[1],
    accounts[8] standing in for the RCT contract, and Alice (accounts[2]) and
    Bob (accounts[3]) each holding 100 reputation.
    """
    admin, updater, alice, bob, rct = accounts[0], accounts[1], accounts[2], accounts[3], accounts[8]
    reputation_contract.grantRole(reputation_contract.UPDATER_ROLE(), updater, sender=admin)
    reputation_contract.setRctContract(rct, sender=admin)
    for user in (alice, bob):
        reputation_contract.mint(user, sender=admin)
        reputation_contract.increaseReputation(user, 100, "TEST:seed", sender=updater)
    return reputation_contract


def purpose(n):
    return n.to_bytes(32, "big")


# --- SBT ---

def test_token_ids_increment(ledger):
    assert ledger.ownerOf(1) == accounts[2]
    assert ledger.ownerOf(2) == accounts[3]


def test_safe_transfer_and_approved_transfer_are_blocked(ledger):
    alice, bob, carol = accounts[2], accounts[3], accounts[4]
    with reverts("RAIN: This token is non-transferable"):
        ledger.safeTransferFrom(alice, carol, 1, sender=alice)
    ledger.approve(bob, 1, sender=alice)
    with reverts("RAIN: This token is non-transferable"):
        ledger.transferFrom(alice, carol, 1, sender=bob)


def test_user_cannot_be_minted_a_second_identity(ledger):
    alice, bob = accounts[2], accounts[3]
    with reverts("RAIN: User already has an identity"):
        ledger.mint(alice, sender=accounts[0])
    assert ledger.balanceOf(alice) == 1
    assert ledger.totalReputation() == ledger.reputationScores(alice) + ledger.reputationScores(bob) == 200


def test_identity_and_reputation_are_independent(reputation_contract):
    """Minting never changes a score, whether or not the user already holds reputation."""
    admin, updater, carol = accounts[0], accounts[1], accounts[4]
    reputation_contract.grantRole(reputation_contract.UPDATER_ROLE(), updater, sender=admin)
    reputation_contract.increaseReputation(carol, 5, "r", sender=updater)
    reputation_contract.mint(carol, sender=admin)
    assert reputation_contract.reputationScores(carol) == reputation_contract.totalReputation() == 5


# --- increase / broken-promise record / slash ---

@pytest.mark.parametrize("fn,args", [
    ("increaseReputation", (10, "r")),
    ("recordBroken", (10, "r")),
    ("slash", (10,)),
])
def test_only_updater_can_change_scores(ledger, fn, args):
    alice = accounts[2]
    for caller in (accounts[0], alice, accounts[9]):  # not even the admin
        with reverts("Caller is not a trusted updater"):
            getattr(ledger, fn)(alice, *args, sender=caller)
    assert ledger.reputationScores(alice) == 100
    assert ledger.brokenScores(alice) == 0


def test_increase_reputation(ledger):
    updater, alice = accounts[1], accounts[2]
    tx = ledger.increaseReputation(alice, 25, "PROMISE_FULFILLED:1", sender=updater)
    assert ledger.reputationScores(alice) == 125
    assert ledger.totalReputation() == 225
    event = ev(tx)['ReputationIncreased']
    assert (event['user'], event['amount'], event['reason']) == (alice, 25, "PROMISE_FULFILLED:1")


def test_increase_can_create_reputation_for_a_user_without_an_sbt(ledger):
    """Characterisation: holding the SBT is not a precondition for holding reputation."""
    stranger = accounts[7]
    assert ledger.balanceOf(stranger) == 0
    ledger.increaseReputation(stranger, 5, "r", sender=accounts[1])
    assert ledger.reputationScores(stranger) == 5


def test_a_broken_promise_is_recorded_and_does_not_reduce_reputation(ledger):
    updater, alice, bob = accounts[1], accounts[2], accounts[3]
    tx = ledger.recordBroken(alice, 40, "PROMISE_DEFAULTED:1", sender=updater)
    assert ledger.brokenScores(alice) == 40
    assert ledger.reputationScores(alice) == 100  # untouched, and so is her share of dividends
    assert ledger.totalReputation() == 200
    assert ledger.getLiquidReputation(alice) == 100
    event = ev(tx)['BrokenPromiseRecorded']
    assert (event['user'], event['amount'], event['reason']) == (alice, 40, "PROMISE_DEFAULTED:1")

    ledger.recordBroken(alice, 1000, "PROMISE_DEFAULTED:2", sender=updater)  # not clamped by the score
    assert ledger.brokenScores(alice) == 1040
    assert ledger.brokenScores(bob) == 0


def test_reliability_is_the_posterior_mean_of_the_two_counters(ledger):
    updater, alice, stranger = accounts[1], accounts[2], accounts[7]
    E18 = 10**18
    assert ledger.reliability(alice, 0, 0) == E18  # 100 kept, nothing broken, no prior
    ledger.recordBroken(alice, 25, "r", sender=updater)
    assert ledger.reliability(alice, 0, 0) == 100 * E18 // 125
    assert ledger.reliability(alice, 60, 15) == 160 * E18 // 200  # prior of 60 kept to 15 broken

    # A stranger is whatever the reader's prior says, and without a prior there is nothing to say.
    assert ledger.reliability(stranger, 3, 1) == 3 * E18 // 4
    with reverts("RAIN: No evidence and no prior"):
        ledger.reliability(stranger, 0, 0)

    # Reputation destroyed by a slash (or a forfeited bond) no longer counts as kept.
    ledger.slash(alice, 100, sender=updater)
    assert ledger.reliability(alice, 0, 0) == 0


def test_slash(ledger):
    updater, alice = accounts[1], accounts[2]
    tx = ledger.slash(alice, 30, sender=updater)
    assert ledger.reputationScores(alice) == 70
    assert ledger.totalReputation() == 170
    assert ev(tx)['ReputationSlashed']['amount'] == 30


def test_slash_is_clamped_at_zero(ledger):
    updater, alice = accounts[1], accounts[2]
    tx = ledger.slash(alice, 1000, sender=updater)
    assert ledger.reputationScores(alice) == 0
    assert ledger.totalReputation() == 100
    assert ev(tx)['ReputationSlashed']['amount'] == 100
    tx = ledger.slash(alice, 1, sender=updater)
    assert 'ReputationSlashed' not in ev(tx)


def test_total_reputation_tracks_the_sum_of_scores(ledger):
    updater, alice, bob = accounts[1], accounts[2], accounts[3]
    ledger.increaseReputation(alice, 7, "r", sender=updater)
    ledger.slash(bob, 300, sender=updater)
    ledger.recordBroken(alice, 50, "r", sender=updater)  # does not enter the total
    ledger.slash(alice, 3, sender=updater)
    ledger.increaseReputation(bob, 11, "r", sender=updater)
    ledger.slash(bob, 500, sender=updater)
    assert ledger.reputationScores(alice) == 104
    assert ledger.reputationScores(bob) == 0
    assert ledger.totalReputation() == 104


# --- delinquency ---

def test_only_rct_contract_sets_delinquent_status(ledger):
    alice = accounts[2]
    for caller in (accounts[0], accounts[1], alice):
        with reverts("Only the RCT contract can set delinquent status"):
            ledger.setDelinquentStatus(alice, True, sender=caller)
    tx = ledger.setDelinquentStatus(alice, True, sender=accounts[8])
    assert ledger.isDelinquent(alice)
    assert ev(tx)['DelinquentStatusChanged']['isDelinquent'] == True


def test_rct_contract_can_only_be_set_once_and_only_by_admin(reputation_contract):
    with reverts("Admin only"):
        reputation_contract.setRctContract(accounts[8], sender=accounts[1])
    reputation_contract.setRctContract(accounts[8], sender=accounts[0])
    with reverts("RCT contract already set"):
        reputation_contract.setRctContract(accounts[7], sender=accounts[0])
    assert reputation_contract.rctContractAddress() == accounts[8]


def test_ledger_does_not_police_delinquency(ledger):
    """
    The flag is a signal to scripts and to the oracle. The ledger applies whatever the updater
    sends: whether a kept promise earns anything is decided by the promisor's status when it
    was kept (see rain.reputation.process_promise_log), not their status when the update arrives.
    """
    updater, alice, rct = accounts[1], accounts[2], accounts[8]
    ledger.setDelinquentStatus(alice, True, sender=rct)
    ledger.increaseReputation(alice, 1, "earned before the default", sender=updater)
    ledger.recordBroken(alice, 10, "r", sender=updater)
    ledger.slash(alice, 10, sender=updater)
    assert ledger.reputationScores(alice) == 91
    assert ledger.brokenScores(alice) == 10
    assert ledger.isDelinquent(alice)


# --- staking ---
#
# A stake belongs to its controller (the account that created it). `script` below is
# accounts[5], standing in for a script contract.

MAX_UINT = 2**256 - 1


def test_user_can_stake_and_release_their_own_reputation(ledger):
    alice = accounts[2]
    tx = ledger.stake(alice, 60, purpose(1), sender=alice)
    assert ledger.stakedReputation(alice) == 60
    assert ledger.getLiquidReputation(alice) == 40
    assert ledger.reputationScores(alice) == 100  # staking does not change the score
    assert ledger.totalReputation() == 200
    assert ledger.getStake(alice, purpose(1)) == (alice, 60, True, False)
    event = ev(tx)['ReputationStaked']
    assert (event['controller'], event['user'], event['amount']) == (alice, alice, 60)

    tx = ledger.releaseStake(purpose(1), sender=alice)
    assert ledger.stakedReputation(alice) == 0
    assert ledger.getLiquidReputation(alice) == 100
    assert ledger.getStake(alice, purpose(1)) == (alice, 60, True, True)
    assert ev(tx)['StakeReleased']['amount'] == 60


def test_controller_needs_a_stake_allowance_from_the_user(ledger):
    alice, script = accounts[2], accounts[5]
    with reverts("Insufficient stake allowance"):
        ledger.stake(alice, 1, purpose(1), sender=script)

    tx = ledger.approveStake(script, 70, sender=alice)
    assert ev(tx)['StakeApproval']['amount'] == 70
    with reverts("Insufficient stake allowance"):
        ledger.stake(alice, 71, purpose(1), sender=script)

    ledger.stake(alice, 50, purpose(1), sender=script)
    assert ledger.stakeAllowance(alice, script) == 20  # consumed
    assert ledger.getStake(script, purpose(1)) == (alice, 50, True, False)
    with reverts("Insufficient stake allowance"):
        ledger.stake(alice, 21, purpose(2), sender=script)


def test_unlimited_stake_allowance_is_not_consumed(ledger):
    alice, script = accounts[2], accounts[5]
    ledger.approveStake(script, MAX_UINT, sender=alice)
    ledger.stake(alice, 50, purpose(1), sender=script)
    assert ledger.stakeAllowance(alice, script) == MAX_UINT


def test_stake_allowance_is_per_controller(ledger):
    alice, script, stranger = accounts[2], accounts[5], accounts[9]
    ledger.approveStake(script, 100, sender=alice)
    with reverts("Insufficient stake allowance"):
        ledger.stake(alice, 1, purpose(1), sender=stranger)
    assert ledger.stakedReputation(alice) == 0


def test_only_the_controller_can_release_a_stake(ledger):
    """In particular the staker cannot unlock a bond that a script holds."""
    alice, script, stranger = accounts[2], accounts[5], accounts[9]
    ledger.approveStake(script, 100, sender=alice)
    ledger.stake(alice, 100, purpose(1), sender=script)
    for caller in (alice, stranger, accounts[0], accounts[1]):
        with reverts("Stake does not exist"):
            ledger.releaseStake(purpose(1), sender=caller)
        with reverts("Stake does not exist"):
            ledger.forfeitStake(purpose(1), sender=caller)
    assert ledger.stakedReputation(alice) == 100
    ledger.releaseStake(purpose(1), sender=script)
    assert ledger.stakedReputation(alice) == 0


def test_cannot_stake_more_than_liquid_reputation(ledger):
    alice = accounts[2]
    ledger.stake(alice, 60, purpose(1), sender=alice)
    with reverts("Insufficient liquid reputation"):
        ledger.stake(alice, 41, purpose(2), sender=alice)
    ledger.stake(alice, 40, purpose(2), sender=alice)
    assert ledger.getLiquidReputation(alice) == 0


def test_failed_stake_does_not_consume_allowance(ledger):
    alice, script = accounts[2], accounts[5]
    ledger.approveStake(script, 500, sender=alice)
    with reverts("Insufficient liquid reputation"):
        ledger.stake(alice, 101, purpose(1), sender=script)
    assert ledger.stakeAllowance(alice, script) == 500


def test_purpose_ids_are_namespaced_by_controller(ledger):
    alice, bob, script = accounts[2], accounts[3], accounts[5]
    ledger.approveStake(script, 100, sender=bob)
    ledger.stake(alice, 10, purpose(1), sender=alice)
    ledger.stake(bob, 20, purpose(1), sender=script)  # same id, different controller: no clash
    assert ledger.getStake(alice, purpose(1))[:2] == (alice, 10)
    assert ledger.getStake(script, purpose(1))[:2] == (bob, 20)


def test_controller_cannot_reuse_a_purpose_id(ledger):
    alice = accounts[2]
    ledger.stake(alice, 10, purpose(1), sender=alice)
    with reverts("Stake for this purpose already exists"):
        ledger.stake(alice, 10, purpose(1), sender=alice)
    ledger.releaseStake(purpose(1), sender=alice)
    with reverts("Stake for this purpose already exists"):  # not even once resolved
        ledger.stake(alice, 10, purpose(1), sender=alice)


def test_stake_is_resolved_exactly_once(ledger):
    alice, script = accounts[2], accounts[5]
    ledger.approveStake(script, 100, sender=alice)
    ledger.stake(alice, 30, purpose(1), sender=script)
    ledger.stake(alice, 30, purpose(2), sender=script)

    ledger.releaseStake(purpose(1), sender=script)
    for fn in (ledger.releaseStake, ledger.forfeitStake):
        with reverts("Stake already resolved"):
            fn(purpose(1), sender=script)

    ledger.forfeitStake(purpose(2), sender=script)
    for fn in (ledger.releaseStake, ledger.forfeitStake):
        with reverts("Stake already resolved"):
            fn(purpose(2), sender=script)
    with reverts("Stake does not exist"):
        ledger.releaseStake(purpose(99), sender=script)
    assert ledger.stakedReputation(alice) == 0
    assert ledger.reputationScores(alice) == 70


def test_forfeit_destroys_the_staked_reputation(ledger):
    alice, script = accounts[2], accounts[5]
    ledger.approveStake(script, 100, sender=alice)
    ledger.stake(alice, 60, purpose(1), sender=script)

    tx = ledger.forfeitStake(purpose(1), sender=script)

    assert ledger.reputationScores(alice) == 40
    assert ledger.stakedReputation(alice) == 0
    assert ledger.getLiquidReputation(alice) == 40
    assert ledger.totalReputation() == 140
    assert ledger.getStake(script, purpose(1)) == (alice, 60, True, True)
    event = ev(tx)['StakeForfeited']
    assert (event['controller'], event['user'], event['amount'], event['reputationBurned']) == (script, alice, 60, 60)


def test_controller_can_destroy_no_more_than_the_user_allowed(ledger):
    alice, script = accounts[2], accounts[5]
    ledger.approveStake(script, 30, sender=alice)
    ledger.stake(alice, 30, purpose(1), sender=script)
    ledger.forfeitStake(purpose(1), sender=script)
    with reverts("Insufficient stake allowance"):
        ledger.stake(alice, 1, purpose(2), sender=script)
    assert ledger.reputationScores(alice) == 70


def test_score_can_fall_below_the_stake_without_breaking_anything(ledger):
    updater, alice, script = accounts[1], accounts[2], accounts[5]
    ledger.approveStake(script, 100, sender=alice)
    ledger.stake(alice, 80, purpose(1), sender=script)
    ledger.slash(alice, 50, sender=updater)  # score 50 < staked 80

    assert ledger.getLiquidReputation(alice) == 0
    with reverts("Insufficient liquid reputation"):
        ledger.stake(alice, 1, purpose(2), sender=alice)

    tx = ledger.forfeitStake(purpose(1), sender=script)  # can only burn what is left
    assert ev(tx)['StakeForfeited']['reputationBurned'] == 50
    assert ledger.reputationScores(alice) == 0
    assert ledger.stakedReputation(alice) == 0
    assert ledger.totalReputation() == 100  # Bob's


def test_release_after_score_fell_below_the_stake(ledger):
    updater, alice = accounts[1], accounts[2]
    ledger.stake(alice, 80, purpose(1), sender=alice)
    ledger.slash(alice, 50, sender=updater)
    ledger.releaseStake(purpose(1), sender=alice)
    assert ledger.getLiquidReputation(alice) == ledger.reputationScores(alice) == 50


def test_zero_stake_can_be_created_and_resolved(ledger):
    alice, script = accounts[2], accounts[5]
    ledger.stake(alice, 0, purpose(1), sender=script)  # no allowance needed for nothing
    assert ledger.getStake(script, purpose(1)) == (alice, 0, True, False)
    with reverts("Stake for this purpose already exists"):
        ledger.stake(alice, 0, purpose(1), sender=script)
    ledger.releaseStake(purpose(1), sender=script)
    ledger.stake(alice, 0, purpose(2), sender=script)
    ledger.forfeitStake(purpose(2), sender=script)
    assert ledger.reputationScores(alice) == 100


# --- stateful invariant ---

def test_stateful_ledger_matches_a_simple_model(ledger):
    """Random sequences of updates and stakes: the contract always agrees with a few lines of Python."""
    from hypothesis import settings, strategies as st
    from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule, run_state_machine_as_test

    updater = accounts[1]
    users = [accounts[2], accounts[3], accounts[4], accounts[5]]
    st_user = st.integers(0, len(users) - 1)
    st_amount = st.integers(0, 300)
    start = {"snapshot": chain.snapshot()}

    class LedgerMachine(RuleBasedStateMachine):
        @initialize()
        def reset_chain(self):
            chain.restore(start["snapshot"])
            start["snapshot"] = chain.snapshot()
            self.scores = [ledger.reputationScores(u) for u in users]
            self.broken = [0 for _ in users]
            self.staked = [0 for _ in users]
            self.open_stakes = []  # (purposeId, user index, amount), all controlled by the user
            self.next_purpose = 1

        @rule(i=st_user, amount=st_amount)
        def increase(self, i, amount):
            ledger.increaseReputation(users[i], amount, "r", sender=updater)
            self.scores[i] += amount

        @rule(i=st_user, amount=st_amount)
        def record_broken(self, i, amount):
            ledger.recordBroken(users[i], amount, "r", sender=updater)
            self.broken[i] += amount

        @rule(i=st_user, amount=st_amount)
        def slash(self, i, amount):
            ledger.slash(users[i], amount, sender=updater)
            self.scores[i] = max(0, self.scores[i] - amount)

        @rule(i=st_user, amount=st_amount)
        def stake(self, i, amount):
            liquid = max(0, self.scores[i] - self.staked[i])
            pid = purpose(self.next_purpose)
            self.next_purpose += 1
            if amount > liquid:
                with reverts("Insufficient liquid reputation"):
                    ledger.stake(users[i], amount, pid, sender=users[i])
            else:
                ledger.stake(users[i], amount, pid, sender=users[i])
                self.staked[i] += amount
                self.open_stakes.append((pid, i, amount))

        @rule()
        def release(self):
            if self.open_stakes:
                pid, i, amount = self.open_stakes.pop(0)
                ledger.releaseStake(pid, sender=users[i])
                self.staked[i] -= amount

        @rule()
        def forfeit(self):
            if self.open_stakes:
                pid, i, amount = self.open_stakes.pop()
                ledger.forfeitStake(pid, sender=users[i])
                self.staked[i] -= amount
                self.scores[i] = max(0, self.scores[i] - amount)

        @invariant()
        def contract_matches_model(self):
            for i, user in enumerate(users):
                assert ledger.reputationScores(user) == self.scores[i]
                assert ledger.stakedReputation(user) == self.staked[i]
                assert ledger.brokenScores(user) == self.broken[i]
                assert ledger.getLiquidReputation(user) == max(0, self.scores[i] - self.staked[i])
            assert ledger.totalReputation() == sum(self.scores)

    run_state_machine_as_test(
        LedgerMachine, settings=settings(max_examples=20, stateful_step_count=15, deadline=None)
    )
