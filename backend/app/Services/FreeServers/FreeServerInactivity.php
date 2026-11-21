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
use App\Chat\Server;
use App\Chat\Activity;
use App\Chat\FreeServer;
use App\Chat\ServerActivity;
use App\Services\Wings\Wings;
use App\Chat\UserNotification;
use App\Helpers\ModerationReasonHelper;
use App\Services\Server\WingsSuspensionSync;

/**
 * Login-based rule for free servers: no panel visit by the owner for stop_after_days stops the
 * server, and stored_after_days moves it to storage (suspended, files and allocation kept).
 * Nothing is deleted. A visit before storage clears the stop; a stored server comes back when
 * the owner restores it (or staff lift the suspension).
 *
 * "Last visit" is the newest use of any of the owner's panel sessions; creating or restoring
 * the server also counts, so a new server never starts out idle.
 */
class FreeServerInactivity
{
    /** Suspension reasons set by this job start with this, so a restore never lifts a staff suspension. */
    public const STORAGE_REASON_PREFIX = 'Free server storage';

    private array $policy;

    public function __construct(?array $policy = null)
    {
        $this->policy = $policy ?? FreeServerPolicy::get();
    }

    /**
     * What a run would do now. Nothing is changed.
     *
     * @return array{items: list<array<string, mixed>>, counts: array<string, int>}
     */
    public function plan(): array
    {
        $now = $this->now();
        $items = [];
        $counts = [];
        foreach ($this->rows() as $row) {
            $step = self::decide($row, $this->policy, $now);
            if ($step === null) {
                continue;
            }
            $items[] = self::summary($row, $now) + ['step' => $step];
            $counts[$step] = ($counts[$step] ?? 0) + 1;
        }

        return ['items' => $items, 'counts' => $counts];
    }

    /**
     * Next step for one free server, or null when nothing is due.
     *
     * @param array<string, mixed> $row stage, stage_at, created_at, restored_at, last_login_at, last_device_at,
     *                                  suspended, suspension_reason, suspended_by_uuid
     */
    public static function decide(array $row, array $policy, int $now): ?string
    {
        $stage = isset($row['stage']) && $row['stage'] !== '' ? (string) $row['stage'] : null;
        $suspended = (int) ($row['suspended'] ?? 0) === 1;

        if ($stage === FreeServer::STAGE_STORED) {
            // Staff lifted the storage suspension: treat it like a restore.
            return $suspended ? null : 'reset';
        }

        $lastActive = self::lastActiveAt($row);
        if ($stage === FreeServer::STAGE_STOPPED) {
            $stageAt = self::time($row['stage_at'] ?? null) ?? $now;
            if ($lastActive > $stageAt) {
                return 'clear';
            }
        }
        if (!$policy['inactivity_enabled'] || $suspended) {
            // Suspended by staff or another system: leave it alone.
            return null;
        }

        $idle = $now - $lastActive;
        if ($idle >= $policy['store_after_days'] * 86400) {
            return 'store';
        }
        if ($stage === null && $idle >= $policy['stop_after_days'] * 86400) {
            return 'stop';
        }

        return null;
    }

    /** Unix time of the owner's last visit, or of the creation / restore when that is newer. */
    public static function lastActiveAt(array $row): int
    {
        $times = array_filter([
            self::time($row['created_at'] ?? null),
            self::time($row['restored_at'] ?? null),
            self::time($row['last_login_at'] ?? null),
            self::time($row['last_device_at'] ?? null),
        ], static fn (?int $t): bool => $t !== null);

        return $times === [] ? 0 : max($times);
    }

    /** True when the server is suspended because this job moved it to storage. */
    public static function isStorageSuspension(array $row): bool
    {
        if ((int) ($row['suspended'] ?? 0) !== 1) {
            return false;
        }
        $by = $row['suspended_by_uuid'] ?? null;

        return ($by === null || $by === '') && str_starts_with((string) ($row['suspension_reason'] ?? ''), self::STORAGE_REASON_PREFIX);
    }

    public static function storageReason(int $days): string
    {
        return self::STORAGE_REASON_PREFIX . ': no login for ' . $days . ' days. The owner can restore it from the panel.';
    }

    /**
     * Apply a plan.
     *
     * @return array{applied: array<string, int>, failed: int, results: list<array<string, mixed>>}
     */
    public function execute(array $plan, ?array $actor = null): array
    {
        $applied = [];
        $failed = 0;
        $results = [];
        foreach ($plan['items'] as $item) {
            $step = $item['step'];
            try {
                $outcome = match ($step) {
                    'stop' => $this->stop($item),
                    'store' => $this->store($item),
                    'clear' => $this->clear($item),
                    'reset' => $this->reset($item),
                    default => 'ignored',
                };
            } catch (\Throwable $e) {
                App::getInstance(true)->getLogger()->error('Free server ' . $step . ' failed for server ' . $item['server_id'] . ': ' . $e->getMessage());
                $outcome = 'error: ' . mb_substr($e->getMessage(), 0, 200);
            }
            $ok = !str_starts_with($outcome, 'error');
            $ok ? $applied[$step] = ($applied[$step] ?? 0) + 1 : ++$failed;
            $results[] = ['server_id' => $item['server_id'], 'name' => $item['name'], 'step' => $step, 'outcome' => $outcome];
            if ($ok && in_array($step, ['stop', 'store'], true)) {
                $this->audit($actor, 'free_server_' . $step, $item['name'] . ' (#' . $item['server_id'] . '): ' . $outcome);
            }
        }

        return ['applied' => $applied, 'failed' => $failed, 'results' => $results];
    }

    /**
     * Admin and API view of a row: when the next steps are due given the owner's last visit.
     *
     * @return array<string, mixed>
     */
    public function describe(array $row): array
    {
        $now = $this->now();
        $on = $this->policy['inactivity_enabled'];

        return self::summary($row, $now) + [
            'step' => self::decide($row, $this->policy, $now),
            'stop_at' => $on ? self::dueAt($row, $this->policy['stop_after_days']) : null,
            'store_at' => $on ? self::dueAt($row, $this->policy['store_after_days']) : null,
        ];
    }

    // Steps

    protected function stop(array $item): string
    {
        if (!$this->powerStop($item)) {
            return 'error: the node did not stop the server';
        }
        FreeServer::setStage($item['id'], FreeServer::STAGE_STOPPED, gmdate('Y-m-d H:i:s', $this->now()));
        $this->serverActivity($item, 'free_server_stopped');
        $this->notify($item, UserNotification::KIND_FREE_SERVER_STOPPED, '/server/' . $item['uuid_short']);

        return 'stopped';
    }

    protected function store(array $item): string
    {
        $fields = ModerationReasonHelper::suspensionAppliedFields(self::storageReason($this->policy['store_after_days']), null);
        if (!Server::updateServerById($item['server_id'], $fields)) {
            return 'error: could not update the server';
        }
        FreeServer::setStage($item['id'], FreeServer::STAGE_STORED, gmdate('Y-m-d H:i:s', $this->now()));
        $this->serverActivity($item, 'free_server_stored');
        $note = 'stored';
        if (!$this->syncSuspension($item)) {
            $note = 'stored (node could not be updated)';
        }
        $this->notify($item, UserNotification::KIND_FREE_SERVER_STORED, '/dashboard/servers');

        return $note;
    }

    protected function clear(array $item): string
    {
        FreeServer::setStage($item['id'], null);

        return 'cleared';
    }

    protected function reset(array $item): string
    {
        FreeServer::markRestored($item['id'], gmdate('Y-m-d H:i:s', $this->now()));

        return 'reset';
    }

    // Data access and side effects (protected so tests can replace them)

    /** @return list<array<string, mixed>> */
    protected function rows(): array
    {
        return FreeServer::listWithActivity();
    }

    protected function now(): int
    {
        return time();
    }

    protected function powerStop(array $item): bool
    {
        $node = Node::getNodeById((int) $item['node_id']);
        if (!$node) {
            return false;
        }
        try {
            return Wings::fromNode($node, 15)->getServer()->stopServer((string) $item['uuid'])->isSuccessful();
        } catch (\Throwable $e) {
            App::getInstance(true)->getLogger()->warning('Free server stop failed for ' . $item['uuid'] . ': ' . $e->getMessage());

            return false;
        }
    }

    protected function syncSuspension(array $item): bool
    {
        return WingsSuspensionSync::afterSuspend(['uuid' => $item['uuid'], 'node_id' => $item['node_id']], 15);
    }

    protected function notify(array $item, string $kind, string $link): void
    {
        UserNotification::notify((int) $item['owner_id'], $kind, [
            'server_name' => $item['name'],
            'days' => (string) $item['idle_days'],
        ], $link, $kind . ':' . $item['server_id']);
    }

    protected function serverActivity(array $item, string $event): void
    {
        ServerActivity::createActivity([
            'server_id' => $item['server_id'],
            'node_id' => $item['node_id'],
            'event' => $event,
            'metadata' => json_encode(['idle_days' => $item['idle_days']]),
        ]);
    }

    protected function audit(?array $actor, string $name, string $context): void
    {
        Activity::createActivity([
            'user_uuid' => $actor['uuid'] ?? null,
            'name' => $name,
            'context' => mb_substr($context, 0, 500),
            'ip_address' => $actor === null ? '127.0.0.1' : \App\CloudFlare\CloudFlareRealIP::getRealIP(),
        ]);
    }

    private static function summary(array $row, int $now): array
    {
        $lastActive = self::lastActiveAt($row);

        return [
            'id' => (int) $row['id'],
            'server_id' => (int) $row['server_id'],
            'uuid' => (string) ($row['uuid'] ?? ''),
            'uuid_short' => (string) ($row['uuid_short'] ?? ''),
            'name' => (string) ($row['name'] ?? ''),
            'node_id' => (int) ($row['node_id'] ?? 0),
            'owner_id' => (int) ($row['owner_id'] ?? 0),
            'owner_username' => $row['username'] ?? null,
            'stack' => (string) ($row['stack'] ?? ''),
            'stage' => isset($row['stage']) && $row['stage'] !== '' ? (string) $row['stage'] : null,
            'stage_at' => $row['stage_at'] ?? null,
            'suspended' => (int) ($row['suspended'] ?? 0) === 1,
            'last_login_at' => $row['last_login_at'] ?? null,
            'last_active_at' => $lastActive > 0 ? gmdate('Y-m-d H:i:s', $lastActive) : null,
            'idle_days' => (int) floor(max(0, $now - $lastActive) / 86400),
        ];
    }

    private static function dueAt(array $row, int $days): ?string
    {
        $lastActive = self::lastActiveAt($row);

        return $lastActive > 0 ? gmdate('Y-m-d H:i:s', $lastActive + $days * 86400) : null;
    }

    private static function time(mixed $value): ?int
    {
        if ($value === null || $value === '') {
            return null;
        }
        $t = strtotime((string) $value . ' UTC');

        return $t === false ? null : $t;
    }
}
