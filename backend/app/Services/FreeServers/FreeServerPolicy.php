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

use App\App;
use App\Config\ConfigInterface;

/**
 * Free servers policy, stored as one JSON setting. Off by default. The resource defaults match
 * the create page (512 MB memory, 1 GB disk, 35% CPU); the inactivity rule stops a server after
 * 14 days without a login and moves it to storage (suspended, files kept) after 30.
 */
class FreeServerPolicy
{
    public const SETTING_KEY = 'free_servers_policy';

    private static ?array $cache = null;

    public static function defaults(): array
    {
        return [
            'enabled' => false,
            'memory' => 512,
            'disk' => 1024,
            'cpu' => 35,
            'swap' => 0,
            'io' => 500,
            'database_limit' => 0,
            'backup_limit' => 0,
            // Total allocations, the primary one included.
            'allocation_limit' => 1,
            'max_per_user' => 1,
            // Wings nodes free servers may be placed on. None picked means none is available.
            'node_ids' => [],
            // Stack key => spell id. Stacks without a spell are not offered.
            'stacks' => [],
            'inactivity_enabled' => true,
            'stop_after_days' => 14,
            'store_after_days' => 30,
            'show_ads_note' => true,
        ];
    }

    public static function get(): array
    {
        if (self::$cache !== null) {
            return self::$cache;
        }
        $raw = App::getInstance(true)->getConfig()->getSetting(self::SETTING_KEY, '');
        $decoded = is_string($raw) && $raw !== '' ? json_decode($raw, true) : null;

        return self::$cache = self::normalize(is_array($decoded) ? $decoded : []);
    }

    public static function normalize(array $input): array
    {
        $d = self::defaults();
        $int = static function (string $key, int $min, int $max) use ($input, $d): int {
            $value = $input[$key] ?? $d[$key];

            return max($min, min($max, is_numeric($value) ? (int) $value : (int) $d[$key]));
        };
        $bool = static function (string $key) use ($input, $d): bool {
            $value = $input[$key] ?? $d[$key];

            return is_string($value) ? in_array(strtolower($value), ['1', 'true', 'yes', 'on'], true) : (bool) $value;
        };

        $nodeIds = [];
        foreach (is_array($input['node_ids'] ?? null) ? $input['node_ids'] : [] as $id) {
            if (is_numeric($id) && (int) $id > 0) {
                $nodeIds[(int) $id] = (int) $id;
            }
        }

        $stacks = [];
        $rawStacks = is_array($input['stacks'] ?? null) ? $input['stacks'] : [];
        foreach (FreeServerStacks::keys() as $key) {
            $spellId = $rawStacks[$key] ?? null;
            if (is_numeric($spellId) && (int) $spellId > 0) {
                $stacks[$key] = (int) $spellId;
            }
        }

        $stopAfter = $int('stop_after_days', 1, 365);

        return [
            'enabled' => $bool('enabled'),
            'memory' => $int('memory', 128, 65536),
            'disk' => $int('disk', 128, 1048576),
            'cpu' => $int('cpu', 1, 1000),
            'swap' => $int('swap', 0, 65536),
            'io' => $int('io', 10, 1000),
            'database_limit' => $int('database_limit', 0, 50),
            'backup_limit' => $int('backup_limit', 0, 50),
            'allocation_limit' => $int('allocation_limit', 1, 50),
            'max_per_user' => $int('max_per_user', 1, 50),
            'node_ids' => array_slice(array_values($nodeIds), 0, 500),
            'stacks' => $stacks,
            'inactivity_enabled' => $bool('inactivity_enabled'),
            'stop_after_days' => $stopAfter,
            // Storage always comes after the stop.
            'store_after_days' => max($stopAfter + 1, $int('store_after_days', 2, 3650)),
            'show_ads_note' => $bool('show_ads_note'),
        ];
    }

    /** Stacks users can pick right now (a spell is set for them). */
    public static function offeredStacks(array $policy): array
    {
        return array_keys($policy['stacks']);
    }

    /** Stack key whose mapped spell is $spellId, or null when the spell is not a free server stack. */
    public static function stackForSpell(int $spellId, ?array $policy = null): ?string
    {
        $policy ??= self::get();
        $key = array_search($spellId, $policy['stacks'], true);

        return is_string($key) ? $key : null;
    }

    public static function save(array $policy): bool
    {
        self::$cache = null;
        $normalized = self::normalize($policy);
        $config = App::getInstance(true)->getConfig();
        $saved = $config->setSetting(self::SETTING_KEY, (string) json_encode($normalized));
        $config->setSetting(ConfigInterface::FREE_SERVERS_ENABLED, $normalized['enabled'] ? 'true' : 'false');

        return $saved;
    }

    public static function flush(): void
    {
        self::$cache = null;
    }
}
