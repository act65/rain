"""Small helpers shared by the contract tests."""
from types import SimpleNamespace

import ape
from ape import chain, project, reverts  # noqa: F401  (re-exported for the tests)

accounts = ape.accounts.test_accounts


class _Logs(list):
    """The logs of one event type in a receipt. `logs["field"]` reads the first one."""

    def __getitem__(self, key):
        if isinstance(key, str):
            return list.__getitem__(self, 0)[key]
        return list.__getitem__(self, key)


class _Events:
    def __init__(self, receipt):
        self._logs = list(receipt.events)

    def __getitem__(self, name):
        logs = _Logs(dict(log.event_arguments) for log in self._logs if log.event_name == name)
        if not logs:
            raise KeyError(f"No {name} event in this transaction")
        return logs

    def __contains__(self, name):
        return any(log.event_name == name for log in self._logs)


def ev(receipt):
    """Events of a transaction, by name: `ev(tx)["Transfer"]["to"]`, `"Transfer" in ev(tx)`."""
    return _Events(receipt)


# Ids are read from the events of the transaction that created them. (A receipt's
# `return_value` is obtained by re-simulating the call, so for a counter it is off by one.)

def action_id_of(receipt):
    return ev(receipt)["ActionCreated"]["actionId"]


def promise_id_of(receipt):
    return ev(receipt)["PromiseCreated"]["promiseId"]


def token_id_of(receipt):
    return ev(receipt)["ClaimMinted"]["tokenId"]


def advance(seconds):
    """Moves the chain's clock forward and mines a block at the new time."""
    chain.pending_timestamp += seconds
    chain.mine()


E18 = 10**18
PERIOD = 30 * 24 * 60 * 60  # the decay period used in tests
ZERO_ADDRESS = "0x" + "00" * 20


def deploy_reputation(admin, retention=E18):
    """RainReputation with a 30-day decay period. By default nothing decays, so amounts in tests are exact."""
    return project.RainReputation.deploy(PERIOD, retention, sender=admin)


def seed_reputation(rep, admin, user, amount):
    """Gives `user` an identity and `amount` of reputation directly (the admin acts as an updater)."""
    if not rep.hasRole(rep.UPDATER_ROLE(), admin):
        rep.grantRole(rep.UPDATER_ROLE(), admin, sender=admin)
    rep.mint(user, sender=admin)
    rep.increaseReputation(user, amount, "TEST:seed", sender=admin)


MAX_UINT = 2**256 - 1


def deploy_treasury(admin, usdc, claim_period, schedule):
    """
    A Treasury whose release schedule comes from `schedule`: a reputation contract (as in
    production), or `(release_per_cycle, cycle_interval)` for a stand-in schedule with those values.
    """
    if isinstance(schedule, tuple):
        release, cycle_interval = schedule
        schedule = project.MockDecaySchedule.deploy(cycle_interval, E18 - release, sender=admin)
    return project.Treasury.deploy(usdc.address, claim_period, schedule.address, sender=admin)


def deploy_system(retention=E18, fee_bps=0, min_fee=E18, point_price=E18 // 25,
                  starting_reputation=1_000 * E18, release=E18, cycle_interval=0):
    """
    Deploys and wires the whole protocol the way `scripts/deploy.py` + `scripts/simulate_loan.py`
    do, except that no role is given to an account that would not hold it in production
    (the admin is only an admin).

    Alice, Bob and Carol each hold 10,000 DMD and an identity, and have given the LoanScript
    every permission it needs over them (authorization to make promises, unlimited currency
    and stake allowances). Their `starting_reputation` is credited by the oracle.

    By default reputation does not decay and each dividend cycle shares out the whole fund, so
    that amounts in tests are exact; the Treasury then takes its schedule from a stand-in.
    With `release=None` it reads the schedule from the reputation contract, as in production.
    """
    admin, oracle, alice, bob, carol = accounts[0:5]
    outsider = accounts[9]

    usdc = project.CurrencyToken.deploy(sender=admin)
    rep = deploy_reputation(admin, retention)
    treasury = deploy_treasury(admin, usdc, 7 * 24 * 60 * 60, rep if release is None else (release, cycle_interval))
    engine = project.CalculusEngine.deploy(usdc.address, treasury.address, fee_bps, min_fee, point_price, sender=admin)
    rct = project.ReputationClaimToken.deploy(rep.address, engine.address, sender=admin)
    updater = project.ReputationUpdater.deploy(rep.address, sender=admin)
    loan = project.LoanScript.deploy(engine.address, rep.address, rct.address, usdc.address, sender=admin)

    rep.grantRole(rep.UPDATER_ROLE(), updater.address, sender=admin)
    rep.setRctContract(rct.address, sender=admin)
    updater.grantRole(updater.UPDATER_ROLE(), oracle, sender=admin)

    for user in (alice, bob, carol):
        usdc.mint(user, 10_000 * E18, sender=admin)
        rep.mint(user, sender=admin)
        usdc.approve(engine.address, MAX_UINT, sender=user)
        engine.setScriptAuthorization(loan.address, True, sender=user)
        engine.approveScript(loan.address, usdc.address, MAX_UINT, sender=user)
        rep.approveStake(loan.address, MAX_UINT, sender=user)
    if starting_reputation:
        updater.applyReputationChanges(
            [(user.address, starting_reputation, "TEST:starting reputation") for user in (alice, bob, carol)], [], sender=oracle
        )

    return SimpleNamespace(
        admin=admin, oracle=oracle, alice=alice, bob=bob, carol=carol, outsider=outsider,
        usdc=usdc, rep=rep, rct=rct, treasury=treasury, engine=engine, updater=updater,
        loan=loan, fee=min_fee, reward=min_fee * E18 // point_price,
    )
