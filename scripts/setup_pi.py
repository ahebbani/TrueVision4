from __future__ import annotations

import json
import platform

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database


def main() -> None:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    print(
        json.dumps(
            {
                "status": "ok",
                "role": config.role.value,
                "platform": platform.platform(),
                "pi_db_path": str(config.pi_db_path),
                "log_dir": str(config.log_dir),
                "next_steps": [
                    "Install Pi-specific camera, serial, and ML dependencies.",
                    "Enable UART and camera access on the Raspberry Pi.",
                    "Run make run or make run-display once the hardware stack is ready.",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
