/*
 * Guest-preview sample data.
 *
 * In the no-account preview we never hit the backend (see http.ts). To let a
 * visitor see what a *curated* study actually looks like, apiFetch serves these
 * fixtures for GET requests while in guest mode. Numbers mirror a real
 * CPTAC -> GDC harmonization so the walkthrough feels authentic.
 *
 * Only types are imported here (no runtime deps) to avoid an import cycle with
 * the HTTP layer.
 */
import type {
    Mapping,
    OntologyMapping,
    Overview,
    QualityMetrics,
    Study,
} from './types';

export const DEMO_STUDY_ID = 'DEMO-CPTAC';

const REVIEWED = '2026-07-12T10:00:00Z';

const demoStudy: Study = {
    id: DEMO_STUDY_ID,
    name: 'CPTAC Endometrial Carcinoma (preview)',
    upload_date: '2026-07-12T09:00:00Z',
    status: 'completed',
    row_count: 153,
    column_count: 24,
};

const m = (
    id: number,
    raw_column: string,
    matched_field: string | null,
    confidence_score: number,
    stage: string,
    status: string,
    alternatives: { field: string; score: number }[] = [],
): Mapping => ({
    id,
    study_id: DEMO_STUDY_ID,
    raw_column,
    matched_field,
    confidence_score,
    stage,
    method: stage === 'stage1' ? 'dictionary' : stage === 'stage2' ? 'sentence-transformer' : 'type-inference',
    alternatives,
    status,
    curator_field: null,
    curator_note: null,
    reviewed_at: status === 'pending' ? null : REVIEWED,
    reviewed_by: status === 'pending' ? null : 'Demo Curator',
});

const demoMappings: Mapping[] = [
    m(1, 'tumor_site', 'primary_site', 1.0, 'stage1', 'accepted'),
    m(2, 'Histologic_Type', 'morphology', 1.0, 'stage1', 'accepted'),
    m(3, 'FIGO_stage', 'figo_stage', 1.0, 'stage1', 'accepted'),
    m(4, 'MSI_status', 'msi_status', 1.0, 'stage1', 'accepted'),
    m(5, 'sex', 'gender', 1.0, 'stage1', 'accepted'),
    m(6, 'BMI', 'bmi', 1.0, 'stage1', 'accepted'),
    m(7, 'vital_status', 'vital_status', 1.0, 'stage1', 'accepted'),
    m(8, 'race', 'race', 1.0, 'stage1', 'accepted'),
    m(9, 'Tumor_Stage_Pathological', 'uicc_pathologic_t', 0.96, 'stage1', 'accepted'),
    m(10, 'tobacco_smoking_status', 'tobacco_smoking_status', 1.0, 'stage1', 'accepted'),
    m(11, 'age', 'age_at_diagnosis', 0.88, 'stage2', 'pending', [
        { field: 'age_at_index', score: 0.83 },
        { field: 'days_to_birth', score: 0.61 },
    ]),
    m(12, 'diagnosis', 'primary_diagnosis', 0.82, 'stage2', 'pending', [
        { field: 'morphology', score: 0.74 },
    ]),
    m(13, 'residual_tumor', 'residual_disease', 0.79, 'stage2', 'pending', [
        { field: 'ajcc_pathologic_stage', score: 0.55 },
    ]),
    m(14, 'TMT_channel', null, 0.21, 'stage3', 'pending'),
    m(15, 'peptide_ratio_norm', null, 0.18, 'stage3', 'pending'),
];

const reviewQueueItems = demoMappings
    .filter((x) => x.status === 'pending')
    .map((x) => ({
        ...x,
        group_key: x.matched_field ?? 'unmapped',
        group_size: 1,
        group_min_confidence: x.confidence_score ?? 0,
    }));

const demoReviewQueue = {
    items: reviewQueueItems,
    stats: {
        pending: reviewQueueItems.length,
        groups: reviewQueueItems.length,
        batchable_groups: 0,
        risky: demoMappings.filter((x) => (x.confidence_score ?? 0) < 0.5).length,
    },
};

const o = (
    id: number,
    field_name: string,
    raw_value: string,
    ontology_term: string | null,
    ontology_id: string | null,
    confidence_score: number,
    status: string,
): OntologyMapping => ({
    id,
    study_id: DEMO_STUDY_ID,
    field_name,
    raw_value,
    ontology_term,
    ontology_id,
    confidence_score,
    status,
    curator_term: null,
    curator_id: null,
});

const demoOntology: OntologyMapping[] = [
    o(1, 'disease', 'Endometrial Carcinoma', 'Endometrial Carcinoma', 'NCIT:C7364', 1.0, 'accepted'),
    o(2, 'disease', 'Serous Carcinoma', 'Serous Adenocarcinoma', 'NCIT:C7570', 0.94, 'accepted'),
    o(3, 'disease', 'Endometrioid Adenocarcinoma', 'Endometrioid Adenocarcinoma', 'NCIT:C6287', 1.0, 'accepted'),
    o(4, 'body_site', 'uterus', 'uterus', 'UBERON:0000995', 1.0, 'accepted'),
    o(5, 'body_site', 'endometrium', 'endometrium', 'UBERON:0001295', 1.0, 'accepted'),
    o(6, 'disease', 'Clear Cell Carcinoma', null, null, 0.42, 'pending'),
];

const demoStudySummary = {
    id: DEMO_STUDY_ID,
    name: demoStudy.name,
    status: 'completed',
    row_count: demoStudy.row_count ?? 153,
    column_count: demoStudy.column_count ?? 24,
    mapped_columns: 13,
    pending_review: 5,
    avg_confidence: 0.82,
    review_progress: 66,
};

const demoOverview: Overview = {
    total_studies: 1,
    total_columns: 24,
    total_rows: 153,
    mapped_columns: 13,
    pending_review: 5,
    accepted: 10,
    rejected: 0,
    avg_confidence: 0.82,
    review_progress: 66,
    stage_breakdown: [
        { stage: 'stage1', count: 10, percentage: 41.7 },
        { stage: 'stage2', count: 3, percentage: 12.5 },
        { stage: 'stage3', count: 2, percentage: 8.3 },
        { stage: 'unmapped', count: 9, percentage: 37.5 },
    ],
    studies: [demoStudySummary],
};

const demoQuality: QualityMetrics = {
    study_id: DEMO_STUDY_ID,
    total_columns: 24,
    mapped_columns: 13,
    unmapped_columns: 11,
    avg_confidence: 0.82,
    auto_accepted: 10,
    pending_review: 5,
    rejected: 0,
    new_field_suggestions: 2,
    stage_breakdown: demoOverview.stage_breakdown,
    confidence_distribution: [
        { bucket: '0.9–1.0', min_val: 0.9, max_val: 1.0, count: 10 },
        { bucket: '0.7–0.9', min_val: 0.7, max_val: 0.9, count: 3 },
        { bucket: '0.5–0.7', min_val: 0.5, max_val: 0.7, count: 0 },
        { bucket: '< 0.5', min_val: 0, max_val: 0.5, count: 2 },
    ],
};

/** Return a canned response for a GET while in guest preview, or null if the
 *  path has no fixture (caller then blocks the call). Writes always get null. */
export function guestFixture(path: string, method: string): { data: unknown } | null {
    if (method.toUpperCase() !== 'GET') return null;
    const p = path.split('?')[0];
    switch (p) {
        case '/overview':
            return { data: demoOverview };
        case '/studies':
            return { data: [demoStudy] };
        case `/studies/${DEMO_STUDY_ID}`:
            return { data: demoStudy };
        case `/mappings/${DEMO_STUDY_ID}`:
            return { data: demoMappings };
        case `/mappings/${DEMO_STUDY_ID}/review-queue`:
            return { data: demoReviewQueue };
        case `/ontology/mappings/${DEMO_STUDY_ID}`:
            return { data: demoOntology };
        case `/quality/${DEMO_STUDY_ID}`:
            return { data: demoQuality };
        case '/schema-versions':
        case '/target-schemas':
            return { data: [] };
        default:
            return null;
    }
}
