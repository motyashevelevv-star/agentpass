"""Generate checkout-local sandbox configuration. Never overwrites existing .env."""

from pathlib import Path
from secrets import token_bytes
from base64 import urlsafe_b64encode

root = Path(__file__).resolve().parent.parent
path = root / ".env"
if not path.exists():
    path.write_text(
        "ENVIRONMENT=sandbox\nDATABASE_URL=postgresql+psycopg://agentpass:local-sandbox-only@localhost:5432/agentpass\nENCRYPTION_KEY="
        + urlsafe_b64encode(token_bytes(32)).decode()
        + "\nSEED_DEMO=true\nDEMO_PASSWORD=AgentPass-demo-2026!\nWEB_ORIGIN=http://localhost:3000\nCOOKIE_SECURE=false\n"
    )
    path.chmod(0o600)
    print("Created .env (local sandbox only)")
else:
    print("Existing .env preserved")
