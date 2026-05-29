"""refmatrix: roaring-bitmap reference index for docs, code, and concepts."""
__version__ = "0.3.26"

from refmatrix.store import Store
from refmatrix.query import QueryEngine

__all__ = ["Store", "QueryEngine", "__version__"]
