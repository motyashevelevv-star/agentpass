import assert from "node:assert/strict";
import {
  AgentPass,
  AgentPassError,
} from "../packages/sdk-typescript/dist/index.js";
let input = "";
for await (const chunk of process.stdin) input += chunk;
const options = JSON.parse(input);
const ap = new AgentPass({
  baseUrl: options.base_url,
  apiKey: options.api_key,
});
const intentInput = (amount) => ({
  agent_id: options.agent_id,
  mandate_id: options.mandate_id,
  merchant: "Soundstore",
  category: "electronics",
  amount,
  currency: "RUB",
  description: "SDK smoke test",
  idempotency_key: crypto.randomUUID(),
  timestamp: new Date().toISOString(),
  structured_metadata: { source: "sdk-smoke" },
});
if (options.mode === "approved") {
  const ready = await ap.waitForDecision(options.intent_id, {
    timeoutMs: 10000,
  });
  assert.equal(ready.status, "authorized");
  const executed = await ap.executeIntent(ready.id);
  assert.equal(executed.status, "completed");
  console.log(
    JSON.stringify({ passed: ["approval-poll", "approved-execution"] }),
  );
} else if (options.mode === "revoked") {
  await assert.rejects(
    ap.listIntents(),
    (e) => e instanceof AgentPassError && e.status === 401,
  );
  console.log(JSON.stringify({ passed: ["revoked-key-rejected"] }));
} else {
  const input = intentInput(800000);
  const i = await ap.createIntent(input);
  assert.equal(i.decision, "APPROVE");
  assert.equal((await ap.createIntent(input)).id, i.id);
  const one = await ap.executeIntent(i.id);
  const two = await ap.executeIntent(i.id);
  assert.equal(one.status, "completed");
  assert.equal(one.transaction.id, two.transaction.id);
  const cancelled = await ap.createIntent(intentInput(100000));
  assert.equal(
    (await ap.cancelIntent(cancelled.id)).reservation.status,
    "released",
  );
  const ask = await ap.createIntent(intentInput(1200000));
  assert.equal(ask.decision, "ASK");
  await assert.rejects(
    ap.executeIntent(ask.id),
    (e) => e instanceof AgentPassError && e.code === "NOT_AUTHORIZED",
  );
  const denied = await ap.createIntent(intentInput(1800000));
  assert.equal(denied.decision, "DENY");
  assert.equal((await ap.getIntent(i.id)).id, i.id);
  assert.equal((await ap.listAgents()).items.length, 1);
  assert.equal((await ap.listMandates()).items.length, 1);
  console.log(
    JSON.stringify({
      passed: [
        "create",
        "idempotency",
        "get",
        "list",
        "execute-once",
        "cancel-release",
        "ASK",
        "DENY",
        "agent-scope",
      ],
      approval_id: ask.approval.id,
      intent_id: ask.id,
    }),
  );
}
