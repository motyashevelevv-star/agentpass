"""Live API + built SDK + HTTP webhook verification. Creates isolated demo resources, no SQL edits."""

import argparse, json, os, subprocess, time
from pathlib import Path
import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:8000")
args = parser.parse_args()
configuration = dotenv_values(root / ".env")
password = os.environ.get("DEMO_PASSWORD") or configuration.get("DEMO_PASSWORD")
if not password:
    raise RuntimeError("DEMO_PASSWORD missing")
with httpx.Client(base_url=args.base_url, timeout=15) as client:
    response = client.post(
        "/v1/auth/login", json={"email": "demo@agentpass.local", "password": password}
    )
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies["ap_csrf"]

    def post(path, body=None):
        response = client.post(path, json=body)
        response.raise_for_status()
        return response.json()

    demo = post("/v1/sandbox/demo")
    key = post(
        "/v1/developer/api-keys",
        {"name": "SDK Verification", "agent_id": demo["agent"]["id"]},
    )
    options = {
        "base_url": args.base_url,
        "api_key": key["secret"],
        "agent_id": demo["agent"]["id"],
        "mandate_id": demo["mandate"]["id"],
    }

    def sdk(extra):
        result = subprocess.run(
            ["node", str(root / "infra/verify-sdk.mjs")],
            input=json.dumps({**options, **extra}),
            text=True,
            capture_output=True,
            check=True,
            cwd=root,
        )
        return json.loads(result.stdout)

    initial = sdk({})
    resolved = post(
        "/v1/approvals/" + initial["approval_id"] + "/resolve", {"action": "approve"}
    )
    assert resolved["decision"] == "APPROVE"
    approved = sdk({"mode": "approved", "intent_id": initial["intent_id"]})
    config = client.get("/v1/webhooks/config").json()
    hook = post(
        "/v1/webhooks",
        {"name": "Local signature receiver", "url": config["sandbox_receiver_url"]},
    )
    delivery = post("/v1/webhooks/" + hook["id"] + "/test")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        deliveries = client.get("/v1/webhooks/deliveries").json()["items"]
        row = next((d for d in deliveries if d["id"] == delivery["id"]), None)
        if row and row["status"] == "delivered":
            break
        time.sleep(1)
    assert row and row["status"] == "delivered", "Webhook was not delivered"
    receipts = client.get("/v1/webhooks/receipts").json()["items"]
    assert any(r["id"] == delivery["id"] for r in receipts)
    client.delete("/v1/developer/api-keys/" + key["id"]).raise_for_status()
    revoked = sdk({"mode": "revoked"})
    print(
        json.dumps(
            {
                "passed": initial["passed"]
                + approved["passed"]
                + revoked["passed"]
                + ["real-http-webhook", "verified-signature"],
                "base_url": args.base_url,
            },
            ensure_ascii=False,
        )
    )
