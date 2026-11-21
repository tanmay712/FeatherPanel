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

namespace App\Chat;

/**
 * Servers created through the free tier (featherpanel_free_servers). The owner is always the
 * server's current owner, so a server handed to someone else counts for them.
 */
class FreeServer
{
    public const STAGE_STOPPED = 'stopped';

    public const STAGE_STORED = 'stored';

    public const TABLE = 'featherpanel_free_servers';

    /**
     * Columns returned for listings: the free server row, the server basics and the owner's last
     * panel visit: the newest use of any of their sessions, and the device tracker as a fallback
     * for older login cookies that have no session row.
     */
    private const LIST_COLUMNS = 'f.id, f.server_id, f.stack, f.stage, f.stage_at, f.restored_at, f.created_at,
        s.uuid, s.uuidShort AS uuid_short, s.name, s.node_id, s.owner_id, s.suspended, s.suspension_reason,
        s.suspended_by_uuid, s.memory, s.disk, s.cpu, s.status,
        (SELECT MAX(us.last_seen_at) FROM featherpanel_user_sessions us WHERE us.user_id = s.owner_id) AS last_login_at,
        (SELECT MAX(d.last_seen) FROM featherpanel_user_devices d
            WHERE d.user_uuid = (SELECT ou.uuid FROM featherpanel_users ou WHERE ou.id = s.owner_id)) AS last_device_at';

    public static function create(int $serverId, string $stack, ?\PDO $pdo = null): int | false
    {
        $pdo ??= Database::getPdoConnection();
        $stmt = $pdo->prepare('INSERT INTO ' . self::TABLE . ' (server_id, stack, created_at) VALUES (:server_id, :stack, :created_at)');
        if (!$stmt->execute(['server_id' => $serverId, 'stack' => $stack, 'created_at' => gmdate('Y-m-d H:i:s')])) {
            return false;
        }

        return (int) $pdo->lastInsertId();
    }

    public static function getByServerId(int $serverId): ?array
    {
        $stmt = Database::getPdoConnection()->prepare('SELECT ' . self::LIST_COLUMNS . ' FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id WHERE f.server_id = :id LIMIT 1');
        $stmt->execute(['id' => $serverId]);

        return $stmt->fetch(\PDO::FETCH_ASSOC) ?: null;
    }

    /**
     * Like getByServerId(), for pages that must keep working when the free servers table is
     * missing (an update whose migrations have not run yet): errors count as "not a free server".
     */
    public static function findForServer(int $serverId): ?array
    {
        try {
            return self::getByServerId($serverId);
        } catch (\Throwable) {
            return null;
        }
    }

    public static function getByUuidShortForOwner(string $uuidShort, int $ownerId): ?array
    {
        $stmt = Database::getPdoConnection()->prepare('SELECT ' . self::LIST_COLUMNS . ' FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id WHERE s.uuidShort = :uuid AND s.owner_id = :owner LIMIT 1');
        $stmt->execute(['uuid' => $uuidShort, 'owner' => $ownerId]);

        return $stmt->fetch(\PDO::FETCH_ASSOC) ?: null;
    }

    public static function countForOwner(int $ownerId): int
    {
        $stmt = Database::getPdoConnection()->prepare('SELECT COUNT(*) FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id WHERE s.owner_id = :owner');
        $stmt->execute(['owner' => $ownerId]);

        return (int) $stmt->fetchColumn();
    }

    /**
     * Free server ids of the owner, oldest first.
     *
     * @return list<int>
     */
    public static function idsForOwner(int $ownerId): array
    {
        $stmt = Database::getPdoConnection()->prepare('SELECT f.id FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id WHERE s.owner_id = :owner ORDER BY f.id ASC');
        $stmt->execute(['owner' => $ownerId]);

        return array_map('intval', $stmt->fetchAll(\PDO::FETCH_COLUMN));
    }

    /** @return list<array<string, mixed>> */
    public static function listForOwner(int $ownerId): array
    {
        $stmt = Database::getPdoConnection()->prepare('SELECT ' . self::LIST_COLUMNS . ' FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id WHERE s.owner_id = :owner ORDER BY f.id ASC');
        $stmt->execute(['owner' => $ownerId]);

        return $stmt->fetchAll(\PDO::FETCH_ASSOC);
    }

    /**
     * Free servers with their owner, optionally filtered by stage and a search on the server
     * name, owner or short uuid. Used by the inactivity job and the admin list.
     *
     * @return list<array<string, mixed>>
     */
    public static function listWithActivity(?string $stage = null, ?string $search = null, int $limit = 0, int $offset = 0): array
    {
        [$where, $params] = self::filters($stage, $search);
        $sql = 'SELECT ' . self::LIST_COLUMNS . ', u.username, u.email
            FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id
            LEFT JOIN featherpanel_users u ON u.id = s.owner_id' . $where . ' ORDER BY f.id ASC';
        if ($limit > 0) {
            $sql .= ' LIMIT ' . (int) $limit . ' OFFSET ' . max(0, (int) $offset);
        }
        $stmt = Database::getPdoConnection()->prepare($sql);
        $stmt->execute($params);

        return $stmt->fetchAll(\PDO::FETCH_ASSOC);
    }

    public static function countWithActivity(?string $stage = null, ?string $search = null): int
    {
        [$where, $params] = self::filters($stage, $search);
        $stmt = Database::getPdoConnection()->prepare('SELECT COUNT(*) FROM ' . self::TABLE . ' f
            JOIN featherpanel_servers s ON s.id = f.server_id
            LEFT JOIN featherpanel_users u ON u.id = s.owner_id' . $where);
        $stmt->execute($params);

        return (int) $stmt->fetchColumn();
    }

    /** @return array<string, int> stage => count, 'running' for servers without a stage */
    public static function stageCounts(): array
    {
        $rows = Database::getPdoConnection()->query('SELECT COALESCE(stage, \'running\') AS stage, COUNT(*) AS total FROM ' . self::TABLE . ' GROUP BY COALESCE(stage, \'running\')')->fetchAll(\PDO::FETCH_ASSOC);
        $counts = ['running' => 0, self::STAGE_STOPPED => 0, self::STAGE_STORED => 0];
        foreach ($rows as $row) {
            $counts[(string) $row['stage']] = (int) $row['total'];
        }

        return $counts;
    }

    public static function setStage(int $id, ?string $stage, ?string $at = null): bool
    {
        $stmt = Database::getPdoConnection()->prepare('UPDATE ' . self::TABLE . ' SET stage = :stage, stage_at = :at WHERE id = :id');

        return $stmt->execute(['stage' => $stage, 'at' => $stage === null ? null : ($at ?? gmdate('Y-m-d H:i:s')), 'id' => $id]);
    }

    public static function setStack(int $id, string $stack): bool
    {
        return Database::getPdoConnection()->prepare('UPDATE ' . self::TABLE . ' SET stack = :stack WHERE id = :id')->execute(['stack' => $stack, 'id' => $id]);
    }

    /** Back to running: the inactivity clock starts again from now. */
    public static function markRestored(int $id, ?string $at = null): bool
    {
        $stmt = Database::getPdoConnection()->prepare('UPDATE ' . self::TABLE . ' SET stage = NULL, stage_at = NULL, restored_at = :at WHERE id = :id');

        return $stmt->execute(['at' => $at ?? gmdate('Y-m-d H:i:s'), 'id' => $id]);
    }

    public static function deleteById(int $id): bool
    {
        return Database::getPdoConnection()->prepare('DELETE FROM ' . self::TABLE . ' WHERE id = :id')->execute(['id' => $id]);
    }

    /**
     * @return array{0: string, 1: array<string, string>}
     */
    private static function filters(?string $stage, ?string $search): array
    {
        $clauses = [];
        $params = [];
        if ($stage === 'running') {
            $clauses[] = 'f.stage IS NULL';
        } elseif ($stage === self::STAGE_STOPPED || $stage === self::STAGE_STORED) {
            $clauses[] = 'f.stage = :stage';
            $params['stage'] = $stage;
        }
        $search = $search !== null ? trim($search) : '';
        if ($search !== '') {
            $clauses[] = '(s.name LIKE :q1 OR u.username LIKE :q2 OR u.email LIKE :q3 OR s.uuidShort LIKE :q4)';
            $like = '%' . addcslashes($search, '%_\\') . '%';
            $params += ['q1' => $like, 'q2' => $like, 'q3' => $like, 'q4' => $like];
        }

        return [$clauses === [] ? '' : ' WHERE ' . implode(' AND ', $clauses), $params];
    }
}
