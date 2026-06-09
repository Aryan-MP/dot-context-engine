"""Intelligent code chunking.

Splits source files into semantic chunks aligned to function/class/module
boundaries rather than fixed token windows. Each chunk carries enough
metadata (symbol name, kind, line range, imports) for ranking later.

Oversized symbols are split on blank-line boundaries; tiny adjacent
symbols are merged so embeddings aren't wasted on three-line getters.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from dot.indexer.parser import CodeParser, ParsedFile

# Soft bounds, measured with the cheap ~4 chars/token heuristic.
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 30


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars per token). Good enough for budgeting."""
    return max(1, len(text) // 4)


@dataclass
class Chunk:
    """A semantic chunk of code ready for embedding and storage."""

    chunk_id: str
    file_path: str
    language: str
    kind: str  # function | class | method | module | comment
    symbol: str
    start_line: int
    end_line: int
    content: str
    docstring: str = ""
    imports: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.content)

    def embedding_text(self) -> str:
        """Text used for embedding: prefix with location so similar code in
        different modules still embeds distinctly."""
        header = f"{self.file_path} :: {self.symbol} ({self.kind})"
        doc = f"\n{self.docstring}" if self.docstring else ""
        return f"{header}{doc}\n{self.content}"


def _chunk_id(file_path: str, symbol: str, content: str) -> str:
    digest = hashlib.sha256(f"{file_path}::{symbol}::{content}".encode()).hexdigest()
    return digest[:16]


def _split_oversized(content: str, start_line: int) -> list[tuple[int, int, str]]:
    """Split a large block on blank lines into (start, end, text) pieces."""
    lines = content.splitlines()
    pieces: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    piece_start = start_line
    for offset, line in enumerate(lines):
        buffer.append(line)
        text = "\n".join(buffer)
        if estimate_tokens(text) >= MAX_CHUNK_TOKENS and not line.strip():
            pieces.append((piece_start, start_line + offset, text))
            buffer = []
            piece_start = start_line + offset + 1
    if buffer:
        pieces.append((piece_start, start_line + len(lines) - 1, "\n".join(buffer)))
    return pieces


def chunk_file(path: Path, source: str | None = None, parser: CodeParser | None = None) -> list[Chunk]:
    """Chunk a single file into semantic units."""
    parser = parser or CodeParser()
    if source is None:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    parsed = parser.parse(path, source)
    return chunk_parsed(parsed, source)


def chunk_parsed(parsed: ParsedFile, source: str) -> list[Chunk]:
    lines = source.splitlines()
    chunks: list[Chunk] = []
    covered: set[int] = set()

    # Sort symbols so classes come before their methods; skip methods whose
    # class chunk already covers them unless the class is oversized.
    symbols = sorted(parsed.symbols, key=lambda s: (s.start_line, -(s.end_line - s.start_line)))

    for symbol in symbols:
        if symbol.kind == "comment":
            continue
        span = range(symbol.start_line, symbol.end_line + 1)
        content = "\n".join(lines[symbol.start_line - 1 : symbol.end_line])
        if not content.strip():
            continue

        if symbol.kind == "class" and estimate_tokens(content) > MAX_CHUNK_TOKENS:
            # Oversized class: emit a skeleton chunk (signature + docstring)
            # and let methods be chunked individually below.
            skeleton = symbol.signature + (f'\n    """{symbol.docstring}"""' if symbol.docstring else "")
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(parsed.file_path, symbol.name, skeleton),
                    file_path=parsed.file_path,
                    language=parsed.language,
                    kind="class",
                    symbol=symbol.name,
                    start_line=symbol.start_line,
                    end_line=symbol.start_line,
                    content=skeleton,
                    docstring=symbol.docstring,
                    imports=parsed.imports,
                )
            )
            continue

        if all(line in covered for line in span):
            continue  # already inside an emitted chunk
        covered.update(span)

        if estimate_tokens(content) > MAX_CHUNK_TOKENS:
            for piece_index, (start, end, text) in enumerate(_split_oversized(content, symbol.start_line)):
                chunks.append(
                    Chunk(
                        chunk_id=_chunk_id(parsed.file_path, f"{symbol.name}#{piece_index}", text),
                        file_path=parsed.file_path,
                        language=parsed.language,
                        kind=symbol.kind,
                        symbol=f"{symbol.name} (part {piece_index + 1})",
                        start_line=start,
                        end_line=end,
                        content=text,
                        docstring=symbol.docstring if piece_index == 0 else "",
                        imports=parsed.imports,
                    )
                )
        else:
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(parsed.file_path, symbol.name, content),
                    file_path=parsed.file_path,
                    language=parsed.language,
                    kind=symbol.kind,
                    symbol=symbol.name,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    content=content,
                    docstring=symbol.docstring,
                    imports=parsed.imports,
                )
            )

    # Module-level leftovers (imports, constants, top-level statements).
    uncovered_lines = [
        (index, line)
        for index, line in enumerate(lines, start=1)
        if index not in covered and line.strip()
    ]
    if uncovered_lines:
        module_text = "\n".join(line for _, line in uncovered_lines)
        if estimate_tokens(module_text) >= MIN_CHUNK_TOKENS:
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(parsed.file_path, "<module>", module_text),
                    file_path=parsed.file_path,
                    language=parsed.language,
                    kind="module",
                    symbol="<module>",
                    start_line=uncovered_lines[0][0],
                    end_line=uncovered_lines[-1][0],
                    content=module_text,
                    imports=parsed.imports,
                )
            )

    # Annotated comments become their own small chunks — they carry "why".
    for comment in parsed.comments:
        context = "\n".join(lines[comment.start_line - 1 : comment.end_line])
        chunks.append(
            Chunk(
                chunk_id=_chunk_id(parsed.file_path, f"comment@{comment.start_line}", context),
                file_path=parsed.file_path,
                language=parsed.language,
                kind="comment",
                symbol=comment.name,
                start_line=comment.start_line,
                end_line=comment.end_line,
                content=context,
                tags=comment.tags,
            )
        )

    # Merge runs of tiny chunks from the same file/kind to avoid waste.
    return _merge_tiny(chunks)


def _merge_tiny(chunks: list[Chunk]) -> list[Chunk]:
    merged: list[Chunk] = []
    for chunk in chunks:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.kind == chunk.kind
            and previous.kind in {"function", "method"}
            and previous.token_estimate < MIN_CHUNK_TOKENS
            and chunk.token_estimate < MIN_CHUNK_TOKENS
            and previous.end_line + 3 >= chunk.start_line
        ):
            content = previous.content + "\n\n" + chunk.content
            merged[-1] = Chunk(
                chunk_id=_chunk_id(previous.file_path, f"{previous.symbol}+{chunk.symbol}", content),
                file_path=previous.file_path,
                language=previous.language,
                kind=previous.kind,
                symbol=f"{previous.symbol}, {chunk.symbol}",
                start_line=previous.start_line,
                end_line=chunk.end_line,
                content=content,
                imports=previous.imports,
            )
        else:
            merged.append(chunk)
    return merged
