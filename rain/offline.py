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
