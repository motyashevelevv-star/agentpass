/** Live integration verification: actual API/worker/PostgreSQL, no mock responses. */
import { AgentPass } from '../packages/sdk-typescript/dist/index.js';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const baseUrl=process.env.AGENTPASS_URL || 'http://localhost:8000';
let input='';for await (const chunk of process.stdin) input+=chunk;
const credentials=JSON.parse(input);
const login=await fetch(baseUrl+'/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
assert.equal(login.status,200);
const cookies=login.headers.getSetCookie().map(x=>x.split(';')[0]);
const csrf=decodeURIComponent(cookies.find(x=>x.startsWith('ap_csrf=')).split('=')[1]);
const cookie=cookies.join('; ');
const owner=new AgentPass({baseUrl,session:{cookie,csrfToken:csrf}});
const agent=await owner.registerAgent({name:'SDK pilot verification '+randomUUID().slice(0,8)});
const mandate=await owner.createMandate({agent_id:agent.id,name:'TEST SDK mandate',currency:'RUB',categories:['electronics'],
  per_transaction:1500000,daily_limit:2500000,weekly_limit:10000000,monthly_limit:25000000,approval_threshold:1000000,
  valid_from:new Date(Date.now()-60000).toISOString(),valid_until:new Date(Date.now()+86400000).toISOString()});
const key=await owner.createApiKey({name:'TEST agent',agent_id:agent.id});
const executorKey=await owner.createApiKey({name:'TEST executor',agent_id:agent.id,purpose:'executor'});
const ap=new AgentPass({baseUrl,apiKey:key.secret});
const executor=new AgentPass({baseUrl,apiKey:executorKey.secret});
const body=amount=>({agent_id:agent.id,mandate_id:mandate.id,merchant:'Soundstore',merchant_id:'catalog:soundstore',order_id:randomUUID(),
  category:'electronics',amount,currency:'RUB',description:'SDK TEST',idempotency_key:randomUUID(),timestamp:new Date().toISOString(),structured_metadata:{test:true}});
let passed=0;const check=(a,b)=>{assert.deepEqual(a,b);passed++;};
const payload=body(800000);
const i=await ap.createIntent(payload);check(i.decision_kind,'APPROVE');
check((await ap.createIntent(payload)).id,i.id);
const grant=await ap.requestExecutionGrant(i.id);
check((await ap.requestExecutionGrant(i.id)).grant_token,grant.grant_token);
await assert.rejects(()=>ap.submitExecution(grant.grant_token),e=>e.status===403);passed++;
const executions=await Promise.all([executor.submitExecution(grant.grant_token),executor.submitExecution(grant.grant_token)]);
check(executions[0].id,executions[1].id);
let operation=executions[0];const deadline=Date.now()+30000;
while(operation.status!=='succeeded' && Date.now()<deadline){await new Promise(r=>setTimeout(r,200));operation=await executor.getExecution(operation.id);}
check(operation.status,'succeeded');check(operation.provider,'local_simulator');
const completed=await ap.getIntent(i.id);check(completed.transaction.status,'simulated');
check((await executor.submitExecution(grant.grant_token)).id,operation.id);
const ask=await ap.createIntent(body(1200000));check(ask.decision_kind,'ASK_USER');
await assert.rejects(()=>ap.requestExecutionGrant(ask.id),e=>e.code==='NOT_AUTHORIZED');passed++;
const approved=await fetch(baseUrl+`/v1/approvals/${ask.approval.id}/resolve`,{method:'POST',headers:{Cookie:cookie,'X-CSRF-Token':csrf,'Content-Type':'application/json'},body:JSON.stringify({action:'approve'})});
check(approved.status,200);
const denied=await ap.createIntent(body(1800000));check(denied.decision_kind,'DENY');
check((await owner.listAuditEvents()).items.some(e=>e.action==='execution.queued'),true);
await owner.revokeMandate(mandate.id);
await assert.rejects(()=>ap.requestExecutionGrant(ask.id),e=>e.status===409);passed++;
const logout=await fetch(baseUrl+'/v1/auth/logout',{method:'POST',headers:{Cookie:cookie,'X-CSRF-Token':csrf}});
check(logout.status,200);
console.log(JSON.stringify({passed,kind:'live SDK grant/executor/ASK/revocation verification'}));
