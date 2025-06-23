import pytest
from brownie import RainfallPool, CurrencyToken, accounts, chain, reverts
from brownie.test import given, strategy

# --- Constants ---
SECONDS_PER_YEAR = 365 * 24 * 60 * 60
INITIAL_USDC_MINT_AMOUNT = 1_000_000 * (10**18) # For users
POOL_INITIAL_USDC = 100_000 * (10**18) # Initial liquidity for the pool by owner for some tests
DECIMALS = 10**18

# --- Fixtures ---

@pytest.fixture
def owner():
    return accounts[0]

@pytest.fixture
def user1():
    return accounts[1]

@pytest.fixture
def user2():
    return accounts[2]

@pytest.fixture
def usdc_token(owner): # This will be our DMD token acting as USDC
    token = CurrencyToken.deploy({'from': owner})
    token.mint(owner, INITIAL_USDC_MINT_AMOUNT, {'from': owner}) # Mint some for the owner too
    return token

@pytest.fixture
def rainfall_pool(owner, usdc_token):
    pool = RainfallPool.deploy(usdc_token.address, {'from': owner})
    # Owner can provide some initial liquidity to avoid division by zero in some rate calculations
    # if no deposits are made yet in a test.
    if usdc_token.balanceOf(owner) >= POOL_INITIAL_USDC:
        usdc_token.approve(pool.address, POOL_INITIAL_USDC, {'from': owner})
        pool.deposit(POOL_INITIAL_USDC, {'from': owner})
    return pool

@pytest.fixture
def setup_users_with_usdc(owner, usdc_token, user1, user2):
    usdc_token.mint(user1, INITIAL_USDC_MINT_AMOUNT, {'from': owner})
    usdc_token.mint(user2, INITIAL_USDC_MINT_AMOUNT, {'from': owner})
    return {"user1": user1, "user2": user2}


# --- Helper Functions ---
def approx_eq(val1, val2, tolerance_wei=1000): # Using fixed wei tolerance like in treasury
    return abs(val1 - val2) <= tolerance_wei

# --- Tests ---

def test_initial_state(rainfall_pool, usdc_token, owner):
    assert rainfall_pool.usdcToken() == usdc_token.address
    assert rainfall_pool.owner() == owner
    assert rainfall_pool.name() == "Rainfall Pool Share"
    assert rainfall_pool.symbol() == "rSHARE"
    assert rainfall_pool.decimals() == 18
    # Use approx_eq for borrowIndex due to potential small interest accrual during fixture setup deposit
    assert approx_eq(rainfall_pool.borrowIndex(), 1 * DECIMALS)
    assert rainfall_pool.lastInterestAccrualTimestamp() > 0

    # Check if owner's initial deposit (if any in fixture) reflected correctly
    if POOL_INITIAL_USDC > 0 and usdc_token.balanceOf(owner) >= POOL_INITIAL_USDC:
        assert rainfall_pool.totalSupplied() == POOL_INITIAL_USDC
        assert rainfall_pool.totalSupply() == POOL_INITIAL_USDC # Shares should be 1:1 for first deposit
        assert rainfall_pool.balanceOf(owner) == POOL_INITIAL_USDC
        assert usdc_token.balanceOf(rainfall_pool.address) == POOL_INITIAL_USDC

def test_deposit_usdc_and_mint_rshares(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    deposit_amount = 1000 * DECIMALS

    usdc_token.approve(rainfall_pool.address, deposit_amount, {'from': user})

    initial_pool_usdc_balance = usdc_token.balanceOf(rainfall_pool.address)
    initial_total_supplied = rainfall_pool.totalSupplied()
    initial_total_shares = rainfall_pool.totalSupply()
    initial_user_shares = rainfall_pool.balanceOf(user)

    tx = rainfall_pool.deposit(deposit_amount, {'from': user})

    # Check balances
    assert usdc_token.balanceOf(rainfall_pool.address) == initial_pool_usdc_balance + deposit_amount
    assert rainfall_pool.totalSupplied() == initial_total_supplied + deposit_amount

    # Share calculation: sharesToMint = (amountDeposited * currentTotalShares) / currentTotalSupply (before deposit)
    # If initial_total_shares is 0 (first depositor after owner's initial in fixture), shares are 1:1 with amount
    expected_shares_minted = 0
    if initial_total_shares == 0 or initial_total_supplied == 0: # Should not be the case due to fixture's owner deposit
        expected_shares_minted = deposit_amount
    else:
        expected_shares_minted = (deposit_amount * initial_total_shares) / initial_total_supplied

    assert rainfall_pool.totalSupply() == initial_total_shares + expected_shares_minted
    assert approx_eq(rainfall_pool.balanceOf(user), initial_user_shares + expected_shares_minted)

    # Check event
    assert "Deposited" in tx.events
    event = tx.events["Deposited"]
    assert event["user"] == user
    assert event["amountUSDC"] == deposit_amount
    assert approx_eq(event["amountShares"], expected_shares_minted)


def test_withdraw_usdc_and_burn_rshares(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    deposit_amount = 2000 * DECIMALS
    usdc_token.approve(rainfall_pool.address, deposit_amount, {'from': user})
    rainfall_pool.deposit(deposit_amount, {'from': user})

    user_shares_before_withdraw = rainfall_pool.balanceOf(user)
    shares_to_burn = user_shares_before_withdraw // 2 # Withdraw half

    initial_pool_usdc_balance = usdc_token.balanceOf(rainfall_pool.address)
    initial_total_supplied = rainfall_pool.totalSupplied()
    initial_total_shares = rainfall_pool.totalSupply()

    # Expected USDC: usdcToWithdraw = (sharesToBurn * currentTotalSupply) / currentTotalShares
    expected_usdc_to_withdraw = (shares_to_burn * initial_total_supplied) / initial_total_shares

    tx = rainfall_pool.withdraw(shares_to_burn, {'from': user})

    assert approx_eq(usdc_token.balanceOf(rainfall_pool.address), initial_pool_usdc_balance - expected_usdc_to_withdraw)
    assert approx_eq(rainfall_pool.totalSupplied(), initial_total_supplied - expected_usdc_to_withdraw)
    assert approx_eq(rainfall_pool.totalSupply(), initial_total_shares - shares_to_burn)
    assert approx_eq(rainfall_pool.balanceOf(user), user_shares_before_withdraw - shares_to_burn)

    # Check event
    assert "Withdrawn" in tx.events
    event = tx.events["Withdrawn"]
    assert event["user"] == user
    assert approx_eq(event["amountUSDC"], expected_usdc_to_withdraw)
    assert approx_eq(event["amountShares"], shares_to_burn)

def test_withdraw_insufficient_shares(rainfall_pool, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    # User has some shares from owner's initial deposit if user is owner, otherwise 0.
    # Let's ensure user has 0 shares if not owner.
    if user != rainfall_pool.owner():
         assert rainfall_pool.balanceOf(user) == 0
         with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
            rainfall_pool.withdraw(1 * DECIMALS, {'from': user})

def test_borrow_usdc(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    borrow_amount = 100 * DECIMALS

    # Ensure pool has enough liquidity (owner deposited initially in fixture)
    assert rainfall_pool.getAvailableCash() >= borrow_amount

    initial_user_usdc_balance = usdc_token.balanceOf(user)
    initial_pool_usdc_balance = usdc_token.balanceOf(rainfall_pool.address)
    initial_total_borrowed = rainfall_pool.totalBorrowed()
    initial_borrow_index = rainfall_pool.borrowIndex()

    tx = rainfall_pool.borrow(borrow_amount, {'from': user})

    assert usdc_token.balanceOf(user) == initial_user_usdc_balance + borrow_amount
    assert usdc_token.balanceOf(rainfall_pool.address) == initial_pool_usdc_balance - borrow_amount
    assert rainfall_pool.totalBorrowed() == initial_total_borrowed + borrow_amount
    assert rainfall_pool.borrowedAmountByUser(user) == borrow_amount # First time borrow
    assert approx_eq(rainfall_pool.userBorrowIndex(user), rainfall_pool.borrowIndex()) # userBorrowIndex is set to current borrowIndex

    # Event
    assert "Borrowed" in tx.events
    assert tx.events["Borrowed"]["user"] == user
    assert tx.events["Borrowed"]["amountUSDC"] == borrow_amount

def test_borrow_insufficient_liquidity(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    # Try to borrow more than available cash
    borrow_amount_too_high = rainfall_pool.getAvailableCash() + 100 * DECIMALS

    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.borrow(borrow_amount_too_high, {'from': user})

def test_repay_usdc(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    borrow_amount = 200 * DECIMALS
    repay_amount = borrow_amount # Repay full amount (approx, due to no time passing for interest)

    rainfall_pool.borrow(borrow_amount, {'from': user}) # User borrows

    initial_user_usdc_balance = usdc_token.balanceOf(user)
    initial_pool_usdc_balance = usdc_token.balanceOf(rainfall_pool.address)
    initial_total_borrowed = rainfall_pool.totalBorrowed()

    # Simulate some time for minor interest, then repay
    chain.sleep(100) # Sleep for 100 seconds
    chain.mine()
    rainfall_pool.accrueInterest() # Accrue interest before repay

    amount_owed_before_repay = rainfall_pool.getAmountOwed(user)
    # Attempt to repay the full amount owed
    usdc_token.approve(rainfall_pool.address, amount_owed_before_repay, {'from': user})
    tx = rainfall_pool.repay(amount_owed_before_repay, {'from': user})

    assert approx_eq(usdc_token.balanceOf(user), initial_user_usdc_balance - amount_owed_before_repay)
    assert approx_eq(usdc_token.balanceOf(rainfall_pool.address), initial_pool_usdc_balance + amount_owed_before_repay)

    final_owed = rainfall_pool.getAmountOwed(user)
    assert final_owed < 1000 # Should be very close to 0 (or exactly 0) if fully repaid
    if approx_eq(final_owed, 0):
        assert rainfall_pool.userBorrowIndex(user) == 0 # Resets if fully paid

    # Event
    assert "Repaid" in tx.events
    assert tx.events["Repaid"]["user"] == user
    assert approx_eq(tx.events["Repaid"]["amountUSDC"], amount_owed_before_repay)


def test_interest_accrual_increases_total_borrowed_and_supplied(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    borrow_amount = 5000 * DECIMALS # User borrows a significant amount

    # Ensure user has enough USDC and approves pool
    usdc_token.mint(user, borrow_amount * 2, {'from': accounts[0]})
    usdc_token.approve(rainfall_pool.address, borrow_amount * 2, {'from': user})

    # User deposits some to be able to borrow (or rely on owner's initial deposit)
    if rainfall_pool.balanceOf(user) == 0: # If user has no shares yet
        rainfall_pool.deposit(borrow_amount, {'from':user})


    rainfall_pool.borrow(borrow_amount, {'from': user})

    initial_total_borrowed = rainfall_pool.totalBorrowed()
    initial_total_supplied = rainfall_pool.totalSupplied()
    initial_borrow_index = rainfall_pool.borrowIndex()

    chain.sleep(SECONDS_PER_YEAR // 12) # Sleep for approx 1 month
    chain.mine()

    tx_accrue = rainfall_pool.accrueInterest()

    new_borrow_index = rainfall_pool.borrowIndex()
    new_total_borrowed = rainfall_pool.totalBorrowed()
    new_total_supplied = rainfall_pool.totalSupplied()

    assert new_borrow_index > initial_borrow_index
    assert new_total_borrowed > initial_total_borrowed
    assert new_total_supplied > initial_total_supplied

    # Interest accumulated = new_total_borrowed - initial_total_borrowed
    # This interest should also increase total_supplied
    interest_accumulated = new_total_borrowed - initial_total_borrowed
    assert approx_eq(new_total_supplied, initial_total_supplied + interest_accumulated)

    assert "InterestAccrued" in tx_accrue.events
    event = tx_accrue.events["InterestAccrued"]
    assert event["newBorrowIndex"] == new_borrow_index
    assert approx_eq(event["interestAccumulated"], interest_accumulated)


def test_get_amount_owed_with_interest(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    borrow_amount = 1000 * DECIMALS
    rainfall_pool.borrow(borrow_amount, {'from': user})

    chain.sleep(SECONDS_PER_YEAR // 2) # Approx 6 months
    chain.mine()
    rainfall_pool.accrueInterest()

    amount_owed = rainfall_pool.getAmountOwed(user)
    assert amount_owed > borrow_amount # Owed amount should be principal + interest

    # Rough check: interest rate is BASE (2%) + MULTIPLIER (20%) * UTILIZATION
    # Utilization is totalBorrowed / totalSupplied.
    # If user1 is the only borrower and owner deposited POOL_INITIAL_USDC (100k)
    # and user1 borrowed 1k. Utilization = 1k / (100k + interest_on_100k_if_any_before_borrow)
    # This is a complex calculation to verify precisely without knowing exact state,
    # but amount_owed should be greater than principal.
    # Example: If rate is 10% per year, after 6 months, interest is 5%. Owed = 1050.
    # current_rate_per_second = rainfall_pool.getCurrentBorrowRatePerSecond()
    # expected_interest = borrow_amount * current_rate_per_second * (SECONDS_PER_YEAR / 2) / DECIMALS (This is simplified)
    # A more precise check would use the borrowIndex: owed = P * (currentIndex / indexAtBorrowTime)

    expected_owed = (borrow_amount * rainfall_pool.borrowIndex()) / rainfall_pool.userBorrowIndex(user)
    assert approx_eq(amount_owed, expected_owed)


def test_exchange_rate_changes_with_interest(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    borrow_amount = 10000 * DECIMALS # User borrows
    deposit_for_shares_amount = borrow_amount * 2
    usdc_token.approve(rainfall_pool.address, deposit_for_shares_amount, {'from':user}) # Approve for potential deposit

    if rainfall_pool.balanceOf(user) == 0 and rainfall_pool.owner() != user: # If user is not owner and has no shares
         rainfall_pool.deposit(deposit_for_shares_amount, {'from':user}) # Deposit to have shares and allow borrowing

    initial_exchange_rate = rainfall_pool.getExchangeRate()

    # User borrows, pool accrues interest
    rainfall_pool.borrow(borrow_amount, {'from': user})
    chain.sleep(SECONDS_PER_YEAR // 4) # Approx 3 months
    chain.mine()
    rainfall_pool.accrueInterest()

    final_exchange_rate = rainfall_pool.getExchangeRate()
    # Exchange rate is TotalUSDCInPool / Total rSHARE tokens.
    # TotalUSDCInPool (totalSupplied) increases with interest. Total rSHARE tokens do not change from interest alone.
    # So, exchange rate should increase.
    assert final_exchange_rate > initial_exchange_rate

# --- Admin Functions ---
def test_set_owner(rainfall_pool, owner, user1):
    rainfall_pool.transferOwnership(user1, {'from': owner})
    assert rainfall_pool.owner() == user1
    # Attempt to call again from old owner
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.transferOwnership(owner, {'from': owner})
    # New owner can transfer back
    rainfall_pool.transferOwnership(owner, {'from': user1})
    assert rainfall_pool.owner() == owner

# --- Edge Cases ---
def test_deposit_zero(rainfall_pool, user1):
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.deposit(0, {'from': user1})

def test_withdraw_zero_shares(rainfall_pool, user1):
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.withdraw(0, {'from': user1})

def test_borrow_zero(rainfall_pool, user1):
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.borrow(0, {'from': user1})

def test_repay_zero(rainfall_pool, user1):
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.repay(0, {'from': user1})

def test_repay_when_not_borrowed(rainfall_pool, usdc_token, setup_users_with_usdc):
    user = setup_users_with_usdc["user1"]
    repay_amount = 100 * DECIMALS
    usdc_token.approve(rainfall_pool.address, repay_amount, {'from': user})
    with pytest.raises(Exception): # Changed from reverts to broad Exception due to BadResponseFormat
        rainfall_pool.repay(repay_amount, {'from': user})

# Test with multiple users interacting
def test_multiple_users_deposit_withdraw_borrow(rainfall_pool, usdc_token, setup_users_with_usdc):
    user1 = setup_users_with_usdc["user1"]
    user2 = setup_users_with_usdc["user2"]

    # User1 deposits
    deposit1_amount = 5000 * DECIMALS
    usdc_token.approve(rainfall_pool.address, deposit1_amount, {'from': user1})
    rainfall_pool.deposit(deposit1_amount, {'from': user1})
    user1_shares = rainfall_pool.balanceOf(user1)
    assert user1_shares > 0

    # User2 deposits
    deposit2_amount = 3000 * DECIMALS
    usdc_token.approve(rainfall_pool.address, deposit2_amount, {'from': user2})
    rainfall_pool.deposit(deposit2_amount, {'from': user2})
    user2_shares = rainfall_pool.balanceOf(user2)
    assert user2_shares > 0

    # User1 borrows
    borrow1_amount = 1000 * DECIMALS
    rainfall_pool.borrow(borrow1_amount, {'from': user1})
    assert rainfall_pool.borrowedAmountByUser(user1) > 0

    chain.sleep(1000)
    chain.mine()
    rainfall_pool.accrueInterest()

    # User2 borrows
    borrow2_amount = 500 * DECIMALS
    rainfall_pool.borrow(borrow2_amount, {'from': user2})
    assert rainfall_pool.borrowedAmountByUser(user2) > 0

    # User1 repays (partially or fully)
    amount_owed_user1 = rainfall_pool.getAmountOwed(user1)
    repay1_amount = amount_owed_user1 // 2
    usdc_token.approve(rainfall_pool.address, repay1_amount, {'from': user1})
    rainfall_pool.repay(repay1_amount, {'from': user1})
    assert rainfall_pool.getAmountOwed(user1) < amount_owed_user1

    # User2 withdraws some shares
    shares_to_withdraw_user2 = user2_shares // 3
    rainfall_pool.withdraw(shares_to_withdraw_user2, {'from': user2})
    assert rainfall_pool.balanceOf(user2) < user2_shares

    # Check some invariants
    assert rainfall_pool.totalSupplied() >= rainfall_pool.totalBorrowed()
    assert usdc_token.balanceOf(rainfall_pool.address) == rainfall_pool.getAvailableCash()
