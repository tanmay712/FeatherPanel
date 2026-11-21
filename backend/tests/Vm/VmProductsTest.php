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

namespace App\Tests\Vm;

use App\Helpers\ModuleGate;
use PHPUnit\Framework\TestCase;
use App\Services\Vm\VmProducts;

/**
 * VDS (Proxmox VE nodes) and VPS (OrveX nodes): product mapping, list filters and the
 * module gate rules for the virtual server API they share.
 */
class VmProductsTest extends TestCase
{
    public function testNodeTypesMapToProducts(): void
    {
        $this->assertSame('vds', VmProducts::productForNodeType('proxmox'));
        $this->assertSame('vps', VmProducts::productForNodeType('orvex'));
        $this->assertSame('vps', VmProducts::productForNodeType(' OrveX '));
        // Rows from before node types existed, or without a node, are Proxmox nodes.
        $this->assertSame('vds', VmProducts::productForNodeType(null));
        $this->assertSame('vds', VmProducts::productForNodeType(''));
        $this->assertSame('vds', VmProducts::productForNodeType('xen'));

        $this->assertSame('orvex', VmProducts::nodeTypeForProduct('vps'));
        $this->assertSame('proxmox', VmProducts::nodeTypeForProduct('vds'));
        $this->assertSame(ModuleGate::VDS, VmProducts::VDS);
        $this->assertSame(ModuleGate::VPS, VmProducts::VPS);
    }

    public function testNodeTypeValuesAreNormalized(): void
    {
        $this->assertSame('orvex', VmProducts::normalizeNodeType('ORVEX'));
        $this->assertSame('proxmox', VmProducts::normalizeNodeType(' proxmox'));
        foreach ([null, '', 'vps', 'vds', 'orvex2', 1, ['orvex'], true] as $bad) {
            $this->assertNull(VmProducts::normalizeNodeType($bad), var_export($bad, true));
        }

        foreach ([null, '', '   '] as $none) {
            $this->assertFalse(VmProducts::isInvalidFilter($none), var_export($none, true));
        }
        $this->assertFalse(VmProducts::isInvalidFilter('orvex'));
        $this->assertFalse(VmProducts::isInvalidFilter('Proxmox'));
        $this->assertTrue(VmProducts::isInvalidFilter('vps'));
        $this->assertTrue(VmProducts::isInvalidFilter(['orvex']));
    }

    public function testListsOnlyContainSwitchedOnProducts(): void
    {
        $both = ['vds' => true, 'vps' => true];
        $this->assertSame(['proxmox', 'orvex'], VmProducts::listableNodeTypes(null, $both));
        $this->assertSame(['proxmox', 'orvex'], VmProducts::listableNodeTypes('', $both));
        $this->assertSame(['orvex'], VmProducts::listableNodeTypes('orvex', $both));
        $this->assertSame(['proxmox'], VmProducts::listableNodeTypes('PROXMOX', $both));

        $vpsOff = ['vds' => true, 'vps' => false];
        $this->assertSame(['proxmox'], VmProducts::listableNodeTypes(null, $vpsOff));
        $this->assertSame([], VmProducts::listableNodeTypes('orvex', $vpsOff));
        $this->assertSame(['proxmox'], VmProducts::listableNodeTypes('proxmox', $vpsOff));

        $vdsOff = ['vds' => false, 'vps' => true];
        $this->assertSame(['orvex'], VmProducts::listableNodeTypes(null, $vdsOff));
        $this->assertSame([], VmProducts::listableNodeTypes('proxmox', $vdsOff));

        $this->assertSame([], VmProducts::listableNodeTypes(null, ['vds' => false, 'vps' => false]));
        // Missing switches count as on, like the module settings themselves.
        $this->assertSame(['proxmox', 'orvex'], VmProducts::listableNodeTypes(null, []));
        // An unknown filter value lists nothing (controllers answer 400 before this).
        $this->assertSame([], VmProducts::listableNodeTypes('xen', $both));
    }

    public function testNodeTypeSqlMirrorsIsOrvex(): void
    {
        $expr = VmProducts::nodeTypeSql('n');
        $this->assertSame(
            "(CASE WHEN LOWER(TRIM(COALESCE(n.node_type, ''))) = 'orvex' OR LOWER(TRIM(COALESCE(n.`user`, ''))) LIKE '%@orvex'"
            . " THEN 'orvex' ELSE 'proxmox' END)",
            $expr,
        );
        $this->expectException(\InvalidArgumentException::class);
        VmProducts::nodeTypeSql('n; DROP TABLE x');
    }

    public function testSqlConditionUsesNamedParameters(): void
    {
        $params = ['search' => '%a%'];
        $sql = VmProducts::sqlCondition('n', ['orvex'], $params);
        $this->assertSame(' AND ' . VmProducts::nodeTypeSql('n') . ' IN (:vm_node_type_0)', $sql);
        $this->assertSame(['search' => '%a%', 'vm_node_type_0' => 'orvex'], $params);

        $params = [];
        $sql = VmProducts::sqlCondition('node', ['proxmox', 'orvex', 'orvex', 'bogus'], $params, 'nt');
        $this->assertSame(' AND ' . VmProducts::nodeTypeSql('node') . ' IN (:nt_0, :nt_1)', $sql);
        $this->assertSame(['nt_0' => 'proxmox', 'nt_1' => 'orvex'], $params);

        $params = [];
        $this->assertSame(' AND 1 = 0', VmProducts::sqlCondition('n', [], $params));
        $this->assertSame(' AND 1 = 0', VmProducts::sqlCondition('n', ['bogus'], $params));
        $this->assertSame([], $params);

        $this->assertTrue(VmProducts::coversAll(['orvex', 'proxmox']));
        $this->assertFalse(VmProducts::coversAll(['orvex']));
        $this->assertFalse(VmProducts::coversAll([]));
    }

    public function testVirtualServerPathsAreSharedByVdsAndVps(): void
    {
        foreach ([
            '/api/user/vm-instances',
            '/api/user/vm-instances/12/power',
            '/api/user/vds-chatbot/chat',
            '/api/admin/vm-instances/creation-status/abc',
            '/api/admin/vm-nodes/3/orvex/token',
            '/api/admin/vm-templates/9',
            '/api/admin/analytics/vds/dashboard',
        ] as $path) {
            $this->assertTrue(ModuleGate::isVmPath($path), $path);
            $this->assertSame('vds', ModuleGate::moduleForPath($path), $path);
        }
        foreach (['/api/user/vm-instancesx', '/api/admin/vm-capacity', '/api/remote/orvex/register', '/api/admin/servers'] as $path) {
            $this->assertFalse(ModuleGate::isVmPath($path), $path);
        }
        $this->assertSame('game', ModuleGate::moduleForPath('/api/admin/servers/1'));
        $this->assertSame('web', ModuleGate::moduleForPath('/api/user/webspaces'));
        $this->assertNull(ModuleGate::moduleForPath('/api/remote/orvex/register'));
    }

    public function testResourcesAreFoundInVirtualServerPaths(): void
    {
        $this->assertSame(['instance', 12], ModuleGate::vmResourceFromPath('/api/user/vm-instances/12'));
        $this->assertSame(['instance', 12], ModuleGate::vmResourceFromPath('/api/user/vm-instances/12/backups/3'));
        $this->assertSame(['instance', 7], ModuleGate::vmResourceFromPath('/api/admin/vm-instances/7/power'));
        $this->assertSame(['node', 3], ModuleGate::vmResourceFromPath('/api/admin/vm-nodes/3'));
        $this->assertSame(['node', 3], ModuleGate::vmResourceFromPath('/api/admin/vm-nodes/3/ips/5'));
        $this->assertSame(['template', 9], ModuleGate::vmResourceFromPath('/api/admin/vm-templates/9'));

        foreach ([
            '/api/user/vm-instances',
            '/api/user/vm-instances/tasks/abc',
            '/api/admin/vm-instances/creation-status/99',
            '/api/admin/vm-nodes',
            '/api/admin/vm-nodes/abc',
            '/api/user/vds-chatbot/conversations/4',
            '/api/admin/analytics/vds/dashboard',
            '/api/user/vm-instances/12x',
        ] as $path) {
            $this->assertNull(ModuleGate::vmResourceFromPath($path), $path);
        }
    }

    public function testGateDecidesPerNodeWhenOnlyOneProductIsOn(): void
    {
        // Both on: nothing to check.
        $this->assertNull(ModuleGate::vmModuleToCheck(true, true, true, 'orvex'));
        $this->assertNull(ModuleGate::vmModuleToCheck(true, true, false, null));
        // Both off: the whole virtual server API is refused (reported as VDS).
        $this->assertSame('vds', ModuleGate::vmModuleToCheck(false, false, false, null));
        $this->assertSame('vds', ModuleGate::vmModuleToCheck(false, false, true, 'orvex'));
        // VPS off: OrveX resources are refused, Proxmox ones and lists pass.
        $this->assertSame('vps', ModuleGate::vmModuleToCheck(true, false, true, 'orvex'));
        $this->assertSame('vds', ModuleGate::vmModuleToCheck(true, false, true, 'proxmox'));
        $this->assertNull(ModuleGate::vmModuleToCheck(true, false, false, null));
        // VDS off: the other way round.
        $this->assertSame('vds', ModuleGate::vmModuleToCheck(false, true, true, 'proxmox'));
        $this->assertSame('vps', ModuleGate::vmModuleToCheck(false, true, true, 'orvex'));
        // Unknown resources go on to the controller, which answers 404.
        $this->assertNull(ModuleGate::vmModuleToCheck(false, true, true, null));
    }
}
