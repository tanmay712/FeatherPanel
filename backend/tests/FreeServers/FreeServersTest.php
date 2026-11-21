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

namespace App\Tests\FreeServers;

use PHPUnit\Framework\TestCase;
use App\Controllers\Admin\SpellsController;
use App\Services\FreeServers\FreeServerPolicy;
use App\Services\FreeServers\FreeServerStacks;
use App\Services\FreeServers\FreeServerService;
use App\Services\FreeServers\FreeServerPlacement;
use App\Services\FreeServers\FreeServerVariables;
use App\Services\FreeServers\FreeServerInactivity;

/**
 * Free servers: policy defaults and clamping, the bundled spells, node placement, generated
 * passwords, the login-based inactivity rule and the create flow (with the data access faked).
 */
class FreeServersTest extends TestCase
{
    private const NOW = 1_800_000_000;

    public function testPolicyDefaultsMatchTheCreatePage(): void
    {
        $p = FreeServerPolicy::normalize([]);
        self::assertFalse($p['enabled']);
        self::assertSame([512, 1024, 35], [$p['memory'], $p['disk'], $p['cpu']]);
        self::assertSame([14, 30], [$p['stop_after_days'], $p['store_after_days']]);
        self::assertTrue($p['inactivity_enabled']);
        self::assertTrue($p['show_ads_note']);
        self::assertSame(1, $p['max_per_user']);
        self::assertSame([], $p['node_ids']);
        self::assertSame([], $p['stacks']);
    }

    public function testPolicyClampsValuesAndDropsUnknownStacks(): void
    {
        $p = FreeServerPolicy::normalize([
            'enabled' => 'true',
            'memory' => 5,
            'cpu' => '9999',
            'max_per_user' => 'lots',
            'node_ids' => [3, '3', 0, -1, 'x', 7],
            'stacks' => ['nodejs' => '12', 'python' => 0, 'cobol' => 5, 'redis' => 9],
            'stop_after_days' => 20,
            'store_after_days' => 10,
        ]);
        self::assertTrue($p['enabled']);
        self::assertSame(128, $p['memory']);
        self::assertSame(1000, $p['cpu']);
        self::assertSame(1, $p['max_per_user']);
        self::assertSame([3, 7], $p['node_ids']);
        self::assertSame(['nodejs' => 12, 'redis' => 9], $p['stacks']);
        // Storage always comes after the stop.
        self::assertSame(21, $p['store_after_days']);
        self::assertSame('redis', FreeServerPolicy::stackForSpell(9, $p));
        self::assertNull(FreeServerPolicy::stackForSpell(5, $p));
    }

    public function testBundledSpellsImportAndMatchTheCatalog(): void
    {
        $map = new \ReflectionMethod(SpellsController::class, 'mapImportJsonToSpellData');
        $normalize = new \ReflectionMethod(SpellsController::class, 'normalizeSpellImportJson');
        self::assertSame(
            ['nodejs', 'python', 'bun', 'java', 'csharp', 'rust', 'lua', 'mongodb', 'mariadb', 'postgresql', 'redis'],
            FreeServerStacks::keys()
        );
        foreach (FreeServerStacks::CATALOG as $key => $meta) {
            $path = FreeServerStacks::eggPath($key);
            self::assertNotNull($path, $key);
            $egg = json_decode((string) file_get_contents($path), true);
            self::assertIsArray($egg, $key);
            self::assertSame($meta['uuid'], $egg['uuid'] ?? null, $key);
            self::assertContains($egg['meta']['version'] ?? '', ['PTDL_v1', 'PTDL_v2'], $key);

            // The import keeps the egg's uuid (when it is free), which is how the installer finds them again.
            self::assertSame($meta['uuid'], $normalize->invoke(null, $egg)['uuid'] ?? null, $key);
            $spell = $map->invoke(null, $egg, 1);
            self::assertNotSame('', trim((string) $spell['startup']), $key);
            self::assertNotEmpty(json_decode((string) $spell['docker_images'], true), $key);

            // Every stack can be created without the user typing anything.
            $variables = array_map(static fn (array $v): array => [
                'env_variable' => $v['env_variable'],
                'default_value' => $v['default_value'] ?? '',
                'rules' => $v['rules'] ?? '',
            ], $egg['variables'] ?? []);
            self::assertSame([], FreeServerVariables::build($variables)['missing'], $key);
        }
        self::assertNull(FreeServerStacks::eggPath('cobol'));
    }

    public function testPlacementPicksTheEmptiestNodeWithRoom(): void
    {
        $node = static fn (int $id, array $extra = []): array => $extra + [
            'id' => $id, 'memory' => 4096, 'memory_overallocate' => 0, 'disk' => 50000, 'disk_overallocate' => 0,
            'maintenance_mode' => 0, 'memory_used' => 0, 'disk_used' => 0, 'free_allocations' => 5,
        ];
        $ranked = FreeServerPlacement::rank([
            $node(1, ['memory_used' => 3000]),
            $node(2, ['memory_used' => 1000]),
            $node(3, ['memory_used' => 3800]),                     // no room for 512 MB
            $node(4, ['maintenance_mode' => '1']),                  // maintenance
            $node(5, ['free_allocations' => 0]),                    // no free port
            $node(6, ['memory_used' => 3800, 'memory_overallocate' => 50]),
            $node(7, ['memory_overallocate' => -1, 'memory_used' => 999999]), // unlimited
            $node(8, ['disk_used' => 49500]),                       // no disk left
        ], 512, 1024);
        self::assertSame([7, 2, 6, 1], $ranked);
        self::assertNull(FreeServerPlacement::limit(1000, -1));
        self::assertSame(1500, FreeServerPlacement::limit(1000, 50));
    }

    public function testPasswordsAreGeneratedAndRespectMaxLength(): void
    {
        $built = FreeServerVariables::build([
            ['env_variable' => 'PGPASSWORD', 'default_value' => 'Pl3453Ch4n63M3!', 'rules' => 'required|string|max:20'],
            ['env_variable' => 'MONGO_USER_PASS', 'default_value' => '', 'rules' => 'required|string'],
            ['env_variable' => 'ACCESS_TOKEN', 'default_value' => '', 'rules' => 'nullable|string'],
            ['env_variable' => 'MAIN_FILE', 'default_value' => 'index.js', 'rules' => 'required|string|max:16'],
            ['env_variable' => 'MUST_SET', 'default_value' => '', 'rules' => 'required|string'],
        ]);
        self::assertSame(20, strlen($built['values']['PGPASSWORD']));
        self::assertNotSame('Pl3453Ch4n63M3!', $built['values']['PGPASSWORD']);
        self::assertSame(24, strlen($built['values']['MONGO_USER_PASS']));
        self::assertMatchesRegularExpression('/^[A-Za-z0-9]+$/', $built['values']['MONGO_USER_PASS']);
        self::assertSame('', $built['values']['ACCESS_TOKEN']);
        self::assertSame('index.js', $built['values']['MAIN_FILE']);
        self::assertSame(['MUST_SET'], $built['missing']);
        self::assertTrue(FreeServerVariables::isSecret('SERVER_PASSWORD'));
        self::assertFalse(FreeServerVariables::isSecret('USER_UPLOAD'));
    }

    public function testInactivityStopsThenStoresAndNeverDeletes(): void
    {
        $policy = FreeServerPolicy::normalize([]);
        $at = static fn (int $daysAgo): string => gmdate('Y-m-d H:i:s', self::NOW - $daysAgo * 86400);
        $row = static fn (array $extra): array => $extra + [
            'stage' => null, 'stage_at' => null, 'created_at' => $at(100), 'restored_at' => null,
            'last_login_at' => null, 'last_device_at' => null, 'suspended' => 0, 'suspension_reason' => null, 'suspended_by_uuid' => null,
        ];

        self::assertNull(FreeServerInactivity::decide($row(['last_login_at' => $at(13)]), $policy, self::NOW));
        self::assertSame('stop', FreeServerInactivity::decide($row(['last_login_at' => $at(14)]), $policy, self::NOW));
        // The device tracker counts as a visit too (older login cookies have no session row).
        self::assertNull(FreeServerInactivity::decide($row(['last_login_at' => $at(40), 'last_device_at' => $at(2)]), $policy, self::NOW));
        // A new server is never idle from the start.
        self::assertNull(FreeServerInactivity::decide($row(['created_at' => $at(1)]), $policy, self::NOW));
        // Stopped: waits for storage, and clears once the owner is back.
        self::assertNull(FreeServerInactivity::decide($row(['stage' => 'stopped', 'stage_at' => $at(5), 'last_login_at' => $at(20)]), $policy, self::NOW));
        self::assertSame('store', FreeServerInactivity::decide($row(['stage' => 'stopped', 'stage_at' => $at(16), 'last_login_at' => $at(30)]), $policy, self::NOW));
        self::assertSame('clear', FreeServerInactivity::decide($row(['stage' => 'stopped', 'stage_at' => $at(5), 'last_login_at' => $at(1)]), $policy, self::NOW));
        // Never logged in for 30+ days: straight to storage.
        self::assertSame('store', FreeServerInactivity::decide($row(['last_login_at' => $at(31)]), $policy, self::NOW));
        // Stored stays stored until restored; staff lifting the suspension resets it.
        $stored = ['stage' => 'stored', 'stage_at' => $at(1), 'suspended' => 1, 'suspension_reason' => FreeServerInactivity::storageReason(30)];
        self::assertNull(FreeServerInactivity::decide($row($stored + ['last_login_at' => $at(0)]), $policy, self::NOW));
        self::assertSame('reset', FreeServerInactivity::decide($row(['suspended' => 0] + $stored), $policy, self::NOW));
        // Suspended by staff: left alone. Rule turned off: nothing happens.
        self::assertNull(FreeServerInactivity::decide($row(['suspended' => 1, 'last_login_at' => $at(60)]), $policy, self::NOW));
        $off = FreeServerPolicy::normalize(['inactivity_enabled' => false]);
        self::assertNull(FreeServerInactivity::decide($row(['last_login_at' => $at(60)]), $off, self::NOW));

        self::assertTrue(FreeServerInactivity::isStorageSuspension($row($stored)));
        self::assertFalse(FreeServerInactivity::isStorageSuspension($row(['suspended_by_uuid' => 'staff-uuid'] + $stored)));
        self::assertFalse(FreeServerInactivity::isStorageSuspension($row(['suspended' => 1, 'suspension_reason' => 'Abuse'])));
    }

    public function testPlanListsOnlyServersWithAStepDue(): void
    {
        $at = static fn (int $daysAgo): string => gmdate('Y-m-d H:i:s', self::NOW - $daysAgo * 86400);
        $base = ['stage' => null, 'stage_at' => null, 'restored_at' => null, 'last_device_at' => null, 'suspended' => 0,
            'suspension_reason' => null, 'suspended_by_uuid' => null, 'node_id' => 1, 'owner_id' => 2, 'uuid' => 'u', 'stack' => 'nodejs'];
        $service = new class(FreeServerPolicy::normalize([]), [
            ['id' => 1, 'server_id' => 11, 'uuid_short' => 'aaaaaaaa', 'name' => 'Active', 'created_at' => $at(50), 'last_login_at' => $at(1)] + $base,
            ['id' => 2, 'server_id' => 12, 'uuid_short' => 'bbbbbbbb', 'name' => 'Idle', 'created_at' => $at(50), 'last_login_at' => $at(15)] + $base,
            ['id' => 3, 'server_id' => 13, 'uuid_short' => 'cccccccc', 'name' => 'Gone', 'created_at' => $at(50), 'last_login_at' => null] + $base,
        ]) extends FreeServerInactivity {
            public function __construct(array $policy, private array $fake)
            {
                parent::__construct($policy);
            }

            protected function rows(): array
            {
                return $this->fake;
            }

            protected function now(): int
            {
                return 1_800_000_000;
            }
        };
        $plan = $service->plan();
        self::assertSame(['stop' => 1, 'store' => 1], $plan['counts']);
        self::assertSame([12, 13], array_column($plan['items'], 'server_id'));
        self::assertSame(15, $plan['items'][0]['idle_days']);
        self::assertSame(50, $plan['items'][1]['idle_days']);

        $row = ['id' => 4, 'server_id' => 14, 'uuid_short' => 'dddddddd', 'name' => 'Row', 'created_at' => $at(50), 'last_login_at' => $at(1)] + $base;
        $described = $service->describe($row);
        self::assertNull($described['step']);
        self::assertSame(gmdate('Y-m-d H:i:s', self::NOW + 13 * 86400), $described['stop_at']);
        self::assertSame(gmdate('Y-m-d H:i:s', self::NOW + 29 * 86400), $described['store_at']);
        $off = new class(FreeServerPolicy::normalize(['inactivity_enabled' => false])) extends FreeServerInactivity {
            protected function now(): int
            {
                return 1_800_000_000;
            }
        };
        self::assertNull($off->describe($row)['stop_at']);
        self::assertNull($off->describe($row)['store_at']);
    }

    public function testNamesAndDescriptionsAreCleaned(): void
    {
        self::assertSame('My awesome bot', FreeServerService::cleanName("  My \t awesome\nbot "));
        self::assertSame('', FreeServerService::cleanName(str_repeat('a', 61)));
        self::assertSame('', FreeServerService::cleanName(['array']));
        self::assertSame('line one' . "\n" . 'line two', FreeServerService::cleanDescription("line one\r\nline two\x07 "));
        self::assertSame(500, mb_strlen(FreeServerService::cleanDescription(str_repeat('é', 600))));
    }

    public function testCreateChecksTheRequestBeforeTouchingNodes(): void
    {
        $service = $this->fakeService(['enabled' => false]);
        self::assertSame('FREE_SERVERS_DISABLED', $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => 'Bot'])['code']);

        $service = $this->fakeService();
        self::assertSame('FREE_SERVER_STACK_UNAVAILABLE', $service->create(['id' => 2], ['stack' => 'python', 'name' => 'Bot'])['code']);
        self::assertSame('FREE_SERVER_STACK_UNAVAILABLE', $service->create(['id' => 2], ['stack' => 'cobol', 'name' => 'Bot'])['code']);
        self::assertSame('FREE_SERVER_INVALID_NAME', $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => '   '])['code']);

        $service = $this->fakeService([], ['count' => 1]);
        $result = $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => 'Bot']);
        self::assertSame(['FREE_SERVER_LIMIT_REACHED', 409], [$result['code'], $result['status']]);
        self::assertSame([], $service->calls);
    }

    public function testCreateRetriesTakenPortsAndBrokenNodes(): void
    {
        // Node 1: first port was taken by a parallel request, second one works.
        $service = $this->fakeService([], ['results' => [
            '1:100' => ['ok' => false, 'code' => 'ALLOCATION_IN_USE', 'message' => 'x', 'status' => 400],
            '1:101' => ['ok' => true, 'server_id' => 55],
        ]]);
        $result = $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => '  My bot ', 'description' => 'Hi']);
        self::assertTrue($result['ok']);
        self::assertSame(55, $result['server_id']);
        self::assertSame(['1:100', '1:101'], $service->calls);
        $payload = $service->payloads['1:101'];
        self::assertSame(['My bot', 'Hi', 512, 1024, 35, 7, 3], [$payload['name'], $payload['description'], $payload['memory'], $payload['disk'], $payload['cpu'], $payload['spell_id'], $payload['realms_id']]);
        self::assertSame('ghcr.io/pelican-eggs/yolks:nodejs_24', $payload['image']);
        self::assertSame('index.js', $payload['variables']['MAIN_FILE']);

        // Node 1 is down: node 2 takes it.
        $service = $this->fakeService([], ['results' => [
            '1:100' => ['ok' => false, 'code' => 'WINGS_ERROR', 'message' => 'down', 'status' => 500],
            '2:200' => ['ok' => true, 'server_id' => 56],
        ]]);
        self::assertSame(56, $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => 'Bot'])['server_id']);

        // Every node down: one clear error for the user.
        $service = $this->fakeService([], ['results' => [
            '1:100' => ['ok' => false, 'code' => 'WINGS_ERROR', 'message' => 'down', 'status' => 500],
            '2:200' => ['ok' => false, 'code' => 'FAILED_TO_CREATE_SERVER_IN_WINGS', 'message' => 'down', 'status' => 500],
        ]]);
        self::assertSame('FREE_SERVER_CREATE_FAILED', $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => 'Bot'])['code']);

        // A problem with the request itself is not retried on another node.
        $service = $this->fakeService([], ['results' => [
            '1:100' => ['ok' => false, 'code' => 'MISSING_REQUIRED_VARIABLES', 'message' => 'x', 'status' => 400],
        ]]);
        self::assertSame('MISSING_REQUIRED_VARIABLES', $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => 'Bot'])['code']);
        self::assertSame(['1:100'], $service->calls);

        // No node with room.
        $service = $this->fakeService([], ['nodes' => []]);
        self::assertSame('FREE_SERVER_NO_CAPACITY', $service->create(['id' => 2], ['stack' => 'nodejs', 'name' => 'Bot'])['code']);
    }

    public function testStorageSyncsWingsAndGenericCleanupSkipsFreeServers(): void
    {
        $backend = dirname(__DIR__, 2);
        $inactivity = (string) file_get_contents($backend . '/app/Services/FreeServers/FreeServerInactivity.php');
        self::assertStringContainsString('WingsSuspensionSync::afterSuspend', $inactivity);
        $service = (string) file_get_contents($backend . '/app/Services/FreeServers/FreeServerService.php');
        self::assertStringContainsString('WingsSuspensionSync::afterUnsuspend', $service);
        $cleanup = (string) file_get_contents($backend . '/app/Services/InactiveCleanup/InactiveCleanupService.php');
        self::assertMatchesRegularExpression('/NOT EXISTS\s*\(\s*SELECT 1 FROM featherpanel_free_servers/', $cleanup);
        $cron = (string) file_get_contents($backend . '/storage/cron/php/ZFreeServerInactivity.php');
        self::assertStringContainsString('FreeServerInactivity', $cron);
    }

    private function fakeService(array $policy = [], array $fake = []): FreeServerService
    {
        $policy = FreeServerPolicy::normalize($policy + ['enabled' => true, 'node_ids' => [1, 2], 'stacks' => ['nodejs' => 7]]);
        $fake += [
            'count' => 0,
            'nodes' => [1, 2],
            'ports' => [1 => [100, 101, 102], 2 => [200]],
            'results' => [],
        ];

        return new class($policy, $fake) extends FreeServerService {
            public array $calls = [];

            public array $payloads = [];

            public function __construct(array $policy, private array $fake)
            {
                parent::__construct($policy);
            }

            protected function countFor(int $userId): int
            {
                return $this->fake['count'];
            }

            protected function spell(int $spellId): ?array
            {
                return $spellId === 7 ? [
                    'id' => 7, 'realm_id' => 3, 'startup' => 'node "/home/container/{{MAIN_FILE}}"',
                    'docker_images' => '{"Nodejs 24":"ghcr.io/pelican-eggs/yolks:nodejs_24"}', 'default_docker_image' => null,
                ] : null;
            }

            protected function spellVariables(int $spellId): array
            {
                return [['env_variable' => 'MAIN_FILE', 'default_value' => 'index.js', 'rules' => 'required|string']];
            }

            protected function rankNodes(): array
            {
                return $this->fake['nodes'];
            }

            protected function freeAllocation(int $nodeId, array $exclude): ?int
            {
                foreach ($this->fake['ports'][$nodeId] ?? [] as $port) {
                    if (!in_array($port, $exclude, true)) {
                        return $port;
                    }
                }

                return null;
            }

            protected function createServer(array $user, array $payload): array
            {
                $key = $payload['node_id'] . ':' . $payload['allocation_id'];
                $this->calls[] = $key;
                $this->payloads[$key] = $payload;

                return $this->fake['results'][$key] ?? ['ok' => false, 'code' => 'ALLOCATION_IN_USE', 'message' => 'x', 'status' => 400];
            }

            protected function finishCreate(array $user, int $serverId, string $stack, int $max): array
            {
                return ['ok' => true, 'server_id' => $serverId, 'stack' => $stack];
            }

            protected function withUserLock(int $userId, callable $fn): array
            {
                return $fn();
            }
        };
    }
}
