import pytest
import math
from unittest.mock import MagicMock

from rain.protocol_fee import (
    calculate_new_protocol_fee,
    DEFAULT_REP_GAIN_ON_FULFILLMENT,
    DEFAULT_SAFETY_MARGIN
)

# --- Mock Contract Objects ---

class MockCalculusEngine:
    def __init__(self, fee=0):
        self._protocol_fee = fee

    def protocolFee(self):
        return self._protocol_fee

class MockRainReputation:
    def __init__(self, total_rep=0):
        self._total_reputation = total_rep

    def totalReputation(self):
        return self._total_reputation

class MockTreasuryV2:
    def __init__(self, num_cycles=0, cycle_details=None):
        self._num_cycles = num_cycles
        # cycle_details should be a dict mapping cycle_id to a tuple/list
        # where index 2 is totalAmount
        self._cycle_details_map = cycle_details if cycle_details else {}

    def getNumberOfCycles(self):
        return self._num_cycles

    def getCycleDetails(self, cycle_id: int):
        if cycle_id in self._cycle_details_map:
            return self._cycle_details_map[cycle_id]
        raise Exception(f"MockTreasuryV2: Cycle ID {cycle_id} not found.")


# --- Test Cases ---

def test_calculate_new_protocol_fee_happy_path():
    mock_calc_engine = MockCalculusEngine(fee=100 * 10**18) # Current fee 100
    mock_rep_contract = MockRainReputation(total_rep=10000 * 10**18) # Total rep 10,000

    # Last cycle (ID 0) had 5000 DMD distributed
    mock_treasury = MockTreasuryV2(
        num_cycles=1,
        cycle_details={0: (0, 0, 5000 * 10**18, 0, 0)} # (merkleRoot, totalRewards, totalAmount, startBlock, endBlock)
    )

    # Expected calculation:
    # total_reputation = 10000e18
    # last_dividend_amount = 5000e18
    # value_per_rep = 5000e18 / 10000e18 = 0.5
    # rep_gain (default) = 25e18
    # value_of_rep_gain = 0.5 * 25e18 = 12.5e18
    # safety_margin (default) = 1.5
    # new_fee = ceil(12.5e18 * 1.5) = ceil(18.75e18) = 19e18 (approx, due to ceil)
    # Actually, new_fee = math.ceil(18.75 * 10**18) = math.ceil(18750000000000000000) = 18750000000000000000
    # The scaling happens before ceil.

    expected_value_per_rep = (5000 * 10**18) / (10000 * 10**18) # 0.5
    expected_value_of_rep_gain = expected_value_per_rep * DEFAULT_REP_GAIN_ON_FULFILLMENT # 0.5 * 25e18 = 12.5e18
    expected_raw_new_fee = expected_value_of_rep_gain * DEFAULT_SAFETY_MARGIN # 12.5e18 * 1.5 = 18.75e18
    expected_final_fee = math.ceil(expected_raw_new_fee)

    new_fee = calculate_new_protocol_fee(mock_calc_engine, mock_rep_contract, mock_treasury)

    assert new_fee is not None
    assert new_fee == expected_final_fee
    assert new_fee == 18750000000000000000 # explicit check for 18.75e18 being ceiled


def test_calculate_new_protocol_fee_custom_params():
    mock_calc_engine = MockCalculusEngine(fee=100 * 10**18)
    mock_rep_contract = MockRainReputation(total_rep=10000 * 10**18)
    mock_treasury = MockTreasuryV2(
        num_cycles=1,
        cycle_details={0: (0, 0, 5000 * 10**18, 0, 0)}
    )

    custom_rep_gain = 50 * 10**18 # 50 rep
    custom_safety_margin = 2.0

    # Expected calculation:
    # value_per_rep = 0.5 (as above)
    # value_of_rep_gain = 0.5 * 50e18 = 25e18
    # new_fee = ceil(25e18 * 2.0) = ceil(50e18) = 50e18
    expected_value_per_rep = (5000 * 10**18) / (10000 * 10**18)
    expected_value_of_rep_gain = expected_value_per_rep * custom_rep_gain
    expected_raw_new_fee = expected_value_of_rep_gain * custom_safety_margin
    expected_final_fee = math.ceil(expected_raw_new_fee)

    new_fee = calculate_new_protocol_fee(
        mock_calc_engine, mock_rep_contract, mock_treasury,
        rep_gain_on_fulfillment=custom_rep_gain,
        safety_margin=custom_safety_margin
    )
    assert new_fee is not None
    assert new_fee == expected_final_fee
    assert new_fee == 50 * 10**18


def test_total_reputation_zero():
    mock_calc_engine = MockCalculusEngine()
    mock_rep_contract = MockRainReputation(total_rep=0) # Total rep is zero
    mock_treasury = MockTreasuryV2(num_cycles=1, cycle_details={0: (0,0,1000,0,0)})

    new_fee = calculate_new_protocol_fee(mock_calc_engine, mock_rep_contract, mock_treasury)
    assert new_fee is None

def test_no_dividend_cycles():
    mock_calc_engine = MockCalculusEngine()
    mock_rep_contract = MockRainReputation(total_rep=10000 * 10**18)
    mock_treasury = MockTreasuryV2(num_cycles=0) # No cycles

    new_fee = calculate_new_protocol_fee(mock_calc_engine, mock_rep_contract, mock_treasury)
    assert new_fee is None

def test_last_dividend_amount_zero():
    mock_calc_engine = MockCalculusEngine()
    mock_rep_contract = MockRainReputation(total_rep=10000 * 10**18)
    mock_treasury = MockTreasuryV2(
        num_cycles=1,
        cycle_details={0: (0, 0, 0, 0, 0)} # Last dividend amount is zero
    )

    new_fee = calculate_new_protocol_fee(mock_calc_engine, mock_rep_contract, mock_treasury)
    assert new_fee is None

def test_get_cycle_details_error():
    mock_calc_engine = MockCalculusEngine()
    mock_rep_contract = MockRainReputation(total_rep=10000 * 10**18)

    # Configure mock_treasury.getCycleDetails to raise an error
    mock_treasury = MockTreasuryV2(num_cycles=1) # Has one cycle
    # Don't add cycle_id 0 to _cycle_details_map, so it will raise default Exception
    # OR explicitly make it raise:
    mock_treasury_raising_error = MagicMock(spec=MockTreasuryV2)
    mock_treasury_raising_error.getNumberOfCycles.return_value = 1
    mock_treasury_raising_error.getCycleDetails.side_effect = Exception("RPC error")

    new_fee = calculate_new_protocol_fee(mock_calc_engine, mock_rep_contract, mock_treasury_raising_error)
    assert new_fee is None

def test_fee_calculation_involves_ceil():
    mock_calc_engine = MockCalculusEngine()
    mock_rep_contract = MockRainReputation(total_rep=100 * 10**18) # 100 rep
    mock_treasury = MockTreasuryV2(
        num_cycles=1,
        cycle_details={0: (0,0, 10 * 10**18,0,0)} # 10 DMD
    )

    # value_per_rep = 10 / 100 = 0.1
    # rep_gain = 25e18
    # value_of_rep_gain = 0.1 * 25e18 = 2.5e18
    # safety_margin = 1.5
    # new_fee_raw = 2.5e18 * 1.5 = 3.75e18
    # new_fee_ceil = ceil(3.75e18) = 375...001 if not careful, or just ceil the number then scale
    # The code does: math.ceil(value_of_rep_gain * _safety_margin)
    # math.ceil(3.75 * 10**18) = math.ceil(3750000000000000000) = 3750000000000000000

    # Let's use values that will definitely need ceiling for the final small integer part
    # value_per_rep * rep_gain * margin = some_float.
    # Example: value_of_rep_gain * _safety_margin = 3.000000000000000001 (hypothetical to force ceil)
    # The current calculation is precise with large integers, so direct float issues are less likely
    # unless division results in repeating decimals.
    # (10e18 / 100e18) * 25e18 * 1.5 = 0.1 * 25e18 * 1.5 = 2.5e18 * 1.5 = 3.75e18
    # math.ceil(3.75e18) is just 3.75e18 because it's already an integer multiple of 1.
    # The ceil is more relevant if the number of wei would be fractional.
    # Let's test with numbers that would produce a fraction if not for large integer arithmetic.

    mock_rep_contract_ceil = MockRainReputation(total_rep=3 * 10**18) # 3 rep
    mock_treasury_ceil = MockTreasuryV2(
        num_cycles=1,
        cycle_details={0: (0,0, 10 * 10**18,0,0)} # 10 DMD
    )
    # value_per_rep = 10/3
    # rep_gain = 25e18
    # value_of_rep_gain = (10/3) * 25e18 = (250/3)e18
    # safety_margin = 1.5
    # new_fee_raw = (250/3)e18 * 1.5 = (250/3)e18 * (3/2) = 125e18. This is still whole.

    # Let's try to make value_of_rep_gain * _safety_margin result in a non-integer scaled value
    # if it were float arithmetic.
    # Example: value_of_rep_gain = 100, safety_margin = 1.0000000000000001 (won't work with current structure)
    # The result of (rep_gain * total_dividend_amount * safety_margin) / total_reputation
    # then ceiled.

    # Let rep_gain = 1, total_dividend = 7, total_rep = 2, safety_margin = 1
    # (1 * 7 * 1) / 2 = 3.5. Ceil(3.5) = 4.
    mock_rep_contract_force_ceil = MockRainReputation(total_rep=2)
    mock_treasury_force_ceil = MockTreasuryV2(num_cycles=1, cycle_details={0: (0,0,7,0,0)})
    custom_rep_gain_ceil = 1
    custom_safety_margin_ceil = 1.0 # Exact, no margin effect on float part here

    # value_per_rep = 7 / 2 = 3.5
    # value_of_rep_gain = 3.5 * 1 = 3.5
    # new_fee_raw = 3.5 * 1.0 = 3.5
    # math.ceil(3.5) = 4
    new_fee = calculate_new_protocol_fee(
        mock_calc_engine, mock_rep_contract_force_ceil, mock_treasury_force_ceil,
        rep_gain_on_fulfillment=custom_rep_gain_ceil,
        safety_margin=custom_safety_margin_ceil
    )
    assert new_fee == 4

    # Example with safety margin causing ceiling
    # rep_gain = 1, total_dividend = 5, total_rep = 2, safety_margin = 1.1
    # value_per_rep = 5/2 = 2.5
    # value_of_rep_gain = 2.5 * 1 = 2.5
    # new_fee_raw = 2.5 * 1.1 = 2.75
    # math.ceil(2.75) = 3
    mock_treasury_force_ceil_margin = MockTreasuryV2(num_cycles=1, cycle_details={0: (0,0,5,0,0)})
    custom_safety_margin_ceil2 = 1.1
    new_fee_margin = calculate_new_protocol_fee(
        mock_calc_engine, mock_rep_contract_force_ceil, mock_treasury_force_ceil_margin,
        rep_gain_on_fulfillment=custom_rep_gain_ceil,
        safety_margin=custom_safety_margin_ceil2
    )
    assert new_fee_margin == 3
