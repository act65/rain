#!/bin/bash

# This mnemonic is public and for testing purposes only.
# DO NOT USE THIS MNEMONIC FOR ANY REAL WALLET.
TEST_MNEMONIC="candy maple cake sugar pudding cream honey rich smooth crumble sweet treat"

# Define some named accounts for clarity in scripts
# Ganache will generate 10 accounts from the mnemonic.
# Account 0: Deployer/Owner
# Account 1: Alice
# Account 2: Bob
# Account 3: Charlie
# ...and so on.

echo "================================================================="
echo "Starting local Ganache blockchain..."
echo "Mnemonic: $TEST_MNEMONIC"
echo "================================================================="
echo "--- Named Accounts ---"
echo "Account 0: Deployer"
echo "Account 1: Alice"
echo "Account 2: Bob"
echo "Account 3: Charlie"
echo "----------------------"

ganache-cli \
    --mnemonic "$TEST_MNEMONIC" \
    --port 8545 \
    --accounts 10 \
    --defaultBalanceEther 1000 \
    --gasLimit 12000000 \
    --deterministic