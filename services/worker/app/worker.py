# services/worker/app/worker.py
import os
import time
import threading
from celery import Celery
from kg_common.ingest import process_document
from prometheus_client import start_http_server

# ---- Celery config ----
BROKER_URL  = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
BACKEND_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

# keep socket timeouts short to avoid hangs
BROKER_URL  += "?socket_connect_timeout=3&socket_timeout=3&health_check_interval=5"
BACKEND_URL += "?socket_connect_timeout=3&socket_timeout=3&health_check_interval=5"

celery = Celery("kg_worker", broker=BROKER_URL, backend=BACKEND_URL)
celery.conf.broker_connection_retry_on_startup = True
celery.conf.broker_connection_max_retries = 3
celery.conf.broker_transport_options = {
    "max_retries": 3,
    "interval_start": 0,
    "interval_step": 1,
    "interval_max": 3,
}
celery.conf.result_expires = 3600

# ---- Task ----
@celery.task(name="tasks.process_path")
def process_path(path: str, doc_id: str):
    """
    API sends (path, doc_id). We read the file here and pass bytes to the common ingest.
    """
    with open(path, "rb") as f:
        data = f.read()
    filename = os.path.basename(path)
    return process_document(filename, data, doc_id)

# ---- Optional: metrics on :9808 ----
def _metrics_server():
    start_http_server(9808)
    while True:
        time.sleep(5)

# If you want metrics, run celery via the CLI (as your container does) and start this thread on import:
if os.getenv("WORKER_METRICS", "1") == "1":
    t = threading.Thread(target=_metrics_server, daemon=True)
    t.start()
