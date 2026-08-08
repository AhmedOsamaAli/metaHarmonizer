const INTERNAL_ORIGIN = 'https://metaharmonizer.invalid';

export function safeInternalPath(value: unknown, fallback = '/'): string {
  if (typeof value !== 'string') return fallback;

  const path = value.trim();
  if (!path.startsWith('/') || path.startsWith('//') || /[\\\u0000-\u001f]/.test(path)) {
    return fallback;
  }

  let decoded = path;
  try {
    decoded = decodeURIComponent(decoded);
    decoded = decodeURIComponent(decoded);
  } catch {
    return fallback;
  }

  if (decoded.startsWith('//') || decoded.includes('\\')) return fallback;

  const parsed = new URL(path, INTERNAL_ORIGIN);
  return parsed.origin === INTERNAL_ORIGIN ? path : fallback;
}
