FROM python:3.12-slim

LABEL maintainer="eibo.richter@gmail.com"
LABEL description="Idle Space RPG - IRC Idle Game Bot"

# Create non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot/ ./bot/

# Create data directory
RUN mkdir -p /data && chown botuser:botuser /data

# Switch to non-root user
USER botuser

# Health check - verify the process is running
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD pgrep -f "python -m bot" || exit 1

# Run the bot
CMD ["python", "-m", "bot"]
