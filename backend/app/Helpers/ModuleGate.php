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

namespace App\Helpers;

use App\App;
use App\Chat\Database;
use App\Config\ConfigInterface;
use App\Services\Vm\VmProducts;
use Symfony\Component\HttpFoundation\Response;

/**
 * Admin-toggleable panel modules (game servers, web hosting, VDS, VPS).
 *
 * A disabled module keeps its data but its user and admin API answers 403 MODULE_DISABLED.
 * Daemon callbacks (Wings, FeatherQuilld, Proxmox tasks, OrveX node registration) are never
 * gated so running infrastructure keeps reporting while a module is hidden.
 *
 * VDS (Proxmox VE nodes) and VPS (OrveX nodes) share the virtual server API. A request for
 * one server, node or template is refused when the module of its node is off; list
 * endpoints leave out the switched-off product themselves ({@see self::listableVmNodeTypes()}).
 */
class ModuleGate
{
    public const GAME = 'game';
    public const WEB = 'web';
    public const VDS = 'vds';
    public const VPS = 'vps';

    /** @var array<string, string> */
    private const SETTING_KEYS = [
        self::GAME => ConfigInterface::MODULE_GAME_ENABLED,
        self::WEB => ConfigInterface::MODULE_WEB_ENABLED,
        self::VDS => ConfigInterface::MODULE_VDS_ENABLED,
        self::VPS => ConfigInterface::MODULE_VPS_ENABLED,
    ];

    /**
     * API path prefixes owned by a module. Matched on whole path segments.
     *
     * @var array<string, string>
     */
    private const PREFIXES = [
        '/api/user/servers' => self::GAME,
        '/api/user/spells' => self::GAME,
        '/api/user/realms' => self::GAME,
        '/api/admin/servers' => self::GAME,
        '/api/admin/server-activities' => self::GAME,
        '/api/admin/nodes' => self::GAME,
        '/api/admin/allocations' => self::GAME,
        '/api/admin/realms' => self::GAME,
        '/api/admin/spells' => self::GAME,
        '/api/admin/spell-variables' => self::GAME,
        '/api/admin/mounts' => self::GAME,
        '/api/admin/wings-backups' => self::GAME,
        '/api/admin/backup-schedules' => self::GAME,
        '/api/admin/subdomains' => self::GAME,
        '/api/admin/pterodactyl-importer' => self::GAME,
        '/api/admin/analytics/servers' => self::GAME,
        '/api/user/free-servers' => self::GAME,
        '/api/admin/free-servers' => self::GAME,
        '/api/user/webspaces' => self::WEB,
        '/api/admin/webspaces' => self::WEB,
        '/api/admin/web-nodes' => self::WEB,
        '/api/admin/webplates' => self::WEB,
        '/api/admin/hosting-packages' => self::WEB,
        '/api/admin/mail-hosts' => self::WEB,
        '/api/admin/dns-hosts' => self::WEB,
    ];

    /**
     * Virtual server API shared by the VDS and VPS modules. Matched on whole path segments.
     *
     * @var list<string>
     */
    private const VM_PREFIXES = [
        '/api/user/vm-instances',
        '/api/user/vds-chatbot',
        '/api/admin/vm-instances',
        '/api/admin/vm-nodes',
        '/api/admin/vm-templates',
        '/api/admin/analytics/vds',
    ];

    /**
     * Module owning a path. Shared virtual server paths report VDS, the module they had
     * before VPS existed; {@see self::check()} applies the per-node rules for them.
     */
    public static function moduleForPath(string $path): ?string
    {
        if (self::isVmPath($path)) {
            return self::VDS;
        }
        foreach (self::PREFIXES as $prefix => $module) {
            if (self::matchesPrefix($path, $prefix)) {
                return $module;
            }
        }

        return null;
    }

    public static function isVmPath(string $path): bool
    {
        foreach (self::VM_PREFIXES as $prefix) {
            if (self::matchesPrefix($path, $prefix)) {
                return true;
            }
        }

        return false;
    }

    public static function isEnabled(string $module): bool
    {
        $key = self::SETTING_KEYS[$module] ?? null;
        if ($key === null) {
            return true;
        }

        return App::getInstance(true)->getConfig()->getSetting($key, 'true') !== 'false';
    }

    /**
     * Returns the refusal for a request to a disabled module, or null when it may proceed.
     */
    public static function check(string $path): ?Response
    {
        if (self::isVmPath($path)) {
            return self::checkVm($path);
        }

        $module = self::moduleForPath($path);
        if ($module === null || self::isEnabled($module)) {
            return null;
        }

        return self::refusal($module);
    }

    /**
     * Which virtual server products are switched on.
     *
     * @return array<string, bool> product => switched on
     */
    public static function vmProducts(): array
    {
        return [
            VmProducts::VDS => self::isEnabled(self::VDS),
            VmProducts::VPS => self::isEnabled(self::VPS),
        ];
    }

    /**
     * Node types a virtual server list may return for an optional `node_type` filter.
     *
     * @return list<string>
     */
    public static function listableVmNodeTypes(?string $requested = null): array
    {
        return VmProducts::listableNodeTypes($requested, self::vmProducts());
    }

    /**
     * Refusal for creating something on a node of this type while its module is off, or null.
     */
    public static function refuseVmNodeType(?string $nodeType): ?Response
    {
        $module = VmProducts::productForNodeType($nodeType);

        return self::isEnabled($module) ? null : self::refusal($module);
    }

    /**
     * The server, node or template a virtual server API path is about, as [kind, id].
     *
     * @return array{0: 'instance'|'node'|'template', 1: int}|null null for lists and other paths
     */
    public static function vmResourceFromPath(string $path): ?array
    {
        if (preg_match('#^/api/(?:user|admin)/vm-instances/(\d+)(?:/|$)#', $path, $m) === 1) {
            return ['instance', (int) $m[1]];
        }
        if (preg_match('#^/api/admin/vm-nodes/(\d+)(?:/|$)#', $path, $m) === 1) {
            return ['node', (int) $m[1]];
        }
        if (preg_match('#^/api/admin/vm-templates/(\d+)(?:/|$)#', $path, $m) === 1) {
            return ['template', (int) $m[1]];
        }

        return null;
    }

    /**
     * Module that decides a virtual server request when only one of VDS and VPS is on.
     *
     * @param string|null $nodeType node type of the requested resource, null when unknown
     *
     * @return string|null the module to check, or null when the request may proceed
     */
    public static function vmModuleToCheck(bool $vdsOn, bool $vpsOn, bool $hasResource, ?string $nodeType): ?string
    {
        if ($vdsOn && $vpsOn) {
            return null;
        }
        if (!$vdsOn && !$vpsOn) {
            return self::VDS;
        }
        if (!$hasResource || $nodeType === null) {
            // Lists filter themselves; unknown ids get their 404 from the controller.
            return null;
        }

        return VmProducts::productForNodeType($nodeType);
    }

    private static function checkVm(string $path): ?Response
    {
        $vdsOn = self::isEnabled(self::VDS);
        $vpsOn = self::isEnabled(self::VPS);
        if ($vdsOn && $vpsOn) {
            return null;
        }

        $resource = ($vdsOn || $vpsOn) ? self::vmResourceFromPath($path) : null;
        $nodeType = $resource !== null ? self::lookupNodeType($resource[0], $resource[1]) : null;
        $module = self::vmModuleToCheck($vdsOn, $vpsOn, $resource !== null, $nodeType);

        if ($module === null || self::isEnabled($module)) {
            return null;
        }

        return self::refusal($module);
    }

    /**
     * Node type of a server, node or template, or null when it does not exist.
     */
    private static function lookupNodeType(string $kind, int $id): ?string
    {
        $type = VmProducts::nodeTypeSql('n');
        $sql = match ($kind) {
            'instance' => 'SELECT ' . $type . ' FROM featherpanel_vm_instances i
                LEFT JOIN featherpanel_vm_nodes n ON n.id = i.vm_node_id WHERE i.id = :id LIMIT 1',
            'node' => 'SELECT ' . $type . ' FROM featherpanel_vm_nodes n WHERE n.id = :id LIMIT 1',
            'template' => 'SELECT ' . $type . ' FROM featherpanel_vm_templates t
                LEFT JOIN featherpanel_vm_nodes n ON n.id = t.vm_node_id WHERE t.id = :id LIMIT 1',
            default => null,
        };
        if ($sql === null) {
            return null;
        }

        try {
            $stmt = Database::getPdoConnection()->prepare($sql);
            $stmt->execute(['id' => $id]);
            $value = $stmt->fetchColumn();
        } catch (\Throwable $e) {
            App::getInstance(true)->getLogger()->warning('ModuleGate: node type lookup failed: ' . $e->getMessage());

            return null;
        }

        return $value === false ? null : (string) $value;
    }

    private static function refusal(string $module): Response
    {
        return ApiResponse::error(
            'This module is disabled by the administrator',
            'MODULE_DISABLED',
            403,
            ['module' => $module],
        );
    }

    private static function matchesPrefix(string $path, string $prefix): bool
    {
        return $path === $prefix || str_starts_with($path, $prefix . '/');
    }
}
