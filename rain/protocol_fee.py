# rain/protocol_fee.py

"""
Core off-chain logic for calculating the dynamic protocol fee.
"""

import math
from typing import Any, Optional

# This value should ideally be synchronized or sourced from a shared config if also used elsewhere (e.g. reputation oracle)
# For now, defined here as it's directly used in fee calculation logic.
# If rain.reputation.REP_GAIN_ON_FULFILLMENT is stable, could import it.
DEFAULT_REP_GAIN_ON_FULFILLMENT = 25 * (10**18)

# Default safety margin, can be overridden
DEFAULT_SAFETY_MARGIN = 1.5

def calculate_new_protocol_fee(
    calculus_engine_contract: Any, # Brownie Contract for CalculusEngine
    rain_reputation_contract: Any, # Brownie Contract for RainReputation
    treasury_v2_contract: Any,     # Brownie Contract for TreasuryV2
    rep_gain_on_fulfillment: Optional[int] = None,
    safety_margin: Optional[float] = None
) -> Optional[int]:
    """
    Calculates a new protocol fee based on system state.

    Args:
        calculus_engine_contract: Instance of the CalculusEngine contract.
        rain_reputation_contract: Instance of the RainReputation contract.
        treasury_v2_contract: Instance of the TreasuryV2 contract.
        rep_gain_on_fulfillment: The amount of reputation gained for a fulfilled promise.
                                 Defaults to DEFAULT_REP_GAIN_ON_FULFILLMENT.
        safety_margin: The safety margin to apply to the calculated fee.
                       Defaults to DEFAULT_SAFETY_MARGIN.

    Returns:
        The calculated new protocol fee as an integer, or None if calculation is not possible.
    """

    _rep_gain = rep_gain_on_fulfillment if rep_gain_on_fulfillment is not None else DEFAULT_REP_GAIN_ON_FULFILLMENT
    _safety_margin = safety_margin if safety_margin is not None else DEFAULT_SAFETY_MARGIN

    current_fee = calculus_engine_contract.protocolFee()
    print(f"  - [Core Logic] Current Protocol Fee: {current_fee / 10**18} DMD")

    # Get the total amount of reputation in the system
    total_reputation = rain_reputation_contract.totalReputation()
    if total_reputation == 0:
        print("  - [Core Logic] ERROR: Total reputation is zero. Cannot calculate fee.")
        return None
    print(f"  - [Core Logic] Total System Reputation: {total_reputation / 10**18}")

    # Get the details of the last dividend cycle
    num_cycles = treasury_v2_contract.getNumberOfCycles()
    if num_cycles == 0:
        print("  - [Core Logic] WARNING: No dividend cycles have occurred yet. Cannot calculate new fee.")
        return None

    last_cycle_id = num_cycles - 1
    try:
        # Ensure getCycleDetails is called correctly if it's part of TreasuryV2 ABI
        last_cycle_details = treasury_v2_contract.getCycleDetails(last_cycle_id)
        last_dividend_amount = last_cycle_details[2] # totalAmount is the 3rd element (index 2)
    except Exception as e:
        print(f"  - [Core Logic] ERROR: Could not retrieve details for cycle {last_cycle_id}: {e}")
        return None

    if last_dividend_amount == 0:
        print("  - [Core Logic] WARNING: Last dividend amount was zero. Using current fee or skipping update.")
        return None # Or return current_fee if no change is desired
    print(f"  - [Core Logic] Last Dividend Pool Size (Cycle {last_cycle_id}): {last_dividend_amount / 10**18} DMD")

    # Value per Rep = Last Dividend Amount / Total Reputation
    value_per_rep = last_dividend_amount / total_reputation
    print(f"  - [Core Logic] Calculated Value Per Reputation Point: {value_per_rep}")

    # Value of Rep Gain = Value per Rep * Amount of Rep Gained for a Fulfilled Promise
    value_of_rep_gain = value_per_rep * _rep_gain
    print(f"  - [Core Logic] Economic Value of Reputation Gain (from one action, using {_rep_gain / 10**18} rep gain): {value_of_rep_gain / 10**18} DMD")

    # New Fee = Value of Rep Gain * Safety Margin
    new_fee = math.ceil(value_of_rep_gain * _safety_margin)
    print(f"  - [Core Logic] Calculated New Fee (with {_safety_margin}x margin): {new_fee / 10**18} DMD")

    return int(new_fee)
