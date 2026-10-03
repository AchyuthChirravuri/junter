// Test-only ESM loader hook: resolves `@vercel/edge-config` to an in-memory
// stub. Used by api/tests/test_action_meta.py via
//   node --import file://.../loader-register.mjs --input-type=module -e "...".
//
// Not part of the deployed surface.
export async function resolve(specifier, context, nextResolve) {
  if (specifier === '@vercel/edge-config') {
    return {
      url: 'file://' + new URL('./edge-config-stub.mjs', import.meta.url).pathname,
      shortCircuit: true,
    };
  }
  return nextResolve(specifier, context);
}