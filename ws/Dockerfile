# Stage 1: Build
FROM python:3.14-alpine3.22 AS builder

# Create user and group
RUN adduser -h /code -u 1000 -D -H ws

# Copy only requirements to leverage Docker cache
COPY --chown=ws:ws /ws/requirements.txt /code/requirements.txt

# Install dependencies
RUN su ws -c "pip3 install --user --no-cache-dir -r /code/requirements.txt"

# Stage 2: Final
FROM python:3.14-alpine3.22

# Create user and group
RUN adduser -h /code -u 1000 -D -H ws

# Set environment variables
ENV PATH="/code/.local/bin:${PATH}"

# Copy the necessary files from the build stage
COPY --chown=ws:ws --from=builder /code /code

# Copy application code
COPY --chown=ws:ws /ws/main.py        /code/main.py
COPY --chown=ws:ws /ws/entrypoint.sh  /code/entrypoint.sh

# Set working directory
WORKDIR /code

# Set user
USER ws

# Entry point
# Production runs main.py directly. The supervising wrapper (entrypoint.sh)
# is still shipped in the image so it can be selected per-deployment via a
# Kubernetes command override (see docs/DEBUG.md) without changing the
# default image behavior.
ENTRYPOINT ["python3", "/code/main.py"]