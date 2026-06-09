"""dot-indexer — the intelligence layer.

Watches the filesystem, parses code into semantic units, chunks it by
function/class boundaries, and generates local embeddings.
"""

from dot.indexer.chunker import Chunk, chunk_file
from dot.indexer.embedder import Embedder
from dot.indexer.parser import CodeParser, ParsedSymbol
from dot.indexer.watcher import ProjectWatcher

__all__ = ["Chunk", "chunk_file", "Embedder", "CodeParser", "ParsedSymbol", "ProjectWatcher"]
