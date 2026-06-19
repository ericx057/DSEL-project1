#!/usr/bin/env python3
"""Compatibility launcher for the production desktop application."""

from src.desktop import spotlight as _spotlight

__all__ = [name for name in dir(_spotlight) if not name.startswith("__")]
globals().update({name: getattr(_spotlight, name) for name in __all__})


if __name__ == "__main__":
    raise SystemExit(_spotlight.main())
