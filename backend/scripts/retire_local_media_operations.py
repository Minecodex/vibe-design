from __future__ import annotations

import asyncio

from app.core.redis_coordination import get_redis_coordinator


async def retire_local_media_operations() -> int:
    coordinator = get_redis_coordinator()
    prefix = f"{coordinator.keys.namespace}:media-operation:"
    return await coordinator.delete_prefix(prefix)


def main() -> None:
    removed = asyncio.run(retire_local_media_operations())
    print(f"removed_media_operation_keys={removed}")


if __name__ == "__main__":
    main()
