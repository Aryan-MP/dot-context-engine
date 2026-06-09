from dot.context.formatter import context_to_dict, format_context
from dot.context.ranker import file_proximity


def test_file_proximity():
    assert file_proximity("billing/payments.py", "billing/payments.py") == 1.0
    same_dir = file_proximity("billing/payments.py", "billing/refunds.py")
    far_away = file_proximity("billing/payments.py", "frontend/app/main.tsx")
    assert same_dir > far_away
    assert file_proximity(None, "anything.py") == 0.0


def test_assemble_context_end_to_end(daemon):
    daemon.full_sync()
    daemon.store.add_memory(
        "Decided to use Decimal over float for currency math", kind="decision"
    )
    context = daemon.assembler.assemble(
        "how do we authorize payments", current_file="billing/payments.py"
    )
    assert not context.is_empty
    assert context.tokens_used <= context.token_budget
    contents = "\n".join(item.chunk.content for item in context.chunks)
    assert "authorize" in contents


def test_assemble_respects_token_budget(daemon):
    daemon.full_sync()
    context = daemon.assembler.assemble("payments", token_budget=200)
    assert context.tokens_used <= 200


def test_formats(daemon):
    daemon.full_sync()
    daemon.store.add_memory("Chose Decimal over float", kind="decision")
    context = daemon.assembler.assemble("payment capture", current_file="billing/payments.py")

    claude_output = format_context(context, "claude")
    assert claude_output.startswith("<codebase_context>")
    assert "</codebase_context>" in claude_output

    copilot_output = format_context(context, "copilot")
    assert copilot_output.startswith("// Context from Dot")

    markdown_output = format_context(context, "markdown")
    assert markdown_output.startswith("## Codebase context")

    raw = context_to_dict(context)
    assert raw["tokens_used"] > 0
    assert all("score" in chunk for chunk in raw["chunks"])


def test_profiles(daemon):
    daemon.full_sync()
    quick = daemon.assembler.assemble("payments", profile="quick-assist")
    assert quick.token_budget == 2000
    deep = daemon.assembler.assemble("payments", profile="deep-dive")
    assert deep.token_budget == 8000
