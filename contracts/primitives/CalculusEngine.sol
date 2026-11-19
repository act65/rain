// File: contracts/primitives/CalculusEngine.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

interface IERC721 {
    function transferFrom(address from, address to, uint256 tokenId) external;
}

/**
 * @title CalculusEngine
 * @author Rain Protocol
 * @dev The core of the Atomic Action Framework: a verifiable log of promises and
 * value transfers.
 *
 * Anyone may write a script (a contract that calls the `monitored*` primitives).
 * Scripts need no permission from the protocol. Instead, every power a script has
 * over a user is one that user granted to that script:
 *
 *   - a script can only name a user as promisor (or as the user of an action) if the
 *     user authorized that script (`setScriptAuthorization`);
 *   - a script can only move a user's tokens up to the allowance the user gave that
 *     script for that asset (`approveScript`, `setScriptNftApproval`).
 *
 * The protocol fee is charged per promise, to the promisor, and is proportional to
 * the amount promised (with a minimum). The fee paid is recorded with the promise:
 * a kept promise earns reputation in proportion to it, at `pointPrice` currency units
 * of fee per reputation point. So reputation has a fixed price, and is a record of
 * fees paid on promises that were kept.
 */
contract CalculusEngine is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;
    using Counters for Counters.Counter;
    Counters.Counter private _promiseIdCounter;
    Counters.Counter private _actionIdCounter;

    // --- Configuration ---
    IERC20 public immutable usdcToken;
    address public immutable treasuryAddress;
    uint256 public feeBps; // fee as a fraction of the amount promised (currency promises only), in basis points
    uint256 public minFee; // the least any promise pays, in currency base units
    uint256 public pointPrice; // currency base units of fee per whole reputation point (1e18 reputation units)

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
        uint256 feePaid;
    }

    struct Action {
        address user; // The end-user on whose behalf the session was opened
        address script; // The script contract that orchestrates the session
    }

    mapping(uint256 => Promise) public promises;
    mapping(uint256 => Action) public actions;

    // --- User -> script permissions ---
    // user => script => may the script open actions / make promises in the user's name?
    mapping(address => mapping(address => bool)) public isScriptAuthorized;
    // owner => script => asset => amount of the owner's ERC20 the script may still move
    mapping(address => mapping(address => mapping(address => uint256))) public scriptAllowance;
    // owner => script => asset => may the script move the owner's NFTs of this collection?
    mapping(address => mapping(address => mapping(address => bool))) public scriptNftApproval;

    // --- Events ---
    event ActionCreated(uint256 indexed actionId, address indexed user, address indexed script);
    event PromiseCreated(uint256 indexed promiseId, uint256 indexed actionId, address indexed promisor);
    event PromiseFulfilled(uint256 indexed promiseId);
    event PromiseDefaulted(uint256 indexed promiseId);
    event ValueTransferred(uint256 indexed actionId, address indexed asset, address indexed from, address to, uint256 amount);
    event FeeParametersUpdated(uint256 feeBps, uint256 minFee);
    event PointPriceUpdated(uint256 pointPrice);
    event ScriptAuthorizationSet(address indexed user, address indexed script, bool authorized);
    event ScriptApproval(address indexed owner, address indexed script, address indexed asset, uint256 amount);
    event ScriptNftApprovalSet(address indexed owner, address indexed script, address indexed asset, bool approved);

    constructor(address _usdcTokenAddress, address _treasuryAddress, uint256 _feeBps, uint256 _minFee, uint256 _pointPrice) {
        require(_pointPrice > 0, "CalculusEngine: Point price must be positive");
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        usdcToken = IERC20(_usdcTokenAddress);
        treasuryAddress = _treasuryAddress;
        feeBps = _feeBps;
        minFee = _minFee;
        pointPrice = _pointPrice;
    }

    /**
     * @notice The fee a promise of `amount` of `asset` pays: `feeBps` of the amount when the
     * promise is in the protocol currency, and never less than `minFee`. Promises of other
     * assets have no comparable size and pay the minimum.
     */
    function quoteFee(address asset, uint256 amount) public view returns (uint256) {
        uint256 proportional = asset == address(usdcToken) ? (amount * feeBps) / 10000 : 0;
        return proportional > minFee ? proportional : minFee;
    }

    modifier onlyActionScript(uint256 actionId) {
        require(actions[actionId].script == msg.sender, "CalculusEngine: Caller is not the original script for this action");
        _;
    }

    // --- User permissions ---

    /// @notice Allow (or stop allowing) `script` to make promises in your name.
    function setScriptAuthorization(address script, bool authorized) external {
        isScriptAuthorized[msg.sender][script] = authorized;
        emit ScriptAuthorizationSet(msg.sender, script, authorized);
    }

    /// @notice Set how much of your `asset` the `script` may move (this also covers protocol fees you owe).
    /// @dev You must separately give the engine itself an ERC20 allowance on the token.
    function approveScript(address script, address asset, uint256 amount) external {
        scriptAllowance[msg.sender][script][asset] = amount;
        emit ScriptApproval(msg.sender, script, asset, amount);
    }

    /// @notice Allow (or stop allowing) `script` to move your NFTs of collection `asset`.
    function setScriptNftApproval(address script, address asset, bool approved) external {
        scriptNftApproval[msg.sender][script][asset] = approved;
        emit ScriptNftApprovalSet(msg.sender, script, asset, approved);
    }

    function _authorized(address user, address script) internal view returns (bool) {
        return user == script || isScriptAuthorized[user][script];
    }

    function _spendScriptAllowance(address owner, address asset, uint256 amount) internal {
        if (owner == msg.sender) return; // a script may always move its own funds
        uint256 allowed = scriptAllowance[owner][msg.sender][asset];
        if (allowed == type(uint256).max) return;
        require(allowed >= amount, "CalculusEngine: Insufficient script allowance");
        scriptAllowance[owner][msg.sender][asset] = allowed - amount;
    }

    // --- Core Primitives ---

    /**
     * @notice Opens an economic session. All promises and transfers of the session
     * refer to the returned `actionId`, and only the calling script can add to it.
     */
    function monitoredAction(address user) external nonReentrant returns (uint256) {
        require(_authorized(user, msg.sender), "CalculusEngine: Script not authorized by user");

        _actionIdCounter.increment();
        uint256 actionId = _actionIdCounter.current();
        actions[actionId] = Action({ user: user, script: msg.sender });

        emit ActionCreated(actionId, user, msg.sender);
        return actionId;
    }

    /**
     * @notice Records a promise and charges the protocol fee to the promisor.
     * @dev The promisor must have authorized the calling script, and (if the fee is
     * non-zero) given it a sufficient allowance of the fee token.
     */
    function monitoredPromise(
        uint256 actionId,
        address promisor,
        address promisee,
        address asset,
        uint256 amount,
        uint256 deadline
    ) external nonReentrant onlyActionScript(actionId) returns (uint256) {
        require(promisor != promisee, "CalculusEngine: Cannot promise to yourself");
        require(_authorized(promisor, msg.sender), "CalculusEngine: Script not authorized by promisor");

        uint256 fee = quoteFee(asset, amount);
        if (fee > 0) {
            _spendScriptAllowance(promisor, address(usdcToken), fee);
            usdcToken.safeTransferFrom(promisor, treasuryAddress, fee);
        }

        _promiseIdCounter.increment();
        uint256 promiseId = _promiseIdCounter.current();

        promises[promiseId] = Promise({
            actionId: actionId,
            promisor: promisor,
            promisee: promisee,
            asset: asset,
            amount: amount,
            deadline: deadline,
            status: PromiseStatus.Pending,
            feePaid: fee
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
    ) external nonReentrant onlyActionScript(actionId) {
        _spendScriptAllowance(from, asset, amount);
        IERC20(asset).safeTransferFrom(from, to, amount);

        emit ValueTransferred(actionId, asset, from, to, amount);
    }

    /**
     * @notice Transfers a specific non-fungible token (ERC721) within a monitored action.
     * @dev This is the primitive used for trading assets like Reputation Claim Tokens (RCTs).
     */
    function monitoredNftTransfer(
        uint256 actionId,
        address asset,
        address from,
        address to,
        uint256 tokenId
    ) external nonReentrant onlyActionScript(actionId) {
        require(
            from == msg.sender || scriptNftApproval[from][msg.sender][asset],
            "CalculusEngine: Script not approved for this collection"
        );
        IERC721(asset).transferFrom(from, to, tokenId);

        // For NFTs, the "amount" is conceptually 1, representing the single token.
        emit ValueTransferred(actionId, asset, from, to, 1);
    }

    function monitoredFulfillment(uint256 promiseId) external nonReentrant onlyActionScript(promises[promiseId].actionId) {
        Promise storage p = promises[promiseId];
        require(p.status == PromiseStatus.Pending, "CalculusEngine: Promise not pending");
        require(block.timestamp <= p.deadline, "CalculusEngine: Promise deadline has passed");

        p.status = PromiseStatus.Fulfilled;
        emit PromiseFulfilled(promiseId);
    }

    function monitoredDefault(uint256 promiseId) external nonReentrant onlyActionScript(promises[promiseId].actionId) {
        Promise storage p = promises[promiseId];
        require(p.status == PromiseStatus.Pending, "CalculusEngine: Promise not pending");
        require(block.timestamp > p.deadline, "CalculusEngine: Promise deadline has not passed");

        p.status = PromiseStatus.Defaulted;
        emit PromiseDefaulted(promiseId);
    }

    // --- Admin Functions ---
    function setFeeParameters(uint256 _feeBps, uint256 _minFee) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        feeBps = _feeBps;
        minFee = _minFee;
        emit FeeParametersUpdated(_feeBps, _minFee);
    }

    /// @notice Changes the price of reputation for promises resolved from now on.
    function setPointPrice(uint256 _pointPrice) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        require(_pointPrice > 0, "CalculusEngine: Point price must be positive");
        pointPrice = _pointPrice;
        emit PointPriceUpdated(_pointPrice);
    }
}
