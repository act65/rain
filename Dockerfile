# Use a single stage for simplicity in a dev environment
FROM python:3.9-slim

# Install system dependencies, Node.js, and global npm packages as root
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

# Create a non-root user for the application
RUN useradd -ms /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# Set PATH to include user's local bin directory
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Copy project-specific files
COPY requirements.txt .
COPY brownie-config.yaml .
# Copy other necessary config files if they exist

# Install Python dependencies as the non-root user
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy the rest of the application code
COPY . .

# Trigger solc installation and contract compilation
# This now runs in the same environment where brownie was installed
RUN brownie compile

# Expose Ganache port
EXPOSE 8545

# Keep container running for exec
CMD ["tail", "-f", "/dev/null"]