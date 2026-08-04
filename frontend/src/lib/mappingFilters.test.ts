import { describe, expect, it } from 'vitest';
import type { Mapping } from '../api/types';
import { defaultMappingStatusFilter } from './mappingFilters';

const mapping = (id: number, status: Mapping['status']): Mapping => ({
    id,
    study_id: 'study',
    raw_column: `column_${id}`,
    matched_field: null,
    confidence_score: null,
    stage: null,
    method: null,
    alternatives: [],
    status,
    curator_field: null,
    curator_note: null,
    reviewed_at: null,
    reviewed_by: null,
});

describe('defaultMappingStatusFilter', () => {
    it('shows pending work when it exists', () => {
        expect(
            defaultMappingStatusFilter([
                mapping(1, 'accepted'),
                mapping(2, 'pending'),
            ]),
        ).toBe('pending');
    });

    it('shows reviewed rows when no pending work remains', () => {
        expect(defaultMappingStatusFilter([mapping(1, 'accepted')])).toBe('all');
    });

    it('honors an explicit deep-link filter', () => {
        expect(defaultMappingStatusFilter([mapping(1, 'accepted')], 'pending')).toBe('pending');
    });
});