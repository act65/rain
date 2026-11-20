# File: scripts/simulate_allowance.py
"""
Offline payments backed by locked funds, and an overspend. Run with `uv run ape run simulate_allowance`.

  1. Before losing the connection Bob locks 100 DMD and a float of 20, and the attester certifies it.
  2. Offline, Bob pays three shops 40 each. Each shop checks the certificate and the note with no
     connection. The third shop has heard of the first two notes and refuses: the three together
     prove an overspend. A fourth shop, which has heard nothing, accepts.
  3. A carrier presents the notes. The first two are paid from the locked funds, although Bob's own
     account is empty. The note that takes the total past 100 pays the carrier what is left of the float.
"""
from ape import accounts, chain, project

from rain.offline import Certificate, Note, accept_note, allowance_nonce, proves_overspend, sign_certificate, sign_note
from rain.utils import load_deployment_data
from scripts import deploy as deploy_script

DEPLOYMENT_FILE = "deployment_addresses.json"
E18 = 10**18
DAY = 24 * 60 * 60


def main():
    print("--- OFFLINE PAYMENTS BACKED BY LOCKED FUNDS ---")
    deploy_script.main()
    deployer, alice, bob, charlie, carrier, dana = accounts.test_accounts[0:6]
    attester = deployer  # in the simulation the deployer plays the oracle
    addresses = load_deployment_data(DEPLOYMENT_FILE)
    engine = project.CalculusEngine.at(addresses["CalculusEngine"])
    currency = project.CurrencyToken.at(addresses["CurrencyToken"])
    script = project.OfflineAllowanceScript.deploy(engine.address, addresses["RainReputation"], addresses["ReputationClaimToken"],
                                                   currency.address, attester.address, sender=deployer)

    print("\n--- 1. Before the connection is lost ---")
    currency.mint(carrier.address, 10 * E18, sender=deployer)
    for user in (bob, carrier):
        currency.approve(engine.address, 2**256 - 1, sender=user)
        engine.approveScript(script.address, currency.address, 2**256 - 1, sender=user)
    expires = chain.blocks.head.timestamp + 7 * DAY
    script.open(100 * E18, 20 * E18, expires, 7 * DAY, 0, sender=bob)
    allowance = script.allowanceCount()
    certificate = Certificate(chain.chain_id, script.address, allowance, bob.address, 100 * E18, 20 * E18, expires)
    certificate_signature = sign_certificate(attester, certificate)
    currency.transfer(deployer.address, currency.balanceOf(bob), sender=bob)
    print("  - Bob locked 100 DMD to pay notes from and a float of 20, and carries the attester's certificate.")
    print(f"  - His own account now holds {currency.balanceOf(bob) / E18} DMD.")

    print("\n--- 2. Offline ---")
    now = chain.blocks.head.timestamp
    shops = (("Alice", alice), ("Charlie", charlie), ("Dana", dana))
    signed = []
    for serial, (name, shop) in enumerate(shops, start=1):
        note = Note(promisor=bob.address, promisee=shop.address, asset=currency.address, amount=40 * E18, issued_at=now,
                    valid_until=expires + 7 * DAY, settle_within=3 * DAY, nonce=allowance_nonce(allowance, serial))
        signed.append((note, sign_note(bob, chain.chain_id, engine.address, script.address, note)))
    check = lambda item, known: accept_note(*item, certificate, certificate_signature, attester.address, engine.address, now, known=known)
    print(f"  - Alice, who has heard nothing: {check(signed[0], [])}")
    print(f"  - Charlie, who has heard nothing: {check(signed[1], [])}")
    print(f"  - Dana, if she has heard of the other two notes: {check(signed[2], signed[:2])}")
    print(f"  - Dana, if she has heard nothing: {check(signed[2], [])}")
    print(f"  - The three notes together prove an overspend to anyone: {proves_overspend(certificate, signed, engine.address)}")
    assert check(signed[0], [])[0] and not check(signed[2], signed[:2])[0] and check(signed[2], [])[0]

    print("\n--- 3. A carrier reaches the chain ---")
    status = {1: "pending (owed by Bob in person)", 2: "paid from the locked funds"}
    for (name, shop), (note, signature) in zip(shops, signed):
        before, carrier_before = currency.balanceOf(shop), currency.balanceOf(carrier)
        script.present(note.as_tuple(), signature, sender=carrier)
        print(f"  - {name}'s note: {status[script.notes(script.noteCount()).status]}. {name} received "
              f"{(currency.balanceOf(shop) - before) / E18} DMD; the carrier's balance moved by {(currency.balanceOf(carrier) - carrier_before) / E18}.")
    a = script.allowances(allowance)
    print(f"  - Overspent: {a.overspent}. Still locked: {a.locked / E18} DMD, which goes towards Dana's note. Float left: {a.float / E18}.")
    assert a.overspent and a.float == 0 and script.notes(3).status == 1
    print("\n--- ALLOWANCE SIMULATION COMPLETE ---")
