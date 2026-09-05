"""Command-line interface for ABtools search-and-tag workflow.

Caution: the import below rebinds the name ``main`` on this package from the
submodule to the function, so ``from ablib.cli import main`` yields the
*function* while ``importlib.import_module("ablib.cli.main")`` yields the
*module*. Code that needs the module (AbtoolsGui does) must use importlib or
``import ablib.cli.main`` and reference the full dotted path.
"""

from .main import main

__all__ = ["main"]
