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

namespace App\Services\Vm;

/**
 * The two virtual server products of OrveX Panel.
 *
 * - VDS: virtual servers on Proxmox VE nodes.
 * - VPS: virtual servers on OrveX nodes, the panel's own node system.
 *
 * Both share one engine (tables, API and runner); a server belongs to the product of
 * its node, decided by `featherpanel_vm_nodes.node_type`. Each product is its own
 * panel module with its own on/off switch, so the product names match the module
 * names used by {@see \App\Helpers\ModuleGate}.
 */
final class VmProducts
{
    public const VDS = 'vds';
    public const VPS = 'vps';

    /** @var array<string, string> node_type => product */
    private const PRODUCT_BY_NODE_TYPE = [
        OrvexNodes::TYPE_PROXMOX => self::VDS,
        OrvexNodes::TYPE => self::VPS,
    ];

    /** Product of a node type. Unknown or missing types are Proxmox nodes (VDS), as before node types existed. */
    public static function productForNodeType(?string $nodeType): string
    {
        return self::PRODUCT_BY_NODE_TYPE[self::normalizeNodeType($nodeType) ?? OrvexNodes::TYPE_PROXMOX];
    }

    public static function nodeTypeForProduct(string $product): string
    {
        return $product === self::VPS ? OrvexNodes::TYPE : OrvexNodes::TYPE_PROXMOX;
    }

    /** The node type a value names ('proxmox' or 'orvex'), or null for anything else. */
    public static function normalizeNodeType(mixed $value): ?string
    {
        if (!is_string($value)) {
            return null;
        }
        $value = strtolower(trim($value));

        return isset(self::PRODUCT_BY_NODE_TYPE[$value]) ? $value : null;
    }

    /**
     * Node types a list request may return: the requested type (when one is given),
     * limited to the products that are switched on.
     *
     * @param array<string, bool> $enabled product => switched on
     *
     * @return list<string> empty when nothing may be listed
     */
    public static function listableNodeTypes(?string $requested, array $enabled): array
    {
        $types = [];
        foreach (self::PRODUCT_BY_NODE_TYPE as $type => $product) {
            if (($enabled[$product] ?? true) === true) {
                $types[] = $type;
            }
        }

        if ($requested === null || trim($requested) === '') {
            return $types;
        }
        $requested = self::normalizeNodeType($requested);

        return $requested !== null && in_array($requested, $types, true) ? [$requested] : [];
    }

    /**
     * True when a node type filter value was given but names no node type.
     */
    public static function isInvalidFilter(mixed $value): bool
    {
        if ($value === null || (is_string($value) && trim($value) === '')) {
            return false;
        }

        return self::normalizeNodeType($value) === null;
    }

    /**
     * SQL expression giving the node type ('orvex' or 'proxmox') of the node joined as `$alias`.
     * Mirrors {@see OrvexNodes::isOrvex()}: OrveX nodes added by hand are recognised by the
     * "@orvex" realm of their API user. A missing node row counts as a Proxmox node.
     */
    public static function nodeTypeSql(string $alias): string
    {
        if (preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/', $alias) !== 1) {
            throw new \InvalidArgumentException('Invalid table alias');
        }

        return "(CASE WHEN LOWER(TRIM(COALESCE({$alias}.node_type, ''))) = '" . OrvexNodes::TYPE . "'"
            . " OR LOWER(TRIM(COALESCE({$alias}.`user`, ''))) LIKE '%@orvex'"
            . " THEN '" . OrvexNodes::TYPE . "' ELSE '" . OrvexNodes::TYPE_PROXMOX . "' END)";
    }

    /**
     * SQL condition (starting with " AND") limiting rows to nodes of the given types, for the
     * node joined as `$alias` (see {@see self::nodeTypeSql()}).
     *
     * @param list<string> $nodeTypes
     * @param array<string, mixed> $params named parameters, extended in place
     */
    public static function sqlCondition(string $alias, array $nodeTypes, array &$params, string $prefix = 'vm_node_type'): string
    {
        $names = [];
        foreach (array_values(array_unique($nodeTypes)) as $i => $type) {
            $type = self::normalizeNodeType($type);
            if ($type === null) {
                continue;
            }
            $name = $prefix . '_' . $i;
            $names[] = ':' . $name;
            $params[$name] = $type;
        }

        if ($names === []) {
            return ' AND 1 = 0';
        }

        return ' AND ' . self::nodeTypeSql($alias) . ' IN (' . implode(', ', $names) . ')';
    }

    /** True when every node type is listed, so no SQL filter is needed. */
    public static function coversAll(array $nodeTypes): bool
    {
        foreach (array_keys(self::PRODUCT_BY_NODE_TYPE) as $type) {
            if (!in_array($type, $nodeTypes, true)) {
                return false;
            }
        }

        return true;
    }
}
