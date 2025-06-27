# Use a single stage for simplicity in a dev environment
FROM python:3.9-slim

# -----------------------------------------------------------------------------
# 1. Install System Dependencies & Global Tools (Least Frequent Changes)
#    This layer is cached unless you change these commands.
# -----------------------------------------------------------------------------
USER root
RUN apt-get update && \
    apt-get install -y curl gnupg && \
    # Install Node.js
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    # Install ganache-cli globally
    npm install -g ganache-cli && \
    # Clean up
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 2. Install Python Dependencies (Changes only when requirements.txt changes)
# -----------------------------------------------------------------------------
RUN useradd -ms /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# Set PATH to include user's local bin directory
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Copy only the requirements file first
COPY --chown=appuser:appuser requirements.txt .

# Install dependencies. This layer will be cached as long as requirements.txt is unchanged.
RUN pip install --no-cache-dir --user -r requirements.txt

# -----------------------------------------------------------------------------
# 3. Compile Contracts & Dependencies (Changes only when contracts change)
#    This is the key change. We compile here to cache the solc download.
# -----------------------------------------------------------------------------
# Copy config and contracts needed for compilation
COPY --chown=appuser:appuser brownie-config.yaml .
COPY --chown=appuser:appuser contracts/ ./contracts

# Run compile. Brownie will download solc the first time and cache it in this layer.
# Subsequent builds will reuse this layer if the contracts haven't changed.
RUN brownie compile

# -----------------------------------------------------------------------------
# 4. Copy Remaining Application Code (Most Frequent Changes)
#    Copying tests and scripts last, as they change most often.
# -----------------------------------------------------------------------------
COPY --chown=appuser:appuser . .

# Expose Ganache port
EXPOSE 8545

# Keep container running for exec
CMD ["tail", "-f", "/dev/null"]