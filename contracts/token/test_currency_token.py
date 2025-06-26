import pytest
from brownie import CurrencyToken, accounts, reverts # type: ignore

@pytest.fixture(scope="module")
def owner():
    return accounts[0]

@pytest.fixture(scope="module")
def user_a():
    return accounts[1]

@pytest.fixture(scope="module")
def user_b():
    return accounts[2]

@pytest.fixture(scope="module")
def currency_token(owner):
    """Deploys the CurrencyToken contract."""
    return owner.deploy(CurrencyToken)

def test_initial_state(currency_token, owner):
    """Test basic ERC20 properties and ownership."""
    assert currency_token.name() == "Demo Dollar"
    assert currency_token.symbol() == "DMD"
    assert currency_token.decimals() == 18  # Default for OpenZeppelin ERC20
    assert currency_token.totalSupply() == 0
    assert currency_token.owner() == owner

def test_mint(currency_token, owner, user_a):
    """Test minting new tokens."""
    mint_amount = 1000 * (10**18)  # 1000 tokens with 18 decimals

    tx = currency_token.mint(user_a, mint_amount, {"from": owner})

    assert currency_token.balanceOf(user_a) == mint_amount
    assert currency_token.totalSupply() == mint_amount

    # Check for Transfer event (from address(0) for minting)
    assert "Transfer" in tx.events
    assert tx.events["Transfer"]["from"] == "0x0000000000000000000000000000000000000000"
    assert tx.events["Transfer"]["to"] == user_a
    assert tx.events["Transfer"]["value"] == mint_amount

def test_mint_to_zero_address(currency_token, owner):
    """Test minting to the zero address (should be disallowed by OZ ERC20 _mint)."""
    mint_amount = 100 * (10**18)
    with reverts("ERC20: mint to the zero address"):
        currency_token.mint("0x0000000000000000000000000000000000000000", mint_amount, {"from": owner})

def test_mint_not_owner(currency_token, user_a, user_b):
    """Test that only the owner can mint tokens."""
    mint_amount = 100 * (10**18)
    with reverts("Ownable: caller is not the owner"):
        currency_token.mint(user_b, mint_amount, {"from": user_a})

def test_transfer(currency_token, owner, user_a, user_b):
    """Test standard ERC20 transfer."""
    initial_mint_amount = 500 * (10**18)
    currency_token.mint(user_a, initial_mint_amount, {"from": owner})

    transfer_amount = 200 * (10**18)
    tx = currency_token.transfer(user_b, transfer_amount, {"from": user_a})

    assert currency_token.balanceOf(user_a) == initial_mint_amount - transfer_amount
    assert currency_token.balanceOf(user_b) == transfer_amount

    assert "Transfer" in tx.events
    assert tx.events["Transfer"]["from"] == user_a
    assert tx.events["Transfer"]["to"] == user_b
    assert tx.events["Transfer"]["value"] == transfer_amount

def test_transfer_insufficient_balance(currency_token, owner, user_a, user_b):
    """Test transfer with insufficient balance."""
    currency_token.mint(user_a, 100 * (10**18), {"from": owner}) # user_a has 100 tokens

    with reverts("ERC20: transfer amount exceeds balance"):
        currency_token.transfer(user_b, 200 * (10**18), {"from": user_a})

def test_approve_and_transfer_from(currency_token, owner, user_a, user_b):
    """Test ERC20 approve and transferFrom mechanics."""
    spender = accounts[3]
    initial_mint_amount = 1000 * (10**18)
    currency_token.mint(user_a, initial_mint_amount, {"from": owner})

    allowance_amount = 300 * (10**18)
    approve_tx = currency_token.approve(spender, allowance_amount, {"from": user_a})

    assert currency_token.allowance(user_a, spender) == allowance_amount
    assert "Approval" in approve_tx.events
    assert approve_tx.events["Approval"]["owner"] == user_a
    assert approve_tx.events["Approval"]["spender"] == spender
    assert approve_tx.events["Approval"]["value"] == allowance_amount

    transfer_amount = 250 * (10**18)
    transfer_tx = currency_token.transferFrom(user_a, user_b, transfer_amount, {"from": spender})

    assert currency_token.balanceOf(user_a) == initial_mint_amount - transfer_amount
    assert currency_token.balanceOf(user_b) == transfer_amount
    assert currency_token.allowance(user_a, spender) == allowance_amount - transfer_amount

    assert "Transfer" in transfer_tx.events
    assert transfer_tx.events["Transfer"]["from"] == user_a
    assert transfer_tx.events["Transfer"]["to"] == user_b
    assert transfer_tx.events["Transfer"]["value"] == transfer_amount

def test_transfer_from_insufficient_allowance(currency_token, owner, user_a, user_b):
    """Test transferFrom with insufficient allowance."""
    spender = accounts[3]
    currency_token.mint(user_a, 500 * (10**18), {"from": owner})
    currency_token.approve(spender, 100 * (10**18), {"from": user_a}) # Allowance is 100

    with reverts("ERC20: insufficient allowance"):
        currency_token.transferFrom(user_a, user_b, 150 * (10**18), {"from": spender})

def test_transfer_from_insufficient_balance(currency_token, owner, user_a, user_b):
    """Test transferFrom where owner has insufficient balance but allowance is fine."""
    spender = accounts[3]
    currency_token.mint(user_a, 50 * (10**18), {"from": owner}) # user_a has only 50 tokens
    currency_token.approve(spender, 100 * (10**18), {"from": user_a}) # Allowance is 100

    with reverts("ERC20: transfer amount exceeds balance"):
        currency_token.transferFrom(user_a, user_b, 70 * (10**18), {"from": spender})

# Ownable tests (transferOwnership, renounceOwnership) are standard from OpenZeppelin
# and can be added if detailed testing of Ownable is required.
# For this contract, the primary custom logic is `mint` restricted by `onlyOwner`.
# The rest are standard ERC20 behaviors.
def test_transfer_ownership(currency_token, owner, user_a):
    """Test transferring ownership."""
    currency_token.transferOwnership(user_a, {"from": owner})
    assert currency_token.owner() == user_a

    # Old owner cannot mint anymore
    with reverts("Ownable: caller is not the owner"):
        currency_token.mint(accounts[3], 100, {"from": owner})

    # New owner can mint
    currency_token.mint(accounts[3], 100, {"from": user_a})
    assert currency_token.balanceOf(accounts[3]) == 100

def test_renounce_ownership(currency_token, owner):
    """Test renouncing ownership."""
    currency_token.renounceOwnership({"from": owner})
    assert currency_token.owner() == "0x0000000000000000000000000000000000000000"

    # No one can mint anymore
    with reverts("Ownable: caller is not the owner"):
        currency_token.mint(accounts[3], 100, {"from": owner})
    with reverts("Ownable: caller is not the owner"):
        currency_token.mint(accounts[3], 100, {"from": accounts[1]}) # Try with another account
```
