"""
A pure-Python model of the protocol's accounting, for simulations.

`Economy` mirrors what the contracts and the oracle do to balances and reputation,
with none of the machinery (no permissions, events, Merkle proofs or integer
rounding). `tests/test_model_vs_contracts.py` replays one scenario through both and
checks they agree.

Differences from the chain, all deliberate simplifications:
  - the oracle is instantaneous: reputation changes when a promise is resolved;
  - a dividend is paid out to every holder at once instead of being claimed;
  - reputation decays once per call to `decay()` (or `pay_dividend()`), not by the clock;
  - amounts are floats.

Two rule sets.

`Economy.current_rules(...)` builds an economy that follows the contracts: the fee is a
fraction of the amount promised (with a minimum), a kept promise earns `fee / point_price`
points, reputation decays, and all fees go through a payout fund that shares out a fixed
fraction of itself each cycle (by default, the decay rate).

The bare constructor gives the ORIGINAL rules (a flat reward per promise, no decay, a
treasury that keeps its capital and pays only its yield, a fee keeper). They are kept
because the experiments that motivated the change (`experiments/fee_dynamics` and others)
run on them. Each rule is switched by one field below.

`Economy.genesis_rules(...)` gives an intermediate design, superseded on 2026-11-19: fees
paid out in full each cycle, with a genesis allocation of reputation whose dividend share
went into a slowly released fund. `experiments/surge_fixes` compares it with what replaced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rain import economics


@dataclass
class Agent:
    money: float = 0.0
    reputation: float = 0.0
    staked: float = 0.0
    debts: int = 0  # outstanding claims (RCTs) against this agent
    dividends_received: float = 0.0
    fees_paid: float = 0.0
    unvested: List[list] = field(default_factory=list)  # [cycle at which it starts earning, amount]; vesting only

    @property
    def earning_reputation(self) -> float:
        """Reputation that takes part in dividends (all of it, unless some is still vesting)."""
        return max(0.0, self.reputation - sum(amount for _, amount in self.unvested))

    @property
    def delinquent(self) -> bool:
        return self.debts > 0

    @property
    def liquid_reputation(self) -> float:
        return max(0.0, self.reputation - self.staked)


@dataclass
class Loan:
    borrower: str
    lender: str
    principal: float
    interest: float
    bond: float
    fee_paid: float = 0.0
    status: str = "requested"  # requested, cancelled, active, repaid, defaulted, resolved


@dataclass
class Economy:
    fee: float = 0.0  # per promise (the minimum fee when `fee_rate` is set)
    fee_rate: float = 0.0  # fee as a fraction of the amount promised
    yield_rate: float = 0.0  # treasury yield per cycle
    rep_gain: float = economics.REP_GAIN
    rep_loss: float = economics.REP_LOSS
    treasury: float = 0.0
    point_price: Optional[float] = None  # currency of fees per reputation point (None: flat `rep_gain` per promise)
    decay_rate: float = 0.0  # fraction of reputation lost per cycle
    pass_through: bool = False  # distribute fees instead of keeping them as capital
    fee_pool: float = 0.0  # fees waiting to be distributed (pass_through only)
    reserve_holder: Optional[str] = None  # an agent whose dividend share is kept back instead of paid
    # What happens to the share kept back: None rolls all of it into the next cycle's pool;
    # a number puts it in `reserve_fund`, of which that fraction is released into each dividend.
    reserve_release: Optional[float] = None
    reserve_fund: float = 0.0
    # The oracle applies reputation changes this many cycles after the promise is resolved (0: at once).
    # A cycle ends with each call to `pay_dividend`.
    oracle_lag: int = 0
    cycle: int = 0
    pending_updates: List[tuple] = field(default_factory=list)  # (apply_at_cycle, kind, agent, amount)
    open_loans: set = field(default_factory=set)  # ids of loans whose bond is still held
    smooth_payout: bool = False  # every fee goes through the fund, which releases `reserve_release` of itself per cycle
    # Alternatives to smoothing that were tried and not adopted (experiments/surge_fixes). Not in the contracts.
    issuance_per_cycle: Optional[float] = None  # mint this many points per cycle, shared pro rata to fees paid on kept promises
    vesting_cycles: int = 0  # newly earned points take part in dividends only after this many cycles
    fee_credits: Dict[str, float] = field(default_factory=dict)  # fees on promises kept this cycle (issuance only)
    agents: Dict[str, Agent] = field(default_factory=dict)
    loans: List[Loan] = field(default_factory=list)
    dividend_history: List[float] = field(default_factory=list)

    @classmethod
    def current_rules(cls, min_fee: float, fee_rate: float, point_price: float, decay_rate: float,
                      release: Optional[float] = None, **kwargs) -> "Economy":
        """
        An economy that follows the deployed contracts. `release` is the fraction of the payout
        fund shared out per cycle; it defaults to the decay rate, which is how the contracts are
        meant to be configured.
        """
        return cls(fee=min_fee, fee_rate=fee_rate, point_price=point_price, decay_rate=decay_rate, pass_through=True,
                   smooth_payout=True, reserve_release=decay_rate if release is None else release, **kwargs)

    @classmethod
    def genesis_rules(cls, min_fee: float, fee_rate: float, point_price: float, decay_rate: float,
                      reserve_release: float, genesis_reputation: float = 0.0, **kwargs) -> "Economy":
        """The superseded design: fees paid out each cycle, and an agent "treasury" holding a genesis allocation."""
        eco = cls(fee=min_fee, fee_rate=fee_rate, point_price=point_price, decay_rate=decay_rate,
                  pass_through=True, reserve_holder="treasury", reserve_release=reserve_release, **kwargs)
        eco.add_agent("treasury", reputation=genesis_reputation)
        return eco

    def start_in_steady_state(self, fee_flow: float) -> None:
        """
        Fills the payout fund to the level at which it pays out `fee_flow` per cycle, and
        queues one cycle's fees, so that a simulation can begin in the steady state.
        """
        release = self.reserve_release
        self.reserve_fund = fee_flow * (1 - release) / release
        self.fee_pool = fee_flow

    # --- agents ---

    def add_agent(self, name: str, money: float = 0.0, reputation: float = 0.0) -> Agent:
        if name in self.agents:
            raise ValueError(f"{name} already exists")
        self.agents[name] = Agent(money=money, reputation=reputation)
        return self.agents[name]

    @property
    def total_reputation(self) -> float:
        return sum(a.reputation for a in self.agents.values())

    def _pay(self, payer: str, payee: Optional[str], amount: float) -> None:
        agent = self.agents[payer]
        if amount > agent.money + 1e-9:
            raise ValueError(f"{payer} cannot pay {amount} (has {agent.money})")
        agent.money -= amount
        if payee is None and self.pass_through:
            self.fee_pool += amount
        elif payee is None:
            self.treasury += amount
        else:
            self.agents[payee].money += amount

    # --- reputation primitives ---

    def _burn(self, name: str, amount: float) -> float:
        agent = self.agents[name]
        burned = min(amount, agent.reputation)
        agent.reputation -= burned
        return burned

    def stake(self, name: str, amount: float) -> None:
        agent = self.agents[name]
        if amount > agent.liquid_reputation + 1e-9:
            raise ValueError("Insufficient liquid reputation")
        agent.staked += amount

    def release_stake(self, name: str, amount: float) -> None:
        self.agents[name].staked -= amount

    def forfeit_stake(self, name: str, amount: float) -> float:
        self.agents[name].staked -= amount
        return self._burn(name, amount)

    # --- promises ---

    def quote_fee(self, amount: float = 0.0) -> float:
        """The fee on one promise of `amount`."""
        return max(self.fee, self.fee_rate * amount)

    def make_promise(self, promisor: str, count: int = 1, amount: float = 0.0) -> float:
        """Records `count` promises of `amount` each: the promisor pays the fee for each. Returns the fee per promise."""
        fee = self.quote_fee(amount)
        self._pay(promisor, None, fee * count)
        self.agents[promisor].fees_paid += fee * count
        return fee

    def reward(self, fee_paid: Optional[float] = None) -> float:
        """Points earned by one kept promise on which `fee_paid` (default: the current fee) was paid."""
        if self.point_price is None:
            return self.rep_gain
        return (self.fee if fee_paid is None else fee_paid) / self.point_price

    def fulfil_promise(self, promisor: str, count: int = 1, fee_paid: Optional[float] = None) -> None:
        """A kept promise earns reputation, unless the promisor is delinquent."""
        if self.agents[promisor].delinquent:  # judged now, when the promise is kept, not when the oracle runs
            return
        if self.issuance_per_cycle is not None:
            paid = (self.fee if fee_paid is None else fee_paid) * count
            self.fee_credits[promisor] = self.fee_credits.get(promisor, 0.0) + paid
            return
        self._oracle("increase", promisor, self.reward(fee_paid) * count)

    def default_promise(self, promisor: str) -> None:
        """A broken promise costs the flat penalty and leaves a claim against the promisor."""
        self.agents[promisor].debts += 1  # on-chain and immediate: the RCT is minted with the default
        self._oracle("decrease", promisor, self.rep_loss)

    def _oracle(self, kind: str, name: str, amount: float) -> None:
        if self.oracle_lag > 0:
            self.pending_updates.append((self.cycle + self.oracle_lag, kind, name, amount))
        else:
            self._apply_update(kind, name, amount)

    def _apply_update(self, kind: str, name: str, amount: float) -> None:
        if kind == "decrease":
            self._burn(name, amount)
        else:
            self.agents[name].reputation += amount
            if self.vesting_cycles:
                self.agents[name].unvested.append([self.cycle + self.vesting_cycles, amount])

    def run_oracle(self) -> None:
        """Applies the reputation changes that are due (called at the start of each dividend)."""
        due = [u for u in self.pending_updates if u[0] <= self.cycle]
        self.pending_updates = [u for u in self.pending_updates if u[0] > self.cycle]
        for _, kind, name, amount in due:
            self._apply_update(kind, name, amount)
        if self.issuance_per_cycle is not None and self.fee_credits:
            total = sum(self.fee_credits.values())
            for name, paid in self.fee_credits.items():
                self._apply_update("increase", name, self.issuance_per_cycle * paid / total)
            self.fee_credits = {}
        if self.vesting_cycles:
            for agent in self.agents.values():
                agent.unvested = [entry for entry in agent.unvested if entry[0] > self.cycle]

    def kept_promises(self, promisor: str, count: int = 1, amount: float = 0.0) -> None:
        """Shorthand for promises made and kept (e.g. a wash trade, or routine honest activity)."""
        fee = self.make_promise(promisor, count, amount)
        self.fulfil_promise(promisor, count, fee_paid=fee)

    # --- loans (LoanScript) ---

    def request_loan(self, borrower: str, lender: str, principal: float, interest: float = 0.0, bond: float = 0.0) -> int:
        if borrower == lender:
            raise ValueError("Cannot borrow from yourself")
        if self.agents[borrower].delinquent:
            raise ValueError("Borrower is delinquent")
        self.stake(borrower, bond)
        self.loans.append(Loan(borrower, lender, principal, interest, bond))
        self.open_loans.add(len(self.loans) - 1)
        return len(self.loans) - 1

    def cancel_loan(self, loan_id: int) -> None:
        loan = self._loan(loan_id, "requested")
        self.open_loans.discard(loan_id)
        loan.status = "cancelled"
        self.release_stake(loan.borrower, loan.bond)

    def fund_loan(self, loan_id: int) -> None:
        loan = self._loan(loan_id, "requested")
        if self.agents[loan.borrower].delinquent:
            raise ValueError("Borrower is delinquent")
        loan.fee_paid = self.make_promise(loan.borrower, amount=loan.principal + loan.interest)
        self._pay(loan.lender, loan.borrower, loan.principal)
        loan.status = "active"

    def repay_loan(self, loan_id: int) -> None:
        loan = self._loan(loan_id, "active")
        self._pay(loan.borrower, loan.lender, loan.principal + loan.interest)
        self.open_loans.discard(loan_id)
        self.release_stake(loan.borrower, loan.bond)
        self.fulfil_promise(loan.borrower, fee_paid=loan.fee_paid)
        loan.status = "repaid"

    def default_loan(self, loan_id: int) -> None:
        loan = self._loan(loan_id, "active")
        self.open_loans.discard(loan_id)
        self.forfeit_stake(loan.borrower, loan.bond)
        self.default_promise(loan.borrower)
        loan.status = "defaulted"

    def resolve_default(self, loan_id: int, settlement: Optional[float] = None) -> None:
        """The defaulter buys the claim back (by default for the full amount owed) and burns it."""
        loan = self._loan(loan_id, "defaulted")
        price = loan.principal + loan.interest if settlement is None else settlement
        self._pay(loan.borrower, loan.lender, price)
        self.agents[loan.borrower].debts -= 1
        loan.status = "resolved"

    def loan(self, borrower: str, lender: str, principal: float, interest: float = 0.0, bond: float = 0.0) -> int:
        """Requests and funds a loan in one step."""
        loan_id = self.request_loan(borrower, lender, principal, interest, bond)
        self.fund_loan(loan_id)
        return loan_id

    def _loan(self, loan_id: int, status: str) -> Loan:
        loan = self.loans[loan_id]
        if loan.status != status:
            raise ValueError(f"Loan is {loan.status}, not {status}")
        return loan

    # --- treasury, dividends and the fee keeper ---

    def donate(self, amount: float) -> None:
        """Capital added to the treasury from outside (not paid by any agent)."""
        self.treasury += amount

    def grant(self, amount: float) -> None:
        """Money from outside to be paid out with the next dividend."""
        self.fee_pool += amount

    def pay_dividend(self, decay: bool = True) -> float:
        """
        Ends a cycle: the treasury's yield (plus any fees or grants waiting to be distributed,
        and the reserve fund's release) is paid out pro rata to reputation, and then (unless
        `decay` is false) reputation decays.
        """
        self.run_oracle()
        if self.smooth_payout:
            self.reserve_fund += self.fee_pool
            self.fee_pool = 0.0
        released = (self.reserve_release or 0.0) * self.reserve_fund
        self.reserve_fund -= released
        dividend = self.yield_rate * self.treasury + self.fee_pool + released
        self.fee_pool = 0.0
        total = sum(a.earning_reputation for a in self.agents.values())
        if dividend > 0 and total > 0:
            for name, agent in self.agents.items():
                share = dividend * agent.earning_reputation / total
                if name == self.reserve_holder:
                    if self.reserve_release is None:
                        self.fee_pool += share  # rolls into the next cycle
                    else:
                        self.reserve_fund += share
                    continue
                agent.money += share
                agent.dividends_received += share
            self.dividend_history.append(dividend)
        if decay:
            self.decay()
        self.cycle += 1
        return dividend

    def decay(self) -> None:
        """One period of reputation decay (a proportional loss, so bonds shrink with the scores they are part of)."""
        if self.decay_rate:
            keep = 1 - self.decay_rate
            for agent in self.agents.values():
                agent.reputation *= keep
                agent.staked *= keep
                for entry in agent.unvested:
                    entry[1] *= keep
            for loan_id in self.open_loans:
                self.loans[loan_id].bond *= keep

    def point_value(self, r: float, window: int = 3) -> Optional[float]:
        """The keeper's estimate of what a point is worth (None before the first dividend)."""
        if not self.dividend_history or self.total_reputation == 0:
            return None
        recent = self.dividend_history[-window:]
        return economics.point_value(sum(recent) / len(recent), self.total_reputation, r)

    def update_fee(self, margin: float = 1.5, r: float = 0.05, window: int = 3) -> float:
        """The fee keeper: re-prices the fee from recent dividends (unchanged until there are any)."""
        v = self.point_value(r, window)
        if v is not None:
            self.fee = economics.keeper_fee(v, margin, self.rep_gain)
        return self.fee
