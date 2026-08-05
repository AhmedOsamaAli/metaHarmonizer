import { apiFetch } from './http';

export interface FederationRecord {
    record_type: 'schema_mapping' | 'ontology_mapping';
    raw_key: string;
    decision: 'accept' | 'reject';
    accepted_target: string;
    ontology_id: string | null;
    confidence_score: number | null;
    dedup_key?: string;
}

export interface FederationBundle {
    payload: {
        bundle_version: number;
        source_instance: string;
        created_at: string;
        mappings: FederationRecord[];
    };
    signature: string;
    source_instance: string;
    public_key: string;
}

export interface FederationImportSummary {
    id: number;
    source_instance: string;
    signature_valid: boolean;
    status: 'pending' | 'approved' | 'rejected';
    mapping_count: number;
    imported_by?: number | null;
    reviewed_by?: number | null;
    reviewed_at?: string | null;
    created_at?: string | null;
}

export async function exportFederationBundle(): Promise<FederationBundle> {
    return apiFetch<FederationBundle>('/federation/export');
}

export async function importFederationBundle(
    bundle: FederationBundle,
): Promise<FederationImportSummary> {
    return apiFetch<FederationImportSummary>('/federation/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bundle),
    });
}

export async function listFederationImports(): Promise<FederationImportSummary[]> {
    return apiFetch<FederationImportSummary[]>('/federation/imports');
}

export async function approveFederationImport(id: number): Promise<FederationImportSummary> {
    return apiFetch<FederationImportSummary>(`/federation/imports/${id}/approve`, {
        method: 'POST',
    });
}

export async function rejectFederationImport(id: number): Promise<FederationImportSummary> {
    return apiFetch<FederationImportSummary>(`/federation/imports/${id}/reject`, {
        method: 'POST',
    });
}
