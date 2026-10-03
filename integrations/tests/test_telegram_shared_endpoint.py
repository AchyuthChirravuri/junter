"""Exercise Telegram request bodies against actual JS handler with fake storage."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.telegram_actions import ActionClient

ROOT = Path(__file__).resolve().parents[2]


class SharedEndpointTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node runtime required')
    def test_telegram_batch_and_endpoint_replay_with_mock_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def collect(body):
                calls.append(body)
                return 200, {'ok': True, 'role': {'id': body['role_id']},
                             'request_id': 'collector', 'applied_at': '2026-10-02T20:00:00Z'}
            ActionClient(Path(tmp) / 'receipts.sqlite', collect).execute('int 3 5 7', 'mock-id')
            driver = """
import fs from 'node:fs';
const calls = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
globalThis.fetch = async () => { throw new Error('network forbidden in test'); };
let store = {roles: [3,5,7].map(id => ({id, status:'pinged', routed:''}))};
let writes = 0;
globalThis.__junterActionStore = async value => {
  if (value === undefined) return {value: structuredClone(store), etag:'mock'};
  store = structuredClone(value); writes++; return {ok:true};
};
const {default:handler} = await import(process.argv[3]);
const results = [];
for (const body of [...calls, calls[0]]) {
  const res = {status(s){this.code=s;return this},setHeader(){},json(b){this.body=b}};
  await handler({method:'POST',body,headers:{}},res);
  results.push({status:res.code,body:res.body});
}
process.stdout.write(JSON.stringify({results,store,writes}));
"""
            script = Path(tmp) / 'driver.mjs'
            script.write_text(driver)
            bodies = Path(tmp) / 'bodies.json'
            bodies.write_text(json.dumps(calls))
            env = os.environ.copy()
            for name in tuple(env):
                if name.startswith('JUNTER_') or name in ('VERCEL', 'EDGE_CONFIG'):
                    env.pop(name)
            env.update(JUNTER_MODE='sandbox', JUNTER_AUDIT_LOG=str(Path(tmp)/'actions.jsonl'))
            proc = subprocess.run(['node', '--no-warnings', '--loader', str(ROOT/'tests/loader.mjs'),
                                   str(script), str(bodies), (ROOT/'api/action.js').as_uri()],
                                  cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual([r['status'] for r in data['results']], [200]*4)
            self.assertEqual(data['writes'], 3)
            self.assertTrue(data['results'][-1]['body']['idempotency_replay'])
            self.assertTrue(all(r['routed'] == 'int' for r in data['store']['roles']))
            records = [json.loads(line) for line in (Path(tmp)/'actions.jsonl').read_text().splitlines()]
            responses = [r for r in records if r.get('phase') == 'response']
            self.assertEqual(len(responses), 4)
            self.assertTrue(all(r['source'] == 'telegram' for r in responses))

    def test_plugin_registers_only_on_jobs_profile(self):
        path = ROOT / 'integrations/hermes-plugin/__init__.py'
        spec = importlib.util.spec_from_file_location('junter_plugin_fixture', path)
        assert spec is not None and spec.loader is not None
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        captured = []
        ctx = SimpleNamespace(register_hook=lambda name, callback: captured.append((name, callback)))
        fake = SimpleNamespace(get_hermes_home=lambda: Path('/mock/profiles/jobs'))
        with patch.dict(sys.modules, hermes_constants=fake):
            plugin.register(ctx)
        self.assertEqual(captured[0][0], 'pre_gateway_dispatch')
        fake.get_hermes_home = lambda: Path('/mock/profiles/forge')
        with patch.dict(sys.modules, hermes_constants=fake), self.assertRaises(RuntimeError):
            plugin.register(ctx)


if __name__ == '__main__':
    unittest.main()
