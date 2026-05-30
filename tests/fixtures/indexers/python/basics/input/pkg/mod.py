"""Basics fixture: top-level function, class with method, module variable."""

MAX_RETRIES = 3


def add(a, b):
    return a + b


class Counter:
    INITIAL = 0

    def __init__(self):
        self.count = self.INITIAL

    def inc(self):
        self.count = add(self.count, 1)
        return self.count
