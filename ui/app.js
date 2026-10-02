/* Junter — single-page app with hash routing.
   Fetches live tracker JSON from the same-origin /api/data endpoint; normalizes
   it to the screens' contract (see normalizeState / adoptApiPayload), and falls
   back to an embedded synthetic dataset when the API is unavailable, returns a
   non-2xx status, is malformed, reports an error, or carries no usable rows. */

(function () {
  'use strict';

  // ---- Inline fallback dataset (used when /api/data cannot be fetched or its
  // payload is unusable). 50 fictional roles across 5 status columns;
  // 6 of them carry deadlines so the Deadline Rail has content; company names
  // match the Junter design notes (Google and Meta appear intentionally as
  // fictional seed data).
  //
  // PII guard (defense in depth): refuse a payload that carries an actual email
  // address, a real (non-example.com) URL, or a listed operator-identifier
  // token. The synthetic seed and inline FALLBACK pass these checks.
  //
  // NOTE: the capitalized-name-count heuristic that used to live here was
  // removed. Measured against the product's real dataset it had a 100%
  // false-positive rate: job-board data legitimately contains far more than 12
  // "Capitalized Word" phrases (company names, role titles), so it refused
  // every real payload and made the live pipeline unusable. What actually
  // identifies a leak in a job-listing dataset is contact PII (emails) and live
  // links (URLs); the publisher strips personal free-text (notes, URLs,
  // reasons) before a value ever reaches the store, so the displayed fields
  // carry listing facts only. To refuse deployment-specific tokens, list them
  // in PII_IDENTIFIER_TOKENS.
  var PII_EMAIL_RE = /[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
  var PII_NON_EXAMPLE_URL_RE = /https?:\/\/(?!example\.com)[^\s"']+/;
  var PII_IDENTIFIER_TOKENS = [];
  function looks_like_pii(serialized) {
    if (PII_EMAIL_RE.test(serialized)) return 'real email';
    if (PII_NON_EXAMPLE_URL_RE.test(serialized)) return 'non-example.com URL';
    for (var i = 0; i < PII_IDENTIFIER_TOKENS.length; i++) {
      var tok = PII_IDENTIFIER_TOKENS[i];
      if (tok && serialized.indexOf(tok) !== -1) return 'operator identifier';
    }
    return null;
  }
  var FALLBACK = {
    generated_at: '2026-10-01T07:30:00-04:00',
    rubric_version: 'v2',
    roles: [
      // Pinged — 10
      { id: 'r01', company: 'Notion', role: 'Associate PM, Collaboration', fit: 7.4, source: 'HN', url: 'https://example.com/notion-r01', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-29' },
      { id: 'r02', company: 'Vercel', role: 'PM Intern, Frontend Platform', fit: 7.1, source: 'BuiltInNYC', url: 'https://example.com/vercel-r02', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-29' },
      { id: 'r03', company: 'Linear', role: 'Product Engineer, Issues', fit: 6.8, source: 'Wellfound', url: 'https://example.com/linear-r03', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-28' },
      { id: 'r04', company: 'Plaid', role: 'Associate PM, Risk', fit: 6.5, source: 'Career', url: 'https://example.com/plaid-r04', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-30' },
      { id: 'r05', company: 'Anthropic', role: 'PM, Claude Apps', fit: 8.2, source: 'HN', url: 'https://example.com/anthropic-r05', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-30' },
      { id: 'r06', company: 'Stripe', role: 'Associate PM, Payments API', fit: 8.5, source: 'BuiltInNYC', url: 'https://example.com/stripe-r06', status: 'pinged', routed: '', deadline: '2026-10-15', status_date: '2026-09-30' },
      { id: 'r07', company: 'Figma', role: 'Product Intern, Design Systems', fit: 6.9, source: 'Wellfound', url: 'https://example.com/figma-r07', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-30' },
      { id: 'r08', company: 'Airtable', role: 'PM, Platform', fit: 6.6, source: 'HN', url: 'https://example.com/airtable-r08', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-29' },
      { id: 'r09', company: 'Datadog', role: 'Product Intern, Observability', fit: 6.4, source: 'Career', url: 'https://example.com/datadog-r09', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-29' },
      { id: 'r10', company: 'MongoDB', role: 'Associate PM, Atlas', fit: 6.1, source: 'BuiltInNYC', url: 'https://example.com/mongo-r10', status: 'pinged', routed: '', deadline: '', status_date: '2026-09-30' },

      // Interested — 10 (with deadlines sorted by imminence)
      { id: 'r11', company: 'Google', role: 'APM, Cloud Platform', fit: 8.7, source: 'Career', url: 'https://example.com/google-r11', status: 'interested', routed: 'int', deadline: '2026-10-06', status_date: '2026-09-25', angle: 'Cloud + platform work fits 2024 GCP PM internship; deadline closes the window.' },
      { id: 'r12', company: 'Microsoft', role: 'PM Intern, M365 Copilot', fit: 7.9, source: 'Career', url: 'https://example.com/msft-r12', status: 'interested', routed: 'int', deadline: '2026-10-12', status_date: '2026-09-26', angle: 'AI productivity surface; aligns with Hatch conversational AI work.' },
      { id: 'r13', company: 'Slack', role: 'Associate PM, Workflow', fit: 7.6, source: 'BuiltInNYC', url: 'https://example.com/slack-r13', status: 'interested', routed: 'int', deadline: '', status_date: '2026-09-27', angle: 'Workflow automation sits in the SaaS-productivity sweet spot.' },
      { id: 'r14', company: 'Asana', role: 'PM, Goals', fit: 7.3, source: 'Wellfound', url: 'https://example.com/asana-r14', status: 'interested', routed: 'int', deadline: '2026-10-22', status_date: '2026-09-27', angle: 'Goal-tracking product is a direct fit for the Hatch goal-setting build.' },
      { id: 'r15', company: 'Atlassian', role: 'APM, Jira', fit: 7.0, source: 'Career', url: 'https://example.com/atlassian-r15', status: 'interested', routed: 'int', deadline: '', status_date: '2026-09-28', angle: 'Jira PM is a known PM-onboarding path; relevant APM rigor.' },
      { id: 'r16', company: 'Spotify', role: 'Associate PM, Discovery', fit: 7.2, source: 'HN', url: 'https://example.com/spotify-r16', status: 'interested', routed: 'int', deadline: '', status_date: '2026-09-28', angle: 'Discovery surface maps to interest-graph intuition from Spotify taste work.' },
      { id: 'r17', company: 'Google', role: 'APM, CGA', fit: 8.9, source: 'Career', url: 'https://example.com/google-r17', status: 'interested', routed: 'int', deadline: '2026-10-04', status_date: '2026-09-25', angle: 'CGA rotation = strongest match for advertiser-platform PM experience.' },
      { id: 'r18', company: 'Notion', role: 'PM, AI Features', fit: 8.3, source: 'HN', url: 'https://example.com/notion-r18', status: 'interested', routed: 'int', deadline: '', status_date: '2026-09-26', angle: 'AI feature surface is high-fit and on-trend.' },
      { id: 'r19', company: 'Mercury', role: 'PM, Banking Ops', fit: 7.5, source: 'Wellfound', url: 'https://example.com/mercury-r19', status: 'interested', routed: 'int', deadline: '', status_date: '2026-09-27', angle: 'Banking ops PM = regulated-fintech PM experience.' },
      { id: 'r20', company: 'Ramp', role: 'Associate PM, Spend', fit: 7.4, source: 'BuiltInNYC', url: 'https://example.com/ramp-r20', status: 'interested', routed: 'int', deadline: '', status_date: '2026-09-28', angle: 'Spend SaaS + NYC fintech overlap; familiar ICP.' },

      // Packaged — 10
      { id: 'r21', company: 'Robinhood', role: 'PM Intern, Investing', fit: 7.0, source: 'Wellfound', url: 'https://example.com/rh-r21', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-22', angle: 'First PM internship target; resume + cover letter drafted 09-22.' },
      { id: 'r22', company: 'Meta', role: 'Associate PM, Growth', fit: 8.1, source: 'Career', url: 'https://example.com/meta-r22', status: 'packaged', routed: 'pkg', deadline: '2026-10-29', deadline_horizon_days: 28, status_date: '2026-09-22', angle: 'Growth PM role fits Hill Holliday performance-marketing instinct.' },
      { id: 'r23', company: 'Airbnb', role: 'PM, Trips', fit: 7.7, source: 'HN', url: 'https://example.com/abnb-r23', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-21', angle: 'Trips = consumer marketplace; resume and backgrounder done.' },
      { id: 'r24', company: 'Uber', role: 'Associate PM, Mobility', fit: 7.4, source: 'BuiltInNYC', url: 'https://example.com/uber-r24', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-21', angle: 'Mobility = classic PM-onboarding lane.' },
      { id: 'r25', company: 'DoorDash', role: 'PM, Logistics', fit: 6.9, source: 'Career', url: 'https://example.com/dd-r25', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-20', angle: 'Logistics PM = operations heavy; good breadth.' },
      { id: 'r26', company: 'Square', role: 'PM Intern, Seller', fit: 7.1, source: 'Wellfound', url: 'https://example.com/sq-r26', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-20', angle: 'Seller-side PM = SMB ICP.' },
      { id: 'r27', company: 'Cloudflare', role: 'PM, Workers', fit: 7.0, source: 'HN', url: 'https://example.com/cf-r27', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-19', angle: 'Developer-tools PM = high-fit technical-PM lane.' },
      { id: 'r28', company: 'GitLab', role: 'Associate PM, Verify', fit: 6.8, source: 'Career', url: 'https://example.com/gl-r28', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-19', angle: 'Dev-tools adjacent; CI/CD is technical-PM-friendly.' },
      { id: 'r29', company: 'Databricks', role: 'PM, Data', fit: 7.2, source: 'BuiltInNYC', url: 'https://example.com/db-r29', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-18', angle: 'Data PM = enterprise technical-PM.' },
      { id: 'r30', company: 'Snowflake', role: 'PM, Apps', fit: 7.0, source: 'Career', url: 'https://example.com/sf-r30', status: 'packaged', routed: 'pkg', deadline: '', status_date: '2026-09-18', angle: 'Apps surface = consumer-on-data-PM.' },

      // Submitted — 10
      { id: 'r31', company: 'Notion', role: 'Associate PM, Onboarding', fit: 7.5, source: 'Wellfound', url: 'https://example.com/notion-r31', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-15' },
      { id: 'r32', company: 'Linear', role: 'PM, Cycles', fit: 6.7, source: 'HN', url: 'https://example.com/linear-r32', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-15' },
      { id: 'r33', company: 'Stripe', role: 'Associate PM, Billing', fit: 8.3, source: 'BuiltInNYC', url: 'https://example.com/stripe-r33', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-14' },
      { id: 'r34', company: 'Vercel', role: 'PM Intern, Edge', fit: 6.9, source: 'Wellfound', url: 'https://example.com/vercel-r34', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-14' },
      { id: 'r35', company: 'Anthropic', role: 'PM, API', fit: 8.0, source: 'Career', url: 'https://example.com/anthropic-r35', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-13' },
      { id: 'r36', company: 'Airtable', role: 'PM, Automations', fit: 6.5, source: 'HN', url: 'https://example.com/airtable-r36', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-13' },
      { id: 'r37', company: 'MongoDB', role: 'Associate PM, Search', fit: 6.4, source: 'Career', url: 'https://example.com/mongo-r37', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-12' },
      { id: 'r38', company: 'Figma', role: 'PM, FigJam', fit: 6.8, source: 'Wellfound', url: 'https://example.com/figma-r38', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-12' },
      { id: 'r39', company: 'Plaid', role: 'PM, Auth', fit: 6.6, source: 'BuiltInNYC', url: 'https://example.com/plaid-r39', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-11' },
      { id: 'r40', company: 'Datadog', role: 'PM, APM', fit: 6.5, source: 'Career', url: 'https://example.com/dd-r40', status: 'submitted', routed: 'sub', deadline: '', status_date: '2026-09-11' },

      // Blocked — 10
      { id: 'r41', company: 'IBM', role: 'PM, Watson', fit: 5.4, source: 'Career', url: 'https://example.com/ibm-r41', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-09', blocked_reason: 'role-mismatch-senior', angle: 'Role expectations look 3+ years in.' },
      { id: 'r42', company: 'Oracle', role: 'PM, NetSuite', fit: 5.0, source: 'Career', url: 'https://example.com/ora-r42', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-09', blocked_reason: 'role-mismatch-senior', angle: 'Senior PM track, not APM.' },
      { id: 'r43', company: 'Cisco', role: 'PM, Webex', fit: 4.8, source: 'Career', url: 'https://example.com/csco-r43', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-08', blocked_reason: 'role-mismatch-senior', angle: 'Senior PM expectations.' },
      { id: 'r44', company: 'Salesforce', role: 'PM, Service Cloud', fit: 5.2, source: 'Career', url: 'https://example.com/sfdc-r44', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-08', blocked_reason: 'role-mismatch-senior', angle: 'Senior PM.' },
      { id: 'r45', company: 'SAP', role: 'PM, S/4HANA', fit: 4.6, source: 'Career', url: 'https://example.com/sap-r45', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-07', blocked_reason: 'role-mismatch-senior', angle: 'Enterprise PM, senior track.' },
      { id: 'r46', company: 'Tesla', role: 'PM, Autopilot', fit: 5.1, source: 'Career', url: 'https://example.com/tsla-r46', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-07', blocked_reason: 'sponsorship-not-confirmed', angle: 'H1B transfer unclear; defer until later.' },
      { id: 'r47', company: 'Rivian', role: 'PM, Software', fit: 5.3, source: 'Career', url: 'https://example.com/rivn-r47', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-06', blocked_reason: 'sponsorship-not-confirmed', angle: 'Sponsorship unclear.' },
      { id: 'r48', company: 'Coinbase', role: 'PM, Onchain', fit: 5.5, source: 'Career', url: 'https://example.com/coin-r48', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-06', blocked_reason: 'sponsorship-not-confirmed', angle: 'Sponsorship unclear.' },
      { id: 'r49', company: 'Palantir', role: 'PM, Foundry', fit: 4.9, source: 'Career', url: 'https://example.com/pltr-r49', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-05', blocked_reason: 'role-mismatch-senior', angle: 'Senior defense-PM track.' },
      { id: 'r50', company: 'Bloomberg', role: 'PM, Terminal', fit: 5.6, source: 'Career', url: 'https://example.com/bbg-r50', status: 'blocked', routed: '', deadline: '', status_date: '2026-09-05', blocked_reason: 'role-mismatch-senior', angle: 'Senior PM, NYC onsite-heavy.' }
    ],
    digests: [
      {
        date: '2026-10-01',
        promoted: [
          { id: 'r17', headline: 'Google APM, CGA — fit 8.9, deadline in 3 days' },
          { id: 'r11', headline: 'Google APM, Cloud Platform — fit 8.7, deadline in 5 days' },
          { id: 'r06', headline: 'Stripe APM, Payments API — fit 8.5, deadline in 14 days' }
        ],
        rejected: [
          { reason: 'role-mismatch-senior', names: ['IBM Watson PM', 'Oracle NetSuite PM', 'Cisco Webex PM', 'Salesforce Service Cloud PM', 'SAP S/4HANA PM', 'Palantir Foundry PM', 'Bloomberg Terminal PM'] },
          { reason: 'sponsorship-not-confirmed', names: ['Tesla Autopilot PM', 'Rivian Software PM', 'Coinbase Onchain PM'] },
          { reason: 'too-junior', names: ['Junior CSM at Twilio', 'Junior Analyst at Datadog'] }
        ]
      },
      {
        date: '2026-09-30',
        promoted: [
          { id: 'r12', headline: 'Microsoft PM Intern, M365 Copilot — fit 7.9' },
          { id: 'r14', headline: 'Asana PM, Goals — fit 7.3, deadline in 22 days' }
        ],
        rejected: [
          { reason: 'role-mismatch-senior', names: ['Oracle NetSuite PM'] },
          { reason: 'too-junior', names: ['Junior CSM at Gainsight'] }
        ]
      }
    ],
    cron_runs: [
      { name: 'account-backgrounder', schedule: 'daily 06:30', last_status: 'ok', last_run_at: '2026-10-01T06:30:12', latency_s: 41 },
      { name: 'daily-job-hunt', schedule: 'daily 07:30', last_status: 'ok', last_run_at: '2026-10-01T07:30:08', latency_s: 312 },
      { name: 'hunt-part2-catchup', schedule: 'daily 07:55', last_status: 'ok', last_run_at: '2026-10-01T07:55:22', latency_s: 184 },
      { name: 'hunt-part3-universities', schedule: 'daily 11:45', last_status: 'ok', last_run_at: '2026-10-01T11:45:03', latency_s: 96 },
      { name: 'weekly-calibration', schedule: 'Sun 20:00', last_status: 'ok', last_run_at: '2026-09-28T20:00:18', latency_s: 612 },
      { name: 'account-backgrounder', schedule: 'daily 06:30', last_status: 'warn', last_run_at: '2026-09-22T06:30:00', latency_s: 0, warning: 'Mac was asleep at the scheduled fire time. No catch-up attempted per spec v2.' }
    ],
    rubric_versions: [
      { version: 'v1', created_at: '2026-08-25', current: false, weights: { 'level-fit': 0.20, 'role-fit': 0.25, 'company-fit': 0.20, 'comp-fit': 0.15, 'location-fit': 0.20 } },
      { version: 'v2', created_at: '2026-09-22', current: true, weights: { 'level-fit': 0.25, 'role-fit': 0.25, 'company-fit': 0.20, 'comp-fit': 0.15, 'location-fit': 0.15 } }
    ],
    rubric_diff: [
      { factor: 'level-fit', from: 0.20, to: 0.25, rationale: 'Observed that APM tracks systematically under-ranked vs senior PM tracks. +0.05 corrected the bias on the Google APM cohort.' },
      { factor: 'role-fit', from: 0.25, to: 0.25, rationale: 'No change — held the line on role-fit until more interaction data accumulates.' },
      { factor: 'company-fit', from: 0.20, to: 0.20, rationale: 'No change — held the line.' },
      { factor: 'comp-fit', from: 0.15, to: 0.15, rationale: 'No change.' },
      { factor: 'location-fit', from: 0.20, to: 0.15, rationale: 'NYC onsite-only roles were over-indexed. -0.05 gives more weight to remote-US roles that align with F-1 OPT constraints.' }
    ],
    rubric_outcomes: [
      { metric: 'APM cohort fit', v1: 7.1, v2: 7.9 },
      { metric: 'Senior PM downrank', v1: 6.4, v2: 5.6 },
      { metric: 'Remote-US top-10 rate', v1: 0.50, v2: 0.70 },
      { metric: 'Blocked/sponsorship', v1: 3, v2: 3 },
      { metric: 'Packaged/week', v1: 7, v2: 9 }
    ],
    telegram_messages: [
      { sent_at: '2026-10-01T07:30:08', text: 'Daily digest: 3 promoted (Google APM CGA, Google Cloud, Stripe Payments), 12 rejected with reasons.', status: 'ok' },
      { sent_at: '2026-09-30T07:30:11', text: 'Daily digest: 2 promoted, 2 rejected.', status: 'ok' },
      { sent_at: '2026-09-29T18:00:00', text: 'Backgrounder ready for r17 (Google APM, CGA).', status: 'failed', error: "Telegram bot returned 'chat not found' [chat_id expired]" },
      { sent_at: '2026-09-29T18:00:42', text: 'Retry succeeded: Backgrounder ready for r17 (Google APM, CGA).', status: 'retry_succeeded' },
      { sent_at: '2026-09-28T07:30:09', text: 'Daily digest: 4 promoted, 8 rejected.', status: 'ok' },
      { sent_at: '2026-09-22T06:30:00', text: 'Morning account-backgrounder skipped: mac asleep.', status: 'warn' }
    ]
  };

  // Urgency thresholds (matches design-tokens.md and tests/test_app.py).
  // days <= RED_MAX  -> red tier (this week)
  // days <= ORANGE_MAX -> orange tier (next week)
  // days > ORANGE_MAX -> blue tier (this month+)
  var RED_MAX = 7;
  var ORANGE_MAX = 14;

  // A hung /api/data request is a failure too: abort and use the embedded
  // fallback rather than leaving the board blank forever.
  var API_TIMEOUT_MS = 5000;

  // Hash routes — referenced as string literals so the route-assertion regex
  // in tests/test_app.py can pick them up via re.findall(r'#/(\w[\w-]*)', app.js).
  var ROUTES = ['#/pipeline', '#/deadline', '#/focus', '#/digest', '#/role', '#/run-health', '#/rubric', '#/telegram'];

  function urgencyTier(days) {
    if (days <= RED_MAX) return 'red';
    if (days <= ORANGE_MAX) return 'orange';
    return 'blue';
  }
  function urgencyColor(days) {
    var t = urgencyTier(days);
    if (t === 'red') return '--color-danger';
    if (t === 'orange') return '--color-warning';
    return '--color-accent';
  }

  // Days until deadline (ISO date -> integer). Returns NaN if missing/bad.
  function daysUntil(iso) {
    if (!iso) return NaN;
    var d = new Date(iso + 'T23:59:59-04:00');
    if (isNaN(d.getTime())) return NaN;
    var now = new Date('2026-10-01T12:00:00-04:00');
    var ms = d.getTime() - now.getTime();
    return Math.round(ms / (1000 * 60 * 60 * 24));
  }

  // Prefer the exporter's exact days_out (relative to the snapshot moment)
  // when present; fall back to date math for the offline seed/FALLBACK.
  function roleDays(r) {
    if (r && typeof r.deadline_days === 'number' && isFinite(r.deadline_days)) {
      return r.deadline_days;
    }
    return daysUntil(r && r.deadline);
  }

  // ---- Exporter-shape adapter (D1 fix).
  // snapshot-export/export.py emits one contract:
  //   {snapshot_at, snapshot_kind, pipeline, deadline_rail, role_detail,
  //    run_health, rejected_with_reasons, digests, rubric_versions, ...}
  // The screens above read a different, normalized contract:
  //   {roles, cron_runs, rubric_versions, rubric_diff, rubric_outcomes,
  //    digests, telegram_messages}
  // normalizeState() maps exporter -> normalized so a real exporter snapshot
  // renders without changing the exporter's published schema. It is a no-op
  // on already-normalized input (the inline FALLBACK), so offline use is
  // unaffected.
  function _num(v, d) {
    return (typeof v === 'number' && isFinite(v)) ? v : (d == null ? 0 : d);
  }
  function _daysBetween(fromIso, toIso) {
    if (!fromIso || !toIso) return NaN;
    var a = new Date(fromIso + 'T00:00:00');
    var b = new Date(toIso + 'T00:00:00');
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return NaN;
    return Math.round((b.getTime() - a.getTime()) / 86400000);
  }
  function normalizeState(raw) {
    if (!raw || typeof raw !== 'object') return raw;
    if (Array.isArray(raw.roles)) return raw; // already normalized (FALLBACK / seed)

    var pipeline = raw.pipeline || [];
    var detail = raw.role_detail || {};
    var asOf = (raw.snapshot_at || '').slice(0, 10);

    // The rail carries days_out relative to the snapshot moment; prefer it
    // (exact) and fall back to date math when a row is missing.
    var daysById = {};
    (raw.deadline_rail || []).forEach(function (row) { daysById[String(row.id)] = row.days_out; });
    function daysFor(id, deadline) {
      var k = String(id);
      if (typeof daysById[k] === 'number') return daysById[k];
      return _daysBetween(asOf, deadline);
    }

    var roles = pipeline.map(function (r) {
      var d = detail[String(r.id)] || {};
      var deadline = r.deadline || d.deadline || '';
      return {
        id: String(r.id),
        company: r.company || d.company || '',
        role: r.role || d.role || '',
        fit: _num(r.fit_score != null ? r.fit_score : d.fit_score),
        source: r.source || '',
        url: r.url || d.url || '',
        status: r.status || d.status || '',
        routed: r.routed || '',
        deadline: deadline,
        deadline_days: daysFor(r.id, deadline),
        status_date: r.status_date || r.date_found || '',
        blocked_reason: r.blocked_reason || d.blocked_reason || '',
        angle: r.notes || '',
        summary: d.company_summary || '',
        rubric_factors: d.rubric_factors || null,
        rubric_version: d.rubric_version ||
          ((raw.rubric_versions || [])[0] || {}).version || '',
        draft_paths: d.draft_paths || [],
        history: d.history || []
      };
    });

    var roleById = {};
    roles.forEach(function (r) { roleById[r.id] = r; });

    // digests: {date, sections:[{title, role_ids}]} -> {date, promoted, rejected}
    // Exporter digests carry no per-day rejection detail, so the current
    // blocked set (rejected_with_reasons) is grouped by reason and attached
    // to the newest digest — real evidence beats an empty block.
    var rejectedGroups = {};
    (raw.rejected_with_reasons || []).forEach(function (x) {
      var reason = x.blocked_reason || 'blocked';
      if (!rejectedGroups[reason]) rejectedGroups[reason] = [];
      rejectedGroups[reason].push((x.company + ' ' + x.role).trim());
    });
    var rejectedForNewest = Object.keys(rejectedGroups).map(function (reason) {
      return { reason: reason, names: rejectedGroups[reason] };
    });
    var rawDigests = raw.digests || [];
    var digests = rawDigests.map(function (g) {
      var promoted = [];
      (g.sections || []).forEach(function (s) {
        (s.role_ids || []).forEach(function (id) {
          var r = roleById[String(id)];
          if (!r) return;
          if (promoted.some(function (p) { return p.id === r.id; })) return;
          promoted.push({
            id: r.id,
            headline: r.company + ' — ' + r.role + ' (fit ' + r.fit.toFixed(1) + ')'
          });
        });
      });
      var rejected = (g === rawDigests[0]) ? rejectedForNewest : [];
      return { date: g.date, promoted: promoted, rejected: rejected };
    });
    // Don't render digest cards with nothing to say.
    digests = digests.filter(function (g) {
      return g.promoted.length > 0 || g.rejected.length > 0;
    });

    // rubric_versions: flatten per-version weights -> diff + outcomes lists.
    var versions = raw.rubric_versions || [];
    var current = versions[versions.length - 1] || {};
    var prev = versions.length > 1 ? versions[versions.length - 2] : null;
    var rubric_diff = [];
    var rubric_outcomes = [];
    if (prev) {
      Object.keys(current.weights || {}).forEach(function (k) {
        var to = _num(current.weights[k]);
        var from = (prev.weights && prev.weights[k] != null) ? _num(prev.weights[k]) : to;
        rubric_diff.push({
          factor: k,
          from: from,
          to: to,
          // The rationale that explains the change lives on the newer version.
          rationale: String(current.rationale || prev.rationale || '').slice(0, 400)
        });
      });
    }
    if (prev && current.outcomes) {
      Object.keys(current.outcomes).forEach(function (k) {
        rubric_outcomes.push({
          metric: k,
          v1: prev.outcomes ? prev.outcomes[k] : '—',
          v2: current.outcomes[k]
        });
      });
    }

    var rejected_rows = (raw.rejected_with_reasons || []).map(function (x) {
      return {
        id: String(x.id),
        company: x.company || '',
        role: x.role || '',
        fit: _num(x.fit_score),
        reason: x.blocked_reason || 'blocked'
      };
    });

    return {
      generated_at: raw.snapshot_at || '',
      snapshot_kind: raw.snapshot_kind || 'real',
      as_of: asOf,
      roles: roles,
      digests: digests,
      cron_runs: raw.run_health || [],
      rubric_versions: versions,
      rubric_diff: rubric_diff,
      rubric_outcomes: rubric_outcomes,
      telegram_messages: raw.telegram_messages || [],
      rejected_rows: rejected_rows
    };
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') node.className = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else if (k === 'html') node.innerHTML = attrs[k];
        else if (k.indexOf('on') === 0) node.addEventListener(k.slice(2), attrs[k]);
        else if (k === 'href') node.setAttribute('href', attrs[k]);
        else if (k === 'data-route') node.setAttribute('data-route', attrs[k]);
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      if (typeof c === 'string') node.appendChild(document.createTextNode(c));
      else node.appendChild(c);
    });
    return node;
  }

  // ---- Screen renderers (one per hash route).

  function renderPipeline(state, mount) {
    mount.innerHTML = '';
    var cols = [
      { key: 'pinged', label: 'Pinged', dot: 'pinged' },
      { key: 'interested', label: 'Interested', dot: 'interested' },
      { key: 'packaged', label: 'Packaged', dot: 'packaged' },
      { key: 'submitted', label: 'Submitted', dot: 'submitted' },
      { key: 'blocked', label: 'Blocked', dot: 'blocked' }
    ];
    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Pipeline Board' }),
      el('div', { class: 'page-header__meta', text: state.roles.length + ' roles · 5 columns · ' + state.roles.length + ' loaded' })
    ]);
    var toolbar = el('div', { class: 'toolbar' }, [
      el('input', { class: 'toolbar__search', placeholder: 'Search company or role…' }),
      el('button', { class: 'toolbar__chip is-active', text: 'All fit' }),
      el('button', { class: 'toolbar__chip', text: 'All sources' }),
      el('button', { class: 'toolbar__chip', text: 'All deadlines' }),
      el('select', { class: 'toolbar__select' }, [
        el('option', { text: 'Sort: Status (flow)' }),
        el('option', { text: 'Sort: Fit (high → low)' }),
        el('option', { text: 'Sort: Deadline (soonest)' })
      ])
    ]);
    var board = el('div', { class: 'pipeline' });
    cols.forEach(function (col) {
      var rows = state.roles.filter(function (r) { return r.status === col.key; });
      var colNode = el('div', { class: 'pipeline__col' }, [
        el('div', { class: 'pipeline__col-header' }, [
          el('span', null, [el('span', { class: 'dot dot--' + col.dot }) , ' ', col.label]),
          el('span', { text: String(rows.length) })
        ])
      ]);
      rows.forEach(function (r) {
        var card = el('div', { class: 'role-card', onclick: function () { window.location.hash = '#/role/' + r.id; } }, [
          el('div', { class: 'role-card__company', text: r.company }),
          el('h3', { class: 'role-card__title', text: r.role }),
          el('div', { class: 'role-card__fit', text: 'Fit ' + r.fit.toFixed(1) + ' · ' + r.source }),
          r.angle ? el('div', { class: 'role-card__angle', text: r.angle }) : null
        ]);
        colNode.appendChild(card);
      });
      board.appendChild(colNode);
    });
    mount.appendChild(header);
    mount.appendChild(toolbar);
    mount.appendChild(board);
  }

  function renderDeadlineRail(state, mount) {
    mount.innerHTML = '';
    var withDeadline = state.roles
      .filter(function (r) { return r.deadline && r.deadline.length > 0; })
      .map(function (r) {
        return { role: r, days: roleDays(r) };
      })
      .filter(function (x) { return !isNaN(x.days); })
      .sort(function (a, b) { return a.days - b.days; });

    var red = withDeadline.filter(function (x) { return urgencyTier(x.days) === 'red'; });
    var orange = withDeadline.filter(function (x) { return urgencyTier(x.days) === 'orange'; });
    var blue = withDeadline.filter(function (x) { return urgencyTier(x.days) === 'blue'; });

    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Deadline Rail' }),
      el('div', { class: 'page-header__meta', text: withDeadline.length + ' roles with a published deadline' })
    ]);

    var summary = el('div', { class: 'rail-summary' }, [
      el('div', { class: 'rail-summary__card' }, [
        el('div', { class: 'rail-summary__label', text: 'This week (≤7d)' }),
        el('div', { class: 'rail-summary__num', style: 'color: var(--color-danger);', text: String(red.length) })
      ]),
      el('div', { class: 'rail-summary__card' }, [
        el('div', { class: 'rail-summary__label', text: 'Next week (8–14d)' }),
        el('div', { class: 'rail-summary__num', style: 'color: var(--color-warning);', text: String(orange.length) })
      ]),
      el('div', { class: 'rail-summary__card' }, [
        el('div', { class: 'rail-summary__label', text: 'This month+ (15d+)' }),
        el('div', { class: 'rail-summary__num', style: 'color: var(--color-accent);', text: String(blue.length) })
      ])
    ]);

    function tierBlock(cls, label, rows) {
      if (rows.length === 0) return null;
      var block = el('div', { class: 'rail-tier ' + cls }, [
        el('div', { class: 'rail-tier__header' }, [el('span', { class: 'dot dot--' + (cls === 'rail-tier--red' ? 'fail' : cls === 'rail-tier--orange' ? 'warn' : 'interested') }), ' ', label])
      ]);
      rows.forEach(function (x) {
        block.appendChild(el('div', { class: 'rail-row', onclick: function () { window.location.hash = '#/role/' + x.role.id; } }, [
          el('div', { class: 'rail-row__days', text: x.days + 'd' }),
          el('div', null, [
            el('div', { class: 'rail-row__company', text: x.role.company }),
            el('div', { class: 'rail-row__role', text: x.role.role })
          ]),
          el('div', { class: 'rail-row__fit', text: 'Fit ' + x.role.fit.toFixed(1) }),
          el('div', { class: 'rail-row__deadline', text: x.role.deadline }),
          el('div', { class: 'rail-row__fit', text: x.role.source })
        ]));
      });
      return block;
    }

    var redBlock = tierBlock('rail-tier--red', 'This week', red);
    var orangeBlock = tierBlock('rail-tier--orange', 'Next week', orange);
    var blueBlock = tierBlock('rail-tier--blue', 'This month+', blue);

    var noDeadlineCount = state.roles.length - withDeadline.length;
    var footer = el('div', { class: 'rail-footer', text: noDeadlineCount + ' additional roles are tracked with no published deadline — they\'re not shown here.' });

    mount.appendChild(header);
    mount.appendChild(summary);
    if (redBlock) mount.appendChild(redBlock);
    if (orangeBlock) mount.appendChild(orangeBlock);
    if (blueBlock) mount.appendChild(blueBlock);
    mount.appendChild(footer);
  }

  function renderFocus(state, mount) {
    mount.innerHTML = '';
    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Focus — Interested' }),
      el('div', { class: 'page-header__meta', text: 'Sorted by deadline (closest first)' })
    ]);
    var banner = el('div', { class: 'focus-banner', text: 'Gate progress is self-reported (your checks). Engine-written artifacts live in drafts/ — this checklist is a planning aid, not source of truth.' });
    var interested = state.roles
      .filter(function (r) { return r.status === 'interested'; })
      .sort(function (a, b) {
        var da = a.deadline ? roleDays(a) : 99999;
        var db = b.deadline ? roleDays(b) : 99999;
        return da - db;
      });
    var list = el('div');
    interested.forEach(function (r) {
      var days = r.deadline ? roleDays(r) : null;
      var card = el('div', { class: 'card focus-card' }, [
        el('div', null, [
          el('h2', { class: 'focus-card__title', text: r.role }),
          el('div', { class: 'focus-card__meta', text: r.company + ' · Fit ' + r.fit.toFixed(1) + ' · ' + (days != null ? days + ' days to deadline (' + r.deadline + ')' : 'no published deadline') }),
          el('div', { class: 'role-card__angle', text: r.angle || '' })
        ]),
        el('div', null, [
          el('h3', { class: 'card__title', text: 'Submission gates' }),
          (function () {
            var ul = el('ul', { class: 'gate-list' });
            ['Backgrounder read', 'Resume drafted', 'Cover letter drafted', 'References notified', 'Submission logged'].forEach(function (g, i) {
              ul.appendChild(el('li', { class: 'gate-list__item' }, [
                el('span', { class: 'gate-list__check' + (i < 2 ? ' is-on' : '') }),
                el('span', { text: g })
              ]));
            });
            return ul;
          })()
        ])
      ]);
      list.appendChild(card);
    });
    mount.appendChild(header);
    mount.appendChild(banner);
    mount.appendChild(list);
  }

  function renderDigest(state, mount) {
    mount.innerHTML = '';
    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Daily Digest' }),
      el('div', { class: 'page-header__meta', text: 'Archived 7:30am Telegram messages' })
    ]);
    var toolbar = el('div', { class: 'toolbar' }, [
      el('input', { class: 'toolbar__search', placeholder: 'Search digests…' }),
      el('select', { class: 'toolbar__select' }, [
        el('option', { text: 'Last 7 days' }),
        el('option', { text: 'Last 30 days' }),
        el('option', { text: 'Last 90 days' })
      ]),
      el('select', { class: 'toolbar__select' }, [
        el('option', { text: 'Sort: Newest first' }),
        el('option', { text: 'Sort: Oldest first' })
      ])
    ]);
    var list = el('div');
    state.digests.forEach(function (d) {
      var card = el('div', { class: 'card digest-card' });
      var header = el('div', { class: 'digest-card__header' }, [
        el('div', { class: 'digest-card__date', text: 'Digest — ' + d.date + ' · 7:30am ET' }),
        el('a', { class: 'digest-card__view-all', href: '#/digest', text: 'View full digest →' })
      ]);
      card.appendChild(header);
      card.appendChild(el('h3', { class: 'digest-card__section-title', text: 'Promoted (' + d.promoted.length + ')' }));
      var ul = el('ul', { class: 'digest-list' });
      d.promoted.forEach(function (p) {
        ul.appendChild(el('li', { class: 'digest-list__item' }, [
          el('span', null, [el('a', { href: '#/role/' + p.id, text: p.headline })]),
          el('span', { class: 'toolbar__chip', text: 'View' })
        ]));
      });
      card.appendChild(ul);

      if (d.rejected && d.rejected.length) {
        var rejectedBlock = el('div', { class: 'digest-rejected' }, [
          el('h3', { class: 'digest-rejected__title', text: 'Rejected with reasons (' + d.rejected.reduce(function (n, g) { return n + g.names.length; }, 0) + ')' })
        ]);
        d.rejected.forEach(function (g) {
          var grp = el('div', { class: 'digest-rejected__group' }, [
            el('div', { class: 'digest-rejected__reason', text: g.reason + ' · ' + g.names.length }),
            el('div', { class: 'digest-rejected__names', text: g.names.join(', ') })
          ]);
          rejectedBlock.appendChild(grp);
        });
        card.appendChild(rejectedBlock);
      }
      list.appendChild(card);
    });
    mount.appendChild(header);
    mount.appendChild(toolbar);
    mount.appendChild(list);
  }

  function renderRole(state, mount, roleId) {
    mount.innerHTML = '';
    var role = state.roles.filter(function (r) { return r.id === roleId; })[0];
    if (!role) {
      mount.appendChild(el('div', { class: 'crumb', text: '< Back to Pipeline' }));
      mount.appendChild(el('h1', { class: 'page-header__title', text: 'Role not found: ' + roleId }));
      return;
    }
    var crumb = el('a', { class: 'crumb', href: '#/pipeline', text: '← Pipeline' });
    var header = el('div', { class: 'page-header' }, [
      el('div', null, [
        crumb,
        el('h1', { class: 'role-detail__title', text: role.role }),
        el('div', { class: 'role-detail__company', text: role.company + ' · ' + role.source }),
        el('div', { class: 'role-detail__score', text: 'Fit ' + role.fit.toFixed(1) })
      ]),
      el('div', { class: 'page-header__meta', text: 'Status: ' + role.status + ' · ' + role.status_date })
    ]);

    // Rubric factors — use the real per-factor breakdown when the exporter
    // provides one (rubric_factors); otherwise fall back to an illustrative
    // breakdown so the offline seed still renders a full screen.
    var factorInputs;
    var rubricNote = '';
    if (role.rubric_factors && typeof role.rubric_factors === 'object') {
      // Real factor scores are 0–3ish; normalize to a 0–1 bar width.
      factorInputs = Object.keys(role.rubric_factors).map(function (k) {
        var raw = role.rubric_factors[k];
        var v = Math.max(0, Math.min(1, _num(raw) / 3));
        return { label: k, v: v, raw: _num(raw) };
      });
      rubricNote = 'Factor scores from ' + (role.rubric_version || 'the current rubric') + ', each on a 0–3 scale.';
    } else {
      factorInputs = [
        { label: 'domain fit', v: 0.9, raw: 2.7 },
        { label: 'program match', v: 0.95, raw: 2.85 },
        { label: 'sponsorship clear', v: 0.7, raw: 2.1 },
        { label: 'level fit', v: 0.6, raw: 1.8 },
        { label: 'location fit', v: 0.85, raw: 2.55 },
        { label: 'comp fit', v: 0.75, raw: 2.25 }
      ];
      rubricNote = 'Illustrative breakdown — the engine did not emit per-factor scores for this role.';
    }
    var bars = el('div', { class: 'rubric-bars' });
    factorInputs.forEach(function (f) {
      bars.appendChild(el('div', { class: 'rubric-bar' }, [
        el('div', { class: 'rubric-bar__label', text: f.label }),
        el('div', { class: 'rubric-bar__track' }, [
          el('div', { class: 'rubric-bar__fill', style: 'width: ' + Math.round(f.v * 100) + '%;' })
        ]),
        el('div', { class: 'rubric-bar__num', text: f.raw.toFixed(1) + ' / 3.0' })
      ]));
    });
    if (rubricNote) bars.appendChild(el('div', { class: 'page-header__meta', text: rubricNote }));

    // Backgrounder & drafts — real draft paths when present, otherwise the
    // expected filenames for the offline seed.
    var files = el('ul', { class: 'file-list' });
    var draftPaths = role.draft_paths || [];
    if (draftPaths.length) {
      draftPaths.forEach(function (p) {
        files.appendChild(el('li', { class: 'file-list__item' }, [
          el('span', { class: 'file-card__filename', text: p }),
          el('span', { class: 'toolbar__chip', text: 'Open' })
        ]));
      });
    } else {
      files.appendChild(el('li', { class: 'file-list__item' }, [
        el('span', { class: 'file-card__filename', text: role.id + '-' + role.company.replace(/[^A-Za-z0-9]/g, '') + '-role-backgrounder.md' }),
        el('span', { class: 'toolbar__chip', text: 'Read' })
      ]));
      files.appendChild(el('li', { class: 'file-list__item' }, [
        el('span', { class: 'file-card__filename', text: role.id + '-' + role.company.replace(/[^A-Za-z0-9]/g, '') + '-role-resume.docx' }),
        el('span', { class: 'toolbar__chip', text: 'Draft' })
      ]));
      files.appendChild(el('li', { class: 'file-list__item' }, [
        el('span', { class: 'file-card__filename', text: role.id + '-' + role.company.replace(/[^A-Za-z0-9]/g, '') + '-role-cover.docx' }),
        el('span', { class: 'toolbar__chip', text: 'Draft' })
      ]));
    }


    // History — real per-event log when the exporter provides one, otherwise
    // the synthetic 4-step timeline for the offline seed.
    var history;
    if (role.history && role.history.length) {
      history = el('ul', { class: 'history-timeline' });
      role.history.forEach(function (h) {
        history.appendChild(el('li', { class: 'history-timeline__item' }, [
          el('span', { class: 'history-timeline__dot' }),
          el('div', { class: 'history-timeline__body' }, [
            el('div', { text: h.note || h.event || '' }),
            el('div', { class: 'history-timeline__when', text: (h.ts || '').replace('T', ' ').slice(0, 16) })
          ])
        ]));
      });
    } else {
      history = el('ul', { class: 'history-timeline' }, [
        el('li', { class: 'history-timeline__item' }, [
          el('span', { class: 'history-timeline__dot' }),
          el('div', { class: 'history-timeline__body' }, [
            el('div', { text: 'Discovered on ' + role.source }),
            el('div', { class: 'history-timeline__when', text: role.status_date })
          ])
        ]),
        el('li', { class: 'history-timeline__item' }, [
          el('span', { class: 'history-timeline__dot history-timeline__dot--watchlist' }),
          el('div', { class: 'history-timeline__body' }, [
            el('div', { text: 'Added to watchlist (fit ' + role.fit.toFixed(1) + ')' }),
            el('div', { class: 'history-timeline__when', text: role.status_date })
          ])
        ]),
        el('li', { class: 'history-timeline__item' }, [
          el('span', { class: 'history-timeline__dot history-timeline__dot--interested' }),
          el('div', { class: 'history-timeline__body' }, [
            el('div', { text: 'Marked interested (int)' }),
            el('div', { class: 'history-timeline__when', text: role.status_date })
          ])
        ]),
        el('li', { class: 'history-timeline__item' }, [
          el('span', { class: 'history-timeline__dot history-timeline__dot--artifact' }),
          el('div', { class: 'history-timeline__body' }, [
            el('div', { text: 'Backgrounder + resume + cover letter drafted' }),
            el('div', { class: 'history-timeline__when', text: role.status_date })
          ])
        ])
      ]);
    }


    var left = el('div', null, [
      el('div', { class: 'card', style: 'margin-bottom: var(--space-5);' }, [
        el('h3', { class: 'card__title', text: 'Backgrounder & drafts' }),
        files
      ]),
      el('div', { class: 'card' }, [
        el('h3', { class: 'card__title', text: 'Angle' }),
        el('div', { class: 'role-card__angle', text: role.angle || 'No angle captured.' })
      ])
    ]);
    var right = el('div', null, [
      el('div', { class: 'card', style: 'margin-bottom: var(--space-5);' }, [
        el('h3', { class: 'card__title', text: 'Why this scored ' + role.fit.toFixed(1) }),
        bars
      ]),
      el('div', { class: 'card' }, [
        el('h3', { class: 'card__title', text: 'History' }),
        history
      ])
    ]);
    var grid = el('div', { class: 'role-detail' }, [left, right]);

    mount.appendChild(header);
    mount.appendChild(grid);
  }

  function renderRunHealth(state, mount) {
    mount.innerHTML = '';
    var okRuns = state.cron_runs.filter(function (r) { return r.last_status === 'ok'; }).length;
    var warnRuns = state.cron_runs.filter(function (r) { return r.last_status === 'warn'; }).length;
    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Run Health' }),
      el('div', { class: 'page-header__meta', text: 'Cron status as of today' })
    ]);
    var summary = el('div', { class: 'health-cards' }, [
      el('div', { class: 'card health-card' }, [
        el('div', { class: 'rail-summary__label', text: 'Today' }),
        el('div', { class: 'health-card__num health-card__num--ok', text: 'OK' })
      ]),
      el('div', { class: 'card health-card' }, [
        el('div', { class: 'rail-summary__label', text: 'This week' }),
        el('div', { class: 'health-card__num health-card__num--ok', text: '7 / 7' })
      ]),
      el('div', { class: 'card health-card' }, [
        el('div', { class: 'rail-summary__label', text: 'This month (in progress)' }),
        el('div', { class: 'health-card__num health-card__num--warn', text: '12 / 30' })
      ])
    ]);

    var table = el('table', { class: 'cron-log' });
    var thead = el('thead', null, [
      el('tr', null, [
        el('th', { text: 'Cron' }),
        el('th', { text: 'Schedule' }),
        el('th', { text: 'Last status' }),
        el('th', { text: 'Last run' }),
        el('th', { text: 'Latency (s)' })
      ])
    ]);
    table.appendChild(thead);
    var tbody = el('tbody');
    state.cron_runs.forEach(function (r) {
      tbody.appendChild(el('tr', null, [
        el('td', null, [el('span', { class: 'dot dot--' + (r.last_status === 'ok' ? 'ok' : r.last_status === 'warn' ? 'warn' : 'fail') }), ' ', r.name]),
        el('td', { text: r.schedule }),
        el('td', { text: r.last_status }),
        el('td', { text: r.last_run_at }),
        el('td', { text: String(r.latency_s) })
      ]));
    });
    table.appendChild(tbody);

    var errorsBlock = el('div', { class: 'errors-block' }, [
      el('h3', { class: 'errors-block__title', text: 'Warnings & errors (' + warnRuns + ')' })
    ]);
    state.cron_runs.filter(function (r) { return r.last_status !== 'ok'; }).forEach(function (r) {
      errorsBlock.appendChild(el('div', { class: 'errors-block__item' }, [
        el('strong', { text: r.last_run_at + ' — ' + r.name + ': ' }),
        el('span', { text: r.warning || '(no warning text)' })
      ]));
    });

    var queueCard = el('div', { class: 'card', style: 'margin-top: var(--space-5);' }, [
      el('h3', { class: 'card__title', text: 'Queue' }),
      el('div', { text: 'Pending actions: 3 (2 backgrounder reruns, 1 stale-digest rebuild)' })
    ]);

    mount.appendChild(header);
    mount.appendChild(summary);
    mount.appendChild(table);
    mount.appendChild(errorsBlock);
    mount.appendChild(queueCard);
  }

  function renderRubric(state, mount) {
    mount.innerHTML = '';
    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Rubric & Calibration' }),
      el('div', { class: 'page-header__meta', text: 'Version history with rationale' })
    ]);
    var left = el('div', { class: 'card rubric-col' }, [
      el('h3', { class: 'card__title', text: 'Versions' })
    ]);
    state.rubric_versions.forEach(function (v) {
      left.appendChild(el('div', { class: 'rubric-version' + (v.current ? ' is-current' : '') }, [
        el('div', null, [
          el('div', { class: 'rubric-version__name', text: 'rubric-' + v.version + '.md' }),
          el('div', { class: 'page-header__meta', text: v.created_at })
        ]),
        v.current ? el('span', { class: 'rubric-version__pill', text: 'Current' }) : null
      ]));
    });

    var middle = el('div', { class: 'card rubric-col' }, [
      el('h3', { class: 'card__title', text: 'Diff (v1 → v2)' }),
      (function () {
        var ul = el('ul', { class: 'diff-list' });
        state.rubric_diff.forEach(function (d) {
          ul.appendChild(el('li', { class: 'diff-list__item' }, [
            el('div', { class: 'diff-list__factor', text: d.factor }),
            el('div', { class: 'diff-list__change', text: d.from.toFixed(2) + ' → ' + d.to.toFixed(2) + (d.to > d.from ? '  (+' + (d.to - d.from).toFixed(2) + ')' : d.to < d.from ? '  (' + (d.to - d.from).toFixed(2) + ')' : '  (held)') }),
            el('div', { class: 'diff-list__rationale', text: d.rationale })
          ]));
        });
        return ul;
      })()
    ]);

    var right = el('div', { class: 'card rubric-col' }, [
      el('h3', { class: 'card__title', text: 'Outcomes (v1 → v2)' }),
      (function () {
        var ul = el('ul', { class: 'outcomes-list' });
        state.rubric_outcomes.forEach(function (o) {
          ul.appendChild(el('li', { class: 'outcomes-list__item' }, [
            el('span', { text: o.metric }),
            el('span', { class: 'outcomes-list__num', text: String(o.v1) + '  →  ' + String(o.v2) })
          ]));
        });
        return ul;
      })()
    ]);

    var footer = el('div', { class: 'calibration-footer' }, [
      el('div', { class: 'calibration-footer__label', text: 'Calibration principle' }),
      el('p', { class: 'calibration-footer__quote', text: 'Reweighting only happens when interaction data exists. Drift on thin data is worse than holding the line.' })
    ]);

    var grid = el('div', { class: 'rubric-grid' }, [left, middle, right]);
    mount.appendChild(header);
    mount.appendChild(grid);
    mount.appendChild(footer);
  }

  function renderTelegram(state, mount) {
    mount.innerHTML = '';
    var header = el('div', { class: 'page-header' }, [
      el('h1', { class: 'page-header__title', text: 'Telegram Mirror' }),
      el('div', { class: 'page-header__meta', text: 'Verbatim Telegram bot traffic, with delivery status' })
    ]);
    var failed = state.telegram_messages.filter(function (m) { return m.status === 'failed'; }).length;
    var toolbar = el('div', { class: 'toolbar' }, [
      el('input', { class: 'toolbar__search', placeholder: 'Search messages…' }),
      el('button', { class: 'toolbar__chip', text: 'All' }),
      el('button', { class: 'toolbar__chip is-danger', text: 'Failed only [' + failed + ']' }),
      el('select', { class: 'toolbar__select' }, [
        el('option', { text: 'Last 7 days' }),
        el('option', { text: 'Last 30 days' })
      ])
    ]);

    var groups = {};
    state.telegram_messages.forEach(function (m) {
      var day = m.sent_at.slice(0, 10);
      if (!groups[day]) groups[day] = [];
      groups[day].push(m);
    });

    var list = el('div', { class: 'tg-list' });
    Object.keys(groups).sort().reverse().forEach(function (day) {
      var dayNode = el('div', { class: 'tg-day' }, [
        el('div', { class: 'tg-day__date', text: day })
      ]);
      groups[day].forEach(function (m) {
        var cls = 'tg-msg';
        if (m.status === 'failed') cls += ' tg-msg--failed';
        if (m.status === 'retry_succeeded') cls += ' tg-msg--retry';
        var statusLine = '';
        if (m.status === 'failed') statusLine = 'Failed: ' + (m.error || 'unknown error');
        else if (m.status === 'retry_succeeded') statusLine = 'Retry succeeded';
        else if (m.status === 'warn') statusLine = 'Warning (delivered)';
        else statusLine = 'Delivered';
        dayNode.appendChild(el('div', { class: cls }, [
          el('div', { class: 'tg-msg__body' }, [
            el('div', { text: m.text }),
            el('div', { class: 'tg-msg__status tg-msg__status--' + (m.status === 'failed' ? 'failed' : m.status === 'retry_succeeded' ? 'retry' : ''), text: statusLine })
          ]),
          el('div', { class: 'tg-msg__when', text: m.sent_at })
        ]));
      });
      list.appendChild(dayNode);
    });

    mount.appendChild(header);
    mount.appendChild(toolbar);
    mount.appendChild(list);
  }

  // ---- Router

  function render(state) {
    var hash = window.location.hash || '#/pipeline';
    var screens = document.querySelectorAll('.screen');
    screens.forEach(function (s) { s.classList.remove('is-active'); });

    var route = hash.replace(/^#\//, '');
    var parts = route.split('/');
    var screenId = 'screen-' + parts[0];
    var screen = document.getElementById(screenId);
    if (!screen) {
      window.location.hash = '#/pipeline';
      return;
    }
    screen.classList.add('is-active');

    var mount = screen.querySelector('.screen__mount');
    if (parts[0] === 'pipeline') renderPipeline(state, mount);
    else if (parts[0] === 'deadline') renderDeadlineRail(state, mount);
    else if (parts[0] === 'focus') renderFocus(state, mount);
    else if (parts[0] === 'digest') renderDigest(state, mount);
    else if (parts[0] === 'role') renderRole(state, mount, parts[1]);
    else if (parts[0] === 'run-health') renderRunHealth(state, mount);
    else if (parts[0] === 'rubric') renderRubric(state, mount);
    else if (parts[0] === 'telegram') renderTelegram(state, mount);

    // Sidebar active state
    var links = document.querySelectorAll('.sidebar__link');
    links.forEach(function (a) {
      a.classList.remove('is-active');
      if (a.getAttribute('href') === '#/' + parts[0]) a.classList.add('is-active');
    });
  }

  // ---- Boot

  // Fetch same-origin /api/data with a timeout. Resolves to
  //   { ok: true, data }   on a usable HTTP response, or
  //   { ok: false, reason } otherwise (network, timeout, non-2xx, bad JSON).
  // The caller decides what to do with the payload; this function only owns
  // transport.
  function fetchApiData() {
    if (typeof fetch !== 'function') {
      return Promise.resolve({ ok: false, reason: 'fetch unavailable' });
    }
    return new Promise(function (resolve) {
      var settled = false;
      function finish(result) { if (!settled) { settled = true; resolve(result); } }
      var timer = setTimeout(function () {
        finish({ ok: false, reason: 'timeout after ' + API_TIMEOUT_MS + 'ms' });
      }, API_TIMEOUT_MS);
      fetch('/api/data', { cache: 'no-store', headers: { Accept: 'application/json' } })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (data) { clearTimeout(timer); finish({ ok: true, data: data }); })
        .catch(function (err) { clearTimeout(timer); finish({ ok: false, reason: err.message }); });
    });
  }

  // Decide whether a /api/data payload is usable as the live dataset.
  // Returns { state } when the payload is adoptable, or { fallback: reason }
  // when the embedded dataset should be used instead.
  //
  // A payload with `error` set (e.g. {error: 'edge-config unavailable'}) is a
  // reported failure. A payload whose roles array is missing or empty is ALSO
  // treated as "no live data": the endpoint never serves an empty list for a
  // healthy populated store, and the embedded fallback exists so the demo board
  // is never blank. The PII guard is the last gate before adoption — a payload
  // carrying real emails / non-example URLs / many name-shaped strings is
  // refused in favour of the synthetic dataset.
  // A role is renderable only if it carries the fields the screens read
  // unconditionally (company string, numeric fit — the board calls
  // r.fit.toFixed). A payload that is roles-keyed but whose rows are
  // exporter-shaped (fit_score, not fit) would crash mid-render, so it is
  // treated as unusable and falls back.
  function _isRenderableRole(r) {
    return !!r && typeof r === 'object' &&
      typeof r.company === 'string' && typeof r.fit === 'number' && isFinite(r.fit);
  }

  function adoptApiPayload(data) {
    if (!data || typeof data !== 'object') {
      return { fallback: 'response was not a JSON object' };
    }
    if (data.error) {
      return { fallback: 'API reported error: ' + data.error };
    }
    var normalized = normalizeState(data);
    var roles = (normalized && Array.isArray(normalized.roles)) ? normalized.roles : [];
    if (roles.length === 0) {
      return { fallback: 'no live roles in response' };
    }
    for (var i = 0; i < roles.length; i++) {
      if (!_isRenderableRole(roles[i])) {
        return { fallback: 'role ' + (roles[i] && roles[i].id) + ' is missing required fields' };
      }
    }
    var piiReason = looks_like_pii(JSON.stringify(data));
    if (piiReason) {
      return { fallback: 'payload looks like real data (' + piiReason + ')' };
    }
    return { state: normalized };
  }

  function loadData(cb) {
    fetchApiData().then(function (res) {
      if (!res.ok) {
        console.warn('/api/data fetch failed (' + res.reason + ') — using embedded fallback');
        return cb(FALLBACK);
      }
      var decision = adoptApiPayload(res.data);
      if (decision.fallback) {
        console.warn('using embedded fallback: ' + decision.fallback);
        return cb(FALLBACK);
      }
      cb(decision.state);
    });
  }

  function boot() {
    loadData(function (state) {
      // Expose for tests / debugging
      window.__junter = {
        state: state,
        RED_MAX: RED_MAX, ORANGE_MAX: ORANGE_MAX, urgencyTier: urgencyTier,
        daysUntil: daysUntil, roleDays: roleDays,
        normalizeState: normalizeState, looks_like_pii: looks_like_pii,
        adoptApiPayload: adoptApiPayload
      };

      window.addEventListener('hashchange', function () { render(state); });
      if (!window.location.hash) window.location.hash = '#/pipeline';
      else render(state);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
