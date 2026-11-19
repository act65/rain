#!/bin/bash
set -e
set -o pipefail

IMAGE_NAME="rain_dev_env"

usage() {
    echo "Usage: ./docker_helper.sh [build|test|simulate|shell|all]"
    exit 1
}

build_image() {
    echo "Building Docker image: $IMAGE_NAME..."
    docker build -t "$IMAGE_NAME" .
}

case "$1" in
    build)    build_image ;;
    test)     docker run --rm "$IMAGE_NAME" uv run ape test ;;
    simulate) docker run --rm "$IMAGE_NAME" uv run ape run run_simulation ;;
    shell)    docker run --rm -it "$IMAGE_NAME" /bin/bash ;;
    all)      build_image && docker run --rm "$IMAGE_NAME" uv run ape test ;;
    *)        usage ;;
esac
