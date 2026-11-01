export interface User {
  id: string;
  name: string;
  email: string;
  platform_admin: boolean;
  mfa_enabled: boolean;
}
export interface Organization {
  id: string;
  name: string;
  role: string;
  status: string;
}
export interface Me {
  user: User;
  organization_id: string;
  role: string;
  organizations: Organization[];
  environment: string;
}
export interface Agent {
  id: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
  project_id: string | null;
}
export interface Usage {
  daily: number;
  weekly: number;
  monthly: number;
}
export interface Mandate {
  id: string;
  name: string;
  agent_id: string;
  agent_name: string;
  currency: string;
  status: string;
  per_transaction: number;
  daily_limit: number;
  weekly_limit: number;
  monthly_limit: number;
  approval_threshold: number;
  categories: string[];
  merchant_allowlist: string[];
  merchant_denylist: string[];
  valid_from: string;
  valid_until: string;
  version: number;
  usage: Usage;
  created_at: string;
}
export interface Reason {
  code: string;
  message: string;
}
export interface Reservation {
  id: string;
  status: string;
  expires_at: string;
  amount: number;
}
export interface Approval {
  id: string;
  intent_id: string;
  status: string;
  expires_at: string;
  resolved_at: string | null;
  created_at: string;
  intent: Intent;
}
export interface Transaction {
  id: string;
  receipt: string;
  amount: number;
  currency: string;
  status: string;
  created_at: string;
}
export interface Intent {
  id: string;
  agent_id: string;
  mandate_id: string;
  merchant: string;
  merchant_id: string | null;
  order_id: string | null;
  execution: PaymentExecution | null;
  category: string;
  amount: number;
  currency: string;
  description: string;
  decision: "APPROVE" | "ASK" | "DENY";
  status: string;
  reasons: Reason[];
  evaluated_version: number;
  created_at: string;
  approval: Approval | null;
  reservation: Reservation | null;
  transaction: Transaction | null;
  structured_metadata: Record<string, unknown>;
}
export interface PaymentExecution {
  id: string;
  provider: 'local_simulator' | 'yookassa_sandbox';
  status: string;
  provider_status: string | null;
  provider_payment_id: string | null;
  confirmation_url: string | null;
  last_error: string | null;
  attempts: number;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface Analytics {
  total: number;
  decisions: Record<string, number>;
  initial_decisions: Record<string, number>;
  evaluations: number;
  active_agents: number;
  spent: number;
  pending: number;
  reserved: number;
  categories: { name: string; amount: number }[];
  decline_reasons: { name: string; count: number }[];
  agent_activity: { name: string; count: number }[];
  trend: { date: string; amount: number }[];
  budgets: {
    id: string;
    name: string;
    currency: string;
    daily_limit: number;
    weekly_limit: number;
    monthly_limit: number;
    usage: Usage;
  }[];
}
export interface ApiKey {
  id: string;
  name: string;
  agent_id: string;
  prefix: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  scopes: string[];
  secret?: string;
}
export interface Webhook {
  id: string;
  name: string;
  url: string;
  active: boolean;
  secret?: string;
}
export interface Delivery {
  id: string;
  endpoint_id: string;
  status: string;
  attempts: number;
  response_status: number | null;
  last_error: string | null;
  created_at: string;
}
export interface Audit {
  id: string;
  actor_id: string;
  action: string;
  resource_id: string;
  created_at: string;
  details: Record<string, unknown>;
}
export interface RequestLog {
  id: string;
  request_id: string;
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  created_at: string;
}
export interface Product {
  id: string;
  name: string;
  amount: number;
  currency: string;
  merchant: string;
  category: string;
  details: string;
  color: string;
}
export interface ConsoleResult {
  product: Product;
  interpreted_budget: number;
  parser: string;
  intent: Intent;
}
