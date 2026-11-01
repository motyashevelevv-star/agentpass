"""Pass sandbox credentials through stdin, not command arguments or logs."""
import json
import os
import subprocess
from pathlib import Path
from dotenv import dotenv_values

root=Path(__file__).resolve().parent.parent
config=dotenv_values(root/'.env')
password=os.environ.get('DEMO_PASSWORD') or config.get('DEMO_PASSWORD')
if not password:
    raise SystemExit('DEMO_PASSWORD is required for the sandbox verifier')
result=subprocess.run(['node',str(root/'infra/verify-pilot-sdk.mjs')],
    input=json.dumps({'email':'demo@agentpass.local','password':password}),text=True,cwd=root)
raise SystemExit(result.returncode)
