// Runs independently of the AgentPass Concierge. Node 22+, built local SDK.
import { AgentPass } from '../../packages/sdk-typescript/dist/index.js';
import { randomUUID } from 'node:crypto';

const required = name => {
  if (!process.env[name]) throw new Error(`Set ${name}; see examples/external-agent/README.md`);
  return process.env[name];
};
const baseUrl=process.env.AGENTPASS_URL || 'http://localhost:8000';
const agent=new AgentPass({baseUrl,apiKey:required('AGENTPASS_API_KEY')});
// This key belongs to the trusted executor; do not distribute it to an LLM.
const executor=new AgentPass({baseUrl,apiKey:required('AGENTPASS_EXECUTOR_KEY')});
const amount=Number(process.env.AMOUNT_MINOR || 800000);
if (!Number.isSafeInteger(amount) || amount<=0) throw new Error('Invalid minor-unit amount');
let intent=await agent.createIntent({
  agent_id:required('AGENTPASS_AGENT_ID'),mandate_id:required('AGENTPASS_MANDATE_ID'),
  merchant:'Soundstore',merchant_id:'catalog:soundstore',order_id:randomUUID(),
  category:'electronics',amount,currency:'RUB',description:'External agent · TEST headphones',
  idempotency_key:randomUUID(),timestamp:new Date().toISOString(),structured_metadata:{source:'external-agent',test:true},
});
console.log(JSON.stringify({intent_id:intent.id,decision:intent.decision_kind,reasons:intent.reasons}));
if (intent.status==='pending') {
  console.log('Waiting for the owner to approve this operation in the AgentPass UI…');
  intent=await agent.waitForDecision(intent.id);
}
if (intent.status!=='authorized') process.exitCode=2;
else {
  const grant=await agent.requestExecutionGrant(intent.id);
  const operation=await executor.submitExecution(grant.grant_token);
  const deadline=Date.now()+30000;
  let current=operation;
  while (['queued','dispatching','pending'].includes(current.status) && Date.now()<deadline) {
    await new Promise(resolve=>setTimeout(resolve,500));
    current=await executor.getExecution(operation.id);
  }
  console.log(JSON.stringify({execution_id:current.id,provider:current.provider,status:current.status,error:current.last_error}));
  if (current.status!=='succeeded') process.exitCode=3;
}
