<?php

/*
 * This file is part of FeatherPanel.
 *
 * Copyright (C) 2025 MythicalSystems Studios
 * Copyright (C) 2025 FeatherPanel Contributors
 * Copyright (C) 2025 Cassian Gherman (aka NaysKutzu)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published
 * by the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * See the LICENSE file or <https://www.gnu.org/licenses/>.
 */

namespace App\Services\FreeServers;

/**
 * Picks the node for a new free server. A node fits when it is not in maintenance, has a free
 * allocation, and the new server stays within its memory and disk limits (the physical amount
 * plus the overallocate percentage; -1 means no limit). Fitting nodes are tried emptiest first.
 */
final class FreeServerPlacement
{
    /**
     * @param list<array<string, mixed>> $nodes Rows with id, memory, memory_overallocate, disk,
     *                                          disk_overallocate, maintenance_mode, memory_used,
     *                                          disk_used and free_allocations
     *
     * @return list<int> Node ids in the order to try them
     */
    public static function rank(array $nodes, int $memory, int $disk): array
    {
        $fits = [];
        foreach ($nodes as $node) {
            if (self::truthy($node['maintenance_mode'] ?? false) || (int) ($node['free_allocations'] ?? 0) < 1) {
                continue;
            }
            $memoryLimit = self::limit((int) ($node['memory'] ?? 0), (int) ($node['memory_overallocate'] ?? 0));
            $diskLimit = self::limit((int) ($node['disk'] ?? 0), (int) ($node['disk_overallocate'] ?? 0));
            $memoryAfter = (int) ($node['memory_used'] ?? 0) + $memory;
            $diskAfter = (int) ($node['disk_used'] ?? 0) + $disk;
            if (($memoryLimit !== null && $memoryAfter > $memoryLimit) || ($diskLimit !== null && $diskAfter > $diskLimit)) {
                continue;
            }
            // Share of memory still free after placing the server; unlimited nodes sort first.
            $headroom = $memoryLimit === null || $memoryLimit <= 0 ? PHP_FLOAT_MAX : ($memoryLimit - $memoryAfter) / $memoryLimit;
            $fits[] = ['id' => (int) $node['id'], 'headroom' => $headroom, 'free' => (int) $node['free_allocations']];
        }
        usort($fits, static function (array $a, array $b): int {
            return [$b['headroom'], $b['free'], $a['id']] <=> [$a['headroom'], $a['free'], $b['id']];
        });

        return array_map(static fn (array $f): int => $f['id'], $fits);
    }

    /** Memory or disk limit in MB, or null when the node allows unlimited overallocation. */
    public static function limit(int $physical, int $overallocatePercent): ?int
    {
        if ($overallocatePercent < 0) {
            return null;
        }

        return (int) floor($physical * (1 + $overallocatePercent / 100));
    }

    private static function truthy(mixed $value): bool
    {
        if (is_string($value)) {
            return in_array(strtolower($value), ['1', 'true', 'yes', 'on'], true);
        }

        return (bool) $value;
    }
}
