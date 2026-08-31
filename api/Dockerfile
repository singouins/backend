# Stage 1: Build
FROM python:3.14-alpine3.22 AS builder

# Create user and group
RUN adduser -h /code -u 1000 -D -H api

# Copy only requirements to leverage Docker cache
COPY --chown=api:api /api/requirements.txt /code/requirements.txt

# Install dependencies
RUN su api -c "pip3 install --user -U -r /code/requirements.txt"

# Stage 2: Final
FROM python:3.14-alpine3.22

# Create user and group
RUN adduser -h /code -u 1000 -D -H api

# Set environment variables
ENV PATH="/code/.local/bin:${PATH}"

# Copy the necessary files from the build stage
COPY --chown=api:api --from=builder /code /code

# Copy application code
COPY --chown=api:api /api    /code
COPY --chown=api:api /mongo  /code/mongo
# api/utils/redis.py is a symlink to ../../_redis/redis.py; COPY doesn't
# dereference symlinks, so its target has to exist at that same relative
# path in the image too (../../_redis from /code/utils, i.e. /_redis).
COPY --chown=api:api /_redis /_redis

# Set working directory
WORKDIR /code

# Set user
USER api

# Entry point
ENTRYPOINT ["/code/main.py"]