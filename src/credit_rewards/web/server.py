"""Dev server entry point (works after pip install -e .)."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "credit_rewards.web.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
