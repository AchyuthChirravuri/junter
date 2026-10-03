// Dependency-free DOM/transport harness: exercises the real public client.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.style = {}; this._text = ''; this.classList = { add() {}, remove() {} }; }
  set innerHTML(v) { this.children = []; this._text = v; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(v) { this._text = String(v); this.children = []; }
  setAttribute(k,v) { this.attrs[k] = String(v); if (k === 'class') this.className = v; }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  removeChild(c) { this.children = this.children.filter(x => x !== c); }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  addEventListener(k,fn) { this.listeners[k] = fn; }
  focus() {}
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  querySelectorAll(s) { const all = []; function visit(n) { if (s[0] === '.' ? String(n.className || '').split(' ').includes(s.slice(1)) : n.tagName === s) all.push(n); (n.children || []).forEach(visit); } this.children.forEach(visit); return all; }
  click() { if (!this.disabled && this.listeners.click) this.listeners.click({ stopPropagation() {} }); }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function boot(useNumericFixture = true) {
  const body = new Element('body');
  const mount = new Element('main'); const screen = new Element('section'); screen.appendChild(mount);
  screen.querySelector = () => mount;
  const requests = [];
  const context = { console: { warn() {}, log() {} }, Promise, Date, Math, crypto: require('node:crypto').webcrypto,
    setTimeout(fn,ms) { if (ms < 100) return setTimeout(fn,ms); return 0; }, clearTimeout,
    window: { location: { hash: '#/pipeline' }, addEventListener(event, fn) { this[event] = fn; } },
    document: { readyState: 'complete', body, addEventListener() {}, querySelectorAll() { return []; },
      getElementById(id) { if (id === 'screen-pipeline' || id === 'screen-role' || id === 'screen-focus') return screen;
        return body.children.find(c => c.id === id) || null; },
      createElement: tag => new Element(tag), createTextNode: t => ({ textContent: t }) },
    fetch(url, options) {
      if (url === '/api/data') return Promise.reject(new Error('offline seed'));
      let resolve, reject; const promise = new Promise((a,b) => { resolve = a; reject = b; });
      requests.push({ url, options, body: JSON.parse(options.body), resolve, reject }); return promise;
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../app.js'), 'utf8'), context);
  await tick();
  const J = context.window.__junter;
  // Fixtures explicitly own integer IDs; this is NOT production rNN mapping.
  if (useNumericFixture) { J.state.roles.forEach((r,i) => { r.id = i + 1; }); context.window.hashchange(); }
  function role(id='r01') {
    const fixtureId = useNumericFixture && /^r\d+$/.test(id) ? String(Number(id.slice(1))) : id;
    return J.state.roles.find(r => String(r.id) === fixtureId);
  }
  function respond(index, status, payload) { requests[index].resolve({ status, json: () => Promise.resolve(payload) }); }
  function toast() { return body.textContent; }
  return { J, role, requests, respond, toast, mount, context };
}
const tests = {
  async visual_success() {
    const h = await boot(); const before = h.role();
    const button = h.mount.querySelectorAll('button').find(n => n.attrs['data-role-id'] === '1' && n.attrs['data-action'] === 'mark_interested');
    assert.ok(button); button.click();
    assert.equal(h.role().routed, 'int');
    const cols = h.mount.querySelectorAll('.pipeline__col');
    const interested = cols.find(c => c.textContent.includes('Interested'));
    assert.ok(interested.textContent.includes(before.role), 'card moved before network resolves');
    await tick(); assert.equal(h.requests.length, 1);
    assert.ok(before.role);
    h.respond(0, 200, { ok: true, role: { ...h.role(), status: 'pinged', routed: 'int', status_date: '2026-10-03', notes: 'authoritative', fit_score: 8.2 } });
    await tick(); assert.equal(h.role().angle, 'authoritative'); assert.equal(h.role().status_date, '2026-10-03');
    assert.equal(h.role().fit, 8.2);
    const reconciled = h.mount.querySelectorAll('.pipeline__col').find(c => c.textContent.includes('Interested'));
    assert.ok(reconciled.textContent.includes(before.role), 'exporter pinged/int stays in Interested');
  },
  async failures() {
    for (const status of [400,404,401,429,500,503]) {
      const h = await boot(); const prev = h.role(); const p = h.J.actOnRole('mark_interested', prev, {});
      assert.equal(h.role().routed, 'int'); await tick();
      h.respond(0,status,{ ok:false, error: { code: 'evil secret https://private.invalid' } });
      const result = await p;
      assert.equal(result.ok,false); assert.equal(h.role(),prev);
      assert.match(h.toast(),/Reverted this change/); assert.ok(!h.toast().includes('private.invalid'));
    }
  },
  async network_retry() {
    const h = await boot(); const p = h.J.actOnRole('mark_interested',h.role(),{}); await tick();
    h.requests[0].reject(new Error('private stack')); const failed = await p;
    assert.equal(h.role().status,'pinged'); assert.match(h.toast(),/Retry/);
    const retry = h.context.document.getElementById('toast-host').querySelector('button');
    assert.ok(retry); retry.click(); await tick();
    assert.equal(h.requests[0].options.body,h.requests[1].options.body);
    h.respond(1,200,{ok:true,role:{...h.role(),status:'interested',routed:'int'}}); await tick();
    assert.equal(h.role().routed,'int'); assert.equal(typeof failed.retry,'function');
  },
  async duplicate() {
    const h = await boot(); const r = h.role(); const p = h.J.actOnRole('mark_interested',r,{});
    const duplicate = h.J.actOnRole('mark_interested',r,{}); assert.equal(p,duplicate); await tick();
    assert.equal(h.requests.length,1); h.respond(0,200,{ok:true,role:h.role()}); await p;
  },
  async different_roles() {
    const h = await boot(); const first = h.J.actOnRole('mark_interested',h.role(),{});
    const second = h.J.actOnRole('mark_packaged',h.role('r02'),{}); await tick();
    assert.equal(h.requests.length,2);
    h.respond(1,200,{ok:true,role:h.role('r02')}); await second;
    h.respond(0,500,{ok:false}); await first;
    assert.equal(h.role().status,'pinged'); assert.equal(h.role('r02').status,'packaged');
  },
  async same_role_queue() {
    for (const status of [200,500,409]) {
      const h = await boot(); const r = h.role();
      const first = h.J.actOnRole('mark_interested',r,{});
      const second = h.J.actOnRole('mark_packaged',r,{});
      assert.equal(h.role().status,'packaged'); await tick(); assert.equal(h.requests.length,1);
      h.respond(0,status,{ok:status===200,role:{...r,status:status===409?'blocked':'interested',routed:status===409?'':'int'}});
      await first; await tick();
      assert.equal(h.role().status,'packaged', 'old response/rollback cannot overwrite newer overlay');
      assert.equal(h.requests.length,2);
      h.respond(1,200,{ok:true,role:{...r,status:'packaged',routed:'pkg'}}); await second;
      assert.equal(h.role().status,'packaged');
    }
  },
  async conflict() {
    const h = await boot(); const r = h.role(); const p = h.J.actOnRole('mark_interested',r,{}); await tick();
    h.respond(0,409,{ok:false,role:{...r,status:'blocked',routed:'',notes:'server note'},error:{code:'conflict'}});
    const result = await p; assert.equal(result.reconciled,true); assert.equal(h.role().status,'blocked');
    assert.equal(h.role().angle,'server note'); assert.equal(h.toast(),'');
  },
  async supported_controls() {
    const h = await boot(); const notes = h.J.postStatusAction('edit_notes',1,{notes:'new note'});
    assert.equal(h.role().angle,'new note'); await tick(); assert.equal(h.requests[0].body.payload.notes,'new note');
    h.respond(0,200,{ok:true,role:h.role()}); await notes;
    const gate = h.J.postStatusAction('complete_gate',1,{gate:'backgrounder_read'});
    assert.equal(h.role().gates.backgrounder_read,true); assert.equal(h.role().gates.gate,undefined);
    await tick(); h.respond(1,200,{ok:true,role:h.role()}); await gate;
    h.context.window.location.hash = '#/focus';
    const interest = h.J.actOnRole('mark_interested',h.role(),{}); await tick();
    h.respond(2,200,{ok:true,role:h.role()}); await interest;
    const focusCard = h.mount.querySelectorAll('.focus-card').find(n => n.textContent.includes(h.role().role));
    const resume = focusCard.querySelectorAll('button').find(n => n.attrs['aria-label'] === 'Complete Resume drafted');
    assert.ok(resume); resume.click(); assert.equal(h.role().gates.resume_drafted,true); await tick();
    assert.equal(h.requests[3].body.payload.gate,'resume_drafted');
    h.respond(3,200,{ok:true,role:h.role()}); await tick();
  },
  async sandbox_uuid() {
    const h = await boot(); h.context.window.location.search = '?mode=personal&token=secret';
    h.J.state.roles[0] = {...h.role(), id:'17'};
    const p = h.J.actOnRole('mark_interested',h.role('17'),{}); await tick(); const req=h.requests[0];
    assert.equal(req.url,'/api/action?mode=sandbox'); assert.equal(req.body.source,'ui'); assert.equal(req.body.role_id,17);
    assert.match(req.body.idempotency_key,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    assert.deepEqual(Object.keys(req.options.headers).sort(),['Accept','Content-Type']);
    h.respond(0,200,{ok:true,role:h.role('17')}); await p;
  },
  async unsafe_response() {
    const h=await boot(); const before=h.role(); const p=h.J.actOnRole('mark_interested',before,{}); await tick();
    h.respond(0,200,{ok:true,role:{...before,url:'https://private.invalid',notes:'person@private.invalid'}});
    assert.equal((await p).ok,false); assert.equal(h.role(),before); assert.ok(!h.toast().includes('private.invalid'));
  },
  async all_supported_actions() {
    const h = await boot(); let index = 0;
    for (const action of ['mark_interested','mark_packaged','mark_submitted','mark_blocked','view']) {
      const p = h.J.postStatusAction(action,1,{}); await tick();
      assert.equal(h.requests[index].body.action,action);
      assert.equal(JSON.stringify(h.requests[index].body.payload),'{}');
      h.respond(index++,200,{ok:true,role:h.role()}); await p;
    }
    h.context.window.location.hash='#/role/1/backgrounder'; h.context.window.hashchange();
    const previous = h.role();
    const edit = h.mount.querySelector('.backgrounder__edit-notes-btn'); assert.ok(edit); edit.click();
    const textarea = h.mount.querySelector('textarea'); assert.ok(textarea); textarea.value='draft';
    const save = h.mount.querySelectorAll('button').find(b => b.textContent === 'Save'); assert.ok(save); save.click();
    assert.equal(h.role().company_research.application_strategy.angle,'draft'); await tick();
    assert.equal(h.requests[index].body.payload.notes,'draft');
    h.respond(index++,400,{ok:false,error:'schema validation failed',error_code:'validation_failed'}); await tick();
    assert.equal(h.role().company_research.application_strategy.angle,previous.company_research.application_strategy.angle);
    assert.match(h.toast(),/validation_failed/);
  },
  async offline_sample() {
    const h = await boot(false); const previous = h.role();
    const result = await h.J.actOnRole('mark_interested',previous,{});
    assert.equal(result.error.code,'offline_sample'); assert.equal(h.requests.length,0);
    assert.equal(h.role(),previous); assert.match(h.toast(),/read-only/);
  },
  async expired_retry() {
    const h=await boot(); const first=h.J.actOnRole('mark_interested',h.role(),{}); await tick();
    h.requests[0].reject(new Error('offline')); const failed=await first;
    const originalNow = Date.now; const future = originalNow() + 61000;
    Date.now = () => future;
    try { assert.equal((await failed.retry()).error.code,'retry_expired'); }
    finally { Date.now = originalNow; }
    assert.equal(h.requests.length,1); assert.match(h.toast(),/Reload and review server state/);
  },
  async superseded_retry() {
    const h=await boot(); const first=h.J.actOnRole('mark_interested',h.role(),{}); await tick();
    h.requests[0].reject(new Error('offline')); const failed=await first;
    const next=h.J.actOnRole('mark_blocked',h.role(),{}); await tick(); h.respond(1,200,{ok:true,role:h.role()}); await next;
    assert.equal((await failed.retry()).error.code,'superseded'); assert.equal(h.requests.length,2);
  }
};
(async () => {
  const name=process.argv[2]; assert.ok(tests[name], 'unknown test'); await tests[name]();
  process.stdout.write(JSON.stringify({test:name,ok:true})+'\n');
})().catch(error => { process.stderr.write(error.stack+'\n'); process.exitCode=1; });
