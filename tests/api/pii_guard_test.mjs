// Guard: no real PII may sit in the committed, non-synthetic artifacts around
// the API route. This mirrors the UI's `looks_like_pii` intent for the files
// this card introduces or touches, so a future edit cannot quietly commit a
// real company URL, email, or a full name.
//
// Scope: the files shipped by this card that are NOT designed to be synthetic
// (the api handler, this repo's root manifests, and the .gitignore). Synthetic
// fixtures are allowed to contain `example.com` URLs and placeholder names and
// are intentionally out of scope.
//
// Heuristics are deliberately narrow to avoid false positives on ordinary code:
//   * any http(s) URL whose host is not example.com (or the reserved .test TLD)
//   * any email whose domain is not example.com
//   * a "Real Person Name" pattern with >= 3 hits in one file
//
// Run:  node --test tests/api
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

const FILES = [
  'api/data.js',
  'package.json',
  'package-lock.json',
  '.gitignore',
];

const URL_RE = /https?:\/\/([^\s"'`)]+)/g;
const EMAIL_RE = /[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})/g;
const NAME_RE = /\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b/g;

// Hosts that are obviously safe: reserved example/doc domains and the npm
// registry entries the lockfile legitimately contains.
const SAFE_HOST = /^(example\.(com|org|net)|.*\.test|localhost|127\.0\.0\.1|registry\.npmjs\.org|openapi\.vercel\.sh|unpkg\.com)/i;

// Words that look like "First Last" but are code/roles, not people.
const NAME_ALLOW = new Set([
  'Acme Test', 'Beta Fixture', 'Edge Config', 'Job Search', 'Pipeline Board',
  'Vercel Edge', 'Global Config', 'Product Manager',
]);

for (const rel of FILES) {
  test(`${rel}: no real URLs, emails, or names`, () => {
    const abs = path.join(REPO_ROOT, rel);
    if (!fs.existsSync(abs)) {
      // Files a given checkout may not have (e.g. lock file absent); skip empty.
      assert.ok(true);
      return;
    }
    const text = fs.readFileSync(abs, 'utf8');

    const badUrls = [...text.matchAll(URL_RE)]
      .map((m) => m[0])
      .filter((u) => !SAFE_HOST.test(new URL(u).host));
    assert.deepEqual(badUrls, [], `non-synthetic URL(s) in ${rel}: ${badUrls.join(', ')}`);

    const badEmails = [...text.matchAll(EMAIL_RE)]
      .map((m) => m[0])
      .filter((e) => !/example\.com$/i.test(e) && !/\.test$/i.test(e));
    assert.deepEqual(badEmails, [], `non-example email(s) in ${rel}: ${badEmails.join(', ')}`);

    const names = [...text.matchAll(NAME_RE)]
      .map((m) => m[0])
      .filter((n) => !NAME_ALLOW.has(n));
    assert.ok(
      names.length < 3,
      `>=3 name-shaped tokens in ${rel} (possible real name): ${names.slice(0, 5).join(', ')}`,
    );
  });
}
