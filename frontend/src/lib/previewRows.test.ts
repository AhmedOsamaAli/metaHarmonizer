import { describe, expect, it } from 'vitest';
import { COMPACT_PREVIEW_ROWS, compactPreviewRows } from './previewRows';

describe('compactPreviewRows', () => {
    it('fills the compact preview with up to ten rows', () => {
        const rows = Array.from({ length: 15 }, (_, index) => index);
        expect(compactPreviewRows(rows)).toEqual(rows.slice(0, 10));
        expect(COMPACT_PREVIEW_ROWS).toBe(10);
    });

    it('keeps every row when the sample is shorter', () => {
        expect(compactPreviewRows([1, 2, 3])).toEqual([1, 2, 3]);
    });
});