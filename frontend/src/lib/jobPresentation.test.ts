import { describe, expect, it } from 'vitest';
import { activeJobMessage } from './jobPresentation';

describe('activeJobMessage', () => {
    it('describes queued work without claiming progress', () => {
        expect(activeJobMessage('queued')).toBe('Waiting for an available worker…');
    });

    it('describes processing without a misleading percentage', () => {
        const message = activeJobMessage('processing');
        expect(message).toBe('Processing…');
        expect(message).not.toContain('%');
    });
});