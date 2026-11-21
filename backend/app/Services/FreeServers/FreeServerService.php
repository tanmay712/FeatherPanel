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
use App\Chat\Node;
use App\Chat\Spell;
use App\Chat\Server;
use App\Chat\Activity;
use App\Chat\Database;
use App\Chat\Allocation;
use App\Chat\FreeServer;
use App\Chat\SpellVariable;
use App\Chat\ServerActivity;
use App\Chat\ServerVariable;
use App\Services\Wings\Wings;
use App\CloudFlare\CloudFlareRealIP;
use App\Helpers\ModerationReasonHelper;
use App\Controllers\Admin\ServersController;
use App\Services\Server\WingsSuspensionSync;
use Symfony\Component\HttpFoundation\Request;

/**
 * Free servers for users: what the create page offers, creating one (placed automatically on
 * an allowed node, through the same flow as the admin create), the user's list and restoring a
 * server from storage.
 *
 * Results are arrays: ['ok' => true, ...] or ['ok' => false, 'code' => ..., 'message' => ..., 'status' => ...].
 */
class FreeServerService
{
    public const NAME_MAX = 60;

    public const DESCRIPTION_MAX = 500;

    /** Admin create errors that are about the node, so the next node is tried. */
    private const NODE_ERRORS = ['WINGS_ERROR', 'WINGS_UNAUTHORIZED', 'WINGS_FORBIDDEN', 'FAILED_TO_CREATE_SERVER_IN_WINGS'];

    private array $policy;

    public function __construct(?array $policy = null)
    {
        $this->policy = $policy ?? FreeServerPolicy::get();
    }

    /** What the create page shows to this user. */
    public function optionsFor(array $user): array
    {
        $p = $this->policy;
        $spells = $this->spellsById(array_values($p['stacks']));
        $stacks = [];
        foreach (FreeServerStacks::CATALOG as $key => $meta) {
            $spellId = $p['stacks'][$key] ?? null;
            $stacks[] = [
                'key' => $key,
                'group' => $meta['group'],
                'available' => $spellId !== null && isset($spells[$spellId]),
            ];
        }
        $used = $this->countFor((int) $user['id']);

        return [
            'enabled' => $p['enabled'],
            'resources' => ['memory' => $p['memory'], 'disk' => $p['disk'], 'cpu' => $p['cpu']],
            'limit' => ['max' => $p['max_per_user'], 'used' => $used, 'reached' => $used >= $p['max_per_user']],
            'stacks' => $stacks,
            'capacity' => $p['enabled'] && $this->rankNodes() !== [],
            'inactivity' => [
                'enabled' => $p['inactivity_enabled'],
                'stop_after_days' => $p['stop_after_days'],
                'store_after_days' => $p['store_after_days'],
            ],
            'notes' => ['ads' => $p['show_ads_note']],
        ];
    }

    /**
     * Create a free server for the user.
     *
     * @param array{stack?: mixed, name?: mixed, description?: mixed} $input
     */
    public function create(array $user, array $input): array
    {
        $p = $this->policy;
        if (!$p['enabled']) {
            return self::fail('FREE_SERVERS_DISABLED', 'Free servers are turned off', 403);
        }
        $stack = is_string($input['stack'] ?? null) ? $input['stack'] : '';
        $spellId = FreeServerStacks::isValid($stack) ? ($p['stacks'][$stack] ?? null) : null;
        $spell = $spellId !== null ? $this->spell($spellId) : null;
        if ($spell === null) {
            return self::fail('FREE_SERVER_STACK_UNAVAILABLE', 'This stack is not available for free servers', 422);
        }
        $name = self::cleanName($input['name'] ?? '');
        if ($name === '') {
            return self::fail('FREE_SERVER_INVALID_NAME', 'Give the server a name of up to ' . self::NAME_MAX . ' characters', 422);
        }
        $description = self::cleanDescription($input['description'] ?? '');

        $variables = FreeServerVariables::build($this->spellVariables((int) $spell['id']));
        $image = Spell::resolveDefaultDockerImage($spell);
        if ($variables['missing'] !== [] || $image === null || trim((string) ($spell['startup'] ?? '')) === '') {
            App::getInstance(true)->getLogger()->error('Free server stack ' . $stack . ' (spell #' . $spell['id'] . ') cannot be used: '
                . ($variables['missing'] !== [] ? 'no default for ' . implode(', ', $variables['missing']) : 'no Docker image or startup command'));

            return self::fail('FREE_SERVER_STACK_MISCONFIGURED', 'This stack is not set up correctly yet. Try another one or ask an administrator.', 500);
        }

        $userId = (int) $user['id'];

        return $this->withUserLock($userId, function () use ($user, $userId, $stack, $spell, $name, $description, $variables, $image, $p): array {
            if ($this->countFor($userId) >= $p['max_per_user']) {
                return self::fail('FREE_SERVER_LIMIT_REACHED', 'You already have the maximum number of free servers', 409);
            }

            $payload = [
                'owner_id' => $userId,
                'name' => $name,
                'description' => $description,
                'memory' => $p['memory'],
                'swap' => $p['swap'],
                'disk' => $p['disk'],
                'io' => $p['io'],
                'cpu' => $p['cpu'],
                'realms_id' => (int) $spell['realm_id'],
                'spell_id' => (int) $spell['id'],
                'startup' => (string) $spell['startup'],
                'image' => $image,
                'database_limit' => $p['database_limit'],
                'backup_limit' => $p['backup_limit'],
                'allocation_limit' => $p['allocation_limit'],
                'show_on_status' => false,
                'variables' => $variables['values'],
            ];

            $last = self::noCapacity();
            foreach (array_slice($this->rankNodes(), 0, 3) as $nodeId) {
                $result = $this->tryNode($user, $payload, $nodeId);
                if ($result['ok']) {
                    return $this->finishCreate($user, (int) $result['server_id'], $stack, $p['max_per_user']);
                }
                if ($result['code'] === 'FREE_SERVER_NO_CAPACITY') {
                    continue;
                }
                $last = $result;
                if (!in_array($result['code'], self::NODE_ERRORS, true)) {
                    // Not a node problem (disk quota, invalid spell data): another node will not help.
                    return $result;
                }
            }

            return in_array($last['code'], self::NODE_ERRORS, true)
                ? self::fail('FREE_SERVER_CREATE_FAILED', 'The server could not be created on the node. Try again in a few minutes.', 503)
                : $last;
        });
    }

    /** The user's free servers. */
    public function listFor(array $user): array
    {
        return array_map(fn (array $row): array => $this->present($row), $this->rowsFor((int) $user['id']));
    }

    /** One of the user's free servers, or null when it is not a free server they own. */
    public function showFor(array $user, string $uuidShort): ?array
    {
        $row = $this->rowForOwner($uuidShort, (int) $user['id']);

        return $row === null ? null : $this->present($row);
    }

    /** Bring a stored free server back: lift the storage suspension and start it. */
    public function restore(array $user, string $uuidShort): array
    {
        $row = $this->rowForOwner($uuidShort, (int) $user['id']);
        if ($row === null) {
            return self::fail('FREE_SERVER_NOT_FOUND', 'Free server not found', 404);
        }
        if ($row['stage'] !== FreeServer::STAGE_STORED) {
            return self::fail('FREE_SERVER_NOT_STORED', 'This server is not in storage', 409);
        }
        if ((int) $row['suspended'] === 1 && !FreeServerInactivity::isStorageSuspension($row)) {
            return self::fail('FREE_SERVER_RESTORE_BLOCKED', 'This server was suspended by staff. Contact support to get it back.', 403);
        }
        $server = ['uuid' => (string) $row['uuid'], 'node_id' => (int) $row['node_id']];
        if ((int) $row['suspended'] === 1) {
            if (!Server::updateServerById((int) $row['server_id'], ModerationReasonHelper::suspensionClearedFields())) {
                return self::fail('FREE_SERVER_RESTORE_FAILED', 'The server could not be restored. Try again.', 500);
            }
            $this->syncUnsuspended($server);
        }
        FreeServer::markRestored((int) $row['id']);
        $started = $this->powerStart($server);
        Activity::createActivity([
            'user_uuid' => $user['uuid'] ?? null,
            'name' => 'free_server_restore',
            'context' => 'Restored free server ' . $row['name'] . ' from storage',
            'ip_address' => CloudFlareRealIP::getRealIP(),
        ]);

        return ['ok' => true, 'server_id' => (int) $row['server_id'], 'uuid_short' => (string) $row['uuid_short'], 'started' => $started];
    }

    /**
     * Switch a free server to another stack: new spell, its startup command, Docker image and
     * variables (fresh passwords), then a reinstall. Files are kept unless the install script of
     * the new stack replaces them. If the node cannot start the reinstall, everything is put back.
     */
    public function changeStack(array $user, string $uuidShort, mixed $stack): array
    {
        $row = $this->rowForOwner($uuidShort, (int) $user['id']);
        if ($row === null) {
            return self::fail('FREE_SERVER_NOT_FOUND', 'Free server not found', 404);
        }
        if ((int) $row['suspended'] === 1 || $row['stage'] === FreeServer::STAGE_STORED) {
            return self::fail('FREE_SERVER_SUSPENDED', 'Restore the server before changing its stack', 409);
        }
        $stack = is_string($stack) ? $stack : '';
        $spellId = FreeServerStacks::isValid($stack) ? ($this->policy['stacks'][$stack] ?? null) : null;
        $spell = $spellId !== null ? $this->spell($spellId) : null;
        if ($spell === null) {
            return self::fail('FREE_SERVER_STACK_UNAVAILABLE', 'This stack is not available for free servers', 422);
        }
        $server = Server::getServerById((int) $row['server_id']);
        if ($server === null) {
            return self::fail('FREE_SERVER_NOT_FOUND', 'Free server not found', 404);
        }
        if ((int) $server['spell_id'] === (int) $spell['id']) {
            return self::fail('FREE_SERVER_SAME_STACK', 'The server already runs this stack', 409);
        }
        $spellVariables = $this->spellVariables((int) $spell['id']);
        $variables = FreeServerVariables::build($spellVariables);
        $image = Spell::resolveDefaultDockerImage($spell);
        if ($variables['missing'] !== [] || $image === null || trim((string) ($spell['startup'] ?? '')) === '') {
            return self::fail('FREE_SERVER_STACK_MISCONFIGURED', 'This stack is not set up correctly yet. Try another one or ask an administrator.', 500);
        }

        $previous = [
            'fields' => [
                'spell_id' => (int) $server['spell_id'],
                'realms_id' => (int) $server['realms_id'],
                'startup' => (string) $server['startup'],
                'image' => (string) $server['image'],
            ],
            'variables' => array_map(static fn (array $v): array => [
                'variable_id' => (int) $v['variable_id'],
                'variable_value' => (string) $v['variable_value'],
            ], ServerVariable::getServerVariablesByServerId((int) $server['id'])),
            'stack' => (string) $row['stack'],
        ];
        $variableRows = [];
        foreach ($spellVariables as $variable) {
            $env = (string) $variable['env_variable'];
            if (array_key_exists($env, $variables['values'])) {
                $variableRows[] = ['variable_id' => (int) $variable['id'], 'variable_value' => $variables['values'][$env]];
            }
        }

        $fields = [
            'spell_id' => (int) $spell['id'],
            'realms_id' => (int) $spell['realm_id'],
            'startup' => (string) $spell['startup'],
            'image' => $image,
        ];
        if (!Server::updateServerById((int) $server['id'], $fields)
            || ($variableRows !== [] && !ServerVariable::createOrUpdateServerVariables((int) $server['id'], $variableRows))
            || ($variableRows === [] && !ServerVariable::deleteServerVariablesByServerId((int) $server['id']))) {
            $this->restoreStack((int) $server['id'], (int) $row['id'], $previous);

            return self::fail('FREE_SERVER_STACK_CHANGE_FAILED', 'The stack could not be changed. Try again.', 500);
        }
        FreeServer::setStack((int) $row['id'], $stack);

        $since = new \DateTimeImmutable();
        if (!$this->reinstall(['uuid' => (string) $server['uuid'], 'node_id' => (int) $server['node_id']])) {
            $this->restoreStack((int) $server['id'], (int) $row['id'], $previous);

            return self::fail('FREE_SERVER_STACK_CHANGE_FAILED', 'The node could not reinstall the server, so nothing was changed. Try again in a few minutes.', 503);
        }
        Server::markInstalling((int) $server['id'], $since);
        ServerActivity::createActivity([
            'server_id' => (int) $server['id'],
            'node_id' => (int) $server['node_id'],
            'user_id' => (int) $user['id'],
            'event' => 'free_server_stack_changed',
            'metadata' => json_encode(['from' => $previous['stack'], 'to' => $stack]),
        ]);
        Activity::createActivity([
            'user_uuid' => $user['uuid'] ?? null,
            'name' => 'free_server_stack_change',
            'context' => 'Switched free server ' . $server['name'] . ' from ' . $previous['stack'] . ' to ' . $stack,
            'ip_address' => CloudFlareRealIP::getRealIP(),
        ]);

        return ['ok' => true, 'server_id' => (int) $server['id'], 'uuid_short' => (string) $server['uuidShort'], 'stack' => $stack];
    }

    /** What the user API shows for a free server row. */
    public function present(array $row): array
    {
        $stage = $row['stage'] !== null && $row['stage'] !== '' ? (string) $row['stage'] : null;
        $lastActive = FreeServerInactivity::lastActiveAt($row);
        $p = $this->policy;

        return [
            'server_id' => (int) $row['server_id'],
            'uuid_short' => (string) $row['uuid_short'],
            'name' => (string) $row['name'],
            'stack' => (string) $row['stack'],
            'stage' => $stage,
            'stage_at' => $row['stage_at'],
            'suspended' => (int) $row['suspended'] === 1,
            'restorable' => $stage === FreeServer::STAGE_STORED && ((int) $row['suspended'] === 0 || FreeServerInactivity::isStorageSuspension($row)),
            'created_at' => $row['created_at'],
            'stop_at' => $p['inactivity_enabled'] && $stage === null && $lastActive > 0 ? gmdate('Y-m-d H:i:s', $lastActive + $p['stop_after_days'] * 86400) : null,
            'store_at' => $p['inactivity_enabled'] && $stage !== FreeServer::STAGE_STORED && $lastActive > 0 ? gmdate('Y-m-d H:i:s', $lastActive + $p['store_after_days'] * 86400) : null,
        ];
    }

    public static function cleanName(mixed $value): string
    {
        if (!is_string($value)) {
            return '';
        }
        $value = preg_replace('/[\x00-\x1F\x7F]+/u', ' ', $value) ?? '';
        $value = trim(preg_replace('/\s+/u', ' ', $value) ?? '');

        return mb_strlen($value) > self::NAME_MAX || strlen($value) > 191 ? '' : $value;
    }

    public static function cleanDescription(mixed $value): string
    {
        if (!is_string($value)) {
            return '';
        }
        $value = str_replace(["\r\n", "\r"], "\n", $value);
        $value = trim(preg_replace('/[\x00-\x08\x0B-\x1F\x7F]+/u', '', $value) ?? '');

        return mb_substr($value, 0, self::DESCRIPTION_MAX);
    }

    // Creation helpers

    /**
     * Record the free server. If the owner went over the limit in the meantime (a parallel
     * request on another web node), the newest server is removed again.
     */
    protected function finishCreate(array $user, int $serverId, string $stack, int $max): array
    {
        $rowId = FreeServer::create($serverId, $stack);
        $ids = $rowId === false ? [] : $this->freeIdsFor((int) $user['id']);
        $position = $rowId === false ? false : array_search($rowId, $ids, true);
        if ($rowId === false || $position === false || $position >= $max) {
            App::getInstance(true)->getLogger()->warning('Free server #' . $serverId . ' removed again: ' . ($rowId === false ? 'could not be recorded' : 'over the limit'));
            $this->deleteServer($serverId);

            return $rowId === false
                ? self::fail('FREE_SERVER_CREATE_FAILED', 'The server could not be created. Try again in a few minutes.', 500)
                : self::fail('FREE_SERVER_LIMIT_REACHED', 'You already have the maximum number of free servers', 409);
        }
        // Free servers follow their own inactivity rule; keep the generic cleanup away from them.
        Server::updateServerById($serverId, ['inactivity_exempt' => 1]);
        $server = Server::getServerById($serverId);
        Activity::createActivity([
            'user_uuid' => $user['uuid'] ?? null,
            'name' => 'free_server_create',
            'context' => 'Created free server ' . ($server['name'] ?? ('#' . $serverId)) . ' (' . $stack . ')',
            'ip_address' => CloudFlareRealIP::getRealIP(),
        ]);

        return [
            'ok' => true,
            'server_id' => $serverId,
            'uuid_short' => (string) ($server['uuidShort'] ?? ''),
            'name' => (string) ($server['name'] ?? ''),
            'stack' => $stack,
        ];
    }

    /** Create on one node, moving to the next free allocation when another request took it first. */
    protected function tryNode(array $user, array $payload, int $nodeId): array
    {
        $tried = [];
        $result = self::noCapacity();
        for ($attempt = 0; $attempt < 3; ++$attempt) {
            $allocationId = $this->freeAllocation($nodeId, $tried);
            if ($allocationId === null) {
                break;
            }
            $tried[] = $allocationId;
            $result = $this->createServer($user, $payload + ['node_id' => $nodeId, 'allocation_id' => $allocationId]);
            if ($result['ok'] || $result['code'] !== 'ALLOCATION_IN_USE') {
                return $result;
            }
        }

        return $result['ok'] || $result['code'] !== 'ALLOCATION_IN_USE' ? $result : self::noCapacity();
    }

    /**
     * Run the admin create flow (validation, allocation claim, variables, Wings, owner email)
     * for the user, as the user.
     */
    protected function createServer(array $user, array $payload): array
    {
        $request = Request::create('/api/admin/servers', 'PUT', [], [], [], ['CONTENT_TYPE' => 'application/json'], (string) json_encode($payload));
        $request->attributes->set('user', $user);
        $response = (new ServersController())->create($request);
        $body = json_decode((string) $response->getContent(), true);
        $body = is_array($body) ? $body : [];
        if ($response->getStatusCode() < 400 && isset($body['data']['server_id'])) {
            return ['ok' => true, 'server_id' => (int) $body['data']['server_id']];
        }
        $code = (string) ($body['error_code'] ?? 'FREE_SERVER_CREATE_FAILED');
        $existing = Server::getServerByAllocationId((int) $payload['allocation_id']);
        if ($code === 'FAILED_TO_SEND_SERVER_CREATED_EMAIL' && $existing !== null && (int) $existing['owner_id'] === (int) $payload['owner_id']) {
            // The server exists and runs; only the "server created" email failed.
            return ['ok' => true, 'server_id' => (int) $existing['id']];
        }
        if ($code === 'FAILED_TO_CREATE_SERVER' && $existing !== null) {
            // Another request took the allocation between the check and the insert.
            $code = 'ALLOCATION_IN_USE';
        }
        App::getInstance(true)->getLogger()->warning('Free server create failed on node #' . $payload['node_id'] . ': ' . $code . ' ' . ($body['message'] ?? ''));

        return self::fail(
            $code,
            (string) ($body['message'] ?? 'The server could not be created'),
            $response->getStatusCode() >= 400 ? $response->getStatusCode() : 500
        );
    }

    /**
     * Allowed nodes that can take another free server, best first.
     *
     * @return list<int>
     */
    protected function rankNodes(): array
    {
        return FreeServerPlacement::rank($this->nodeCandidates($this->policy['node_ids']), $this->policy['memory'], $this->policy['disk']);
    }

    /**
     * @param list<int> $nodeIds
     *
     * @return list<array<string, mixed>>
     */
    protected function nodeCandidates(array $nodeIds): array
    {
        if ($nodeIds === []) {
            return [];
        }
        $placeholders = implode(',', array_fill(0, count($nodeIds), '?'));
        $stmt = Database::getPdoConnection()->prepare('SELECT n.id, n.memory, n.memory_overallocate, n.disk, n.disk_overallocate, n.maintenance_mode,
                (SELECT COALESCE(SUM(s.memory), 0) FROM featherpanel_servers s WHERE s.node_id = n.id) AS memory_used,
                (SELECT COALESCE(SUM(s.disk), 0) FROM featherpanel_servers s WHERE s.node_id = n.id) AS disk_used,
                (SELECT COUNT(*) FROM featherpanel_allocations a WHERE a.node_id = n.id AND a.server_id IS NULL) AS free_allocations
            FROM featherpanel_nodes n WHERE n.id IN (' . $placeholders . ')');
        $stmt->execute(array_values($nodeIds));

        return $stmt->fetchAll(\PDO::FETCH_ASSOC);
    }

    /** @param list<int> $exclude */
    protected function freeAllocation(int $nodeId, array $exclude): ?int
    {
        $ids = Allocation::pickFreeAllocationIdsForNode($nodeId, 1, $exclude);

        return $ids[0] ?? null;
    }

    protected function countFor(int $userId): int
    {
        return FreeServer::countForOwner($userId);
    }

    /** @return list<int> */
    protected function freeIdsFor(int $userId): array
    {
        return FreeServer::idsForOwner($userId);
    }

    /** @return list<array<string, mixed>> */
    protected function rowsFor(int $userId): array
    {
        return FreeServer::listForOwner($userId);
    }

    protected function rowForOwner(string $uuidShort, int $userId): ?array
    {
        return FreeServer::getByUuidShortForOwner($uuidShort, $userId);
    }

    protected function spell(int $spellId): ?array
    {
        return Spell::getSpellById($spellId);
    }

    /**
     * @param list<int> $ids
     *
     * @return array<int, array<string, mixed>>
     */
    protected function spellsById(array $ids): array
    {
        return Spell::getSpellsByIds($ids);
    }

    /** @return list<array<string, mixed>> */
    protected function spellVariables(int $spellId): array
    {
        return SpellVariable::getVariablesBySpellId($spellId);
    }

    protected function deleteServer(int $serverId): void
    {
        $request = new Request();
        $request->attributes->set('user', ['uuid' => null, 'username' => 'Free servers']);
        (new ServersController())->delete($request, $serverId);
    }

    protected function reinstall(array $server): bool
    {
        $node = Node::getNodeById((int) $server['node_id']);
        if (!$node) {
            return false;
        }
        try {
            return Wings::fromNode($node, 30)->getServer()->reinstallServer((string) $server['uuid'])->isSuccessful();
        } catch (\Throwable $e) {
            App::getInstance(true)->getLogger()->warning('Free server reinstall failed for ' . $server['uuid'] . ': ' . $e->getMessage());

            return false;
        }
    }

    /** Put the spell, startup, image, variables and stack back after a failed stack change. */
    protected function restoreStack(int $serverId, int $freeId, array $previous): void
    {
        Server::updateServerById($serverId, $previous['fields']);
        if ($previous['variables'] !== []) {
            ServerVariable::createOrUpdateServerVariables($serverId, $previous['variables']);
        } else {
            ServerVariable::deleteServerVariablesByServerId($serverId);
        }
        FreeServer::setStack($freeId, $previous['stack']);
    }

    protected function syncUnsuspended(array $server): void
    {
        WingsSuspensionSync::afterUnsuspend($server, 15);
    }

    protected function powerStart(array $server): bool
    {
        $node = Node::getNodeById((int) $server['node_id']);
        if (!$node) {
            return false;
        }
        try {
            return Wings::fromNode($node, 15)->getServer()->startServer((string) $server['uuid'])->isSuccessful();
        } catch (\Throwable $e) {
            App::getInstance(true)->getLogger()->warning('Free server start after restore failed for ' . $server['uuid'] . ': ' . $e->getMessage());

            return false;
        }
    }

    /**
     * One create at a time per user on this web node, so two quick clicks cannot both pass the
     * limit check. finishCreate() covers several web nodes.
     */
    protected function withUserLock(int $userId, callable $fn): array
    {
        $dir = defined('APP_CACHE_DIR') ? (string) constant('APP_CACHE_DIR') : sys_get_temp_dir();
        $handle = @fopen(rtrim($dir, '/') . '/free-server-create-' . $userId . '.lock', 'c');
        if ($handle === false) {
            return $fn();
        }
        try {
            flock($handle, LOCK_EX);

            return $fn();
        } finally {
            flock($handle, LOCK_UN);
            fclose($handle);
        }
    }

    private static function noCapacity(): array
    {
        return self::fail('FREE_SERVER_NO_CAPACITY', 'There is no room for a free server right now. Try again later.', 503);
    }

    private static function fail(string $code, string $message, int $status): array
    {
        return ['ok' => false, 'code' => $code, 'message' => $message, 'status' => $status];
    }
}
