"""Production Gunicorn settings.

One worker is intentional: the API uses a local SQLite state database. Threads
allow concurrent requests while SQLite serializes the very short write
transactions used to consume session tokens.
"""

bind = "0.0.0.0:8080"
workers = 1
threads = 4
worker_class = "gthread"
timeout = 30
graceful_timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000
accesslog = None  # Request bodies contain short-lived bearer tokens.
errorlog = "-"
capture_output = True

