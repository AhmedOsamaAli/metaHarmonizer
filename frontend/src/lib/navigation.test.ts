import { describe, expect, it } from 'vitest';
import { safeInternalPath } from './navigation';

describe('safeInternalPath', () => {
  it.each([
    '/review/123',
    '/quality/123?status=pending',
    '/login#form',
  ])('accepts internal path %s', (path) => {
    expect(safeInternalPath(path)).toBe(path);
  });

  it.each([
    undefined,
    '',
    'https://example.com',
    '//example.com/path',
    '/\\example.com/path',
    '/%5cexample.com/path',
    '/%2f%2fexample.com/path',
    '/%252f%252fexample.com/path',
    'javascript:alert(1)',
  ])('rejects unsafe destination %s', (path) => {
    expect(safeInternalPath(path)).toBe('/');
  });

  it('uses the requested fallback', () => {
    expect(safeInternalPath('//example.com', '/upload')).toBe('/upload');
  });
});
