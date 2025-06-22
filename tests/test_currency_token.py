import pytest
from brownie import CurrencyToken, accounts

@pytest.fixture
def currency_token():
    # Deploy the contract
    owner = accounts[0]
    token = CurrencyToken.deploy({'from': owner})
    # Mint initial supply to the owner
    initial_supply = 1_000_000 * 10**18
    token.mint(owner, initial_supply, {'from': owner})
    return token

def test_initial_state(currency_token):
    assert currency_token.name() == "Demo Dollar"
    assert currency_token.symbol() == "DMD"
    assert currency_token.decimals() == 18 # ERC20 default, confirm from contract if ever changed
    assert currency_token.totalSupply() == 1_000_000 * 10**18
    assert currency_token.balanceOf(accounts[0]) == 1_000_000 * 10**18

def test_mint(currency_token):
    owner = accounts[0]
    recipient = accounts[1]
    initial_supply = currency_token.totalSupply()
    initial_recipient_balance = currency_token.balanceOf(recipient)
    mint_amount = 1000 * 10**18

    currency_token.mint(recipient, mint_amount, {'from': owner})

    assert currency_token.totalSupply() == initial_supply + mint_amount
    assert currency_token.balanceOf(recipient) == initial_recipient_balance + mint_amount

def test_mint_not_owner(currency_token):
    non_owner = accounts[1]
    recipient = accounts[2]
    mint_amount = 1000 * 10**18
    with pytest.raises(Exception): # Expecting a revert
        currency_token.mint(recipient, mint_amount, {'from': non_owner})

def test_transfer(currency_token):
    sender = accounts[0]
    recipient = accounts[1]
    initial_sender_balance = currency_token.balanceOf(sender)
    initial_recipient_balance = currency_token.balanceOf(recipient)
    transfer_amount = 500 * 10**18

    currency_token.transfer(recipient, transfer_amount, {'from': sender})

    assert currency_token.balanceOf(sender) == initial_sender_balance - transfer_amount
    assert currency_token.balanceOf(recipient) == initial_recipient_balance + transfer_amount

def test_transfer_insufficient_balance(currency_token):
    sender = accounts[1] # Has 0 balance initially
    recipient = accounts[2]
    transfer_amount = 100 * 10**18
    with pytest.raises(Exception):
        currency_token.transfer(recipient, transfer_amount, {'from': sender})

def test_approve(currency_token):
    owner = accounts[0]
    spender = accounts[1]
    approve_amount = 200 * 10**18

    currency_token.approve(spender, approve_amount, {'from': owner})
    assert currency_token.allowance(owner, spender) == approve_amount

def test_transfer_from(currency_token):
    owner = accounts[0]
    spender = accounts[1]
    recipient = accounts[2]
    initial_owner_balance = currency_token.balanceOf(owner)
    initial_recipient_balance = currency_token.balanceOf(recipient)
    approve_amount = 300 * 10**18
    transfer_amount = 250 * 10**18

    currency_token.approve(spender, approve_amount, {'from': owner})
    currency_token.transferFrom(owner, recipient, transfer_amount, {'from': spender})

    assert currency_token.allowance(owner, spender) == approve_amount - transfer_amount
    assert currency_token.balanceOf(owner) == initial_owner_balance - transfer_amount
    assert currency_token.balanceOf(recipient) == initial_recipient_balance + transfer_amount

def test_transfer_from_insufficient_allowance(currency_token):
    owner = accounts[0]
    spender = accounts[1]
    recipient = accounts[2]
    approve_amount = 100 * 10**18
    transfer_amount = 150 * 10**18 # More than approved

    currency_token.approve(spender, approve_amount, {'from': owner})
    with pytest.raises(Exception):
        currency_token.transferFrom(owner, recipient, transfer_amount, {'from': spender})

def test_transfer_from_insufficient_balance(currency_token):
    owner = accounts[0]
    spender = accounts[1]
    recipient = accounts[2]

    # Mint a small amount to owner so they have less than transfer_amount
    # First, transfer almost all balance from owner to another account
    initial_owner_supply = currency_token.balanceOf(owner)
    transfer_to_temp_amount = initial_owner_supply - (50 * 10**18) # leave 50 tokens
    currency_token.transfer(accounts[3], transfer_to_temp_amount, {'from': owner})

    current_owner_balance = currency_token.balanceOf(owner)
    approve_amount = 100 * 10**18
    transfer_amount = 100 * 10**18 # Owner has less than this

    assert current_owner_balance < transfer_amount # Ensure owner has less than transfer_amount

    currency_token.approve(spender, approve_amount, {'from': owner})
    with pytest.raises(Exception):
        currency_token.transferFrom(owner, recipient, transfer_amount, {'from': spender})
