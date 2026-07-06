import { describe, it, expect } from 'vitest';
import { parseDelimitedPreview } from './parseDelimited';

function fileFrom(name: string, content: string): File {
  return new File([content], name, { type: 'text/plain' });
}

describe('parseDelimitedPreview', () => {
  it('parses a header and quoted CSV fields (commas + escaped quotes)', async () => {
    const csv = 'name,age\n"Doe, John",30\n"He said ""hi""",40\n';
    const res = await parseDelimitedPreview(fileFrom('people.csv', csv));

    expect(res.delimiter).toBe(',');
    expect(res.columns).toEqual(['name', 'age']);
    expect(res.rows[0]).toEqual(['Doe, John', '30']);
    expect(res.rows[1]).toEqual(['He said "hi"', '40']);
  });

  it('detects tab delimiter from a .tsv filename', async () => {
    const tsv = 'col_a\tcol_b\n1\t2\n';
    const res = await parseDelimitedPreview(fileFrom('data.tsv', tsv));

    expect(res.delimiter).toBe('\t');
    expect(res.columns).toEqual(['col_a', 'col_b']);
    expect(res.rows[0]).toEqual(['1', '2']);
  });

  it('caps the preview at maxRows and flags truncation', async () => {
    const header = 'x\n';
    const body = Array.from({ length: 10 }, (_, i) => String(i)).join('\n');
    const res = await parseDelimitedPreview(fileFrom('big.csv', header + body), 3);

    expect(res.rows.length).toBeLessThanOrEqual(3);
    expect(res.truncated).toBe(true);
  });
});
