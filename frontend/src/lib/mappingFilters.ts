import type { Mapping } from '../api/types';

export type MappingStatusFilter = 'all' | 'pending' | 'accepted' | 'rejected';
export type MappingSortKey = 'raw_column' | 'confidence_score' | 'stage' | 'status';
export type MappingSortMode = 'smart' | 'descending' | 'ascending';

const STAGE_RANK: Record<string, number> = {
    stage1: 0,
    stage2: 1,
    stage3: 2,
    stage4: 3,
    invalid: 4,
    unmapped: 5,
};

export function defaultMappingStatusFilter(
    mappings: Mapping[],
    requested?: MappingStatusFilter | null,
): MappingStatusFilter {
    if (requested) return requested;
    if (mappings.some((mapping) => mapping.status === 'pending')) return 'pending';
    return mappings.length > 0 ? 'all' : 'pending';
}

export function sortMappings(
    mappings: Mapping[],
    key: MappingSortKey,
    ascending: boolean,
): Mapping[] {
    const value = (mapping: Mapping): string | number | null => {
        if (key === 'stage') return mapping.stage ? (STAGE_RANK[mapping.stage] ?? null) : null;
        return mapping[key];
    };

    return [...mappings].sort((left, right) => {
        const leftValue = value(left);
        const rightValue = value(right);
        if (leftValue === null && rightValue === null) {
            return left.raw_column.localeCompare(right.raw_column);
        }
        if (leftValue === null) return 1;
        if (rightValue === null) return -1;

        const comparison = typeof leftValue === 'number'
            ? leftValue - (rightValue as number)
            : leftValue.localeCompare(rightValue as string);
        if (comparison === 0) return left.raw_column.localeCompare(right.raw_column);
        return ascending ? comparison : -comparison;
    });
}

export function nextMappingSortMode(
    current: MappingSortMode,
    sameColumn: boolean,
): MappingSortMode {
    if (!sameColumn || current === 'smart') return 'descending';
    if (current === 'descending') return 'ascending';
    return 'smart';
}

export function sortMappingsBySmartRank(
    mappings: Mapping[],
    rankById: Readonly<Record<number, number>>,
): Mapping[] {
    return [...mappings].sort((left, right) => {
        const rankDifference = (rankById[left.id] ?? Number.MAX_SAFE_INTEGER)
            - (rankById[right.id] ?? Number.MAX_SAFE_INTEGER);
        return rankDifference || left.raw_column.localeCompare(right.raw_column);
    });
}