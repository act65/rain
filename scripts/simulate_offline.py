# File: scripts/simulate_offline.py
"""
A payment made while disconnected, and a double spend. Run with `uv run ape run simulate_offline`.

  1. Before losing the connection, Bob gives the note script an allowance to pay from.
  2. Offline, Bob buys from two shops. Neither can check his balance. Each decides what to accept
     from his record (he is a stranger) and the number of places he could be spending at once.
     Bob signs a note to each. He holds enough for one of them.
  3. A carrier reaches the chain and presents both notes. The first is paid. The second is
     recorded all the same, as a promise Bob has a week to keep.
  4. He does not. The promise is broken, the shop holds a claim on him, and he is delinquent.
  5. The oracle and a reader see one kept promise and one broken one.
"""
from ape import accounts, chain, project

from rain.offline import Note, read_notes, sign_note, split_limit
from rain.record import largest_amount_due, weigh
from rain.utils import load_deployment_data
from scripts import deploy as deploy_script
from scripts import run_reputation_oracle as oracle_script

DEPLOYMENT_FILE = "deployment_addresses.json"
E18 = 10**18
DAY = 24 * 60 * 60
BELIEF = dict(risk_tolerance=0.10, floor=100.0, tail_index=1.0, shock_rate=0.02)  # the payees' belief (experiments/offline)


def main():
    print("--- OFFLINE PAYMENTS ---")
    deploy_script.main()
    deployer, alice, bob, charlie, carrier = accounts.test_accounts[0:5]
    addresses = load_deployment_data(DEPLOYMENT_FILE)
    engine = project.CalculusEngine.at(addresses["CalculusEngine"])
    currency = project.CurrencyToken.at(addresses["CurrencyToken"])
    reputation = project.RainReputation.at(addresses["RainReputation"])
    rct = project.ReputationClaimToken.at(addresses["ReputationClaimToken"])
    notes = project.OfflineNoteScript.deploy(engine.address, rct.address, currency.address, sender=deployer)
    print(f"OfflineNoteScript deployed at: {notes.address}")

    print("\n--- 1. Before the connection is lost ---")
    currency.mint(carrier.address, 10 * E18, sender=deployer)  # the carrier fronts the fees
    for user in (bob, carrier):
        currency.approve(engine.address, 2**256 - 1, sender=user)
        engine.approveScript(notes.address, currency.address, 2**256 - 1, sender=user)
    currency.transfer(deployer.address, currency.balanceOf(bob) - 60 * E18, sender=bob)
    print(f"  - Bob holds {currency.balanceOf(bob) / E18} DMD and has let the note script pay from it.")
    print(f"  - He has not authorised the script to make promises for him: {engine.isScriptAuthorized(bob, notes.address)}")

    print("\n--- 2. Offline: two shops, neither can see the chain or each other ---")
    limit = largest_amount_due(weigh([], bob.address).repaid, **BELIEF)
    each = split_limit(limit, 2)
    print(f"  - Bob has no record. A stranger's limit is {limit:.1f}; he could be at 2 shops, so each accepts up to {each:.1f}.")
    now = chain.blocks.head.timestamp
    signed = []
    for nonce, (name, shop) in enumerate((("Alice", alice), ("Charlie", charlie)), start=1):
        note = Note(promisor=bob.address, promisee=shop.address, asset=currency.address, amount=50 * E18,
                    issued_at=now, valid_until=now + 30 * DAY, settle_within=7 * DAY, nonce=nonce)
        assert note.amount / E18 <= each
        signed.append((name, shop, note, sign_note(bob, chain.chain_id, engine.address, notes.address, note)))
        print(f"  - Bob signs a note for {note.amount / E18} DMD to {name}. No transaction is sent.")
    print("  - The two notes promise 100 DMD. Bob holds 60: a double spend, and nothing offline can prevent it.")

    print("\n--- 3. A carrier reaches the chain and presents both notes ---")
    status = {1: "pending", 2: "paid", 3: "defaulted"}
    ids = {}
    for name, shop, note, signature in signed:
        before = currency.balanceOf(shop)
        notes.present(note.as_tuple(), signature, sender=carrier)
        ids[name] = notes.noteCount()
        print(f"  - {name}'s note: {status[notes.notes(ids[name]).status]}. {name} received {(currency.balanceOf(shop) - before) / E18} DMD.")
    assert notes.notes(ids["Alice"]).status == 2 and notes.notes(ids["Charlie"]).status == 1
    print("  - The second note was not rejected. It is a promise on the log, and Bob has 7 days to keep it.")

    print("\n--- 4. The deadline passes ---")
    chain.pending_timestamp += 7 * DAY + 1
    chain.mine()
    notes.claimDefault(ids["Charlie"], sender=charlie)
    rct_id = rct.claimForPromise(notes.notes(ids["Charlie"]).promiseId)
    print(f"  - Charlie holds claim {rct_id} on Bob for {rct.claims(rct_id).shortfallAmount / E18} DMD.")
    print(f"  - Bob is delinquent: {reputation.isDelinquent(bob)}")
    assert rct.ownerOf(rct_id) == charlie.address and reputation.isDelinquent(bob)

    print("\n--- 5. What the record now says ---")
    oracle_script.main()
    kept, broken = reputation.reputationScores(bob) / E18, reputation.brokenScores(bob) / E18
    print(f"  - On chain: Bob's reputation {kept}, broken-promise counter {broken}.")
    evidence = weigh(read_notes(engine, notes), bob.address)
    print(f"  - A reader: {evidence.kept:.0f} kept, {evidence.broken:.0f} broken; "
          f"chance the next promise is kept {evidence.reliability(1, 1):.2f} (from an even prior).")
    assert kept > 0 and broken > 0 and (evidence.kept, evidence.broken) == (1, 1)
    print("\n--- OFFLINE SIMULATION COMPLETE ---")
