"""codemap-semantic-index — embedding-based semantic recall for codemap.

Registers via two entry-point groups:

* ``codemap.cli_commands.embed`` → :func:`codemap_semantic_index.cli.register`
  adds the ``codemap embed`` subcommand tree.
* ``codemap.recall_hooks.semantic`` → :func:`codemap_semantic_index.
  recall_hook.rank` plugs an embedding-based ranker into ``codemap recall``;
  ``codemap-aimemory>=0.4.1`` discovers it automatically and RRF-fuses
  the result with token recall + freshness.
"""

__version__ = "0.1.0"
