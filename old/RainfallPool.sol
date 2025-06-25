// File: contracts/RainfallPool.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/Math.sol"; // For min/max functions if needed

/**
 * @title RainfallPool
 * @dev A lending pool for USDC (CurrencyToken).
 * Users can deposit USDC to lend and earn interest.
 * Users (or other contracts) can borrow USDC and pay interest.
 * Interest rates are dynamic based on pool utilization.
 */
contract RainfallPool is ERC20, Ownable {
    IERC20 public usdcToken; // The underlying USDC token (CurrencyToken)

    // Total USDC supplied to the pool by lenders
    uint256 public totalSupplied;
    // Total USDC currently borrowed from the pool
    uint256 public totalBorrowed;

    // Mapping from user address to their borrowed amount
    mapping(address => uint256) public borrowedAmountByUser;
    // Mapping from user address to the borrow index at the time of their borrow/repay action
    // Used to calculate accrued interest for individual borrows.
    mapping(address => uint256) public userBorrowIndex;

    // Interest rate model parameters (simplified)
    // FUTURE WORK: Placeholder - The interest rate model is simplified (linear based on utilization).
    // A more robust model (e.g., a "kinked" rate model like Aave or Compound) would have different slopes
    // for the interest rate below and above an optimal utilization rate to better manage liquidity risk.
    // Parameters like BASE_RATE, MULTIPLIER, OPTIMAL_UTILIZATION_RATE should also be governable.
    uint256 public constant BASE_RATE_PER_YEAR = 0.02 ether; // 2% expressed in 1e18 format
    uint256 public constant MULTIPLIER_PER_YEAR = 0.2 ether; // 20% expressed in 1e18 format
    uint256 public constant OPTIMAL_UTILIZATION_RATE = 0.8 ether; // 80% expressed in 1e18 format
    uint256 public constant SECONDS_PER_YEAR = 365 days;

    // Cumulative borrow index, tracks accrued interest over time for borrows
    uint256 public borrowIndex;
    // Timestamp of the last interest accrual update
    uint256 public lastInterestAccrualTimestamp;

    // Events
    event Deposited(address indexed user, uint256 amountUSDC, uint256 amountShares);
    event Withdrawn(address indexed user, uint256 amountUSDC, uint256 amountShares);
    event Borrowed(address indexed user, uint256 amountUSDC);
    event Repaid(address indexed user, uint256 amountUSDC);
    event InterestAccrued(uint256 newBorrowIndex, uint256 interestAccumulated);

    constructor(address _usdcTokenAddress) ERC20("Rainfall Pool Share", "rSHARE") Ownable() {
        require(_usdcTokenAddress != address(0), "USDC token address cannot be zero");
        usdcToken = IERC20(_usdcTokenAddress);

        borrowIndex = 1 ether; // Initial index is 1 (1e18)
        lastInterestAccrualTimestamp = block.timestamp;
    }

    // --- Interest Rate Calculation ---

    /**
     * @dev Calculates the current utilization rate of the pool.
     * Utilization = TotalBorrows / TotalSupply
     * Returns value in 1e18 format.
     */
    function getUtilizationRate() public view returns (uint256) {
        if (totalSupplied == 0) {
            return 0; // No supply, so utilization is 0
        }
        // Multiply by 1e18 for precision before division
        return (totalBorrowed * 1 ether) / totalSupplied;
    }

    /**
     * @dev Calculates the current borrow interest rate per second.
     * Simplified model: Rate = BaseRate + (UtilizationRate * Multiplier)
     * If Utilization > OptimalUtilization, rate increases more sharply (not implemented for this version for simplicity).
     * Returns rate per second in 1e18 format.
     */
    function getCurrentBorrowRatePerSecond() public view returns (uint256) {
        uint256 utilizationRate = getUtilizationRate();
        // Annual rate: base + utilization * multiplier
        uint256 borrowRatePerYear = BASE_RATE_PER_YEAR + (utilizationRate * MULTIPLIER_PER_YEAR / 1 ether);
        return borrowRatePerYear / SECONDS_PER_YEAR;
    }

    /**
     * @dev Accrues interest on total borrows, updating the borrowIndex.
     * This function should be called before any major state changes (deposit, withdraw, borrow, repay).
     */
    function accrueInterest() public {
        if (block.timestamp == lastInterestAccrualTimestamp) {
            return; // Already up-to-date
        }

        uint256 timeDelta = block.timestamp - lastInterestAccrualTimestamp;
        uint256 currentBorrowRate = getCurrentBorrowRatePerSecond();

        // FUTURE WORK: Placeholder - Interest calculation uses a simplified compounding approximation.
        // For greater accuracy, especially over longer periods or with very high rates,
        // a more precise compounding formula (e.g., based on exponentiation by squaring for (1+rate)^time)
        // might be necessary, often implemented using fixed-point math libraries (like OpenZeppelin's Math.sol for mulDiv).
        // The current approach `Index_new = Index_old * (1 + Rate * Time)` is a common simplification.
        uint256 interestFactor = currentBorrowRate * timeDelta;
        uint256 newBorrowIndex = borrowIndex + (borrowIndex * interestFactor / 1 ether);

        uint256 interestAccumulatedToPool;
        if (borrowIndex > 0) { // Avoid division by zero if borrowIndex was somehow 0
            interestAccumulatedToPool = ((newBorrowIndex * totalBorrowed) / borrowIndex) - totalBorrowed;
        } else {
            interestAccumulatedToPool = 0;
        }

        borrowIndex = newBorrowIndex;
        lastInterestAccrualTimestamp = block.timestamp;

        totalBorrowed += interestAccumulatedToPool;
        totalSupplied += interestAccumulatedToPool; // Lenders' supply also grows by the interest earned by the pool

        emit InterestAccrued(borrowIndex, interestAccumulatedToPool);
    }

    // --- Lender Functions (Deposit/Withdraw) ---

    /**
     * @dev Deposits USDC into the pool. Mints pool share tokens (rSHARE) to the depositor.
     * The amount of shares minted is proportional to their contribution to the total supply.
     * Shares = AmountDeposited * TotalShares / CurrentTotalSupply (before deposit)
     */
    function deposit(uint256 amountUSDC) external {
        require(amountUSDC > 0, "Deposit amount must be positive");
        accrueInterest(); // Update interest calculations first

        uint256 currentTotalSupply = totalSupplied; // USDC value of total supply
        uint256 currentTotalShares = totalSupply(); // ERC20 total supply of rSHARE tokens

        totalSupplied += amountUSDC;

        uint256 sharesToMint;
        if (currentTotalShares == 0 || currentTotalSupply == 0) {
            // First depositor, or pool was empty. Shares match USDC amount 1:1 initially (scaled by 1e18 for shares if USDC has fewer decimals)
            // Assuming USDC also has 18 decimals like our rSHARE for simplicity here.
            sharesToMint = amountUSDC;
        } else {
            // Shares = AmountDeposited * TotalShares / PreviousUSDCSupply
            sharesToMint = (amountUSDC * currentTotalShares) / currentTotalSupply;
        }

        require(sharesToMint > 0, "Shares to mint must be positive");

        // Transfer USDC from user to this contract
        require(usdcToken.transferFrom(_msgSender(), address(this), amountUSDC), "USDC transfer failed");

        _mint(_msgSender(), sharesToMint);
        emit Deposited(_msgSender(), amountUSDC, sharesToMint);
    }

    /**
     * @dev Withdraws USDC from the pool by burning pool share tokens (rSHARE).
     * AmountUSDC = SharesToBurn * CurrentTotalSupply / TotalShares (before burning)
     */
    function withdraw(uint256 sharesToBurn) external {
        require(sharesToBurn > 0, "Shares to burn must be positive");
        accrueInterest(); // Update interest calculations first

        uint256 currentTotalSupply = totalSupplied; // USDC value of total supply
        uint256 currentTotalShares = totalSupply(); // ERC20 total supply of rSHARE tokens

        require(balanceOf(_msgSender()) >= sharesToBurn, "Insufficient shares");
        require(currentTotalShares > 0, "No shares in the pool to burn"); // Should not happen if user has shares

        // AmountUSDC = SharesToBurn * CurrentUSDCSupply / TotalShares
        uint256 usdcToWithdraw = (sharesToBurn * currentTotalSupply) / currentTotalShares;

        require(usdcToWithdraw > 0, "USDC to withdraw must be positive");
        require(totalSupplied >= usdcToWithdraw, "Pool has insufficient liquidity for withdrawal"); // Check available cash

        totalSupplied -= usdcToWithdraw;

        _burn(_msgSender(), sharesToBurn);

        // Transfer USDC from this contract to the user
        require(usdcToken.transfer(_msgSender(), usdcToWithdraw), "USDC transfer failed");

        emit Withdrawn(_msgSender(), usdcToWithdraw, sharesToBurn);
    }

    // --- Borrower Functions (Borrow/Repay) ---

    /**
     * @dev Borrows USDC from the pool.
     * Caller must have appropriate collateral (not implemented in this contract directly, assumes external check).
     */
    function borrow(uint256 amountUSDC) external {
        require(amountUSDC > 0, "Borrow amount must be positive");
        accrueInterest();

        // Check if pool has enough liquidity (total supplied - total borrowed currently)
        require(totalSupplied - totalBorrowed >= amountUSDC, "Pool has insufficient liquidity to borrow");
        // Additional checks like collateral, credit limit would be here in a full system.

        uint256 amountOwedPreviously = getAmountOwed(_msgSender()); // Includes accrued interest on previous loan
        borrowedAmountByUser[_msgSender()] = amountOwedPreviously + amountUSDC;
        userBorrowIndex[_msgSender()] = borrowIndex; // Store current index for future interest calculation

        totalBorrowed += amountUSDC;

        // Transfer USDC from this contract to the borrower
        require(usdcToken.transfer(_msgSender(), amountUSDC), "USDC transfer failed");

        emit Borrowed(_msgSender(), amountUSDC);
    }

    /**
     * @dev Repays borrowed USDC to the pool.
     * The amount repaid should cover the principal + accrued interest.
     */
    function repay(uint256 amountUSDC) external {
        require(amountUSDC > 0, "Repay amount must be positive");
        accrueInterest();

        address borrower = _msgSender();
        uint256 owedAmount = getAmountOwed(borrower);

        require(owedAmount > 0, "No amount owed or already repaid");
        uint256 actualRepayment = Math.min(amountUSDC, owedAmount); // User cannot overpay their debt through this function

        // Transfer USDC from user to this contract
        require(usdcToken.transferFrom(borrower, address(this), actualRepayment), "USDC transfer failed");

        borrowedAmountByUser[borrower] = owedAmount - actualRepayment;
        totalBorrowed -= actualRepayment;

        // If fully repaid, reset their borrow index, otherwise it stays for remaining debt
        if (borrowedAmountByUser[borrower] == 0) {
             userBorrowIndex[borrower] = 0; // Or some other indicator of no active loan
        } else {
            // Update user's borrow index to current if partially repaid, so future interest is on remaining principal
            userBorrowIndex[borrower] = borrowIndex;
        }


        emit Repaid(borrower, actualRepayment);
    }

    // --- View Functions ---

    /**
     * @dev Returns the total USDC amount owed by a user, including accrued interest.
     */
    function getAmountOwed(address user) public view returns (uint256) {
        uint256 principalBorrowed = borrowedAmountByUser[user];
        if (principalBorrowed == 0) {
            return 0;
        }
        // Calculate interest accrued: Principal * (CurrentBorrowIndex / UserBorrowIndexAtTimeOfBorrow - 1)
        // AmountOwed = Principal * CurrentBorrowIndex / UserBorrowIndexAtTimeOfBorrow
        return (principalBorrowed * borrowIndex) / userBorrowIndex[user];
    }

    /**
     * @dev Returns the total cash available in the pool (not borrowed).
     */
    function getAvailableCash() public view returns (uint256) {
        return totalSupplied - totalBorrowed;
    }

    /**
     * @dev Returns the exchange rate of rSHARE tokens to USDC.
     * 1 rSHARE = X USDC. Returns value in 1e18 format.
     */
    function getExchangeRate() public view returns (uint256) {
        if (totalSupply() == 0) {
            return 1 ether; // Initial rate before any deposits
        }
        // ExchangeRate = TotalUSDCInPool / Total rSHARE tokens
        return (totalSupplied * 1 ether) / totalSupply();
    }
}
