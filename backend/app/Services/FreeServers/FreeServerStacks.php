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
 * The stacks a user can pick for a free server. Each one maps to a spell chosen by an admin;
 * the bundled spells in storage/eggs/free-tier carry the uuids below so they can be found again
 * after an import.
 */
final class FreeServerStacks
{
    public const GROUP_RUNTIME = 'runtime';

    public const GROUP_DATABASE = 'database';

    /**
     * Display order matters: the create page lists the stacks in this order.
     *
     * @var array<string, array{group: string, egg: string, uuid: string}>
     */
    public const CATALOG = [
        'nodejs' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-nodejs.json', 'uuid' => '4c9d2f6b-cbb5-4f16-882b-82ed4b43e33c'],
        'python' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-python.json', 'uuid' => '91696653-e283-4bfe-8776-0f3e905887eb'],
        'bun' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-bun.json', 'uuid' => '87063ab0-13ff-4552-a981-d55f3b86873a'],
        'java' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-java.json', 'uuid' => '07e0c563-7f87-4984-8ab0-4cfc5b5d6f02'],
        'csharp' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-csharp.json', 'uuid' => '0bbe3f99-abad-4d7d-b02f-972c1cb0afbc'],
        'rust' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-rust.json', 'uuid' => '33839719-7f27-45ab-9a74-a6ecc441bf88'],
        'lua' => ['group' => self::GROUP_RUNTIME, 'egg' => 'orvex-free-lua.json', 'uuid' => '399c0a1e-c238-4712-8a2b-af8d29683d2b'],
        'mongodb' => ['group' => self::GROUP_DATABASE, 'egg' => 'orvex-free-mongodb.json', 'uuid' => '0c51b192-5828-4cb1-9368-ded6f2f05949'],
        'mariadb' => ['group' => self::GROUP_DATABASE, 'egg' => 'orvex-free-mariadb.json', 'uuid' => 'f21eee5f-6042-4fdb-a38f-c050345a2881'],
        'postgresql' => ['group' => self::GROUP_DATABASE, 'egg' => 'orvex-free-postgresql.json', 'uuid' => '8b42f8a1-b7ad-4df3-bbfa-e7e3bdb1e53f'],
        'redis' => ['group' => self::GROUP_DATABASE, 'egg' => 'orvex-free-redis.json', 'uuid' => 'f4418bc3-efc0-4d42-85b6-e51744c8c993'],
    ];

    /** @return list<string> */
    public static function keys(): array
    {
        return array_keys(self::CATALOG);
    }

    public static function isValid(string $key): bool
    {
        return isset(self::CATALOG[$key]);
    }

    public static function group(string $key): ?string
    {
        return self::CATALOG[$key]['group'] ?? null;
    }

    /** Folder holding the bundled free-tier eggs. */
    public static function eggDirectory(): string
    {
        return dirname(__DIR__, 3) . '/storage/eggs/free-tier';
    }

    public static function eggPath(string $key): ?string
    {
        if (!self::isValid($key)) {
            return null;
        }
        $path = self::eggDirectory() . '/' . self::CATALOG[$key]['egg'];

        return is_file($path) ? $path : null;
    }
}
