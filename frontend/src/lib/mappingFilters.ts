import type { Mapping } from '../api/types';

export type MappingStatusFilter = 'all' | 'pending' | 'accepted' | 'rejected';

export function defaultMappingStatusFilter(
    mappings: Mapping[],
    requested?: MappingStatusFilter | null,
): MappingStatusFilter {
    if (requested) return requested;
    if (mappings.some((mapping) => mapping.status === 'pending')) return 'pending';
    return mappings.length > 0 ? 'all' : 'pending';
}