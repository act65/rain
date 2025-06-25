// File: interfaces/IReputationClaimToken.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

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
    function burn(uint256 tokenId) external;
    function claims(uint256 tokenId) external view returns (DebtClaim memory);
}