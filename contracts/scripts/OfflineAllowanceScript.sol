// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IAllowanceEngine {
    struct SignedPromise {
        address promisor;
        address promisee;
        address asset;
        uint256 amount;
        uint256 issuedAt;
        uint256 validUntil;
        uint256 settleWithin;
        uint256 nonce;
    }

    function quoteFee(address asset, uint256 amount) external view returns (uint256);
    function monitoredAction(address user) external returns (uint256);
    function monitoredSignedPromise(uint256 actionId, SignedPromise calldata p, bytes calldata signature, address feePayer) external returns (uint256);
    function monitoredTransfer(uint256 actionId, address asset, address from, address to, uint256 amount) external;
    function monitoredFulfillment(uint256 promiseId) external;
    function monitoredDefault(uint256 promiseId) external;
}

interface IAllowanceReputation {
    function stake(address user, uint256 amount, bytes32 purposeId) external;
    function releaseStake(bytes32 purposeId) external;
    function forfeitStake(bytes32 purposeId) external;
}

interface IAllowanceClaimToken {
    function mint(uint256 promiseId) external returns (uint256);
    function burn(uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
    function claims(uint256 tokenId) external view returns (uint256 promiseId, address defaulterAddress, address originalLenderAddress, uint256 shortfallAmount, uint256 defaultTimestamp, address loanContractAddress);
}

interface IAllowanceCurrency {
    function approve(address spender, uint256 amount) external returns (bool);
}

/**
 * @title OfflineAllowanceScript
 * @dev A reference application: payments made while disconnected, backed by funds locked beforehand.
 *
 * Before losing the connection a payer opens an allowance: they lock `amount` of the currency here,
 * and a further `float`. The attester (a key every payee knows) then signs a certificate saying so,
 * which the payer carries: "this payer may have at most `amount` outstanding in notes, signed up to
 * `validUntil`, and forfeits `float` if they exceed it". The float is what overspending costs the
 * payer, so a payee can weigh it against how many others the payer could reach. A note under the allowance is a signed promise whose nonce names the allowance
 * (allowance id in the high 128 bits, the payer's serial number in the low 128).
 *
 *   open         (payer)   locks the amount and the float; may bond reputation.
 *   present      (anyone)  records a note. While the locked amount lasts, the payee is paid from it
 *                          and the presenter's fee is refunded from the float.              -> Paid
 *                          The first note that takes the total presented past the amount
 *                          proves an overspend: whoever presents it receives what is left of
 *                          the float, and the bonded reputation is destroyed. That note and
 *                          any after it are owed by the payer in person.                    -> Pending
 *   pay          (anyone)  settles a pending note from what is still locked and, for the
 *                          rest, the payer's own funds.                                     -> Paid
 *   claimDefault (anyone)  after the note's deadline: a broken promise and a claim. The
 *                          payee receives whatever is still locked.                         -> Defaulted
 *   close        (anyone)  once no more notes can be presented: what remains of the locked
 *                          funds returns to the payer, and the bond if they did not overspend.
 *
 * What this gives a payee who cannot reach the chain: notes within the allowance are certain to be
 * paid, whatever happens to the payer; and notes that together exceed it are proof of fraud that
 * anyone can check from the notes alone. It does not stop a payer handing copies to payees who have
 * not heard of each other. See experiments/offline_allowance.
 */
contract OfflineAllowanceScript {

    IAllowanceEngine public immutable calculusEngine;
    IAllowanceReputation public immutable rainReputation;
    IAllowanceClaimToken public immutable rctContract;
    address public immutable usdcToken;
    address public immutable attester; // signs certificates off-chain; payees check them against this key

    bytes32 public constant CERTIFICATE_TAG = keccak256("Rain offline allowance");

    enum Status { None, Pending, Paid, Defaulted }

    struct Allowance {
        address payer;
        uint256 amount;     // the most the payer's notes may total
        uint256 floatLocked; // the float as it was locked (what the certificate states)
        uint256 validUntil; // notes must be signed by this time
        uint256 closesAt;   // notes must be presented by this time
        uint256 locked;     // what is left of the amount
        uint256 float;      // what is left of the float
        uint256 bond;       // reputation bonded
        uint256 presented;  // total of the notes presented so far
        bool overspent;
        bool closed;
    }

    struct Note {
        uint256 allowanceId;
        address payer;
        address payee;
        address presenter;
        uint256 amount;
        uint256 fee;
        uint256 actionId;
        uint256 promiseId;
        Status status;
    }

    uint256 public allowanceCount;
    uint256 public noteCount;
    mapping(uint256 => Allowance) public allowances;
    mapping(uint256 => Note) public notes;
    mapping(uint256 => uint256) public noteForPromise; // promiseId => noteId

    event AllowanceOpened(uint256 indexed allowanceId, address indexed payer, uint256 amount, uint256 float, uint256 validUntil, uint256 closesAt);
    event NotePresented(uint256 indexed noteId, uint256 indexed promiseId, uint256 indexed allowanceId, address payee, uint256 amount, uint256 issuedAt);
    event NotePaid(uint256 indexed noteId);
    event Overspent(uint256 indexed allowanceId, address indexed provedBy, uint256 reward);
    event NoteDefaulted(uint256 indexed noteId, uint256 rctId);
    event NoteResolved(uint256 indexed noteId, uint256 indexed rctId);
    event AllowanceClosed(uint256 indexed allowanceId, uint256 returned);

    constructor(address _calculusEngineAddress, address _rainReputationAddress, address _rctContractAddress, address _usdcTokenAddress, address _attester) {
        calculusEngine = IAllowanceEngine(_calculusEngineAddress);
        rainReputation = IAllowanceReputation(_rainReputationAddress);
        rctContract = IAllowanceClaimToken(_rctContractAddress);
        usdcToken = _usdcTokenAddress;
        attester = _attester;
        // The engine moves the funds this script holds, so that every payment is on the log.
        IAllowanceCurrency(_usdcTokenAddress).approve(_calculusEngineAddress, type(uint256).max);
    }

    /**
     * @notice Locks `amount` and `float` of the caller's currency until `presentWithin` after `validUntil`.
     * @dev The caller must have given this script a currency allowance for both, and a stake allowance for `bond`.
     */
    function open(uint256 amount, uint256 float, uint256 validUntil, uint256 presentWithin, uint256 bond) external returns (uint256 allowanceId) {
        require(amount > 0, "OfflineAllowance: Nothing to lock");
        require(validUntil > block.timestamp, "OfflineAllowance: Already expired");

        allowanceId = ++allowanceCount;
        uint256 actionId = calculusEngine.monitoredAction(address(this));
        calculusEngine.monitoredTransfer(actionId, usdcToken, msg.sender, address(this), amount + float);
        if (bond > 0) rainReputation.stake(msg.sender, bond, bytes32(allowanceId));

        Allowance storage a = allowances[allowanceId];
        a.payer = msg.sender;
        a.amount = amount;
        a.validUntil = validUntil;
        a.closesAt = validUntil + presentWithin;
        a.locked = amount;
        a.float = float;
        a.floatLocked = float;
        a.bond = bond;
        emit AllowanceOpened(allowanceId, msg.sender, amount, float, validUntil, a.closesAt);
    }

    /// @notice What the attester signs (as an Ethereum signed message) to certify an open allowance.
    function certificateDigest(uint256 allowanceId) public view returns (bytes32) {
        Allowance storage a = allowances[allowanceId];
        require(a.payer != address(0), "OfflineAllowance: No such allowance");
        return keccak256(abi.encode(CERTIFICATE_TAG, block.chainid, address(this), allowanceId, a.payer, a.amount, a.floatLocked, a.validUntil));
    }

    /// @notice Records a note signed under an allowance, and pays it while the locked amount lasts. The caller pays the fee.
    function present(IAllowanceEngine.SignedPromise calldata p, bytes calldata signature) external returns (uint256 noteId) {
        uint256 allowanceId = p.nonce >> 128;
        Allowance storage a = allowances[allowanceId];
        require(a.payer != address(0) && a.payer == p.promisor, "OfflineAllowance: Not this payer's allowance");
        require(!a.closed, "OfflineAllowance: Allowance closed");
        require(p.asset == usdcToken, "OfflineAllowance: Notes are in the currency");
        require(p.issuedAt <= a.validUntil, "OfflineAllowance: Signed after the allowance expired");
        require(p.validUntil <= a.closesAt, "OfflineAllowance: Note outlives the allowance");

        uint256 actionId = calculusEngine.monitoredAction(address(this));
        uint256 promiseId = calculusEngine.monitoredSignedPromise(actionId, p, signature, msg.sender);

        noteId = ++noteCount;
        notes[noteId] = Note({
            allowanceId: allowanceId,
            payer: p.promisor,
            payee: p.promisee,
            presenter: msg.sender,
            amount: p.amount,
            fee: calculusEngine.quoteFee(usdcToken, p.amount),
            actionId: actionId,
            promiseId: promiseId,
            status: Status.Pending
        });
        noteForPromise[promiseId] = noteId;
        emit NotePresented(noteId, promiseId, allowanceId, p.promisee, p.amount, p.issuedAt);

        a.presented += p.amount;
        if (a.presented > a.amount && !a.overspent) _overspent(allowanceId, a, actionId);
        if (a.locked >= p.amount) _payFromLocked(noteId, a);
    }

    function _overspent(uint256 allowanceId, Allowance storage a, uint256 actionId) internal {
        a.overspent = true;
        uint256 reward = a.float;
        a.float = 0;
        if (reward > 0) calculusEngine.monitoredTransfer(actionId, usdcToken, address(this), msg.sender, reward);
        if (a.bond > 0) rainReputation.forfeitStake(bytes32(allowanceId));
        emit Overspent(allowanceId, msg.sender, reward);
    }

    function _payFromLocked(uint256 noteId, Allowance storage a) internal {
        Note storage note = notes[noteId];
        a.locked -= note.amount;
        calculusEngine.monitoredTransfer(note.actionId, usdcToken, address(this), note.payee, note.amount);
        uint256 refund = note.fee < a.float ? note.fee : a.float;
        if (refund > 0) {
            a.float -= refund;
            calculusEngine.monitoredTransfer(note.actionId, usdcToken, address(this), note.presenter, refund);
        }
        note.status = Status.Paid;
        calculusEngine.monitoredFulfillment(note.promiseId);
        emit NotePaid(noteId);
    }

    /// @notice Settles a pending note from the payer's own funds (they must have given this script an allowance for it).
    function pay(uint256 noteId) external {
        Note storage note = notes[noteId];
        require(note.status == Status.Pending, "OfflineAllowance: Note not pending");
        note.status = Status.Paid;
        uint256 fromLocked = _takeLocked(note);
        if (fromLocked > 0) calculusEngine.monitoredTransfer(note.actionId, usdcToken, address(this), note.payee, fromLocked);
        if (note.amount > fromLocked) {
            calculusEngine.monitoredTransfer(note.actionId, usdcToken, note.payer, note.payee, note.amount - fromLocked);
        }
        if (note.fee > 0) calculusEngine.monitoredTransfer(note.actionId, usdcToken, note.payer, note.presenter, note.fee);
        calculusEngine.monitoredFulfillment(note.promiseId); // reverts after the deadline
        emit NotePaid(noteId);
    }

    function claimDefault(uint256 noteId) external {
        Note storage note = notes[noteId];
        require(note.status == Status.Pending, "OfflineAllowance: Note not pending");
        note.status = Status.Defaulted;
        calculusEngine.monitoredDefault(note.promiseId); // reverts until the deadline has passed
        // Whatever is still locked goes towards the note. The claim is for the whole promise all the same.
        uint256 fromLocked = _takeLocked(note);
        if (fromLocked > 0) calculusEngine.monitoredTransfer(note.actionId, usdcToken, address(this), note.payee, fromLocked);
        uint256 rctId = rctContract.mint(note.promiseId);
        emit NoteDefaulted(noteId, rctId);
    }

    /// @dev Takes what a pending note can have of the funds still locked under its allowance.
    function _takeLocked(Note storage note) internal returns (uint256 taken) {
        Allowance storage a = allowances[note.allowanceId];
        taken = a.locked < note.amount ? a.locked : note.amount;
        a.locked -= taken;
    }

    function resolveDefault(uint256 rctId) external {
        (uint256 promiseId, address defaulter, , , , address script) = rctContract.claims(rctId);
        require(script == address(this), "OfflineAllowance: Not a claim from this script");
        require(msg.sender == defaulter, "OfflineAllowance: Only the payer can resolve their own debt");
        require(rctContract.ownerOf(rctId) == msg.sender, "OfflineAllowance: You must own the claim to resolve it");
        rctContract.burn(rctId);
        emit NoteResolved(noteForPromise[promiseId], rctId);
    }

    /// @notice Once no more notes can be presented, returns what is left of the locked funds to the payer.
    function close(uint256 allowanceId) external {
        Allowance storage a = allowances[allowanceId];
        require(a.payer != address(0), "OfflineAllowance: No such allowance");
        require(!a.closed, "OfflineAllowance: Allowance closed");
        require(block.timestamp > a.closesAt, "OfflineAllowance: Notes can still be presented");

        a.closed = true;
        uint256 returned = a.locked + a.float;
        a.locked = 0;
        a.float = 0;
        if (returned > 0) {
            uint256 actionId = calculusEngine.monitoredAction(address(this));
            calculusEngine.monitoredTransfer(actionId, usdcToken, address(this), a.payer, returned);
        }
        if (a.bond > 0 && !a.overspent) rainReputation.releaseStake(bytes32(allowanceId));
        emit AllowanceClosed(allowanceId, returned);
    }
}
