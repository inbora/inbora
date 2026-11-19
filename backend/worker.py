"""Background worker — placeholder.

From Step 2 this process takes reply jobs from the `jobs` table, runs the
agent and sends the answer. For now it only proves it can start and reach
the database. It is NOT deployed in Step 1 (see render.yaml)."""
import time

from app import db

if __name__ == "__main__":
    print(f"[worker] started, database {'ok' if db.ping() else 'unreachable'}", flush=True)
    while True:
        time.sleep(60)
