/**
 * Result<T,E> — explicit success/failure without thrown control flow.
 * Encourages exhaustive handling and keeps error handling declarative.
 */

export type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

export function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}
export function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}
export function trySync<T>(fn: () => T): Result<T, unknown> {
  try { return ok(fn()); } catch (e) { return err(e); }
}
export async function tryAsync<T>(fn: () => Promise<T>): Promise<Result<T, unknown>> {
  try { return ok(await fn()); } catch (e) { return err(e); }
}
