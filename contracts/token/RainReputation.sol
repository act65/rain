// File: contracts/token/RainReputation.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title RainReputation
 * @author Rain Protocol
 * @dev The unified reputation contract: the identity SBT, the reputation ledger and
 * the staking vault.
 *
 * Decay. Reputation is evidence about a person, and evidence goes stale. Every
 * `decayPeriod` seconds all reputation (scores, bonds and the total) is multiplied by
 * `retentionPerPeriod`. Nothing is iterated: each account records the period it was
 * last written in, and the decay since then is applied whenever it is read or written.
 *
 * Delinquency. While a user has outstanding claims against them they are flagged
 * delinquent (set by the RCT contract). Scripts refuse them credit, and the oracle
 * gives no reward for a promise kept while delinquent.
 *
 * Identity. A new identity starts with no reputation. Reputation is only ever
 * credited by the updater (for kept promises).
 *
 * The record. Each account carries two counters, in the same unit (fee paid / point
 * price) and fading at the same rate: reputation, earned by promises kept, and
 * `brokenScores`, added to by promises broken. Together they are the evidence for a
 * belief about the account: with a prior of `a` kept and `b` broken, the chance that
 * the next promise is kept is estimated as (a + kept) / (a + b + kept + broken)
 * (`reliability`). The prior is the reader's choice. A broken promise does not reduce
 * reputation; a script that wants more at stake takes a bond. Dividends follow
 * reputation alone.
 *
 * Staking. A stake is a bond held by a *controller* (the contract that created it,
 * typically a script). Only the controller can release it back to the user or forfeit
 * it (destroy the staked reputation). A controller can only stake reputation the user
 * has allowed it to (`approveStake`), so the amount a script can ever destroy is
 * bounded by what the user put at risk with that script.
 */
contract RainReputation is ERC721, AccessControl {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    uint256 private constant ONE = 1e18;

    // --- Roles ---
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");

    // --- Decay parameters (fixed at deployment) ---
    uint256 public immutable decayPeriod; // seconds
    uint256 public immutable retentionPerPeriod; // fraction kept each period, scaled by 1e18 (1e18 = no decay)
    uint256 public immutable startTime;

    // --- State ---
    struct Account {
        uint256 score; // as of `period`
        uint256 staked; // as of `period`
        uint256 broken; // weight of broken promises, as of `period`
        uint256 period;
    }
    mapping(address => Account) private _accounts;
    uint256 private _total; // as of `_totalPeriod`
    uint256 private _totalPeriod;

    mapping(address => bool) public isDelinquent;
    address public rctContractAddress;

    struct Stake {
        address user;
        uint256 amount; // as of `period`
        uint256 period;
        bool exists;
        bool isResolved; // released or forfeited
    }
    // keccak256(controller, purposeId) => stake. Controllers cannot collide with each other.
    mapping(bytes32 => Stake) private _stakes;
    // user => controller => amount of reputation the controller may still stake on the user's behalf
    mapping(address => mapping(address => uint256)) public stakeAllowance;

    // --- Events ---
    event ReputationIncreased(address indexed user, uint256 amount, string reason);
    event BrokenPromiseRecorded(address indexed user, uint256 amount, string reason);
    event StakeApproval(address indexed user, address indexed controller, uint256 amount);
    event ReputationStaked(bytes32 indexed purposeId, address indexed controller, address indexed user, uint256 amount);
    event StakeReleased(bytes32 indexed purposeId, address indexed controller, address indexed user, uint256 amount);
    event StakeForfeited(bytes32 indexed purposeId, address indexed controller, address indexed user, uint256 amount, uint256 reputationBurned);
    event ReputationSlashed(address indexed user, uint256 amount);
    event DelinquentStatusChanged(address indexed user, bool isDelinquent);

    /**
     * @param _decayPeriod Length of a decay period in seconds.
     * @param _retentionPerPeriod Fraction of reputation kept each period, scaled by 1e18.
     */
    constructor(uint256 _decayPeriod, uint256 _retentionPerPeriod) ERC721("Rain Reputation Token", "RAIN") {
        require(_decayPeriod > 0, "RAIN: Decay period must be positive");
        require(_retentionPerPeriod > 0 && _retentionPerPeriod <= ONE, "RAIN: Retention must be in (0, 1]");
        decayPeriod = _decayPeriod;
        retentionPerPeriod = _retentionPerPeriod;
        startTime = block.timestamp;
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    // --- Decay arithmetic ---

    function currentPeriod() public view returns (uint256) {
        return (block.timestamp - startTime) / decayPeriod;
    }

    /// @dev retentionPerPeriod ** n, scaled by 1e18, by repeated squaring. Tends to zero; cannot overflow.
    function _retention(uint256 n) internal view returns (uint256 z) {
        z = ONE;
        uint256 x = retentionPerPeriod;
        if (x == ONE) return ONE;
        while (n > 0) {
            if (n & 1 == 1) z = (z * x) / ONE;
            x = (x * x) / ONE;
            n >>= 1;
        }
    }

    /// @dev What is left today of `amount` recorded in `fromPeriod`.
    function _decayed(uint256 amount, uint256 fromPeriod) internal view returns (uint256) {
        uint256 elapsed = currentPeriod() - fromPeriod;
        return elapsed == 0 ? amount : (amount * _retention(elapsed)) / ONE;
    }

    /// @dev Brings an account's stored values up to the current period.
    function _sync(address user) internal returns (Account storage a) {
        a = _accounts[user];
        uint256 period = currentPeriod();
        if (a.period != period) {
            a.score = _decayed(a.score, a.period);
            a.staked = _decayed(a.staked, a.period);
            a.broken = _decayed(a.broken, a.period);
            a.period = period;
        }
    }

    function _syncTotal() internal {
        uint256 period = currentPeriod();
        if (_totalPeriod != period) {
            _total = _decayed(_total, _totalPeriod);
            _totalPeriod = period;
        }
    }

    // --- Views (all as of now) ---

    function reputationScores(address user) public view returns (uint256) {
        Account storage a = _accounts[user];
        return _decayed(a.score, a.period);
    }

    function stakedReputation(address user) public view returns (uint256) {
        Account storage a = _accounts[user];
        return _decayed(a.staked, a.period);
    }

    /// @notice The faded weight of the promises `user` has broken, in the unit of reputation.
    function brokenScores(address user) public view returns (uint256) {
        Account storage a = _accounts[user];
        return _decayed(a.broken, a.period);
    }

    /**
     * @notice The estimated chance that `user` keeps their next promise, scaled by 1e18,
     * for a reader whose belief about a stranger is `priorKept` kept to `priorBroken` broken
     * (in points). Reputation destroyed by a forfeited bond or a slash no longer counts as kept.
     */
    function reliability(address user, uint256 priorKept, uint256 priorBroken) external view returns (uint256) {
        uint256 kept = priorKept + reputationScores(user);
        uint256 total = kept + priorBroken + brokenScores(user);
        require(total > 0, "RAIN: No evidence and no prior");
        return (kept * ONE) / total;
    }

    function totalReputation() public view returns (uint256) {
        return _decayed(_total, _totalPeriod);
    }

    /// @notice Reputation not locked in a stake (zero if the score has fallen below the staked amount).
    function getLiquidReputation(address user) public view returns (uint256) {
        uint256 score = reputationScores(user);
        uint256 staked = stakedReputation(user);
        return score > staked ? score - staked : 0;
    }

    // --- SBT and Identity Management ---

    /// @notice Issues the identity token. A new identity holds no reputation.
    function mint(address user) public {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        require(balanceOf(user) == 0, "RAIN: User already has an identity");
        _tokenIds.increment();
        _safeMint(user, _tokenIds.current());
    }

    function _beforeTokenTransfer(address from, address to, uint256 tokenId, uint256 batchSize) internal override {
        require(from == address(0), "RAIN: This token is non-transferable");
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }

    // --- Reputation Modification (Called by Trusted Updater) ---

    function _credit(address user, uint256 amount) internal {
        Account storage a = _sync(user);
        _syncTotal();
        a.score += amount;
        _total += amount;
    }

    function _burnReputation(address user, uint256 amount) internal returns (uint256 burned) {
        Account storage a = _sync(user);
        _syncTotal();
        burned = a.score >= amount ? amount : a.score;
        if (burned > 0) {
            a.score -= burned;
            // Accounts and the total decay separately, so they can differ by rounding dust.
            _total = _total > burned ? _total - burned : 0;
        }
    }

    function increaseReputation(address user, uint256 amount, string calldata reason) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        // No check of `isDelinquent` here. Whether a kept promise earns anything depends on the
        // promisor's status when the promise was kept, which the oracle reads from the event log;
        // their status when the update happens to arrive must not matter.
        _credit(user, amount);
        emit ReputationIncreased(user, amount, reason);
    }

    /**
    * @notice Records a broken promise of weight `amount` (the fee paid on it / the point
    * price, the reputation it would have earned). Reputation is not reduced.
    */
    function recordBroken(address user, uint256 amount, string calldata reason) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        Account storage a = _sync(user);
        a.broken += amount;
        emit BrokenPromiseRecorded(user, amount, reason);
    }

    /**
    * @notice Applies a severe, punitive penalty (e.g. a governance or arbitration ruling). Clamped at zero.
    */
    function slash(address user, uint256 amountToSlash) external {
        require(hasRole(UPDATER_ROLE, msg.sender), "Caller is not a trusted updater");
        uint256 actualSlashAmount = _burnReputation(user, amountToSlash);
        if (actualSlashAmount > 0) {
            emit ReputationSlashed(user, actualSlashAmount);
        }
    }

    // --- Staking ---

    /// @notice Set how much of your reputation `controller` may stake (and so put at risk) on your behalf.
    function approveStake(address controller, uint256 amount) external {
        stakeAllowance[msg.sender][controller] = amount;
        emit StakeApproval(msg.sender, controller, amount);
    }

    function _stakeKey(address controller, bytes32 purposeId) internal pure returns (bytes32) {
        return keccak256(abi.encode(controller, purposeId));
    }

    /**
     * @notice Locks `amount` of `user`'s liquid reputation under `purposeId`. The caller
     * becomes the stake's controller. Zero-amount stakes are allowed. A stake decays at
     * the same rate as the score it is part of.
     */
    function stake(address user, uint256 amount, bytes32 purposeId) external {
        Stake storage s = _stakes[_stakeKey(msg.sender, purposeId)];
        require(!s.exists, "Stake for this purpose already exists");

        if (msg.sender != user) {
            uint256 allowed = stakeAllowance[user][msg.sender];
            if (allowed != type(uint256).max) {
                require(allowed >= amount, "Insufficient stake allowance");
                stakeAllowance[user][msg.sender] = allowed - amount;
            }
        }
        Account storage a = _sync(user);
        require((a.score > a.staked ? a.score - a.staked : 0) >= amount, "Insufficient liquid reputation");

        a.staked += amount;
        s.user = user;
        s.amount = amount;
        s.period = a.period;
        s.exists = true;

        emit ReputationStaked(purposeId, msg.sender, user, amount);
    }

    /// @dev Marks the caller's stake resolved and unlocks it. Returns the stake and what is left of it today.
    function _resolve(bytes32 purposeId) internal returns (Stake storage s, uint256 amountNow) {
        s = _stakes[_stakeKey(msg.sender, purposeId)];
        require(s.exists, "Stake does not exist");
        require(!s.isResolved, "Stake already resolved");
        s.isResolved = true;
        amountNow = _decayed(s.amount, s.period);
        Account storage a = _sync(s.user);
        a.staked = a.staked > amountNow ? a.staked - amountNow : 0;
    }

    /// @notice Returns a stake to its user. Only the stake's controller can do this.
    function releaseStake(bytes32 purposeId) external {
        (Stake storage s, uint256 amountNow) = _resolve(purposeId);
        emit StakeReleased(purposeId, msg.sender, s.user, amountNow);
    }

    /// @notice Destroys the staked reputation. Only the stake's controller can do this.
    function forfeitStake(bytes32 purposeId) external {
        (Stake storage s, uint256 amountNow) = _resolve(purposeId);
        // The score may already have been reduced below the stake by the oracle.
        uint256 burned = _burnReputation(s.user, amountNow);
        emit StakeForfeited(purposeId, msg.sender, s.user, amountNow, burned);
    }

    /// @notice A stake as it stands today (`amount` is what is left of it after decay).
    function getStake(address controller, bytes32 purposeId)
        external
        view
        returns (address user, uint256 amount, bool exists, bool isResolved)
    {
        Stake storage s = _stakes[_stakeKey(controller, purposeId)];
        return (s.user, _decayed(s.amount, s.period), s.exists, s.isResolved);
    }

    // --- Delinquency and Admin Functions ---

    function setRctContract(address _rctContractAddress) external {
        require(hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Admin only");
        require(rctContractAddress == address(0), "RCT contract already set");
        rctContractAddress = _rctContractAddress;
    }

    function setDelinquentStatus(address user, bool status) external {
        require(msg.sender == rctContractAddress, "Only the RCT contract can set delinquent status");
        isDelinquent[user] = status;
        emit DelinquentStatusChanged(user, status);
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721, AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}
