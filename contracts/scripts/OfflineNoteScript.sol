// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface INoteEngine {
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

interface INoteClaimToken {
    function mint(uint256 promiseId) external returns (uint256);
    function burn(uint256 tokenId) external;
    function ownerOf(uint256 tokenId) external view returns (address);
    function claims(uint256 tokenId) external view returns (uint256 promiseId, address defaulterAddress, address originalLenderAddress, uint256 shortfallAmount, uint256 defaultTimestamp, address loanContractAddress);
}

/**
 * @title OfflineNoteScript
 * @dev A reference application: a payment made while disconnected.
 *
 * A payer with no connection signs a note: "I will pay this payee this amount". The payee
 * accepts it on the strength of the payer's record, as a lender would, because nothing can
 * check the payer's balance. Later, anyone who reaches the chain presents the note.
 *
 *   present      (anyone)  the note becomes a promise by the payer to the payee. The presenter
 *                          pays the protocol fee. If the payer's funds are there, the payee is
 *                          paid at once and the presenter gets the fee back.     -> Paid
 *                          If not, the payer has `settleWithin` to find them.    -> Pending
 *   pay          (anyone)  settles a pending note from the payer's funds.        -> Paid
 *   claimDefault (anyone)  after the deadline: the promise is broken and the
 *                          payee receives a claim on the payer.                  -> Defaulted
 *   resolveDefault (payer) burns the re-acquired claim.
 *
 * A payer can sign more notes than they can pay (a double spend). Nothing here prevents
 * that. The second note is recorded all the same and, if it is not paid, as a broken
 * promise. What a payee should accept from a payer it cannot check is the subject of
 * `rain.offline` and experiments/offline.
 *
 * The payer needs no authorization on chain for a note to be recorded: the signature is
 * the consent, so a payer cannot make their notes unrecordable by withdrawing permissions.
 * For a note to be *paid*, the payer must have given this script an allowance of the
 * currency (`CalculusEngine.approveScript`) before going offline, and still hold the funds.
 */
contract OfflineNoteScript {

    INoteEngine public immutable calculusEngine;
    INoteClaimToken public immutable rctContract;
    address public immutable usdcToken;

    enum Status { None, Pending, Paid, Defaulted }

    struct Note {
        address payer;
        address payee;
        address presenter; // paid the protocol fee, and is owed it back by the payer
        uint256 amount;
        uint256 fee;
        uint256 actionId;
        uint256 promiseId;
        Status status;
    }

    uint256 public noteCount;
    mapping(uint256 => Note) public notes;
    mapping(uint256 => uint256) public noteForPromise; // promiseId => noteId

    event NotePresented(uint256 indexed noteId, uint256 indexed promiseId, address indexed payer, address payee, uint256 amount, uint256 issuedAt);
    event NotePaid(uint256 indexed noteId);
    event NoteDefaulted(uint256 indexed noteId, uint256 rctId);
    event NoteResolved(uint256 indexed noteId, uint256 indexed rctId);

    constructor(address _calculusEngineAddress, address _rctContractAddress, address _usdcTokenAddress) {
        calculusEngine = INoteEngine(_calculusEngineAddress);
        rctContract = INoteClaimToken(_rctContractAddress);
        usdcToken = _usdcTokenAddress;
    }

    /**
     * @notice Records a signed note and pays it if the payer's funds are available.
     * @dev The caller pays the protocol fee (and must have given this script an allowance for
     * it). A payee is never charged for a note that somebody else chose to present.
     */
    function present(INoteEngine.SignedPromise calldata p, bytes calldata signature) external returns (uint256 noteId) {
        require(p.asset == usdcToken, "OfflineNote: Notes are in the currency");

        uint256 actionId = calculusEngine.monitoredAction(address(this));
        uint256 promiseId = calculusEngine.monitoredSignedPromise(actionId, p, signature, msg.sender);

        noteId = ++noteCount;
        notes[noteId] = Note({
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
        emit NotePresented(noteId, promiseId, p.promisor, p.promisee, p.amount, p.issuedAt);

        _tryToPay(noteId);
    }

    /// @notice Settles a pending note, once the payer's funds are there. Reverts if they are not.
    function pay(uint256 noteId) external {
        require(notes[noteId].status == Status.Pending, "OfflineNote: Note not pending");
        require(_tryToPay(noteId), "OfflineNote: Payer's funds are not available");
    }

    function claimDefault(uint256 noteId) external {
        Note storage note = notes[noteId];
        require(note.status == Status.Pending, "OfflineNote: Note not pending");

        note.status = Status.Defaulted;
        calculusEngine.monitoredDefault(note.promiseId); // reverts until the deadline has passed
        uint256 rctId = rctContract.mint(note.promiseId); // the claim goes to the payee; the payer is delinquent
        emit NoteDefaulted(noteId, rctId);
    }

    /// @notice Lets the payer clear their name once they have re-acquired the claim (settled with its holder).
    function resolveDefault(uint256 rctId) external {
        (uint256 promiseId, address defaulter, , , , address script) = rctContract.claims(rctId);
        require(script == address(this), "OfflineNote: Not a claim from this script");
        require(msg.sender == defaulter, "OfflineNote: Only the payer can resolve their own debt");
        require(rctContract.ownerOf(rctId) == msg.sender, "OfflineNote: You must own the claim to resolve it");
        rctContract.burn(rctId);
        emit NoteResolved(noteForPromise[promiseId], rctId);
    }

    function _tryToPay(uint256 noteId) internal returns (bool) {
        try this.pull(noteId) {
            Note storage note = notes[noteId];
            note.status = Status.Paid;
            calculusEngine.monitoredFulfillment(note.promiseId); // reverts after the deadline
            emit NotePaid(noteId);
            return true;
        } catch {
            return false;
        }
    }

    /// @dev Both transfers or neither. Callable only by this contract (so that it can be tried).
    function pull(uint256 noteId) external {
        require(msg.sender == address(this), "OfflineNote: Internal");
        Note storage note = notes[noteId];
        calculusEngine.monitoredTransfer(note.actionId, usdcToken, note.payer, note.payee, note.amount);
        if (note.fee > 0) {
            calculusEngine.monitoredTransfer(note.actionId, usdcToken, note.payer, note.presenter, note.fee);
        }
    }
}
