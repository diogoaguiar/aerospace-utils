"""Errors shared across modules."""


class UsageError(ValueError):
    """The request can't be carried out as asked: bad arguments, unknown layout, wrong window count."""
