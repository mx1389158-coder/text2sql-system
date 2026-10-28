from pathlib import Path

from packages.execution.demo_db import create_demo_database


if __name__ == "__main__":
    path = create_demo_database(Path("data/snapshots/demo.db"))
    print(f"Demo database ready: {path.resolve()}")

