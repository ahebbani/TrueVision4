from __future__ import annotations

import json
import platform

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_server_database


def main() -> None:
    config = load_config(RuntimeRole.SERVER)
    initialize_server_database(config.server_db_path)
    print(
        json.dumps(
            {
                "status": "ok",
                "role": config.role.value,
                "platform": platform.platform(),
                "server_db_path": str(config.server_db_path),
                "log_dir": str(config.log_dir),
                "next_steps": [
                    "Install faster-whisper, Zeroconf, and Ollama on the target server.",
                    "Set OLLAMA_URL and Telegram credentials if those integrations are needed.",
                    "Run make run-server after configuring the environment.",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
