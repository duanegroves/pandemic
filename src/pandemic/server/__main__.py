"""``python -m pandemic.server [--host H] [--port P]``."""

import argparse

import uvicorn


def main() -> None:
    p = argparse.ArgumentParser(description="Pandemic multiplayer server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    # ws_max_size is a hard transport cap; rooms.MAX_MESSAGE_BYTES is the softer protocol limit.
    uvicorn.run("pandemic.server.app:app", host=args.host, port=args.port, ws_max_size=64 * 1024)


if __name__ == "__main__":
    main()
