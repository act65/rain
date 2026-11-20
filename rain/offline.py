"""
Payments made while disconnected.

A payer with no connection signs a note; the payee accepts it without being able to check
the payer's balance, and the note is recorded on the chain later (`OfflineNoteScript`). A
note is therefore a promise, and accepting one is lending. Two things follow.

  - What a payee should accept is a credit limit, read from the payer's record with
    `rain.record`. But the limit is on everything the payer owes at once, and a payee who is
    disconnected sees only its own notes. `split_limit` divides the limit among the places
    the payer could be spending at the same time.
  - A double spend is not rejected when the notes are recorded. Every note becomes a promise,
    and the ones the payer cannot pay become broken promises on a record they cannot shed.

`Note`, `note_digest` and `sign_note` are the client side of
`CalculusEngine.monitoredSignedPromise`: the digest is computed here, with no call to the
chain, because the payer has none to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

SIGNED_PROMISE_TAG = "Rain signed promise"


@dataclass(frozen=True)
class Note:
    """A promise as its promisor signs it (`CalculusEngine.SignedPromise`). Times are in seconds."""
    promisor: str
    promisee: str
    asset: str
    amount: int
    issued_at: int
    valid_until: int
    settle_within: int
    nonce: int

    def as_tuple(self) -> Tuple:
        return (str(self.promisor), str(self.promisee), str(self.asset), int(self.amount), int(self.issued_at),
                int(self.valid_until), int(self.settle_within), int(self.nonce))


def note_digest(chain_id: int, engine: str, script: str, note: Note) -> bytes:
    """What the promisor signs: the same 32 bytes as `CalculusEngine.signedPromiseDigest(script, note)`."""
    from eth_abi import encode
    from eth_utils import keccak
    return keccak(encode(
        ["bytes32", "uint256", "address", "address", "(address,address,address,uint256,uint256,uint256,uint256,uint256)"],
        [keccak(text=SIGNED_PROMISE_TAG), int(chain_id), str(engine), str(script), note.as_tuple()],
    ))


def sign_note(account: Any, chain_id: int, engine: str, script: str, note: Note) -> bytes:
    """The promisor's signature (65 bytes: r, s, v). `account` is anything with ape's `sign_message`."""
    from eth_account.messages import encode_defunct
    return account.sign_message(encode_defunct(primitive=note_digest(chain_id, engine, script, note))).encode_rsv()


def split_limit(limit: float, views: int) -> float:
    """
    What one payee should accept from a payer whose limit is `limit`, when the payer could be
    spending in `views` places that cannot see each other before any of them reaches the chain.
    """
    if views < 1:
        raise ValueError("A payer is seen from at least one place")
    return limit / views


def read_notes(engine_contract: Any, script_contract: Any) -> list:
    """
    The resolved notes of an `OfflineNoteScript`, as `rain.record.Entry`s with times in seconds:
    `created` is when the payer signed and `time` when the note was paid or defaulted. Between
    the two the note was owed, whatever the chain knew, which is what
    `rain.record.weigh(..., concurrent=True)` needs.
    """
    from rain.record import Entry
    height = engine_contract.PromiseCreated.chain_manager.blocks.height
    issued = {log.event_arguments["promiseId"]: log.event_arguments["issuedAt"]
              for log in script_contract.NotePresented.range(0, height + 1)}
    entries = []
    for event_name, kept in (("PromiseFulfilled", True), ("PromiseDefaulted", False)):
        for log in getattr(engine_contract, event_name).range(0, height + 1):
            promise_id = log.event_arguments["promiseId"]
            if promise_id not in issued:
                continue
            p = engine_contract.promises(promise_id)
            when = engine_contract.provider.get_block(log.block_number).timestamp
            entries.append((log.block_number, log.log_index, Entry(
                promisor=str(p[1]), promisee=str(p[2]), asset=str(p[3]), amount=p[4], kept=kept,
                time=when, fee_paid=p[7], created=issued[promise_id],
            )))
    return [entry for _, _, entry in sorted(entries, key=lambda x: (x[0], x[1]))]


# --- an allowance backed by locked funds (OfflineAllowanceScript) ---

CERTIFICATE_TAG = "Rain offline allowance"


@dataclass(frozen=True)
class Certificate:
    """What the attester signs about an allowance that is open on the chain. The payer carries it."""
    chain_id: int
    script: str
    allowance_id: int
    payer: str
    amount: int
    float: int  # forfeited to whoever proves an overspend
    valid_until: int


def allowance_nonce(allowance_id: int, serial: int) -> int:
    """The nonce of a note under an allowance: the allowance in the high 128 bits, the payer's serial number below."""
    if not 0 <= serial < 1 << 128:
        raise ValueError("serial out of range")
    return (int(allowance_id) << 128) | serial


def certificate_digest(certificate: Certificate) -> bytes:
    """The same 32 bytes as `OfflineAllowanceScript.certificateDigest(allowance_id)`."""
    from eth_abi import encode
    from eth_utils import keccak
    c = certificate
    return keccak(encode(["bytes32", "uint256", "address", "uint256", "address", "uint256", "uint256", "uint256"],
                         [keccak(text=CERTIFICATE_TAG), int(c.chain_id), str(c.script), int(c.allowance_id), str(c.payer),
                          int(c.amount), int(c.float), int(c.valid_until)]))


def sign_certificate(attester_account: Any, certificate: Certificate) -> bytes:
    from eth_account.messages import encode_defunct
    return attester_account.sign_message(encode_defunct(primitive=certificate_digest(certificate))).encode_rsv()


def signer_of(digest: bytes, signature: bytes) -> str:
    """The address that signed `digest` as an Ethereum signed message. Needs no chain."""
    from eth_account import Account
    from eth_account.messages import encode_defunct
    return Account.recover_message(encode_defunct(primitive=digest), signature=signature)


def _same(a: str, b: str) -> bool:
    return str(a).lower() == str(b).lower()


def _genuine(note: Note, signature: bytes, certificate: Certificate, engine: str) -> bool:
    c = certificate
    return (_same(note.promisor, c.payer) and note.nonce >> 128 == c.allowance_id and note.issued_at <= c.valid_until
            and _same(signer_of(note_digest(c.chain_id, engine, c.script, note), signature), c.payer))


def proves_overspend(certificate: Certificate, signed_notes: Any, engine: str) -> bool:
    """
    Whether these notes prove that the payer overspent the allowance: distinct notes, each signed by the
    payer under this certificate, that total more than its amount. Anyone can check this from the notes
    alone, and nobody but the payer can produce them. `signed_notes` is (note, signature) pairs.
    """
    seen = {note.nonce: note.amount for note, signature in signed_notes if _genuine(note, signature, certificate, engine)}
    return sum(seen.values()) > certificate.amount


def accept_note(note: Note, signature: bytes, certificate: Certificate, certificate_signature: bytes, attester: str,
                engine: str, now: int, known: Any = ()) -> Tuple[bool, str]:
    """
    A payee's check, with no connection: is the certificate the attester's and still valid, is the note the
    payer's under it, and would the notes the payee knows of (`known`, (note, signature) pairs), with this
    one, stay within the allowance? Returns (accept, reason).
    """
    c = certificate
    if not _same(signer_of(certificate_digest(c), certificate_signature), attester):
        return False, "the certificate is not signed by the attester"
    if now > c.valid_until:
        return False, "the certificate has expired"
    if not _genuine(note, signature, c, engine):
        return False, "the note is not the payer's under this certificate"
    if proves_overspend(c, list(known) + [(note, signature)], engine):
        return False, "with the notes already known, this one overspends the allowance"
    return True, "within the allowance"
