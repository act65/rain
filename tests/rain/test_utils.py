import json
import os
import pytest
from rain.utils import save_deployment_data, load_deployment_data

def test_save_and_load_deployment_data(tmp_path):
    """
    Tests that data saved can be correctly loaded back.
    """
    sample_data = {
        "contractA": "0x123...",
        "contractB": "0x456...",
        "network": "mainnet",
        "version": 1.0
    }
    # Create a subdirectory for the test file to ensure tmp_path works as expected
    test_dir = tmp_path / "test_data"
    test_dir.mkdir()
    file_path = test_dir / "deployment.json"

    # Save data
    save_deployment_data(sample_data, str(file_path))

    # Load data
    loaded_data = load_deployment_data(str(file_path))

    assert loaded_data == sample_data

def test_load_deployment_data_file_not_found(tmp_path):
    """
    Tests that loading a non-existent file returns an empty dict.
    """
    # Create a path to a non-existent file within the temp directory
    non_existent_file_path = tmp_path / "non_existent.json"

    loaded_data = load_deployment_data(str(non_existent_file_path))
    assert loaded_data == {}

def test_load_deployment_data_json_decode_error(tmp_path):
    """
    Tests that loading a file with invalid JSON returns an empty dict.
    """
    # Create a subdirectory for the test file
    test_dir = tmp_path / "test_data_malformed"
    test_dir.mkdir()
    malformed_file_path = test_dir / "malformed.json"

    # Create a file with invalid JSON content
    with open(malformed_file_path, "w") as f:
        f.write("this is not valid json")

    loaded_data = load_deployment_data(str(malformed_file_path))
    assert loaded_data == {}

def test_save_deployment_data_creates_file(tmp_path):
    """
    Tests that save_deployment_data actually creates a file.
    """
    sample_data = {"test": "data"}
    file_path = tmp_path / "new_deployment.json"

    save_deployment_data(sample_data, str(file_path))

    assert os.path.exists(file_path)
    # Clean up by removing the file if needed, though tmp_path handles it
    # os.remove(file_path) # Not strictly necessary with tmp_path

def test_empty_data_save_and_load(tmp_path):
    """
    Tests saving and loading empty deployment data.
    """
    empty_data = {}
    file_path = tmp_path / "empty_deployment.json"

    save_deployment_data(empty_data, str(file_path))
    loaded_data = load_deployment_data(str(file_path))

    assert loaded_data == empty_data
