from __future__ import annotations

import argparse
import json

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.store import PiStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage face embeddings in the TrueVision Pi database")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--prune", type=int, help="Face ID to prune")
    parser.add_argument("--keep", type=int, default=10)
    parser.add_argument("--delete", type=int, help="Face ID to delete")
    args = parser.parse_args()

    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    store = PiStore(config.pi_db_path)

    if args.stats:
        payload = []
        for face in store.list_faces():
            embeddings = store.list_face_embeddings(face_id=face.id)
            average_quality = round(sum(record.quality for record in embeddings) / len(embeddings), 2) if embeddings else 0.0
            payload.append(
                {
                    "face_id": face.id,
                    "name": face.name,
                    "embedding_count": len(embeddings),
                    "average_quality": average_quality,
                }
            )
        print(json.dumps({"stats": payload}, indent=2))
        return

    if args.prune is not None:
        removed = store.prune_face_embeddings(args.prune, keep=args.keep)
        print(json.dumps({"pruned": args.prune, "removed": removed, "keep": args.keep}, indent=2))
        return

    if args.delete is not None:
        deleted = store.delete_face(args.delete)
        print(json.dumps({"deleted": args.delete, "success": deleted}, indent=2))
        return

    parser.error("Choose one of --stats, --prune, or --delete")


if __name__ == "__main__":
    main()
