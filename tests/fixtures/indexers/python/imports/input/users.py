"""Imports fixture: from-import, alias import, call resolution."""

from os import path as p
from collections import defaultdict


def slugify(name):
    return name.lower()


def load(filename):
    full = p.abspath(filename)
    buckets = defaultdict(list)
    return full, buckets
