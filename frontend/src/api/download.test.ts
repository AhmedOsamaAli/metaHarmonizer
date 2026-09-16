import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetchResponse } from './http';
import { downloadApiFile, filenameFromContentDisposition } from './download';

vi.mock('./http', () => ({
  apiFetchResponse: vi.fn(),
}));

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('filenameFromContentDisposition', () => {
  it('reads quoted and UTF-8 filenames', () => {
    expect(filenameFromContentDisposition('attachment; filename="result.csv"', 'fallback.csv'))
      .toBe('result.csv');
    expect(filenameFromContentDisposition(
      "attachment; filename*=UTF-8''harmonized%20result.csv",
      'fallback.csv',
    )).toBe('harmonized result.csv');
  });

  it('uses the fallback for missing or malformed values', () => {
    expect(filenameFromContentDisposition(null, 'fallback.csv')).toBe('fallback.csv');
    expect(filenameFromContentDisposition(
      "attachment; filename*=UTF-8''bad%ZZname",
      'fallback.csv',
    )).toBe('fallback.csv');
  });
});

describe('downloadApiFile', () => {
  it('downloads the authenticated blob and revokes its URL after a delay', async () => {
    vi.useFakeTimers();
    vi.mocked(apiFetchResponse).mockResolvedValue(new Response('a,b\n1,2\n', {
      headers: { 'content-disposition': 'attachment; filename="harmonized.csv"' },
    }));
    const click = vi.fn();
    const remove = vi.fn();
    const appendChild = vi.fn();
    const anchor = { href: '', download: '', hidden: false, click, remove };
    vi.stubGlobal('document', {
      createElement: vi.fn().mockReturnValue(anchor),
      body: { appendChild },
    });
    const createObjectURL = vi.fn().mockReturnValue('blob:download');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });

    await downloadApiFile('/export/study/harmonized', 'fallback.csv');

    expect(apiFetchResponse).toHaveBeenCalledWith('/export/study/harmonized');
    expect(anchor).toMatchObject({
      href: 'blob:download',
      download: 'harmonized.csv',
      hidden: true,
    });
    expect(appendChild).toHaveBeenCalledWith(anchor);
    expect(click).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();
    await vi.runAllTimersAsync();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:download');
  });

  it('rejects an empty response instead of starting a broken download', async () => {
    vi.mocked(apiFetchResponse).mockResolvedValue(new Response(new Blob([])));

    await expect(downloadApiFile('/export/study/harmonized', 'fallback.csv'))
      .rejects.toThrow('empty file');
  });
});
