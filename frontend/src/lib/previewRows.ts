export const COMPACT_PREVIEW_ROWS = 10;

export function compactPreviewRows<T>(rows: T[]): T[] {
    return rows.slice(0, COMPACT_PREVIEW_ROWS);
}