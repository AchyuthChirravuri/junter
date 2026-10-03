// Intentionally explicit operator command: migrates and seeds only the checked-in
// synthetic fixture. It refuses absent configuration and never reads tracker.csv.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Pool } from '@neondatabase/serverless';
import { syntheticContext, __test } from '../lib/transactional-store.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const context = syntheticContext();
const fixture = JSON.parse(await fs.readFile(path.join(root, 'synthetic-data/seed.json'), 'utf8'));
if (fixture.snapshot_kind !== 'synthetic' || !Array.isArray(fixture.pipeline)) throw new Error('synthetic fixture required');
if (!fixture.pipeline.every(role => Number.isSafeInteger(role.id) && role.id > 0) || new Set(fixture.pipeline.map(role => role.id)).size !== fixture.pipeline.length) {
  throw new Error('synthetic fixture requires unique positive integer role ids');
}
if (context.namespace !== 'junter_synthetic') throw new Error('only the approved junter_synthetic namespace may be seeded');
const sql = await fs.readFile(path.join(root, 'storage/migrations/001_synthetic_transactional_store.sql'), 'utf8');
const pool = new Pool({ connectionString: process.env[__test.URL_KEY] });
const client = await pool.connect();
try {
  await client.query('BEGIN');
  await client.query(sql);
  const table = `"${context.namespace}"."roles"`;
  for (const role of fixture.pipeline) {
    await client.query(`INSERT INTO ${table} (role_id, payload) VALUES ($1, $2::jsonb) ON CONFLICT (role_id) DO NOTHING`, [role.id, JSON.stringify(role)]);
  }
  const { rows } = await client.query(`SELECT COUNT(*)::int AS role_count FROM ${table}`);
  if (rows[0].role_count !== fixture.pipeline.length) throw new Error('seed role count does not match the approved synthetic fixture');
  await client.query('COMMIT');
  process.stdout.write(`synthetic seed complete: ${rows[0].role_count} roles\n`);
} catch (error) {
  try { await client.query('ROLLBACK'); } catch { /* preserve original error */ }
  throw error;
} finally {
  client.release();
  await pool.end();
}
