"""Run the background worker as its own process (optional).

By default the worker runs inside the API (EMBEDDED_WORKER=true). When traffic
grows, set EMBEDDED_WORKER=false on the API and run this as a separate Render
background worker: `python worker.py`."""
from app.worker_loop import run_forever

if __name__ == "__main__":
    run_forever()
