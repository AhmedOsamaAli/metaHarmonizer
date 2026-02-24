/* ------------------------------------------------------------------ */
/*  MetaHarmonizer Dashboard — TypeScript Types                       */
/* ------------------------------------------------------------------ */

export interface Study {
    id: string;
    name: string;
    upload_date: string;
    status: string;
    file_path?: string;
    row_count?: number;
    column_count?: number;
}

export interface AlternativeMatch {
    field: string;
    score: number;
    method?: string;
}

export interface Mapping {
    id: number;
    study_id: string;
    raw_column: string;
    matched_field: string | null;
    confidence_score: number | null;
    stage: string | null;
    method: string | null;
    alternatives: AlternativeMatch[];
    status: string;
    curator_field: string | null;
    curator_note: string | null;
    reviewed_at: string | null;
    reviewed_by: string | null;
}

export interface OntologyMapping {
    id: number;
    study_id: string;
    field_name: string;
    raw_value: string;
    ontology_term: string | null;
    ontology_id: string | null;
    confidence_score: number | null;
    status: string;
}

export interface StageBreakdown {
    stage: string;
    count: number;
    percentage: number;
}

export interface ConfidenceBucket {
    bucket: string;
    min_val: number;
    max_val: number;
    count: number;
}

export interface QualityMetrics {
    study_id: string;
    total_columns: number;
    mapped_columns: number;
    unmapped_columns: number;
    avg_confidence: number;
    auto_accepted: number;
    pending_review: number;
    rejected: number;
    new_field_suggestions: number;
    stage_breakdown: StageBreakdown[];
    confidence_distribution: ConfidenceBucket[];
}

export interface HarmonizeResponse {
    job_id: string;
    status: string;
    study_name: string;
    row_count: number;
    column_count: number;
    message: string;
}

export interface HarmonizationResults {
    study: Study;
    mappings: Mapping[];
    total: number;
}

export interface OntologySearchResult {
    term: string;
    ontology_id: string;
    ontology: string;
    score: number;
}
