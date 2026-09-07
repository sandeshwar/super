/**
 * Error taxonomy — SOLID: Open/Closed via hierarchy, single responsibility per class.
 * All app errors extend AppError for exhaustive handling in UI.
 */

export class AppError extends Error {
  readonly code: string;
  readonly cause?: unknown;
  constructor(message: string, code = 'APP_ERROR', cause?: unknown) {
    super(message);
    this.name = this.constructor.name;
    this.code = code;
    this.cause = cause;
  }
}

export class ApiError extends AppError {
  readonly status: number;
  readonly payload?: unknown;
  constructor(message: string, status: number, payload?: unknown) {
    super(message, `API_${status}`, payload);
    this.status = status;
    this.payload = payload;
  }
  get isAuth(): boolean { return this.status === 401; }
  get isNotFound(): boolean { return this.status === 404; }
  get isServer(): boolean { return this.status >= 500; }
}

export class NetworkError extends AppError {
  constructor(message = 'Network unavailable', cause?: unknown) {
    super(message, 'NETWORK_ERROR', cause);
  }
}

export class ValidationError extends AppError {
  readonly field?: string;
  constructor(message: string, field?: string) {
    super(message, 'VALIDATION_ERROR');
    this.field = field;
  }
}

export class StreamError extends AppError {
  constructor(message: string, cause?: unknown) {
    super(message, 'STREAM_ERROR', cause);
  }
}

export class AbortError extends AppError {
  constructor(message = 'Aborted', cause?: unknown) {
    super(message, 'ABORT', cause);
    this.name = 'AbortError';
  }
}

/**
 * Parse unknown throw into AppError without leaking internals.
 * Never shows stack to user — maps to safe message.
 */
export function toAppError(e: unknown): AppError {
  if (e instanceof AppError) return e;
  if (e instanceof DOMException && e.name === 'AbortError') return new AbortError('Request aborted', e);
  if (e instanceof TypeError && /fetch|network/i.test(e.message)) return new NetworkError(e.message, e);
  if (e instanceof Error) return new AppError(e.message, 'UNKNOWN', e);
  return new AppError(String(e), 'UNKNOWN', e);
}

export function userMessage(e: unknown): string {
  const err = toAppError(e);
  if (err instanceof AbortError) return 'Stopped';
  if (err instanceof ApiError) {
    if (err.isAuth) return 'Sign-in needed — paste the access token from your SUPER start URL.';
    if (err.isNotFound) return err.message || 'Not found';
    if (err.isServer) return 'Server error — check the backend logs';
    return err.message;
  }
  if (err instanceof NetworkError) return 'Network error — is the SUPER server running?';
  if (err instanceof ValidationError) return err.message;
  return err.message || 'Something went wrong';
}
