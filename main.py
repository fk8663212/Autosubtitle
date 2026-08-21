from __future__ import annotations

import sys

from autosubtitle.cli import main as cli_main


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        from autosubtitle.web import main as web_main

        return web_main(sys.argv[2:])
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
