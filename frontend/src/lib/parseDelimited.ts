// Dependency-free delimited-file parser: previews an upload's columns
// client-side (handles quoted fields, escaped quotes, embedded newlines).

export interface ParsedPreview {
  columns: string[];
  rows: string[][];
  /** Total data rows actually scanned (may equal maxRows if truncated). */
  scannedRows: number;
  /** True when the file had more rows than we parsed for the preview. */
  truncated: boolean;
  delimiter: ',' | '\t';
}

/** Pick a delimiter from the filename / first line (CSV vs TSV). */
function detectDelimiter(name: string, firstLine: string): ',' | '\t' {
  const lower = name.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.txt')) return '\t';
  if (lower.endsWith('.csv')) return ',';
  // Fall back to whichever appears more on the header line.
  const tabs = (firstLine.match(/\t/g) || []).length;
  const commas = (firstLine.match(/,/g) || []).length;
  return tabs > commas ? '\t' : ',';
}

/** Parse a single delimited line, honouring double-quoted fields. */
function parseLine(line: string, delim: string): string[] {
  const out: string[] = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === delim) {
      out.push(field);
      field = '';
    } else {
      field += ch;
    }
  }
  out.push(field);
  return out;
}

/**
 * Read a File's first ~chunk and parse a header + up to ``maxRows`` data rows.
 * Reads at most ``maxBytes`` so a huge upload doesn't freeze the browser.
 */
export async function parseDelimitedPreview(
  file: File,
  maxRows = 50,
  maxBytes = 2 * 1024 * 1024,
): Promise<ParsedPreview> {
  const blob = file.size > maxBytes ? file.slice(0, maxBytes) : file;
  const text = await blob.text();

  // Split into logical lines, keeping quoted newlines together.
  const lines: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
      current += ch;
    } else if ((ch === '\n' || ch === '\r') && !inQuotes) {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      lines.push(current);
      current = '';
      // Stop early once we have header + maxRows + a little slack.
      if (lines.length > maxRows + 1) break;
    } else {
      current += ch;
    }
  }
  if (current && lines.length <= maxRows + 1) lines.push(current);

  const nonEmpty = lines.filter((l) => l.length > 0);
  const delimiter = detectDelimiter(file.name, nonEmpty[0] ?? '');

  const columns = nonEmpty.length ? parseLine(nonEmpty[0], delimiter) : [];
  const rows = nonEmpty.slice(1, maxRows + 1).map((l) => parseLine(l, delimiter));

  return {
    columns,
    rows,
    scannedRows: rows.length,
    truncated: file.size > maxBytes || nonEmpty.length > maxRows + 1,
    delimiter,
  };
}
