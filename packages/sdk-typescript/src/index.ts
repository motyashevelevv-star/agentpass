/** Typed sandbox SDK. Authorization does not execute a payment. Amounts are minor units. */
export type Decision = "APPROVE" | "ASK" | "DENY";
export interface IntentInput {
  agent_id: string;
  mandate_id: string;
  merchant: string;
  merchant_id?: string | null;
  order_id?: string | null;
  category: string;
  amount: number;
  currency: string;
  description: string;
  idempotency_key: string;
  timestamp: string;
  structured_metadata: Record<string, unknown>;
}
export interface Reason {
  code: string;
  message: string;
}
export interface Intent extends IntentInput {
  id: string;
  decision: Decision;
  status:
    "authorized" | "pending" | "denied" | "completed" | "cancelled" | "expired" | "executing" | "payment_pending" | "payment_unknown";
  decision_kind: "APPROVE" | "ASK_USER" | "DENY";
  execution: Execution | null;
  reasons: Reason[];
  evaluated_version: number;
  approval: { id: string; status: string; expires_at: string } | null;
  reservation: {
    id: string;
    status: string;
    expires_at: string;
    amount: number;
  } | null;
  transaction: {
    id: string;
    receipt: string;
    status: "simulated" | "external_test";
    amount: number;
    currency: string;
  } | null;
}
export interface Agent {
  id: string;
  name: string;
  status: string;
  description: string;
}
export interface Mandate {
  id: string;
  agent_id: string;
  currency: string;
  status: string;
  categories: string[];
  per_transaction: number;
  daily_limit: number;
  weekly_limit: number;
  monthly_limit: number;
  approval_threshold: number;
  version: number;
  valid_from: string;
  valid_until: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export type Provider = "local_simulator" | "yookassa_sandbox";
export interface ExecutionGrant {
  id: string; intent_id: string; provider: Provider;
  expires_at: string; grant_token: string; single_use: true;
}
export interface Execution {
  id: string; intent_id: string; provider: Provider;
  status: "queued" | "dispatching" | "pending" | "unknown" | "succeeded" | "cancelled" | "failed" | "refunded";
  provider_payment_id: string | null; provider_status: string | null;
  confirmation_url: string | null; last_error: string | null; attempts: number;
}
export interface MandateInput {
  agent_id: string; name: string; currency: "RUB"; categories: string[];
  merchant_allowlist?: string[]; merchant_denylist?: string[];
  per_transaction: number; daily_limit: number; weekly_limit: number;
  monthly_limit: number; approval_threshold: number;
  valid_from: string; valid_until: string;
}
export interface Key {
  id: string; name: string; scopes: string[]; expires_at: string; secret?: string;
}
export interface AuditEvent {
  id: string; action: string; resource_id: string; created_at: string;
  details: Record<string, unknown>;
}
type Options = {baseUrl:string;fetch?:typeof fetch;timeoutMs?:number;organizationId?:string} & (
  {apiKey:string;session?:never} |
  {apiKey?:never;session:{cookie:string;csrfToken:string;mfaCode?:()=>Promise<string>}}
);
export class AgentPassError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
    this.name = "AgentPassError";
  }
}
export class AgentPass {
  private baseUrl: string;
  constructor(
    private options: Options,
  ) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
  }
  private async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
    stepUp = false,
  ): Promise<T> {
    const res = await (this.options.fetch || fetch)(
      `${this.baseUrl}/v1${path}`,
      {
        method,
        headers: {
          ...(this.options.apiKey ? {Authorization: `Bearer ${this.options.apiKey}`} : {
            Cookie: this.options.session!.cookie,
            "X-CSRF-Token": this.options.session!.csrfToken,
          }),
          ...(this.options.organizationId ? {"X-Organization-ID":this.options.organizationId} : {}),
          ...(stepUp && this.options.session?.mfaCode ? {"X-MFA-Code":await this.options.session.mfaCode()} : {}),
          "Content-Type": "application/json",
          ...(body && typeof body === "object" && "idempotency_key" in body
            ? { "Idempotency-Key": String(body.idempotency_key) }
            : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
        signal: AbortSignal.timeout(this.options.timeoutMs || 10000),
      },
    );
    const value = await res.json();
    if (!res.ok)
      throw new AgentPassError(
        res.status,
        value.error?.code || "REQUEST_FAILED",
        value.error?.message || "Request failed",
        value.error?.request_id,
      );
    return value as T;
  }
  createIntent(input: IntentInput) {
    return this.request<Intent>("/intents", "POST", input);
  }
  getIntent(id: string) {
    return this.request<Intent>(`/intents/${encodeURIComponent(id)}`);
  }
  listIntents(
    options: { limit?: number; offset?: number; decision?: Decision } = {},
  ) {
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(options)) query.set(k, String(v));
    return this.request<Page<Intent>>(`/intents?${query}`);
  }
  executeIntent(id: string) {
    return this.request<Intent>(
      `/intents/${encodeURIComponent(id)}/execute`,
      "POST",
    );
  }
  cancelIntent(id: string) {
    return this.request<Intent>(
      `/intents/${encodeURIComponent(id)}/cancel`,
      "POST",
    );
  }
  listAgents() {
    return this.request<Page<Agent>>("/agents");
  }
  listMandates() {
    return this.request<Page<Mandate>>("/mandates");
  }
  requestExecutionGrant(id:string, provider:Provider="local_simulator") {
    return this.request<ExecutionGrant>(`/intents/${encodeURIComponent(id)}/execution-grant`,"POST",{provider});
  }
  submitExecution(grantToken:string) {
    return this.request<Execution>("/executions","POST",{grant_token:grantToken});
  }
  getExecution(id:string) {
    return this.request<Execution>(`/executions/${encodeURIComponent(id)}`);
  }
  reconcileExecution(id:string) {
    return this.request<Execution>(`/executions/${encodeURIComponent(id)}/reconcile`,"POST");
  }
  /** Control plane requires an authenticated owner/developer session, never an agent key. */
  registerAgent(input:{name:string;description?:string;project_id?:string}) {
    return this.request<Agent>("/agents","POST",input);
  }
  createMandate(input:MandateInput) {
    return this.request<Mandate>("/mandates","POST",input,true);
  }
  revokeMandate(id:string) {
    return this.request<Mandate>(`/mandates/${encodeURIComponent(id)}/revoke`,"POST");
  }
  createApiKey(input:{name:string;agent_id:string;purpose?:"agent"|"executor";expires_days?:number}) {
    return this.request<Key>("/developer/api-keys","POST",input,true);
  }
  listAuditEvents(options:{limit?:number;offset?:number}={}) {
    const query=new URLSearchParams();
    for (const [key,value] of Object.entries(options)) query.set(key,String(value));
    return this.request<Page<AuditEvent>>(`/audit-events?${query}`);
  }
  async waitForDecision(
    id: string,
    {
      signal,
      intervalMs = 2000,
      timeoutMs = 900000,
    }: { signal?: AbortSignal; intervalMs?: number; timeoutMs?: number } = {},
  ) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      signal?.throwIfAborted();
      const intent = await this.getIntent(id);
      signal?.throwIfAborted();
      if (intent.status !== "pending") return intent;
      await new Promise<void>((resolve, reject) => {
        const done = () => {
          clearTimeout(timer);
          signal?.removeEventListener("abort", abort);
          resolve();
        };
        const abort = () => {
          clearTimeout(timer);
          signal?.removeEventListener("abort", abort);
          reject(signal?.reason);
        };
        const timer = setTimeout(done, intervalMs);
        signal?.addEventListener("abort", abort, { once: true });
      });
    }
    throw new AgentPassError(
      408,
      "APPROVAL_TIMEOUT",
      "Approval wait timed out",
    );
  }
}
