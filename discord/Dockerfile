# Stage 1: Build
FROM python:3.14-alpine3.22 AS builder

# Create user and group
RUN adduser -h /code -u 1000 -D -H discord

# Copy only requirements to leverage Docker cache
COPY --chown=discord:discord /discord/requirements.txt /code/requirements.txt

# Install dependencies
RUN su discord -c "pip3 install --user --no-cache-dir -r /code/requirements.txt"

# Stage 2: Final
FROM python:3.14-alpine3.22

# Create user and group
RUN adduser -h /code -u 1000 -D -H discord

# Set environment variables
ENV PATH="/code/.local/bin:${PATH}"

# Copy the necessary files from the build stage
COPY --chown=discord:discord --from=builder /code /code

# Copy application code
COPY --chown=discord:discord /discord   /code
COPY --chown=discord:discord /mongo     /code/mongo

# Set working directory
WORKDIR /code

# Set user
USER discord

# Entry point
ENTRYPOINT ["/code/main.py"]