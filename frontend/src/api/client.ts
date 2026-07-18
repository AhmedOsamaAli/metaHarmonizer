// API client — centralised HTTP layer every component calls into.

import { apiFetch, BASE } from './http';
import type {
    AuditEvent,
    HarmonizationResults,
    HarmonizeAccepted,
    Mapping,
    OntologyMapping,
    OntologySearchResult,
    Overview,
    Paginated,
    QualityMetrics,
    Study,
} from './types';

/** Thin wrapper kept for backwards compatibility: routes legacy `${BASE}/x`
 *  paths through the shared auth-aware fetch (bearer token + 401 refresh). */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
    const path = url.startsWith(BASE) ? url.slice(BASE.length) : url;
    return apiFetch<T>(path, init);
}

/* ---------- Studies ---------- */

export async function listStudies(): Promise<Study[]> {
    return request<Study[]>(`${BASE}/studies`);
}

export async function getOverview(): Promise<Overview> {
    return request<Overview>(`${BASE}/overview`);
}

export async function getStudy(id: string): Promise<Study> {
    return request<Study>(`${BASE}/studies/${id}`);
}

export async function deleteStudy(id: string): Promise<void> {
    await request<void>(`${BASE}/studies/${id}`, { method: 'DELETE' });
}

export async function completeStudy(id: string): Promise<Study> {
    return request<Study>(`${BASE}/studies/${id}/complete`, { method: 'POST' });
}

/* ---------- Harmonize ---------- */

export type HarmonizeMode = 'both' | 'schema' | 'ontology';

export interface HarmonizeOptions {
    /** Which mappers to run. Default 'both'. */
    mode?: HarmonizeMode;
    /** Registered target-schema version to map against. Omit for current. */
    schemaVersionId?: number;
    /** Engine target schema to map into (GDC / cBioPortal / cMD / …). */
    targetSchema?: string;
    /** Column allow-list that scopes the ontology pass (required for 'ontology'). */
    ontologyColumns?: string[];
}

export interface TargetSchema {
    id: number;
    label: string;
    is_current: boolean;
    source_path?: string;
    created_at?: string | null;
}

/** Registered target schemas the curator can map an upload against. */
export async function listTargetSchemas(): Promise<TargetSchema[]> {
    return request<TargetSchema[]>(`${BASE}/schema-versions`);
}

export interface EngineTargetSchema {
    key: string;
    label: string;
    fields: number;
}

/** Target schemas the engine can map into (GDC / cBioPortal / cMD / …). */
export async function listEngineTargetSchemas(): Promise<EngineTargetSchema[]> {
    return request<EngineTargetSchema[]>(`${BASE}/target-schemas`);
}

export async function uploadAndHarmonize(
    file: File,
    opts: HarmonizeOptions = {},
): Promise<HarmonizeAccepted> {
    const form = new FormData();
    form.append('file', file);
    if (opts.mode) form.append('mode', opts.mode);
    if (opts.schemaVersionId != null)
        form.append('schema_version_id', String(opts.schemaVersionId));
    if (opts.targetSchema) form.append('target_schema', opts.targetSchema);
    if (opts.ontologyColumns?.length)
        form.append('ontology_columns', opts.ontologyColumns.join(','));
    return request<HarmonizeAccepted>(`${BASE}/harmonize`, {
        method: 'POST',
        body: form,
    });
}

export async function getHarmonizationResults(
    jobId: string,
): Promise<HarmonizationResults> {
    return request<HarmonizationResults>(`${BASE}/harmonize/${jobId}`);
}

/* ---------- Mappings ---------- */

export async function getStudyMappings(studyId: string): Promise<Mapping[]> {
    return request<Mapping[]>(`${BASE}/mappings/${studyId}`);
}

/** Active-learning review queue (G7): pending mappings ordered risky-first and
 * grouped by suggested target so look-alikes are adjacent and batchable. */
export interface ReviewQueueItem extends Mapping {
    group_key: string;
    group_size: number;
    group_min_confidence: number;
}
export interface ReviewQueue {
    items: ReviewQueueItem[];
    stats: { pending: number; groups: number; batchable_groups: number; risky: number };
}
export async function getReviewQueue(studyId: string): Promise<ReviewQueue> {
    return request<ReviewQueue>(`${BASE}/mappings/${studyId}/review-queue`);
}

export interface ColumnContext {
    study_id: string;
    column: string;
    total_rows: number;
    distinct_values: number;
    null_count: number;
    samples: { value: string; count: number }[];
}

/** Sample distinct values for one raw column — context to help pick a term. */
export async function getColumnContext(
    studyId: string,
    column: string,
    limit = 15,
): Promise<ColumnContext> {
    return request<ColumnContext>(
        `${BASE}/mappings/${studyId}/columns/${encodeURIComponent(column)}/context?limit=${limit}`,
    );
}

export async function acceptMapping(mappingId: number, remember = false): Promise<Mapping> {
    return request<Mapping>(`${BASE}/mappings/${mappingId}/accept?remember=${remember}`, {
        method: 'POST',
    });
}

export async function rejectMapping(mappingId: number): Promise<Mapping> {
    return request<Mapping>(`${BASE}/mappings/${mappingId}/reject`, {
        method: 'POST',
    });
}

export async function editMapping(
    mappingId: number,
    newField: string,
    note = '',
    remember = false,
): Promise<Mapping> {
    return request<Mapping>(`${BASE}/mappings/${mappingId}/edit?remember=${remember}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_field: newField, note }),
    });
}

export async function batchUpdateMappings(
    mappingIds: number[],
    action: 'accepted' | 'rejected',
): Promise<{ updated: number; action: string }> {
    return request(`${BASE}/mappings/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping_ids: mappingIds, action }),
    });
}

/** On-demand Stage-4 LLM rematch for one column. Requires GEMINI_API_KEY on the
 * server; surfaces a clear error otherwise. Returns ranked field suggestions. */
export async function llmRematch(
    mappingId: number,
): Promise<{ field: string; confidence: number; reasoning: string }[]> {
    const res = await request<{
        suggestions: { field: string; confidence: number; reasoning: string }[];
    }>(`${BASE}/mappings/${mappingId}/llm`, { method: 'POST' });
    return res.suggestions ?? [];
}

/* ---------- Quality ---------- */

export async function getQualityMetrics(studyId: string): Promise<QualityMetrics> {
    return request<QualityMetrics>(`${BASE}/quality/${studyId}`);
}

/* ---------- Ontology ---------- */

export async function searchOntology(
    query: string,
    ontology = '',
): Promise<OntologySearchResult[]> {
    const params = new URLSearchParams({ query });
    if (ontology) params.set('ontology', ontology);
    return request<OntologySearchResult[]>(`${BASE}/ontology/search?${params}`);
}

export async function getOntologyMappings(
    studyId: string,
): Promise<OntologyMapping[]> {
    return request<OntologyMapping[]>(`${BASE}/ontology/mappings/${studyId}`);
}

/** Batch-suggest ontology terms for a study's unmatched values in one request.
 * Returns a map of mapping id → best candidate term/id/score. */
export async function suggestOntologyTerms(
    studyId: string,
): Promise<Record<string, { term: string; ontology_id: string; score: number }>> {
    const res = await request<{
        suggestions: Record<string, { term: string; ontology_id: string; score: number }>;
    }>(`${BASE}/ontology/suggest/${studyId}`, { method: 'POST' });
    return res.suggestions ?? {};
}

export async function acceptOntologyMapping(id: number, remember = false): Promise<OntologyMapping> {
    return request<OntologyMapping>(`${BASE}/ontology/mappings/${id}/accept?remember=${remember}`, { method: 'POST' });
}

export async function rejectOntologyMapping(id: number): Promise<OntologyMapping> {
    return request<OntologyMapping>(`${BASE}/ontology/mappings/${id}/reject`, { method: 'POST' });
}

export async function editOntologyMapping(
    id: number,
    newTerm: string,
    newId = '',
    remember = false,
): Promise<OntologyMapping> {
    return request<OntologyMapping>(`${BASE}/ontology/mappings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_term: newTerm, new_id: newId || undefined, remember }),
    });
}

/* ---------- Export ---------- */

export function getExportUrl(
    studyId: string,
    format: 'harmonized' | 'cbioportal' | 'cbioportal-study' | 'report',
): string {
    return `${BASE}/export/${studyId}/${format}`;
}

/** Labeled-dataset export (confirmed mappings) — CSV or JSONL (G9). */
export function getLabeledExportUrl(
    studyId: string,
    format: 'csv' | 'jsonl' = 'csv',
): string {
    return `${BASE}/export/${studyId}/labeled?format=${format}`;
}

/* ---------- Audit (admin) ---------- */

export async function queryAudit(params: {
    action?: string;
    study_id?: string;
    actor_id?: number;
    since?: string;
    until?: string;
    cursor?: string;
    limit?: number;
}): Promise<Paginated<AuditEvent>> {
    const qs = new URLSearchParams();
    if (params.action) qs.set('action', params.action);
    if (params.study_id) qs.set('study_id', params.study_id);
    if (params.actor_id != null) qs.set('actor_id', String(params.actor_id));
    if (params.since) qs.set('since', params.since);
    if (params.until) qs.set('until', params.until);
    if (params.cursor) qs.set('cursor', params.cursor);
    if (params.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return request<Paginated<AuditEvent>>(`${BASE}/audit${q ? `?${q}` : ''}`);
}
