# Gunicorn configuration for Railway deployment

# Worker Settings
workers = 2  # Reduced number of workers for Railway's memory constraints
worker_class = 'aiohttp.GunicornWebWorker'
worker_connections = 100  # Reduced connections per worker
max_requests = 1000  # Restart workers after handling this many requests
max_requests_jitter = 50  # Add randomness to max_requests
timeout = 120  # Increased timeout for long-polling
graceful_timeout = 30

# Memory Management
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
worker_tmp_dir = '/tmp'

# Resource Management
preload_app = False  # Don't preload app to save memory
daemon = False
pidfile = None
umask = 0
user = None
group = None

# Logging
accesslog = '-'  # Log to stdout
errorlog = '-'   # Log to stderr
loglevel = 'info'
access_log_format = '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process Naming
proc_name = 'telegram_bot'

# SSL/TLS
ssl_version = 2
cert_reqs = 0

def on_starting(server):
    """Called just before the master process is initialized."""
    import resource
    # Set soft limit for memory usage
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 512, -1))  # 512MB soft limit