// File: contracts/mocks/MockYieldSource.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title MockYieldSource
 * @dev A simple mock contract to simulate a yield-bearing protocol for testing the Treasury.
 * It simply holds and returns the deposited funds.
 */
contract MockYieldSource {
    // This function mimics depositing into a protocol like Aave.
    function deposit(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external {
        // In a real protocol, this would do much more. Here, we just pull the funds.
        IERC20(asset).transferFrom(msg.sender, address(this), amount);
    }

    // This function mimics withdrawing from a protocol.
    function withdraw(address asset, uint256 amount, address to) external returns (uint256) {
        // Simply send the funds back to the requested address.
        IERC20(asset).transfer(to, amount);
        return amount;
    }
}