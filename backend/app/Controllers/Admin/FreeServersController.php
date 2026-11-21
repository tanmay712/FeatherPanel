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

namespace App\Controllers\Admin;

use App\Chat\Node;
use App\Chat\Spell;
use App\Chat\Activity;
use App\Chat\Database;
use App\Chat\FreeServer;
use App\Helpers\ApiResponse;
use OpenApi\Attributes as OA;
use App\CloudFlare\CloudFlareRealIP;
use Symfony\Component\HttpFoundation\Request;
use App\Services\FreeServers\FreeServerPolicy;
use App\Services\FreeServers\FreeServerStacks;
use Symfony\Component\HttpFoundation\Response;
use App\Services\FreeServers\FreeServerVariables;
use App\Services\FreeServers\FreeServerInactivity;
use App\Services\FreeServers\FreeServerSpellInstaller;

/**
 * Free servers: the policy (resources, nodes, stack spells, inactivity rule), one-click setup
 * of the bundled spells, the list of free servers and a manual inactivity run.
 */
class FreeServersController
{
    #[OA\Get(
        path: '/api/admin/free-servers/settings',
        summary: 'Free server settings',
        description: 'The free servers policy, the Wings nodes and spells to choose from, and a check of each stack.',
        tags: ['Admin - Free servers'],
        responses: [new OA\Response(response: 200, description: 'Settings loaded')]
    )]
    public function settings(Request $request): Response
    {
        return ApiResponse::success($this->settingsPayload(FreeServerPolicy::get()), 'Free server settings loaded');
    }

    #[OA\Put(
        path: '/api/admin/free-servers/settings',
        summary: 'Save free server settings',
        tags: ['Admin - Free servers'],
        requestBody: new OA\RequestBody(required: true, content: new OA\JsonContent(type: 'object')),
        responses: [
            new OA\Response(response: 200, description: 'Settings saved'),
            new OA\Response(response: 422, description: 'Invalid settings'),
        ]
    )]
    public function updateSettings(Request $request): Response
    {
        $data = json_decode($request->getContent(), true);
        if (!is_array($data)) {
            return ApiResponse::error('Invalid request body', 'INVALID_REQUEST_BODY', 400);
        }
        $input = array_merge(FreeServerPolicy::get(), array_intersect_key($data, FreeServerPolicy::defaults()));
        $policy = FreeServerPolicy::normalize($input);

        $knownNodes = array_map('intval', array_column(Node::getAllNodes(), 'id'));
        $unknownNodes = array_diff($policy['node_ids'], $knownNodes);
        if ($unknownNodes !== []) {
            return ApiResponse::error('Unknown node: #' . implode(', #', $unknownNodes), 'FREE_SERVERS_UNKNOWN_NODE', 422);
        }
        $spells = Spell::getSpellsByIds(array_values($policy['stacks']));
        foreach ($policy['stacks'] as $key => $spellId) {
            if (!isset($spells[$spellId])) {
                return ApiResponse::error('The spell picked for ' . $key . ' does not exist', 'FREE_SERVERS_UNKNOWN_SPELL', 422);
            }
        }
        if ($policy['enabled'] && ($policy['node_ids'] === [] || $policy['stacks'] === [])) {
            return ApiResponse::error('Pick at least one node and one stack before turning free servers on', 'FREE_SERVERS_NOT_READY', 422);
        }

        if (!FreeServerPolicy::save($policy)) {
            return ApiResponse::error('Failed to save the free server settings', 'FREE_SERVERS_SAVE_FAILED', 500);
        }
        $saved = FreeServerPolicy::get();
        $this->log($request, 'free_servers_settings_update', sprintf(
            'Free servers %s: %d MB / %d MB / %d%% CPU, %d per user, %d node(s), %d stack(s), stop after %d days, storage after %d days',
            $saved['enabled'] ? 'on' : 'off',
            $saved['memory'],
            $saved['disk'],
            $saved['cpu'],
            $saved['max_per_user'],
            count($saved['node_ids']),
            count($saved['stacks']),
            $saved['stop_after_days'],
            $saved['store_after_days']
        ));

        return ApiResponse::success($this->settingsPayload($saved), 'Free server settings saved');
    }

    #[OA\Post(
        path: '/api/admin/free-servers/install-spells',
        summary: 'Set up the bundled free-tier spells',
        description: 'Imports the bundled spells into the "Free servers" realm and maps each stack to its spell. Stacks that already have a working spell are left alone unless listed in stacks.',
        tags: ['Admin - Free servers'],
        requestBody: new OA\RequestBody(required: false, content: new OA\JsonContent(properties: [
            new OA\Property(property: 'stacks', type: 'array', items: new OA\Items(type: 'string')),
        ])),
        responses: [new OA\Response(response: 200, description: 'Spells set up')]
    )]
    public function installSpells(Request $request): Response
    {
        $data = json_decode($request->getContent() ?: '{}', true);
        $stacks = is_array($data) && is_array($data['stacks'] ?? null) ? array_values(array_filter($data['stacks'], 'is_string')) : [];
        $result = (new FreeServerSpellInstaller())->install($request->attributes->get('user') ?? [], $stacks);
        $this->log($request, 'free_servers_install_spells', sprintf(
            'Free server spells: %d imported, %d reused, %d failed',
            count($result['imported']),
            count($result['reused']),
            count($result['failed'])
        ));
        FreeServerPolicy::flush();

        return ApiResponse::success($result + ['settings' => $this->settingsPayload(FreeServerPolicy::get())], 'Free server spells set up');
    }

    #[OA\Get(
        path: '/api/admin/free-servers/servers',
        summary: 'List free servers',
        tags: ['Admin - Free servers'],
        parameters: [
            new OA\Parameter(name: 'page', in: 'query', schema: new OA\Schema(type: 'integer', default: 1)),
            new OA\Parameter(name: 'limit', in: 'query', schema: new OA\Schema(type: 'integer', default: 20)),
            new OA\Parameter(name: 'stage', in: 'query', schema: new OA\Schema(type: 'string', enum: ['running', 'stopped', 'stored'])),
            new OA\Parameter(name: 'search', in: 'query', schema: new OA\Schema(type: 'string')),
        ],
        responses: [new OA\Response(response: 200, description: 'Free servers loaded')]
    )]
    public function servers(Request $request): Response
    {
        $page = max(1, (int) $request->query->get('page', 1));
        $limit = max(1, min(100, (int) $request->query->get('limit', 20)));
        $stage = (string) $request->query->get('stage', '');
        $stage = in_array($stage, ['running', FreeServer::STAGE_STOPPED, FreeServer::STAGE_STORED], true) ? $stage : null;
        $search = trim((string) $request->query->get('search', ''));
        $search = $search !== '' ? mb_substr($search, 0, 100) : null;

        $total = FreeServer::countWithActivity($stage, $search);
        $inactivity = new FreeServerInactivity();
        $items = array_map(
            static fn (array $row): array => $inactivity->describe($row),
            FreeServer::listWithActivity($stage, $search, $limit, ($page - 1) * $limit)
        );

        return ApiResponse::success([
            'items' => $items,
            'counts' => FreeServer::stageCounts(),
            'pagination' => [
                'page' => $page,
                'limit' => $limit,
                'total' => $total,
                'total_pages' => (int) max(1, ceil($total / $limit)),
            ],
        ], 'Free servers loaded');
    }

    #[OA\Post(
        path: '/api/admin/free-servers/run',
        summary: 'Run the free server inactivity check now',
        description: 'Stops, stores, clears and resets free servers exactly like the hourly task.',
        tags: ['Admin - Free servers'],
        responses: [new OA\Response(response: 200, description: 'Run finished')]
    )]
    public function run(Request $request): Response
    {
        $service = new FreeServerInactivity();
        $result = $service->execute($service->plan(), $request->attributes->get('user'));
        $this->log($request, 'free_servers_inactivity_run', 'Ran the free server inactivity check: ' . json_encode($result['applied']) . ', failed ' . $result['failed']);

        return ApiResponse::success($result, 'Free server inactivity check finished');
    }

    private function settingsPayload(array $policy): array
    {
        $pdo = Database::getPdoConnection();
        $nodes = [];
        $rows = $pdo->query('SELECT n.id, n.name, n.memory, n.disk, n.memory_overallocate, n.disk_overallocate, n.maintenance_mode, l.name AS location_name,
                (SELECT COUNT(*) FROM featherpanel_allocations a WHERE a.node_id = n.id AND a.server_id IS NULL) AS free_allocations,
                (SELECT COALESCE(SUM(s.memory), 0) FROM featherpanel_servers s WHERE s.node_id = n.id) AS memory_used
            FROM featherpanel_nodes n LEFT JOIN featherpanel_locations l ON l.id = n.location_id ORDER BY n.name ASC')->fetchAll(\PDO::FETCH_ASSOC);
        foreach ($rows as $row) {
            $nodes[] = [
                'id' => (int) $row['id'],
                'name' => (string) $row['name'],
                'location' => $row['location_name'],
                'memory' => (int) $row['memory'],
                'memory_used' => (int) $row['memory_used'],
                'disk' => (int) $row['disk'],
                'free_allocations' => (int) $row['free_allocations'],
                'maintenance' => in_array((string) $row['maintenance_mode'], ['1', 'true'], true),
            ];
        }

        $spells = [];
        foreach (Spell::getAllSpellsWithRealm() as $spell) {
            $spells[] = ['id' => (int) $spell['id'], 'name' => (string) $spell['name'], 'realm' => $spell['realm_name'] ?? null, 'uuid' => (string) $spell['uuid']];
        }
        $spellsById = array_column($spells, null, 'id');

        $stacks = [];
        foreach (FreeServerStacks::CATALOG as $key => $meta) {
            $spellId = $policy['stacks'][$key] ?? null;
            $problem = null;
            if ($spellId !== null && !isset($spellsById[$spellId])) {
                $problem = 'spell_missing';
            } elseif ($spellId !== null) {
                $check = FreeServerVariables::build(\App\Chat\SpellVariable::getVariablesBySpellId($spellId), static fn (int $n): string => str_repeat('x', $n));
                if ($check['missing'] !== []) {
                    $problem = 'variables_missing';
                }
            }
            $stacks[] = [
                'key' => $key,
                'group' => $meta['group'],
                'spell_id' => $spellId,
                'bundled' => FreeServerStacks::eggPath($key) !== null,
                'bundled_uuid' => $meta['uuid'],
                'problem' => $problem,
            ];
        }

        return [
            'policy' => $policy,
            'nodes' => $nodes,
            'spells' => $spells,
            'stacks' => $stacks,
            'counts' => FreeServer::stageCounts(),
        ];
    }

    private function log(Request $request, string $name, string $context): void
    {
        $user = $request->attributes->get('user');
        Activity::createActivity([
            'user_uuid' => $user['uuid'] ?? null,
            'name' => $name,
            'context' => mb_substr($context, 0, 500),
            'ip_address' => CloudFlareRealIP::getRealIP(),
        ]);
    }
}
