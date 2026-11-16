"""Shared stub: any use of a stubbed package fails loudly."""


class Unavailable:
    """Stands in for a class the worker never uses."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError(f"{type(self).__name__} is stubbed out in the twin worker image")


def make(name: str) -> type:
    return type(name, (Unavailable,), {})
