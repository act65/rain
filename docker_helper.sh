#!/bin/bash

set -e # Exit immediately if a command exits with a non-zero status.
set -o pipefail # The return value of a pipeline is the status of the last command to exit with a non-zero status, or zero if no command exited with a non-zero status

IMAGE_NAME="solidity_dev_env"
CONTAINER_NAME="solidity_app_dev"
GANACHE_PORT=8545
TEST_MNEMONIC="candy maple cake sugar pudding cream honey rich smooth crumble sweet treat"

# Function to build the Docker image
build_image() {
    echo "Building Docker image: $IMAGE_NAME..."
    docker build -t "$IMAGE_NAME" .
    echo "✅ Docker image built."
}

# Function to start Ganache in a detached container
start_ganache_container() {
    echo "Starting Ganache container: $CONTAINER_NAME..."
    
    # More robust cleanup: attempt to stop and remove, ignoring errors if it doesn't exist
    echo "Ensuring no old container with the name $CONTAINER_NAME exists..."
    docker stop "$CONTAINER_NAME" > /dev/null 2>&1 || true
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1 || true

    echo "Creating new container..."
    docker run -d --name "$CONTAINER_NAME" \
        -p "${GANACHE_PORT}:${GANACHE_PORT}" \
        "$IMAGE_NAME" \
        ganache-cli \
        --host 0.0.0.0 \
        --port "$GANACHE_PORT" \
        --mnemonic "$TEST_MNEMONIC" \
        --accounts 10 \
        --defaultBalanceEther 1000 \
        --gasLimit 12000000 \
        --deterministic > /dev/null

    echo "Waiting for Ganache to start..."
    # Simple wait, can be improved with health check
    sleep 5
    docker logs "$CONTAINER_NAME" # Show Ganache logs to confirm startup
    echo "✅ Ganache container started."
}

# Function to stop and remove the Ganache container
stop_ganache_container() {
    echo "Stopping and removing Ganache container: $CONTAINER_NAME..."
    if [ "$(docker ps -q -f name="^${CONTAINER_NAME}$")" ]; then
        docker stop "$CONTAINER_NAME" > /dev/null
        docker rm "$CONTAINER_NAME" > /dev/null
        echo "✅ Ganache container stopped and removed."
    else
        echo "Ganache container $CONTAINER_NAME is not running."
    fi
}

# Function to run Brownie tests in the Ganache container
# This approach uses `docker exec` into the already running Ganache container.
# An alternative would be to use docker-compose or link containers.
run_tests() {
    if ! [ "$(docker ps -q -f name="^${CONTAINER_NAME}$")" ]; then
        echo "Error: Ganache container $CONTAINER_NAME is not running. Please start it first with './docker_helper.sh start_ganache'."
        exit 1
    fi
    echo "Running tests in container $CONTAINER_NAME..."
    # Ensure contracts are compiled (should be done in Dockerfile, but good for safety)
    # docker exec "$CONTAINER_NAME" brownie compile
    # Run tests, Brownie will connect to Ganache at 127.0.0.1:8545 (within container)
    docker exec "$CONTAINER_NAME" brownie test -s # -s shows print output
    echo "✅ Tests finished."
}

# Function to run all steps: build, start ganache, run tests, stop ganache
run_all() {
    build_image
    start_ganache_container
    trap stop_ganache_container EXIT # Ensure Ganache is stopped even if tests fail
    run_tests
    # stop_ganache_container will be called by trap
}

# Function to open a shell in the running Ganache container
open_shell() {
    if ! [ "$(docker ps -q -f name="^${CONTAINER_NAME}$")" ]; then
        echo "Error: Ganache container $CONTAINER_NAME is not running. Please start it first with './docker_helper.sh start_ganache'."
        exit 1
    fi
    echo "Opening shell in container $CONTAINER_NAME..."
    docker exec -it "$CONTAINER_NAME" /bin/bash
}


# Main script logic
if [ -z "$1" ]; then
    echo "Usage: ./docker_helper.sh [build|start_ganache|stop_ganache|test|all|shell]"
    exit 1
fi

case "$1" in
    build)
        build_image
        ;;
    start_ganache)
        start_ganache_container
        ;;
    stop_ganache)
        stop_ganache_container
        ;;
    test)
        run_tests
        ;;
    all)
        run_all
        ;;
    shell)
        open_shell
        ;;
    *)
        echo "Invalid command: $1"
        echo "Usage: ./docker_helper.sh [build|start_ganache|stop_ganache|test|all|shell]"
        exit 1
        ;;
esac
