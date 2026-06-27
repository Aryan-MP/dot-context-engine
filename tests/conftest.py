import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dot.config import ProjectConfig  # noqa: E402

SAMPLE_PY = '''"""Payment processing module."""
import json
from decimal import Decimal


class PaymentProcessor:
    """Handles payment authorization and capture.

    NOTE: we decided to use Decimal over float because currency math
    must be exact.
    """

    def __init__(self, gateway):
        self.gateway = gateway

    def authorize(self, amount: Decimal, card_token: str) -> str:
        """Authorize a payment, returning an auth id."""
        # TODO: add retry with exponential backoff
        response = self.gateway.post("/authorize", json={"amount": str(amount)})
        return response["auth_id"]

    def capture(self, auth_id: str) -> bool:
        """Capture a previously authorized payment."""
        return self.gateway.post("/capture", json={"auth_id": auth_id})["ok"]


def format_receipt(amount: Decimal, currency: str = "USD") -> str:
    """Render a human-readable receipt line."""
    return f"{currency} {amount:.2f}"
'''


@pytest.fixture
def project(tmp_path):
    """A tiny throwaway project with one Python file, initialized for Dot."""
    (tmp_path / "billing").mkdir()
    (tmp_path / "billing" / "payments.py").write_text(SAMPLE_PY)
    (tmp_path / "billing" / "refunds.py").write_text(
        "from billing.payments import PaymentProcessor\n\n"
        "def refund(processor, auth_id):\n"
        '    """Refund a captured payment."""\n'
        "    return processor.gateway.post('/refund', json={'auth_id': auth_id})\n"
    )
    config = ProjectConfig(project_root=str(tmp_path))
    config.save()
    return config


@pytest.fixture
def daemon(project):
    from dot.daemon import Daemon

    return Daemon(project)
