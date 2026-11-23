"""Allow ``python -m bmp2dxf ...``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
