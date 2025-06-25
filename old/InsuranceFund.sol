// File: contracts/InsuranceFund.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

// Interface to interact with the ReputationClaimToken contract
interface IReputationClaimToken {
    struct DebtClaim {
        address defaulterAddress;
        address originalLenderAddress;
        uint256 shortfallAmount;
        uint256 defaultTimestamp;
        address loanContractAddress;
    }
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function claims(uint256 tokenId) external view returns (DebtClaim memory);
}

/**
 * @title InsuranceFund
 * @author Rain Protocol
 * @dev This contract acts as the liquidity backstop for the protocol. It is funded by a share
 * of protocol fees and serves as the "buyer of last resort" for Reputation Claim Tokens (RCTs),
 * providing immediate cash to lenders who have suffered a default.
 */
contract InsuranceFund is Ownable {
    IERC20 public immutable usdcToken;
    IReputationClaimToken public immutable rctContract;
    uint256 public redemptionRateBps; // Basis points, e.g., 9000 = 90%

    event ClaimRedeemed(
        uint256 indexed tokenId,
        address indexed seller,
        uint256 shortfallAmount,
        uint256 payoutAmount
    );
    event RedemptionRateUpdated(uint256 newRateBps);

    constructor(
        address _usdcTokenAddress,
        address _rctContractAddress,
        uint256 _initialRedemptionRateBps
    ) {
        require(_usdcTokenAddress != address(0) && _rctContractAddress != address(0), "Zero address");
        require(_initialRedemptionRateBps <= 10000, "Rate cannot exceed 100%");
        
        usdcToken = IERC20(_usdcTokenAddress);
        rctContract = IReputationClaimToken(_rctContractAddress);
        redemptionRateBps = _initialRedemptionRateBps;
    }

    /**
     * @notice Allows a user to redeem their RCT for immediate USDC.
     * @dev The user must own the RCT and must have approved this contract to transfer it.
     * This contract buys the RCT at a discount defined by `redemptionRateBps`.
     * @param tokenId The ID of the RCT to redeem.
     */
    function redeemClaim(uint256 tokenId) external {
        // Check that the caller is the legitimate owner of the RCT
        require(rctContract.ownerOf(tokenId) == msg.sender, "InsuranceFund: Caller is not the owner of the claim token");

        // Get the details of the debt from the RCT contract
        IReputationClaimToken.DebtClaim memory claim = rctContract.claims(tokenId);
        uint256 shortfallAmount = claim.shortfallAmount;

        // Calculate the payout based on the current redemption rate
        uint256 payoutAmount = (shortfallAmount * redemptionRateBps) / 10000;

        // Ensure the fund has enough capital to make the payment
        require(usdcToken.balanceOf(address(this)) >= payoutAmount, "InsuranceFund: Insufficient liquidity");

        // Pay the user their discounted amount
        usdcToken.transfer(msg.sender, payoutAmount);

        // Take ownership of the RCT. The fund now holds the claim.
        rctContract.transferFrom(msg.sender, address(this), tokenId);

        emit ClaimRedeemed(tokenId, msg.sender, shortfallAmount, payoutAmount);
    }

    // --- Admin Functions ---

    /**
     * @notice Updates the redemption rate for RCTs.
     * @param _newRateBps The new rate in basis points (1 to 10000).
     */
    function setRedemptionRate(uint256 _newRateBps) external onlyOwner {
        require(_newRateBps <= 10000, "Rate cannot exceed 100%");
        redemptionRateBps = _newRateBps;
        emit RedemptionRateUpdated(_newRateBps);
    }

    /**
     * @notice Allows the owner (DAO) to withdraw surplus funds for investment or other purposes.
     * @param amount The amount of USDC to withdraw.
     */
    function emergencyWithdraw(uint256 amount) external onlyOwner {
        require(usdcToken.balanceOf(address(this)) >= amount, "Cannot withdraw more than balance");
        usdcToken.transfer(owner(), amount);
    }
}