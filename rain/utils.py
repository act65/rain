# rain/utils.py

"""
This module will contain common utility functions used across
the off-chain tools for the Rain protocol.
"""
import json
from typing import Dict, Any

def save_deployment_data(data: Dict[str, Any], filepath: str) -> None:
    """
    Saves deployment data (like contract addresses) to a JSON file.

    Args:
        data: A dictionary containing the data to save.
        filepath: The path to the JSON file.
    """
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Deployment data saved to {filepath}")

def load_deployment_data(filepath: str) -> Dict[str, Any]:
    """
    Loads deployment data from a JSON file.

    Args:
        filepath: The path to the JSON file.

    Returns:
        A dictionary containing the loaded data.
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        print(f"Deployment data loaded from {filepath}")
        return data
    except FileNotFoundError:
        print(f"Error: Deployment file {filepath} not found.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}.")
        return {}

# More utilities will be added below.
