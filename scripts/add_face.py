from __future__ import annotations

import argparse
import json

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.store import PiStore, serialize_face


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a face record to the Pi database")
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)

    store = PiStore(config.pi_db_path)
    face = store.add_face(args.name)
    print(json.dumps({"face": serialize_face(face)}, indent=2))


if __name__ == "__main__":
    main()
