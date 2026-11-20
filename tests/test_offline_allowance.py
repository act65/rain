"""
Offline payments backed by locked funds: OfflineAllowanceScript and the payee's checks in rain.offline.

Claims tested:
  - opening an allowance locks the amount and the float; the certificate the attester signs is computed
    and checked with no call to the chain;
  - a note within the allowance is paid from the locked funds whatever has become of the payer's account,
    and the presenter's fee is refunded from the float;
  - notes that together exceed the allowance prove an overspend from the notes alone, and nobody but the
    payer can make such a proof; a payee who knows of the earlier notes refuses the one that overspends;
  - on the chain, the note that takes the total past the amount gives the rest of the float to whoever
    presents it and destroys the bonded reputation; that note is owed by the payer in person;
  - such a note is paid from what is still locked and the payer's own funds, or defaults, the payee
    receiving what was still locked and a claim;
  - a note under another payer's allowance, signed after it expired, or outliving it, is refused;
  - once no more notes can be presented, what is left returns to the payer, and the bond if they did not overspend;
  - the model (rain.model.Economy) reproduces the money.
"""
import pytest
from helpers import MAX_UINT, E18, advance, chain, deploy_system, ev, project, reverts

from rain.model import Economy
from rain.offline import (
    Certificate, Note, accept_note, allowance_nonce, certificate_digest, proves_overspend, sign_certificate, sign_note,
    signer_of,
)

DAY = 24 * 60 * 60
PENDING, PAID, DEFAULTED = 1, 2, 3
AMOUNT, FLOAT, BOND = 100 * E18, 10 * E18, 50 * E18


@pytest.fixture
def s():
    """Bob pays; Alice and Carol are shops; the outsider carries notes; the oracle's key attests."""
    s = deploy_system(fee_bps=100, min_fee=E18 // 10, starting_reputation=200 * E18)
    s.allow = project.OfflineAllowanceScript.deploy(s.engine.address, s.rep.address, s.rct.address, s.usdc.address, s.oracle.address, sender=s.admin)
    s.usdc.mint(s.outsider, 1_000 * E18, sender=s.admin)
    s.usdc.approve(s.engine.address, MAX_UINT, sender=s.outsider)
    for user in (s.alice, s.bob, s.carol, s.outsider):
        s.engine.approveScript(s.allow.address, s.usdc.address, MAX_UINT, sender=user)
    s.rep.approveStake(s.allow.address, MAX_UINT, sender=s.bob)
    s.serial = 0
    return s


def opened(s, bond=BOND):
    """Bob locks 100 and a float of 10 for a week; notes can be presented for a further week."""
    s.expires = chain.blocks.head.timestamp + 7 * DAY
    tx = s.allow.open(AMOUNT, FLOAT, s.expires, 7 * DAY, bond, sender=s.bob)
    s.id = ev(tx)["AllowanceOpened"]["allowanceId"]
    s.cert = Certificate(chain.chain_id, s.allow.address, s.id, s.bob.address, AMOUNT, FLOAT, s.expires)
    s.cert_sig = sign_certificate(s.oracle, s.cert)
    return s.id


def note(s, payee, amount, **changes):
    s.serial += 1
    now = chain.blocks.head.timestamp
    fields = dict(promisor=s.bob.address, promisee=payee.address, asset=s.usdc.address, amount=amount, issued_at=now,
                  valid_until=s.expires + 7 * DAY, settle_within=3 * DAY, nonce=allowance_nonce(s.id, s.serial))
    fields.update(changes)
    n = Note(**fields)
    return n, sign_note(s.bob, chain.chain_id, s.engine.address, s.allow.address, n)


def present(s, signed_note, sender):
    n, signature = signed_note
    return s.allow.present(n.as_tuple(), signature, sender=sender)


def test_opening_locks_the_funds_and_the_certificate_needs_no_chain(s):
    before = s.usdc.balanceOf(s.bob)
    opened(s)
    assert s.usdc.balanceOf(s.bob) == before - AMOUNT - FLOAT
    assert s.usdc.balanceOf(s.allow.address) == AMOUNT + FLOAT
    assert s.rep.stakedReputation(s.bob) == BOND
    assert certificate_digest(s.cert) == bytes(s.allow.certificateDigest(s.id))
    assert signer_of(certificate_digest(s.cert), s.cert_sig) == s.oracle.address == s.allow.attester()


def test_a_payee_checks_a_note_with_no_connection(s):
    opened(s)
    now = chain.blocks.head.timestamp
    n, sig = note(s, s.alice, 40 * E18)
    check = lambda *a, **k: accept_note(*a, attester=s.oracle.address, engine=s.engine.address, **k)
    assert check(n, sig, s.cert, s.cert_sig, now=now) == (True, "within the allowance")
    assert not check(n, sig, s.cert, sign_certificate(s.carol, s.cert), now=now)[0]  # not the attester's certificate
    assert not check(n, sig, s.cert, s.cert_sig, now=s.expires + 1)[0]  # expired
    bigger = Certificate(chain.chain_id, s.allow.address, s.id, s.bob.address, 10 * AMOUNT, FLOAT, s.expires)
    assert not check(n, sig, bigger, s.cert_sig, now=now)[0]  # the payer altered the certificate
    forged = sign_note(s.carol, chain.chain_id, s.engine.address, s.allow.address, n)
    assert not check(n, forged, s.cert, s.cert_sig, now=now)[0]  # not the payer's note


def test_a_note_within_the_allowance_is_paid_whatever_becomes_of_the_payer(s):
    opened(s)
    signed = note(s, s.alice, 40 * E18)
    s.usdc.transfer(s.outsider, s.usdc.balanceOf(s.bob), sender=s.bob)  # Bob's own account is now empty
    s.engine.approveScript(s.allow.address, s.usdc.address, 0, sender=s.bob)
    before = [s.usdc.balanceOf(u) for u in (s.alice, s.outsider)]
    tx = present(s, signed, s.outsider)
    note_id = ev(tx)["NotePresented"]["noteId"]
    assert s.allow.notes(note_id)["status"] == PAID
    assert s.usdc.balanceOf(s.alice) == before[0] + 40 * E18
    assert s.usdc.balanceOf(s.outsider) == before[1]  # the carrier's fee came back from the float
    a = s.allow.allowances(s.id)
    assert (a["locked"], a["float"], a["presented"], a["overspent"]) == (60 * E18, FLOAT - 4 * E18 // 10, 40 * E18, False)
    assert certificate_digest(s.cert) == bytes(s.allow.certificateDigest(s.id))  # the certificate states the float as locked


def test_an_overspend_is_proved_by_the_notes_alone(s):
    opened(s)
    notes = [note(s, shop, 40 * E18) for shop in (s.alice, s.carol, s.alice)]
    engine = s.engine.address
    assert not proves_overspend(s.cert, notes[:2], engine)
    assert proves_overspend(s.cert, notes, engine)
    assert not proves_overspend(s.cert, [notes[0]] * 5, engine)  # the same note five times is one note
    n = notes[2][0]
    framed = (n, sign_note(s.carol, chain.chain_id, engine, s.allow.address, n))
    assert not proves_overspend(s.cert, notes[:2] + [framed], engine)  # nobody else can make the payer's notes
    now = chain.blocks.head.timestamp
    accept, reason = accept_note(*notes[2], s.cert, s.cert_sig, s.oracle.address, engine, now, known=notes[:2])
    assert not accept and "overspends" in reason
    assert accept_note(*notes[2], s.cert, s.cert_sig, s.oracle.address, engine, now, known=notes[:1])[0]


def overspent(s):
    """Three notes of 40 against an allowance of 100. Returns the id of the third."""
    opened(s)
    notes = [note(s, shop, 40 * E18) for shop in (s.alice, s.carol, s.alice)]
    present(s, notes[0], s.alice)
    present(s, notes[1], s.carol)
    s.carrier_before = s.usdc.balanceOf(s.outsider)
    tx = present(s, notes[2], s.outsider)
    return tx, ev(tx)["NotePresented"]["noteId"]


def test_the_note_that_overspends_rewards_its_presenter_and_destroys_the_bond(s):
    rep_before = s.rep.reputationScores(s.bob)
    tx, third = overspent(s)
    left_of_float = FLOAT - 2 * (4 * E18 // 10)
    assert ev(tx)["Overspent"]["provedBy"] == s.outsider.address
    assert ev(tx)["Overspent"]["reward"] == left_of_float
    assert s.usdc.balanceOf(s.outsider) == s.carrier_before - 4 * E18 // 10 + left_of_float
    assert s.rep.reputationScores(s.bob) == rep_before - BOND
    assert s.rep.stakedReputation(s.bob) == 0
    assert s.allow.notes(third)["status"] == PENDING
    a = s.allow.allowances(s.id)
    assert (a["locked"], a["float"], a["overspent"]) == (20 * E18, 0, True)


def test_an_overspent_note_is_paid_from_what_is_locked_and_the_payer_in_person(s):
    tx, third = overspent(s)
    before = [s.usdc.balanceOf(u) for u in (s.alice, s.bob, s.outsider)]
    s.allow.pay(third, sender=s.carol)  # anyone can
    assert s.allow.notes(third)["status"] == PAID
    assert s.usdc.balanceOf(s.alice) == before[0] + 40 * E18
    assert s.usdc.balanceOf(s.bob) == before[1] - 20 * E18 - 4 * E18 // 10  # 20 came from what was locked
    assert s.usdc.balanceOf(s.outsider) == before[2] + 4 * E18 // 10
    assert s.allow.allowances(s.id)["locked"] == 0


def test_an_overspent_note_left_unpaid_is_a_broken_promise(s):
    tx, third = overspent(s)
    s.engine.approveScript(s.allow.address, s.usdc.address, 0, sender=s.bob)
    with reverts():
        s.allow.pay(third, sender=s.alice)
    with reverts("CalculusEngine: Promise deadline has not passed"):
        s.allow.claimDefault(third, sender=s.alice)
    advance(3 * DAY + 1)
    alice_before = s.usdc.balanceOf(s.alice)
    rct_id = ev(s.allow.claimDefault(third, sender=s.outsider))["NoteDefaulted"]["rctId"]
    assert s.allow.notes(third)["status"] == DEFAULTED
    assert s.usdc.balanceOf(s.alice) == alice_before + 20 * E18  # what was still locked
    assert s.rct.ownerOf(rct_id) == s.alice.address
    assert s.rep.isDelinquent(s.bob)


def test_notes_outside_the_allowance_are_refused(s):
    opened(s)
    n, sig = note(s, s.alice, 40 * E18, promisor=s.carol.address)
    with reverts("OfflineAllowance: Not this payer's allowance"):
        s.allow.present(n.as_tuple(), sign_note(s.carol, chain.chain_id, s.engine.address, s.allow.address, n), sender=s.alice)
    late = note(s, s.alice, 40 * E18, valid_until=s.expires + 8 * DAY)
    with reverts("OfflineAllowance: Note outlives the allowance"):
        present(s, late, s.alice)
    in_time = note(s, s.alice, 40 * E18)
    advance(7 * DAY + 60)
    after = note(s, s.alice, 40 * E18)  # dated after the allowance expired
    with reverts("OfflineAllowance: Signed after the allowance expired"):
        present(s, after, s.alice)
    present(s, in_time, s.alice)  # signed in time, presented within the window


def test_closing_returns_what_is_left(s):
    opened(s)
    present(s, note(s, s.alice, 40 * E18), s.alice)
    with reverts("OfflineAllowance: Notes can still be presented"):
        s.allow.close(s.id, sender=s.bob)
    advance(14 * DAY + 1)
    before = s.usdc.balanceOf(s.bob)
    s.allow.close(s.id, sender=s.outsider)  # anyone can; the funds go to the payer
    assert s.usdc.balanceOf(s.bob) == before + 60 * E18 + FLOAT - 4 * E18 // 10
    assert s.rep.stakedReputation(s.bob) == 0 and s.rep.reputationScores(s.bob) == 200 * E18
    assert s.usdc.balanceOf(s.allow.address) == 0
    with reverts("OfflineAllowance: Allowance closed"):
        s.allow.close(s.id, sender=s.bob)


def test_the_model_reproduces_the_money(s):
    people = {"alice": s.alice, "bob": s.bob, "carol": s.carol, "carrier": s.outsider}
    before = {name: s.usdc.balanceOf(who) for name, who in people.items()}
    tx, third = overspent(s)
    s.engine.approveScript(s.allow.address, s.usdc.address, 0, sender=s.bob)
    advance(3 * DAY + 1)
    s.allow.claimDefault(third, sender=s.outsider)
    advance(14 * DAY)
    s.allow.close(s.id, sender=s.bob)

    e = Economy.current_rules(min_fee=0.1, fee_rate=0.01, point_price=0.04, decay_rate=0.0)
    for name in people:
        e.add_agent(name, money=before[name] / E18)
    a = e.open_allowance("bob", 100.0, 10.0)
    assert e.present_allowance_note(a, "alice", 40.0)
    assert e.present_allowance_note(a, "carol", 40.0)
    e.agents["bob"].money, kept_aside = 0.0, e.agents["bob"].money  # Bob withdrew the script's permission to pay from his account
    assert not e.present_allowance_note(a, "alice", 40.0, presenter="carrier")
    e.agents["bob"].money = kept_aside
    e.close_allowance(a)
    for name, who in people.items():
        assert s.usdc.balanceOf(who) / E18 == pytest.approx(e.agents[name].money), name
