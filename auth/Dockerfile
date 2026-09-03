# Stage 1: Build
FROM python:3.14-alpine3.22 AS builder

# Create user and group
RUN adduser -h /code -u 1000 -D -H auth

# Copy only requirements to leverage Docker cache
COPY --chown=auth:auth /auth/requirements.txt /code/requirements.txt

# Install dependencies
RUN su auth -c "pip3 install --user -U -r /code/requirements.txt"

# Stage 2: Final
FROM python:3.14-alpine3.22

# Create user and group
RUN adduser -h /code -u 1000 -D -H auth

# Set environment variables
ENV PATH="/code/.local/bin:${PATH}"

# Copy the necessary files from the build stage
COPY --chown=auth:auth --from=builder /code /code

# Copy application code
COPY --chown=auth:auth /auth   /code
COPY --chown=auth:auth /mongo  /code/mongo

# Set working directory
WORKDIR /code

# Set user
USER auth

# Entry point
ENTRYPOINT ["/code/main.py"]
