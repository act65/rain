"""
Payments made while disconnected: CalculusEngine.monitoredSignedPromise and OfflineNoteScript.

Claims tested:
  - a note is signed with no call to the chain: `rain.offline.note_digest` equals the engine's digest;
  - the signature is the consent: a payer who never authorised the script is bound by a note they
    signed, for the script, engine, chain and terms they signed and no others, once;
  - whoever presents a note pays the fee; if the payer's funds are there the payee is paid at once
    and the presenter is refunded by the payer;
  - a double spend is not rejected: both notes are recorded, the one that cannot be paid stays
    pending, and after the deadline it is a broken promise, a claim for the payee and a delinquent payer;
  - a payer who finds the money in time keeps the promise;
  - a payer cannot make a note unrecordable by emptying their account or withdrawing allowances;
  - the oracle credits the kept note and counts the broken one; the reader sees notes owed at once;
  - the model (rain.model.Economy.settle_note) reproduces the money.
"""
import pytest
from helpers import MAX_UINT, E18, advance, chain, deploy_system, ev, project, reverts

from rain.model import Economy
from rain.offline import Note, note_digest, read_notes, sign_note
from rain.record import weigh
from rain.reputation import process_promise_log, to_update_tuples

DAY = 24 * 60 * 60
PENDING, PAID, DEFAULTED = 1, 2, 3
P_PENDING, P_FULFILLED, P_DEFAULTED = 0, 1, 2
FEE_BPS = 100  # 1%


@pytest.fixture
def s():
    """
    Bob pays; Alice and Carol are shops. Bob has given the note script an allowance to pay from
    and nothing else: he has not authorised it to make promises. The shops and the outsider (a
    carrier) can pay fees through it.
    """
    s = deploy_system(fee_bps=FEE_BPS, min_fee=E18 // 10, starting_reputation=0)
    s.notes = project.OfflineNoteScript.deploy(s.engine.address, s.rct.address, s.usdc.address, sender=s.admin)
    s.usdc.mint(s.outsider, 1_000 * E18, sender=s.admin)
    s.usdc.approve(s.engine.address, MAX_UINT, sender=s.outsider)
    for user in (s.alice, s.bob, s.carol, s.outsider):
        s.engine.approveScript(s.notes.address, s.usdc.address, MAX_UINT, sender=user)
    s.nonce = 0
    return s


def note(s, payee, amount, **changes):
    s.nonce += 1
    now = chain.blocks.head.timestamp
    fields = dict(promisor=s.bob.address, promisee=payee.address, asset=s.usdc.address, amount=amount,
                  issued_at=now, valid_until=now + 30 * DAY, settle_within=7 * DAY, nonce=s.nonce)
    fields.update(changes)
    return Note(**fields)


def signed(s, n, signer=None, script=None):
    return sign_note(signer or s.bob, chain.chain_id, s.engine.address, script or s.notes.address, n)


def present(s, n, sender, **kw):
    tx = s.notes.present(n.as_tuple(), signed(s, n, **kw), sender=sender)
    return ev(tx)["NotePresented"]["noteId"]


def run_oracle(s):
    increases, broken, _ = process_promise_log(s.engine, s.rep, 0, chain.blocks.height)
    s.updater.applyReputationChanges(to_update_tuples(increases), to_update_tuples(broken), sender=s.oracle)


def test_the_digest_is_computed_without_the_chain(s):
    n = note(s, s.alice, 200 * E18)
    assert note_digest(chain.chain_id, s.engine.address, s.notes.address, n) == bytes(s.engine.signedPromiseDigest(s.notes.address, n.as_tuple()))


def test_a_note_is_paid_when_presented_and_the_payer_never_authorised_the_script(s):
    assert not s.engine.isScriptAuthorized(s.bob, s.notes.address)
    before = [s.usdc.balanceOf(u) for u in (s.alice, s.bob)]
    n = note(s, s.alice, 200 * E18)
    note_id = present(s, n, s.alice)
    stored = s.notes.notes(note_id)
    assert stored["status"] == PAID
    assert s.engine.promises(stored["promiseId"])["status"] == P_FULFILLED
    assert s.engine.promises(stored["promiseId"])["promisor"] == s.bob.address
    assert s.engine.promises(stored["promiseId"])["feePaid"] == 2 * E18
    assert s.usdc.balanceOf(s.alice) == before[0] + 200 * E18  # paid, and the fee she fronted came back
    assert s.usdc.balanceOf(s.bob) == before[1] - 202 * E18


def test_a_carrier_can_present_and_gets_the_fee_back(s):
    before = [s.usdc.balanceOf(u) for u in (s.alice, s.outsider)]
    present(s, note(s, s.alice, 200 * E18), s.outsider)
    assert s.usdc.balanceOf(s.alice) == before[0] + 200 * E18
    assert s.usdc.balanceOf(s.outsider) == before[1]


def test_a_note_binds_only_what_was_signed(s):
    n = note(s, s.alice, 200 * E18)
    with reverts("CalculusEngine: Not signed by the promisor"):  # signed by someone else
        s.notes.present(n.as_tuple(), signed(s, n, signer=s.carol), sender=s.alice)
    bigger = note(s, s.alice, 900 * E18, nonce=n.nonce, issued_at=n.issued_at, valid_until=n.valid_until)
    with reverts("CalculusEngine: Not signed by the promisor"):  # the amount was changed
        s.notes.present(bigger.as_tuple(), signed(s, n), sender=s.alice)
    other = project.OfflineNoteScript.deploy(s.engine.address, s.rct.address, s.usdc.address, sender=s.admin)
    s.engine.approveScript(other.address, s.usdc.address, MAX_UINT, sender=s.alice)
    with reverts("CalculusEngine: Not signed by the promisor"):  # signed for a different script
        other.present(n.as_tuple(), signed(s, n), sender=s.alice)
    present(s, n, s.alice)
    with reverts("CalculusEngine: Signed promise already recorded"):
        s.notes.present(n.as_tuple(), signed(s, n), sender=s.alice)


def test_a_note_cannot_be_presented_late_or_dated_ahead(s):
    n = note(s, s.alice, 200 * E18, valid_until=chain.blocks.head.timestamp + DAY)
    ahead = note(s, s.alice, 200 * E18, issued_at=chain.blocks.head.timestamp + 10 * DAY)
    with reverts("CalculusEngine: Signed promise is dated in the future"):
        s.notes.present(ahead.as_tuple(), signed(s, ahead), sender=s.alice)
    advance(2 * DAY)
    with reverts("CalculusEngine: Signed promise has expired"):
        s.notes.present(n.as_tuple(), signed(s, n), sender=s.alice)


def double_spend(s):
    """Bob holds 10,000 and signs 6,000 to each shop. Returns the two note ids."""
    first = present(s, note(s, s.alice, 6_000 * E18), s.alice)
    second = present(s, note(s, s.carol, 6_000 * E18), s.carol)
    return first, second


def test_a_double_spend_is_recorded_and_becomes_a_broken_promise(s):
    carol_before = s.usdc.balanceOf(s.carol)
    first, second = double_spend(s)
    assert s.notes.notes(first)["status"] == PAID
    assert s.notes.notes(second)["status"] == PENDING  # recorded, not rejected
    assert s.usdc.balanceOf(s.carol) == carol_before - 60 * E18  # she paid the fee to have it recorded
    with reverts("OfflineNote: Payer's funds are not available"):
        s.notes.pay(second, sender=s.carol)
    with reverts("CalculusEngine: Promise deadline has not passed"):
        s.notes.claimDefault(second, sender=s.carol)

    advance(7 * DAY + 1)
    tx = s.notes.claimDefault(second, sender=s.outsider)  # anyone can
    rct_id = ev(tx)["NoteDefaulted"]["rctId"]
    assert s.notes.notes(second)["status"] == DEFAULTED
    assert s.engine.promises(s.notes.notes(second)["promiseId"])["status"] == P_DEFAULTED
    assert s.rct.ownerOf(rct_id) == s.carol.address
    assert s.rep.isDelinquent(s.bob)

    run_oracle(s)
    assert s.rep.brokenScores(s.bob) == 60 * E18 * E18 // (E18 // 25)  # the weight the note would have earned
    assert s.rep.reputationScores(s.bob) == 60 * E18 * E18 // (E18 // 25)  # from the note that was paid


def test_a_payer_who_finds_the_money_in_time_keeps_the_promise(s):
    first, second = double_spend(s)
    s.usdc.mint(s.bob, 5_000 * E18, sender=s.admin)
    carol_before = s.usdc.balanceOf(s.carol)
    s.notes.pay(second, sender=s.outsider)  # anyone can
    assert s.notes.notes(second)["status"] == PAID
    assert s.usdc.balanceOf(s.carol) == carol_before + 6_060 * E18
    assert not s.rep.isDelinquent(s.bob)
    with reverts("OfflineNote: Note not pending"):
        s.notes.claimDefault(second, sender=s.carol)


def test_a_payer_cannot_make_a_note_unrecordable(s):
    n = note(s, s.alice, 200 * E18)
    signature = signed(s, n)
    # Bob empties his account and withdraws every permission before the note reaches the chain.
    s.usdc.transfer(s.outsider, s.usdc.balanceOf(s.bob), sender=s.bob)
    s.usdc.approve(s.engine.address, 0, sender=s.bob)
    s.engine.approveScript(s.notes.address, s.usdc.address, 0, sender=s.bob)
    tx = s.notes.present(n.as_tuple(), signature, sender=s.alice)
    note_id = ev(tx)["NotePresented"]["noteId"]
    assert s.notes.notes(note_id)["status"] == PENDING
    advance(7 * DAY + 1)
    s.notes.claimDefault(note_id, sender=s.alice)
    assert s.rep.isDelinquent(s.bob)


def test_the_payer_resolves_a_default_by_buying_back_the_claim(s):
    first, second = double_spend(s)
    advance(7 * DAY + 1)
    rct_id = ev(s.notes.claimDefault(second, sender=s.carol))["NoteDefaulted"]["rctId"]
    with reverts("OfflineNote: You must own the claim to resolve it"):
        s.notes.resolveDefault(rct_id, sender=s.bob)
    s.rct.transferFrom(s.carol, s.bob, rct_id, sender=s.carol)  # settled between them
    s.rct.approve(s.notes.address, rct_id, sender=s.bob)
    s.notes.resolveDefault(rct_id, sender=s.bob)
    assert not s.rep.isDelinquent(s.bob)


def test_notes_owed_at_once_are_read_as_a_total(s):
    t0 = chain.blocks.head.timestamp
    a = note(s, s.alice, 300 * E18)
    advance(DAY)
    c = note(s, s.carol, 400 * E18)  # signed a day later, while the first was still unpresented
    advance(DAY)
    present(s, a, s.alice)
    present(s, c, s.carol)
    entries = read_notes(s.engine, s.notes)
    assert [(e.promisee, e.amount, e.kept) for e in entries] == [(s.alice.address, 300 * E18, True), (s.carol.address, 400 * E18, True)]
    assert all(t0 <= e.created < e.time for e in entries)
    assert weigh(entries, s.bob.address).largest_repaid == 400 * E18
    assert weigh(entries, s.bob.address, concurrent=True).largest_repaid == 700 * E18


def test_the_model_reproduces_the_money(s):
    people = {"alice": s.alice, "bob": s.bob, "carol": s.carol}
    before = {name: s.usdc.balanceOf(who) for name, who in people.items()}
    double_spend(s)
    e = Economy.current_rules(min_fee=0.1, fee_rate=FEE_BPS / 10_000, point_price=0.04, decay_rate=0.0)
    for name in people:
        e.add_agent(name, money=before[name] / E18)
    assert e.settle_note("bob", "alice", 6_000.0)
    assert not e.settle_note("bob", "carol", 6_000.0)
    for name, who in people.items():
        assert s.usdc.balanceOf(who) / E18 == pytest.approx(e.agents[name].money)
