import { describe, expect, it, vi } from 'vitest';
import {
  hasRememberedPhiConsent,
  PHI_UPLOAD_CONSENT_KEY,
  rememberPhiConsent,
} from './uploadConsent';

describe('upload PHI consent storage', () => {
  it('remembers only the explicit accepted value', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };

    expect(hasRememberedPhiConsent(storage)).toBe(false);
    rememberPhiConsent(storage);
    expect(values.get(PHI_UPLOAD_CONSENT_KEY)).toBe('accepted');
    expect(hasRememberedPhiConsent(storage)).toBe(true);
  });

  it('fails closed when storage is unavailable', () => {
    const storage = {
      getItem: vi.fn(() => {
        throw new Error('blocked');
      }),
      setItem: vi.fn(() => {
        throw new Error('blocked');
      }),
    };

    expect(hasRememberedPhiConsent(storage)).toBe(false);
    expect(() => rememberPhiConsent(storage)).not.toThrow();
  });
});