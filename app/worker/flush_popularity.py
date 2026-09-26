"""Run the popularity flush once, outside the app process.

    python -m app.worker.flush_popularity
"""

from __future__ import annotations

import asyncio

from app.core.logging_config import configure_logging
from app.db.session import async_session_maker, dispose_engine
from app.services import popularity_service


async def main() -> None:
    configure_logging()
    results = await popularity_service.flush_all(async_session_maker)
    for result in results:
        print(  # noqa: T201 - this is a CLI, not a request handler
            f"{result.entity}: keys={result.keys_processed} rows={result.rows_updated} "
            f"views={result.views_applied}"
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
