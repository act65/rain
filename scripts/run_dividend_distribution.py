# File: scripts/run_dividend_distribution.py
"""
Runs one dividend cycle: the Treasury shares out a fraction of its payout fund (which holds
all the fees received so far), split pro rata to reputation off-chain, and users claim via
Merkle proofs.
"""

from ape import accounts, chain, networks, project

from rain.dividends import calculate_dividend_shares, get_merkle_proof, get_reputation_holders
from rain.utils import expect_revert, load_deployment_data

DEPLOYMENT_FILE = "deployment_addresses.json"


def main():
    print("--- DIVIDEND DISTRIBUTION ---")
    manager = accounts.test_accounts[0]  # Must hold MANAGER_ROLE on the Treasury

    addresses = load_deployment_data(DEPLOYMENT_FILE)
    if not addresses:
        raise RuntimeError("Could not load deployment addresses. Run scripts/deploy.py first.")

    currency_token = project.CurrencyToken.at(addresses["CurrencyToken"])
    rain_reputation = project.RainReputation.at(addresses["RainReputation"])
    treasury = project.Treasury.at(addresses["Treasury"])

    # --- 0. IS A CYCLE DUE? ---
    wait = treasury.nextCycleTimestamp() - chain.pending_timestamp
    if wait > 0:
        if not networks.provider.network.is_local:
            print(f"The next cycle is not due for another {wait} seconds.")
            return
        print(f"(Local chain: moving the clock forward {wait} seconds to when the next cycle is due.)")
        chain.pending_timestamp += wait
        chain.mine()

    # --- 1. THE POOL ---
    fund = treasury.payoutFund() + treasury.uncounted()
    pool = treasury.distributable()
    print(f"\nPayout fund: {fund / 10**18} DMD. This cycle shares out {treasury.releasePerCycle() / 10**16}% of it: {pool / 10**18} DMD.")

    # --- 2. OFF-CHAIN: SHARES AND MERKLE TREE ---
    holders = get_reputation_holders(rain_reputation)
    shares, merkle_root, total_reputation = calculate_dividend_shares(rain_reputation, holders, pool)
    if not shares:
        print("Nobody holds reputation (or the pool is too small to share). Nothing to distribute.")
        return
    print(f"Total reputation: {total_reputation / 10**18}")
    for share in shares:
        print(f"  - {share['account']}: reputation {share['reputation'] / 10**18}, dividend {share['amount'] / 10**18} DMD")

    # --- 3. ON-CHAIN: CREATE THE CYCLE ---
    to_holders = sum(share["amount"] for share in shares)
    treasury.createDividendCycle(merkle_root, to_holders, sender=manager)
    cycle_id = treasury.getNumberOfCycles() - 1
    print(f"\nDividend Cycle {cycle_id} created: {to_holders / 10**18} DMD to holders; {treasury.payoutFund() / 10**18} DMD stays in the fund for later cycles.")

    # --- 4. ON-CHAIN: CLAIMS ---
    by_address = {account.address: account for account in accounts.test_accounts}
    for i, share in enumerate(shares):
        proof = get_merkle_proof(shares, share["account"], share["amount"])
        claimant = by_address[share["account"]]
        if i == 0:  # a claim for more than the allotted amount must fail
            expect_revert(
                lambda: treasury.claimDividend(cycle_id, share["amount"] + 1, proof, sender=claimant), "Invalid Merkle proof"
            )
        balance_before = currency_token.balanceOf(claimant)
        treasury.claimDividend(cycle_id, share["amount"], proof, sender=claimant)
        assert currency_token.balanceOf(claimant) == balance_before + share["amount"]
        print(f"  - {share['account']} claimed {share['amount'] / 10**18} DMD.")

    print("\nDividend distribution complete.")
    return cycle_id, shares
