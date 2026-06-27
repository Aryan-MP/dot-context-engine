"""AST-based code parser.

Extracts semantic units from source files:
- function/method signatures with docstrings
- class definitions and their hierarchy
- import dependencies
- TODO/FIXME/NOTE/HACK comments with surrounding context
- inline "why" comments that explain decisions

Parsing strategy, in order of preference:
1. Python's builtin ``ast`` for .py files (always available, exact).
2. Tree-sitter (via tree-sitter-language-pack) for other languages,
   when the optional dependency is installed.
3. A regex heuristic fallback that still finds functions, classes,
   imports, and annotated comments in most C-like languages.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

COMMENT_TAGS = re.compile(r"\b(TODO|FIXME|HACK|NOTE|XXX|WHY|DECISION)\b[:\s]", re.IGNORECASE)
DECISION_PHRASES = re.compile(
    r"(decided to|chose .+ over|because|workaround for|instead of|trade-?off|intentionally)",
    re.IGNORECASE,
)

LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "tsx", ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "c_sharp", ".swift": "swift", ".scala": "scala", ".sh": "bash",
    ".sql": "sql", ".md": "markdown", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
}


@dataclass
class ParsedSymbol:
    """A semantic unit extracted from source — function, class, comment block."""

    kind: str  # "function" | "class" | "method" | "import" | "comment" | "module"
    name: str
    file_path: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    signature: str = ""
    docstring: str = ""
    parent: str = ""  # enclosing class for methods
    bases: list[str] = field(default_factory=list)  # class hierarchy
    tags: list[str] = field(default_factory=list)  # TODO/FIXME/DECISION markers


@dataclass
class ParsedFile:
    file_path: str
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # modules this file depends on
    comments: list[ParsedSymbol] = field(default_factory=list)  # annotated/why comments


class CodeParser:
    """Parses source files into :class:`ParsedFile` structures."""

    def __init__(self) -> None:
        self._ts_parsers: dict[str, object] = {}

    def parse(self, path: Path, source: str | None = None) -> ParsedFile:
        language = LANGUAGE_BY_EXTENSION.get(path.suffix.lower(), "text")
        if source is None:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("cannot read %s: %s", path, exc)
                return ParsedFile(file_path=str(path), language=language)

        if language == "python":
            parsed = self._parse_python(path, source)
        else:
            parsed = self._parse_tree_sitter(path, source, language) or self._parse_heuristic(
                path, source, language
            )
        parsed.comments = _extract_annotated_comments(str(path), source, language)
        return parsed

    # ------------------------------------------------------------------
    # Python via builtin ast
    # ------------------------------------------------------------------
    def _parse_python(self, path: Path, source: str) -> ParsedFile:
        result = ParsedFile(file_path=str(path), language="python")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.debug("syntax error in %s: %s", path, exc)
            return result

        lines = source.splitlines()

        def signature_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
            line = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            return line.rstrip(":")

        def visit(node: ast.AST, parent: str = "") -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    if isinstance(child, ast.Import):
                        result.imports.extend(alias.name for alias in child.names)
                    elif child.module:
                        result.imports.append(child.module)
                elif isinstance(child, ast.ClassDef):
                    bases = [ast.unparse(b) for b in child.bases]
                    result.symbols.append(
                        ParsedSymbol(
                            kind="class",
                            name=child.name,
                            file_path=str(path),
                            start_line=child.lineno,
                            end_line=child.end_lineno or child.lineno,
                            signature=f"class {child.name}({', '.join(bases)})" if bases else f"class {child.name}",
                            docstring=ast.get_docstring(child) or "",
                            bases=bases,
                        )
                    )
                    visit(child, parent=child.name)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result.symbols.append(
                        ParsedSymbol(
                            kind="method" if parent else "function",
                            name=f"{parent}.{child.name}" if parent else child.name,
                            file_path=str(path),
                            start_line=child.lineno,
                            end_line=child.end_lineno or child.lineno,
                            signature=signature_of(child),
                            docstring=ast.get_docstring(child) or "",
                            parent=parent,
                        )
                    )
                    visit(child, parent=parent)
                else:
                    visit(child, parent=parent)

        visit(tree)
        return result

    # ------------------------------------------------------------------
    # Tree-sitter for other languages (optional dependency)
    # ------------------------------------------------------------------
    def _parse_tree_sitter(self, path: Path, source: str, language: str) -> ParsedFile | None:
        try:
            from tree_sitter_language_pack import get_parser  # type: ignore[import-not-found]
        except ImportError:
            return None
        try:
            parser = self._ts_parsers.get(language)
            if parser is None:
                parser = get_parser(language)
                self._ts_parsers[language] = parser
            tree = parser.parse(source.encode("utf-8"))  # type: ignore[attr-defined]
        except Exception:
            return None

        result = ParsedFile(file_path=str(path), language=language)
        function_types = {
            "function_declaration", "function_definition", "method_definition",
            "method_declaration", "function_item", "arrow_function", "func_literal",
        }
        class_types = {
            "class_declaration", "class_definition", "class_specifier",
            "struct_item", "impl_item", "interface_declaration", "trait_item",
        }
        import_types = {"import_statement", "import_declaration", "use_declaration", "import_from_statement"}

        source_bytes = source.encode("utf-8")

        def text_of(node) -> str:  # noqa: ANN001
            return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

        def name_of(node) -> str:  # noqa: ANN001
            for fname in ("name", "declarator"):
                child = node.child_by_field_name(fname)
                if child is not None:
                    return text_of(child).split("(")[0].strip()
            return "<anonymous>"

        def walk(node, parent: str = "") -> None:  # noqa: ANN001
            for child in node.children:
                if child.type in import_types:
                    result.imports.append(text_of(child).strip())
                elif child.type in class_types:
                    name = name_of(child)
                    result.symbols.append(
                        ParsedSymbol(
                            kind="class", name=name, file_path=str(path),
                            start_line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            signature=text_of(child).splitlines()[0].strip() if text_of(child) else name,
                        )
                    )
                    walk(child, parent=name)
                elif child.type in function_types:
                    name = name_of(child)
                    result.symbols.append(
                        ParsedSymbol(
                            kind="method" if parent else "function",
                            name=f"{parent}.{name}" if parent else name,
                            file_path=str(path),
                            start_line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            signature=text_of(child).splitlines()[0].strip() if text_of(child) else name,
                            parent=parent,
                        )
                    )
                    walk(child, parent=parent)
                else:
                    walk(child, parent=parent)

        walk(tree.root_node)
        return result

    # ------------------------------------------------------------------
    # Regex heuristic fallback
    # ------------------------------------------------------------------
    _FUNC_RE = re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:public|private|protected|static|async|func|fn|def|function)\s+"
        r"[*\s]*([A-Za-z_$][\w$]*)\s*[(<]",
        re.MULTILINE,
    )
    _CLASS_RE = re.compile(
        r"^\s*(?:export\s+)?(?:public\s+|abstract\s+)?(?:class|struct|interface|trait|enum)\s+([A-Za-z_]\w*)",
        re.MULTILINE,
    )
    _IMPORT_RE = re.compile(
        r"^\s*(?:import\s+.+?from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]|"
        r"#include\s+[<\"]([^>\"]+)[>\"]|use\s+([\w:]+)|require\(['\"]([^'\"]+)['\"]\))",
        re.MULTILINE,
    )

    def _parse_heuristic(self, path: Path, source: str, language: str) -> ParsedFile:
        result = ParsedFile(file_path=str(path), language=language)
        lines = source.splitlines()
        for match in self._CLASS_RE.finditer(source):
            line_no = source.count("\n", 0, match.start()) + 1
            result.symbols.append(
                ParsedSymbol(
                    kind="class", name=match.group(1), file_path=str(path),
                    start_line=line_no, end_line=_block_end(lines, line_no),
                    signature=lines[line_no - 1].strip(),
                )
            )
        for match in self._FUNC_RE.finditer(source):
            line_no = source.count("\n", 0, match.start()) + 1
            result.symbols.append(
                ParsedSymbol(
                    kind="function", name=match.group(1), file_path=str(path),
                    start_line=line_no, end_line=_block_end(lines, line_no),
                    signature=lines[line_no - 1].strip(),
                )
            )
        for match in self._IMPORT_RE.finditer(source):
            module = next((g for g in match.groups() if g), None)
            if module:
                result.imports.append(module)
        return result


def _block_end(lines: list[str], start_line: int, max_span: int = 200) -> int:
    """Estimate where a brace/indent block ends, for the heuristic parser."""
    depth = 0
    opened = False
    for offset, line in enumerate(lines[start_line - 1 : start_line - 1 + max_span]):
        depth += line.count("{") - line.count("}")
        if "{" in line:
            opened = True
        if opened and depth <= 0:
            return start_line + offset
    return min(start_line + 20, len(lines))


def _extract_annotated_comments(file_path: str, source: str, language: str) -> list[ParsedSymbol]:
    """Find TODO/FIXME/NOTE comments and 'why' comments explaining decisions."""
    comments: list[ParsedSymbol] = []
    lines = source.splitlines()
    comment_prefix = "#" if language in {"python", "bash", "yaml", "toml"} else "//"

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Comment lines, docstring lines that lead with a tag (NOTE: …),
        # and trailing comments all count.
        is_comment = stripped.startswith((comment_prefix, "/*", "*", "<!--"))
        if not is_comment and not COMMENT_TAGS.match(stripped):
            marker = comment_prefix in line
            if not marker:
                continue
            stripped = line.split(comment_prefix, 1)[1].strip()

        tag_match = COMMENT_TAGS.search(stripped)
        is_decision = bool(DECISION_PHRASES.search(stripped))
        if not tag_match and not is_decision:
            continue

        # capture a little surrounding context so the comment is meaningful
        context_start = max(1, index - 1)
        context_end = min(len(lines), index + 2)
        tags = [tag_match.group(1).upper()] if tag_match else []
        if is_decision:
            tags.append("DECISION")
        comments.append(
            ParsedSymbol(
                kind="comment",
                name=stripped[:80],
                file_path=file_path,
                start_line=context_start,
                end_line=context_end,
                signature=stripped,
                tags=tags,
            )
        )
    return comments
