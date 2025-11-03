# Gunicorn configuration optimized for Railway deployment
import os
import multiprocessing

# Binding
port = os.getenv("PORT", "8080")
bind = f"0.0.0.0:{port}"

# Worker Configuration
workers = 2  # Optimized for Railway's free tier
worker_class = "aiohttp.GunicornWebWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Timeouts
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"
# --- THE BAD LINE IS NOW GONE ---

# Process Naming
proc_name = "tarsbot_gunicorn"

# SSL (handled by Railway)
forwarded_allow_ips = '*'
secure_scheme_headers = {'X-Forwarded-Proto': 'https'}