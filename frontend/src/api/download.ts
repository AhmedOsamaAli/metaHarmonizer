import { apiFetchResponse } from './http';

const REVOKE_DELAY_MS = 60_000;

export function filenameFromContentDisposition(
    contentDisposition: string | null,
    fallback: string,
): string {
    if (!contentDisposition) return fallback;

    const encoded = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)?.[1];
    if (encoded) {
        try {
            return decodeURIComponent(encoded.trim());
        } catch {
            return fallback;
        }
    }

    const quoted = contentDisposition.match(/filename\s*=\s*"([^"]+)"/i)?.[1];
    if (quoted) return quoted;
    return contentDisposition.match(/filename\s*=\s*([^;]+)/i)?.[1]?.trim() || fallback;
}

export async function downloadApiFile(path: string, fallbackFilename: string): Promise<void> {
    const response = await apiFetchResponse(path);
    const blob = await response.blob();
    if (blob.size === 0) throw new Error('The server returned an empty file.');

    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filenameFromContentDisposition(
        response.headers.get('content-disposition'),
        fallbackFilename,
    );
    anchor.hidden = true;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    // Chromium may consume blob URLs asynchronously after click dispatch.
    globalThis.setTimeout(() => URL.revokeObjectURL(objectUrl), REVOKE_DELAY_MS);
}
