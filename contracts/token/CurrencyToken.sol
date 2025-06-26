// File: contracts/token/CurrencyToken.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title CurrencyToken
 * @dev A standard ERC20 token that can be minted by the owner.
 * This will serve as the stablecoin/currency in the demo economy.
 */
contract CurrencyToken is ERC20, Ownable {
    constructor() ERC20("Demo Dollar", "DMD") {}

    /**
     * @dev Creates `amount` tokens and assigns them to `to`, increasing
     * the total supply.
     *
     * Requirements:
     * - `to` cannot be the zero address.
     * - The caller must be the contract owner.
     */
    function mint(address to, uint256 amount) public onlyOwner {
        _mint(to, amount);
    }
}