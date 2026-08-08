import { describe, expect, it } from 'vitest';
import type { Mapping } from '../api/types';
import {
    defaultMappingStatusFilter,
    nextMappingSortMode,
    sortMappings,
    sortMappingsBySmartRank,
} from './mappingFilters';

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

describe('sortMappings', () => {
    const sortable = (
        id: number,
        rawColumn: string,
        confidence: number | null,
        stage: Mapping['stage'],
    ): Mapping => ({
        ...mapping(id, 'pending'),
        raw_column: rawColumn,
        confidence_score: confidence,
        stage,
    });

    const rows = [
        sortable(1, 'beta', 0.8, 'stage3'),
        sortable(2, 'alpha', 0.2, 'stage1'),
        sortable(3, 'gamma', null, null),
        sortable(4, 'delta', 0.5, 'stage2'),
    ];

    it('sorts confidence in either direction and keeps missing values last', () => {
        expect(sortMappings(rows, 'confidence_score', false).map((row) => row.id)).toEqual([1, 4, 2, 3]);
        expect(sortMappings(rows, 'confidence_score', true).map((row) => row.id)).toEqual([2, 4, 1, 3]);
    });

    it('uses the harmonization stage order instead of lexical ordering', () => {
        expect(sortMappings(rows, 'stage', true).map((row) => row.id)).toEqual([2, 4, 1, 3]);
        expect(sortMappings(rows, 'stage', false).map((row) => row.id)).toEqual([1, 4, 2, 3]);
    });

    it('sorts raw columns deterministically', () => {
        expect(sortMappings(rows, 'raw_column', true).map((row) => row.raw_column)).toEqual([
            'alpha',
            'beta',
            'delta',
            'gamma',
        ]);
    });
});

describe('smart review sorting', () => {
    it('cycles smart to descending to ascending and back to smart', () => {
        expect(nextMappingSortMode('smart', true)).toBe('descending');
        expect(nextMappingSortMode('descending', true)).toBe('ascending');
        expect(nextMappingSortMode('ascending', true)).toBe('smart');
        expect(nextMappingSortMode('ascending', false)).toBe('descending');
    });

    it('uses server smart-review rank and places unranked rows last', () => {
        const rows = [mapping(1, 'pending'), mapping(2, 'pending'), mapping(3, 'accepted')];
        expect(sortMappingsBySmartRank(rows, { 1: 1, 2: 0 }).map((row) => row.id)).toEqual([2, 1, 3]);
    });
});