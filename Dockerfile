# Base image with Python and Node.js
FROM python:3.9-slim as builder

# Install Node.js and npm
USER root
RUN apt-get update && \
    apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up a non-root user
RUN useradd -ms /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# Install Python dependencies for Brownie and project
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Install ganache-cli globally using npm
RUN npm install -g ganache-cli

# Add local pip and npm bin directories to PATH
ENV PATH="/home/appuser/.local/bin:/home/appuser/node_modules/.bin:${PATH}"

# Application image
FROM python:3.9-slim

# Create a non-root user and group
RUN groupadd -r appgroup && useradd -r -g appgroup -ms /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# Copy installed tools from builder stage
COPY --from=builder /home/appuser/.local /home/appuser/.local
COPY --from=builder /home/appuser/node_modules /home/appuser/node_modules
COPY --from=builder /usr/bin/node /usr/bin/node
COPY --from=builder /usr/lib/node_modules /usr/lib/node_modules
COPY --from=builder /usr/bin/npm /usr/bin/npm
COPY --from=builder /usr/bin/npx /usr/bin/npx

# Add local pip and npm bin directories to PATH
ENV PATH="/home/appuser/.local/bin:/home/appuser/node_modules/.bin:/usr/lib/node_modules/ganache-cli/cli.js:${PATH}"
# The above line is a bit of a guess for ganache, might need adjustment
# A better way for ganache would be to find its actual installed path or rely on npm's global linking

# Copy project files
COPY . .

# Brownie installs solc on first run or when needed.
# To ensure solc 0.8.19 is available (as per brownie-config.yaml),
# we can trigger its installation. Brownie will download it to ~/.brownie/compilers
# This command also compiles contracts, which is good to do at build time.
# Brownie needs network access to download OpenZeppelin dependencies too.
RUN brownie compile

# Expose Ganache port
EXPOSE 8545

# Default command (can be overridden)
# CMD ["brownie", "test"]
# For now, we'll handle starting Ganache and running tests in a separate script.
CMD ["tail", "-f", "/dev/null"] # Keep container running for exec
