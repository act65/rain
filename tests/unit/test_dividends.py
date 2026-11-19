"""
Claims tested: dividends are split pro rata to reputation, never exceed the pool,
leave less than one base unit of dust per account, and every share is provable
against the published Merkle root.
"""
import pytest
from hypothesis import given, settings, strategies as st

from rain.dividends import build_tree, calculate_dividend_shares, compute_shares, get_merkle_proof
from rain.merkletree import EMPTY_ROOT, leaf_hash, verify_proof

E18 = 10**18
A = "0x33A4622B82D4c04a53e170c638B944ce27cffce3"
B = "0x0063046686E46Dc6F15918b61AE2B121458534a5"
C = "0x21b42413bA931038f35e7A5224FaDb065d297Ba3"


class FakeReputation:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def reputationScores(self, account):
        self.calls.append(account)
        return self.scores.get(account, 0)


# --- compute_shares ---

def test_shares_are_proportional():
    shares = compute_shares({A: 200 * E18, B: 100 * E18, C: 100 * E18}, 400 * E18)
    assert shares == {A: 200 * E18, B: 100 * E18, C: 100 * E18}


def test_shares_round_down_and_leave_dust():
    shares = compute_shares({A: 1, B: 1, C: 1}, 100)
    assert shares == {A: 33, B: 33, C: 33}
    assert 100 - sum(shares.values()) == 1


def test_zero_reputation_accounts_are_excluded():
    assert compute_shares({A: 10, B: 0}, 100) == {A: 100}


def test_shares_that_round_to_zero_are_excluded():
    assert compute_shares({A: 10**6, B: 1}, 1000) == {A: 999}


def test_no_reputation_means_no_shares():
    assert compute_shares({}, 100) == {}
    assert compute_shares({A: 0, B: 0}, 100) == {}


def test_zero_pool_means_no_shares():
    assert compute_shares({A: 5, B: 7}, 0) == {}


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        compute_shares({A: 1}, -1)
    with pytest.raises(ValueError):
        compute_shares({A: -1, B: 5}, 10)


def test_single_holder_takes_everything():
    assert compute_shares({A: 123}, 10**30) == {A: 10**30}


reputations = st.dictionaries(
    st.integers(1, 2**160 - 1).map(lambda i: "0x" + i.to_bytes(20, "big").hex()),
    st.integers(0, 10**30),
    max_size=30,
)


@settings(max_examples=200, deadline=None)
@given(reps=reputations, total=st.integers(0, 10**36))
def test_property_shares_conserve_the_pool(reps, total):
    shares = compute_shares(reps, total)
    total_rep = sum(reps.values())
    paid = sum(shares.values())
    assert paid <= total
    if total_rep > 0:
        # Each account loses strictly less than one base unit to rounding.
        assert total - paid < max(1, sum(1 for r in reps.values() if r > 0))
    for account, share in shares.items():
        assert share > 0
        # Exactly the floor of the pro-rata entitlement.
        assert share * total_rep <= reps[account] * total < (share + 1) * total_rep


@settings(max_examples=100, deadline=None)
@given(reps=reputations, total=st.integers(0, 10**36))
def test_property_more_reputation_never_earns_less(reps, total):
    shares = compute_shares(reps, total)
    ranked = sorted(reps, key=lambda a: reps[a])
    for lo, hi in zip(ranked, ranked[1:]):
        assert shares.get(lo, 0) <= shares.get(hi, 0)


# --- calculate_dividend_shares / get_merkle_proof ---

def test_calculate_dividend_shares_reads_contract_and_builds_root():
    rep = FakeReputation({A: 200 * E18, B: 100 * E18, C: 0})
    shares, root, total_rep = calculate_dividend_shares(rep, [A, B, C], 300 * E18)

    assert total_rep == 300 * E18
    assert shares == [
        {"account": A, "reputation": 200 * E18, "amount": 200 * E18},
        {"account": B, "reputation": 100 * E18, "amount": 100 * E18},
    ]
    assert root == "0x" + build_tree({A: 200 * E18, B: 100 * E18}).root.hex()


def test_calculate_dividend_shares_ignores_duplicate_addresses():
    rep = FakeReputation({A: 10, B: 10})
    shares, _, total_rep = calculate_dividend_shares(rep, [A, B, A], 100)
    assert total_rep == 20
    assert [s["amount"] for s in shares] == [50, 50]


def test_calculate_dividend_shares_with_no_reputation():
    shares, root, total_rep = calculate_dividend_shares(FakeReputation({}), [A, B], 100)
    assert shares == [] and total_rep == 0
    assert root == "0x" + EMPTY_ROOT.hex()


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 13])
def test_every_share_is_provable_against_the_root(n):
    accounts = ["0x" + (i + 1).to_bytes(20, "big").hex() for i in range(n)]
    rep = FakeReputation({a: (i + 1) * E18 for i, a in enumerate(accounts)})
    shares, root, _ = calculate_dividend_shares(rep, accounts, 1000 * E18)
    assert len(shares) == n
    root = bytes.fromhex(root[2:])
    for share in shares:
        proof = [bytes.fromhex(p[2:]) for p in get_merkle_proof(shares, share["account"], share["amount"])]
        assert verify_proof(proof, root, leaf_hash(share["account"], share["amount"]))
        # The same proof must not support a larger claim.
        assert not verify_proof(proof, root, leaf_hash(share["account"], share["amount"] + 1))


def test_proof_for_wrong_amount_raises():
    rep = FakeReputation({A: 1, B: 1})
    shares, _, _ = calculate_dividend_shares(rep, [A, B], 100)
    with pytest.raises(ValueError):
        get_merkle_proof(shares, A, 51)
