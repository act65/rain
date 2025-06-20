#!/bin/bash

echo "======================================="
echo "Installing project dependencies..."
echo "======================================="

# Function to check if a command exists
command_exists () {
    type "$1" &> /dev/null ;
}

# Check for Python 3
if ! command_exists python3; then
    echo "ERROR: Python 3 is not installed. Please install it first."
    exit 1
fi

# Check for pip3
if ! command_exists pip3; then
    echo "ERROR: pip3 is not installed. Please install it first."
    exit 1
fi

# Check for Node.js/npm
if ! command_exists npm; then
    echo "ERROR: Node.js and npm are not installed. Please install them first."
    exit 1
fi

echo "--- Installing eth-brownie ---"
pip3 install eth-brownie

echo ""
echo "--- Installing ganache-cli ---"
npm install -g ganache-cli

echo ""
echo "======================================="
echo "✅ Installation Complete!"
echo "======================================="