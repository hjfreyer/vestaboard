import asyncio
import logging

from .app import run


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("shutting down")


if __name__ == "__main__":
    main()
