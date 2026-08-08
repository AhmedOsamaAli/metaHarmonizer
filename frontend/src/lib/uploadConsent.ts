export const PHI_UPLOAD_CONSENT_KEY = 'metaharmonizer.phi-upload-consent.v1';

type ConsentStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function hasRememberedPhiConsent(storage: ConsentStorage): boolean {
  try {
    return storage.getItem(PHI_UPLOAD_CONSENT_KEY) === 'accepted';
  } catch {
    return false;
  }
}

export function rememberPhiConsent(storage: ConsentStorage): void {
  try {
    storage.setItem(PHI_UPLOAD_CONSENT_KEY, 'accepted');
  } catch {
    return;
  }
}