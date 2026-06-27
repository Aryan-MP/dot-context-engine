from pathlib import Path

from dot.indexer.chunker import chunk_file, estimate_tokens
from dot.indexer.embedder import Embedder, cosine_similarity
from dot.indexer.parser import CodeParser


def test_python_parser_extracts_symbols(project):
    parsed = CodeParser().parse(Path(project.project_root) / "billing" / "payments.py")
    names = {symbol.name for symbol in parsed.symbols}
    assert "PaymentProcessor" in names
    assert "PaymentProcessor.authorize" in names
    assert "format_receipt" in names
    assert "json" in parsed.imports
    klass = next(s for s in parsed.symbols if s.name == "PaymentProcessor")
    assert "payment authorization" in klass.docstring.lower()


def test_parser_finds_annotated_comments(project):
    parsed = CodeParser().parse(Path(project.project_root) / "billing" / "payments.py")
    tags = {tag for comment in parsed.comments for tag in comment.tags}
    assert "TODO" in tags
    assert "DECISION" in tags  # "decided to use Decimal over float"


def test_chunker_produces_semantic_chunks(project):
    chunks = chunk_file(Path(project.project_root) / "billing" / "payments.py")
    symbols = {chunk.symbol for chunk in chunks}
    assert any("PaymentProcessor" in symbol for symbol in symbols)
    function_chunk = next(chunk for chunk in chunks if "format_receipt" in chunk.symbol)
    assert "def format_receipt" in function_chunk.content
    assert function_chunk.start_line > 0


def test_heuristic_parser_handles_typescript(tmp_path):
    source = (
        "import { api } from './api';\n\n"
        "export class UserService {\n"
        "  async getUser(id: string) {\n"
        "    return api.get(`/users/${id}`);\n"
        "  }\n"
        "}\n\n"
        "export function formatName(user) {\n"
        "  return `${user.first} ${user.last}`;\n"
        "}\n"
    )
    path = tmp_path / "service.ts"
    path.write_text(source)
    parsed = CodeParser().parse(path)
    names = {symbol.name for symbol in parsed.symbols}
    assert "UserService" in names
    assert "formatName" in names
    assert "./api" in parsed.imports


def test_embedder_is_deterministic_and_normalized():
    embedder = Embedder()
    [a1] = embedder.embed(["def authorize(amount): pass"])
    a2 = embedder.embed_one("def authorize(amount): pass")
    assert a1 == a2
    assert abs(cosine_similarity(a1, a2) - 1.0) < 1e-9


def test_embedder_similarity_orders_sensibly():
    embedder = Embedder()
    query = embedder.embed_one("payment authorize amount card")
    related = embedder.embed_one("def authorize(self, amount, card_token): ...")
    unrelated = embedder.embed_one("css stylesheet flexbox margin padding")
    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


def test_token_estimate():
    assert estimate_tokens("abcd" * 100) == 100
