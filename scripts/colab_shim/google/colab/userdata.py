"""Environment-backed replacement for ``google.colab.userdata``."""

from __future__ import annotations

import os


class SecretNotFoundError(Exception):
    """Raised when the requested secret is not set in the environment."""


class NotebookAccessError(Exception):
    """Kept for API parity with Colab; never raised by the shim."""


def get(key: str) -> str:
    value = os.environ.get(key)
    if value is None:
        raise SecretNotFoundError(
            f"Secret {key!r} not found. Outside Colab, export it as an environment "
            f"variable before running the notebook."
        )
    return value
