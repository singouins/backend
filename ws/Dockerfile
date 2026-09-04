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
COPY --chown=ws:ws /ws/main.py  /code/main.py

# Set working directory
WORKDIR /code

# Set user
USER ws

# Entry point
ENTRYPOINT ["python3", "/code/main.py"]