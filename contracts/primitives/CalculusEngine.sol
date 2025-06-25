// File: contracts/primitives/CalculusEngine.sol (Revised for Atomic Actions & NFT Transfers)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

// --- NEW: Interface for ERC721 transfer ---
interface IERC721 {
    function transferFrom(address from, address to, uint256 tokenId) external;
}

/**
 * @title CalculusEngine
 * @author Rain Protocol
 * @dev The core of the Atomic Action Framework. This engine enforces that all economic
 * activity begins with a fee-paid, monitored action, creating an inescapable and
 * verifiable log of all promises and value transfers.
 */
contract CalculusEngine is AccessControl, ReentrancyGuard {
    using Counters for Counters.Counter;
    Counters.Counter private _promiseIdCounter;
    Counters.Counter private _actionIdCounter;

    // --- Roles ---
    bytes32 public constant SESSION_CREATOR_ROLE = keccak256("SESSION_CREATOR_ROLE");

    // --- Configuration ---
    IERC20 public immutable usdcToken;
    address public immutable treasuryAddress;
    uint256 public protocolFee;

    // --- Data Structures ---
    enum PromiseStatus { Pending, Fulfilled, Defaulted }

    struct Promise {
        uint256 actionId;
        address promisor;
        address promisee;
        address asset;
        uint256 amount;
        uint256 deadline;
        PromiseStatus status;
    }

    struct Action {
        address user; // The end-user who initiated and paid for the action
        address script; // The script contract that orchestrated the action
    }

    mapping(uint256 => Promise) public promises;
    mapping(uint256 => Action) public actions;

    // --- Events ---
    event ActionCreated(uint256 indexed actionId, address indexed user, address indexed script);
    event PromiseCreated(uint256 indexed promiseId, uint256 indexed actionId, address indexed promisor);
    event PromiseFulfilled(uint256 indexed promiseId);
    event PromiseDefaulted(uint256 indexed promiseId);
    event ValueTransferred(uint256 indexed actionId, address indexed asset, address indexed from, address indexed to, uint256 amount);
    event FeeUpdated(uint256 newFee);

    constructor(address _usdcTokenAddress, address _treasuryAddress, uint256 _initialProtocolFee) {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        usdcToken = IERC20(_usdcTokenAddress);
        treasuryAddress = _treasuryAddress;
        protocolFee = _initialProtocolFee;
    }

    // --- Core Primitives (Revised) ---

    /**
     * @notice The single, mandatory entry point for any economic session.
     * @dev Charges the protocol fee and creates a unique actionId that must be used
     * in all subsequent calls for this session.
     * @param user The end-user on whose behalf the action is being performed and who will pay the fee.
     * @return actionId The unique ID for this new economic session.
     */
    function monitoredAction(address user) external nonReentrant returns (uint256) {
        require(hasRole(SESSION_CREATOR_ROLE, msg.sender), "CalculusEngine: Caller is not a session creator");

        if (protocolFee > 0) {
            usdcToken.transferFrom(user, treasuryAddress, protocolFee);
        }

        _actionIdCounter.increment();
        uint256 actionId = _actionIdCounter.current();
        actions[actionId] = Action({ user: user, script: msg.sender });

        emit ActionCreated(actionId, user, msg.sender);
        return actionId;
    }

    function monitoredPromise(
        uint256 actionId,
        address promisor,
        address promisee,
        address asset,
        uint256 amount,
        uint256 deadline
    ) external nonReentrant returns (uint256) {
        require(hasRole(SESSION_CREATOR_ROLE, msg.sender), "CalculusEngine: Caller is not a session creator");
        require(actions[actionId].script == msg.sender, "CalculusEngine: Caller is not the original script for this action");

        _promiseIdCounter.increment();
        uint256 promiseId = _promiseIdCounter.current();

        promises[promiseId] = Promise({
            actionId: actionId,
            promisor: promisor,
            promisee: promisee,
            asset: asset,
            amount: amount,
            deadline: deadline,
            status: PromiseStatus.Pending
        });

        emit PromiseCreated(promiseId, actionId, promisor);
        return promiseId;
    }

    function monitoredTransfer(
        uint256 actionId,
        address asset,
        address from,
        address to,
        uint256 amount
    ) external nonReentrant {
        require(hasRole(SESSION_CREATOR_ROLE, msg.sender), "CalculusEngine: Caller is not a session creator");
        require(actions[actionId].script == msg.sender, "CalculusEngine: Caller is not the original script for this action");
        
        IERC20(asset).transferFrom(from, to, amount);

        emit ValueTransferred(actionId, asset, from, to, amount);
    }

    /**
     * @notice Transfers a specific non-fungible token (ERC721) within a monitored action.
     * @dev This is the primitive used for trading assets like Reputation Claim Tokens (RCTs).
     * @param actionId The ID of the fee-paid session.
     * @param asset The address of the ERC721 contract.
     * @param from The current owner of the NFT.
     * @param to The new owner of the NFT.
     * @param tokenId The specific ID of the token to transfer.
     */
    function monitoredNftTransfer(
        uint256 actionId,
        address asset,
        address from,
        address to,
        uint256 tokenId
    ) external nonReentrant {
        require(hasRole(SESSION_CREATOR_ROLE, msg.sender), "CalculusEngine: Caller is not a session creator");
        require(actions[actionId].script == msg.sender, "CalculusEngine: Caller is not the original script for this action");
        
        IERC721(asset).transferFrom(from, to, tokenId);

        // For NFTs, the "amount" is conceptually 1, representing the single token.
        emit ValueTransferred(actionId, asset, from, to, 1);
    }

    function monitoredFulfillment(uint256 promiseId) external nonReentrant {
        require(hasRole(SESSION_CREATOR_ROLE, msg.sender), "CalculusEngine: Caller is not a session creator");
        require(actions[promises[promiseId].actionId].script == msg.sender, "CalculusEngine: Caller is not the original script for this action");

        Promise storage p = promises[promiseId];
        require(p.status == PromiseStatus.Pending, "CalculusEngine: Promise not pending");
        require(block.timestamp <= p.deadline, "CalculusEngine: Promise deadline has passed");

        p.status = PromiseStatus.Fulfilled;
        emit PromiseFulfilled(promiseId);
    }

    function monitoredDefault(uint256 promiseId) external nonReentrant {
        require(hasRole(SESSION_CREATOR_ROLE, msg.sender), "CalculusEngine: Caller is not a session creator");
        require(actions[promises[promiseId].actionId].script == msg.sender, "CalculusEngine: Caller is not the original script for this action");

        Promise storage p = promises[promiseId];
        require(p.status == PromiseStatus.Pending, "CalculusEngine: Promise not pending");
        require(block.timestamp > p.deadline, "CalculusEngine: Promise deadline has not passed");

        p.status = PromiseStatus.Defaulted;
        emit PromiseDefaulted(promiseId);
    }

    // --- Admin Functions ---
    function setProtocolFee(uint256 _newFee) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        protocolFee = _newFee;
        emit FeeUpdated(_newFee);
    }
    
    function supportsInterface(bytes4 interfaceId) public view virtual override(AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}