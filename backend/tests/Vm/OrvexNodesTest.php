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

use PHPUnit\Framework\TestCase;
use App\Services\Vm\OrvexNodes;

/**
 * OrveX VPS Node registration rules that need no database: tokens, the addresses
 * the panel may connect to, payload validation and the shared-IPv4 pool.
 */
class OrvexNodesTest extends TestCase
{
    public function testTokensCarryTheNodeIdAndParseBack(): void
    {
        $token = OrvexNodes::generateToken(42);
        $this->assertMatchesRegularExpression('/^orvx_42_[A-Za-z0-9]{48}$/', $token);
        $this->assertSame([42, $token], OrvexNodes::parseToken('  ' . $token . "\n"));
        $this->assertNotSame($token, OrvexNodes::generateToken(42));

        foreach (['', 'orvx_0_' . str_repeat('a', 48), 'orvx_1_' . str_repeat('a', 47), 'orvx_1_' . str_repeat('-', 48), 'orvx_x_' . str_repeat('a', 48), 'Bearer orvx_1_' . str_repeat('a', 48)] as $bad) {
            $this->assertNull(OrvexNodes::parseToken($bad), $bad);
        }
    }

    public function testTokenMustMatchAndBeUnexpired(): void
    {
        $now = 1_800_000_000;
        $token = OrvexNodes::generateToken(7);
        $node = ['registration_token' => $token, 'registration_expires_at' => date('Y-m-d H:i:s', $now + 60)];

        $this->assertTrue(OrvexNodes::tokenMatches($node, $token, $now));
        $this->assertFalse(OrvexNodes::tokenMatches($node, OrvexNodes::generateToken(7), $now));
        $this->assertFalse(OrvexNodes::tokenMatches($node, $token, $now + 61));
        $this->assertFalse(OrvexNodes::tokenMatches(['registration_token' => '', 'registration_expires_at' => $node['registration_expires_at']], '', $now));
        $this->assertFalse(OrvexNodes::tokenMatches(['registration_token' => $token, 'registration_expires_at' => null], $token, $now));
    }

    public function testNodeTypeDetection(): void
    {
        $this->assertTrue(OrvexNodes::isOrvex(['node_type' => 'orvex']));
        $this->assertTrue(OrvexNodes::isOrvex(['node_type' => 'proxmox', 'user' => 'orvex@orvex']));
        $this->assertFalse(OrvexNodes::isOrvex(['node_type' => 'proxmox', 'user' => 'root@pam']));
        $this->assertTrue(OrvexNodes::isPending(['node_type' => 'orvex', 'registered_at' => null]));
        $this->assertFalse(OrvexNodes::isPending(['node_type' => 'orvex', 'registered_at' => '2026-11-20 10:00:00']));
        $this->assertFalse(OrvexNodes::isPending(['node_type' => 'proxmox', 'user' => 'root@pam']));
    }

    public function testNewNodesGetPlaceholdersInsteadOfAdminInput(): void
    {
        $data = OrvexNodes::newNodeDefaults([
            'name' => 'Frankfurt 1',
            'location_id' => 3,
            'fqdn' => '203.0.113.5',
            'secret' => 'typed-by-admin',
            'registered_at' => '2026-01-01 00:00:00',
            'feathertail_enabled' => 1,
        ]);

        $this->assertSame('Frankfurt 1', $data['name']);
        $this->assertSame(3, $data['location_id']);
        $this->assertSame('orvex', $data['node_type']);
        $this->assertSame(OrvexNodes::PENDING_FQDN, $data['fqdn']);
        $this->assertSame('orvex@orvex', $data['user']);
        $this->assertSame('true', $data['tls_no_verify']);
        $this->assertNotSame('typed-by-admin', $data['secret']);
        $this->assertArrayNotHasKey('registered_at', $data);
        $this->assertArrayNotHasKey('feathertail_enabled', $data);
    }

    public function testAllowedAddresses(): void
    {
        foreach (['203.0.113.10', '10.0.0.5', '192.168.1.20', '2001:db8::10', 'node1.example.com', 'node-1'] as $ok) {
            $this->assertTrue(OrvexNodes::isAllowedAddress($ok), $ok);
        }
        foreach (['', '127.0.0.1', '127.1.2.3', '0.0.0.0', '169.254.1.1', '224.0.0.1', '255.255.255.255', '::1', '::', 'fe80::1', 'ff02::1', 'localhost', 'a.localhost', 'pending.invalid', 'bad_host.example', '-x.example.com', 'http://example.com', str_repeat('a', 254)] as $bad) {
            $this->assertFalse(OrvexNodes::isAllowedAddress($bad), $bad);
        }
    }

    public function testValidRegistrationIsNormalised(): void
    {
        [$clean, $errors, $warnings] = OrvexNodes::validateRegistration($this->payload());

        $this->assertSame([], $errors);
        $this->assertSame([], $warnings);
        $this->assertSame('203.0.113.10', $clean['address']);
        $this->assertSame(8006, $clean['port']);
        $this->assertSame('orvex@orvex', $clean['api_user']);
        $this->assertTrue($clean['kvm']);
        $this->assertSame('10.77.0.0/24', $clean['nat']['subnet']);
        $this->assertSame(22000, $clean['nat']['ssh_port_base']);
        $this->assertCount(2, $clean['templates']);
        $this->assertSame(['vmid' => 9000, 'name' => 'ubuntu-24.04-kvm', 'type' => 'qemu', 'description' => 'Ubuntu 24.04 LTS (KVM)'], $clean['templates'][0]);
        $this->assertSame('debian-12-lxc', $clean['templates'][1]['description']);
        $this->assertSame(['hostname' => 'node1.example.com', 'cpus' => 8], $clean['host']);
    }

    public function testConnectionFieldsAreStrict(): void
    {
        $cases = [
            ['address' => '127.0.0.1'],
            ['address' => ''],
            ['port' => 0],
            ['port' => '80a'],
            ['api_user' => 'root@pam'],
            ['api_token_id' => 'bad id'],
            ['api_token_secret' => 'short'],
            ['api_token_secret' => str_repeat('x', 20) . ' space'],
        ];
        foreach ($cases as $override) {
            [, $errors] = OrvexNodes::validateRegistration(array_merge($this->payload(), $override));
            $this->assertNotEmpty($errors, json_encode($override));
        }
    }

    public function testNodeReportProblemsAreWarningsNotErrors(): void
    {
        $payload = array_merge($this->payload(), [
            'nat' => ['subnet' => '10.77.0.0/8', 'gateway' => '10.77.0.1'],
            'templates' => [
                ['vmid' => 9000, 'name' => 'ok-one', 'type' => 'qemu'],
                ['vmid' => 9000, 'name' => 'duplicate', 'type' => 'qemu'],
                ['vmid' => 50, 'name' => 'too-low', 'type' => 'lxc'],
                ['vmid' => 9001, 'name' => 'bad type', 'type' => 'docker'],
                ['vmid' => 'abc', 'name' => 'no-number', 'type' => 'lxc'],
                ['vmid' => '9002', 'name' => 'string-vmid', 'type' => 'LXC', 'description' => '<b>Debian</b> 12'],
            ],
            'tls_fingerprint' => 'not-a-fingerprint',
        ]);
        [$clean, $errors, $warnings] = OrvexNodes::validateRegistration($payload);

        $this->assertSame([], $errors);
        $this->assertNull($clean['nat']);
        $this->assertNull($clean['tls_fingerprint']);
        $this->assertSame([9000, 9002], array_column($clean['templates'], 'vmid'));
        $this->assertSame('lxc', $clean['templates'][1]['type']);
        $this->assertSame('Debian 12', $clean['templates'][1]['description']);
        $this->assertCount(6, $warnings);
    }

    public function testSharedPoolSkipsNetworkBroadcastAndGateway(): void
    {
        $pool = OrvexNodes::poolAddresses('10.77.0.0/24', '10.77.0.1');
        $this->assertCount(253, $pool);
        $this->assertSame('10.77.0.2', $pool[0]);
        $this->assertSame('10.77.0.254', $pool[252]);

        $this->assertSame(['192.168.5.1', '192.168.5.3', '192.168.5.4', '192.168.5.5', '192.168.5.6'], OrvexNodes::poolAddresses('192.168.5.0/29', '192.168.5.2'));
        $this->assertCount(OrvexNodes::MAX_POOL_ADDRESSES, OrvexNodes::poolAddresses('10.80.0.0/16', '10.80.0.1'));
        $this->assertSame([], OrvexNodes::poolAddresses('10.77.0.0/24', '10.78.0.1'));
        $this->assertSame([], OrvexNodes::poolAddresses('10.77.0.0/31', '10.77.0.1'));
    }

    public function testNatValidation(): void
    {
        $this->assertTrue(OrvexNodes::validNat('10.77.0.0/24', '10.77.0.1'));
        $this->assertTrue(OrvexNodes::validNat('10.77.0.9/24', '10.77.0.1'));
        $this->assertFalse(OrvexNodes::validNat('10.77.0.0/24', '10.77.0.0'));
        $this->assertFalse(OrvexNodes::validNat('10.77.0.0/24', '10.77.0.255'));
        $this->assertFalse(OrvexNodes::validNat('10.77.0.0/15', '10.77.0.1'));
        $this->assertFalse(OrvexNodes::validNat('fd00::/64', 'fd00::1'));
        $this->assertTrue(OrvexNodes::ipInSubnet('10.77.0.200', '10.77.0.0/24'));
        $this->assertFalse(OrvexNodes::ipInSubnet('10.77.1.1', '10.77.0.0/24'));
    }

    public function testInstallInfoHidesExpiredTokens(): void
    {
        $now = 1_800_000_000;
        $node = [
            'node_type' => 'orvex',
            'registered_at' => null,
            'registration_token' => 'orvx_5_' . str_repeat('A', 48),
            'registration_expires_at' => date('Y-m-d H:i:s', $now + 3600),
            'agent_info' => '{"kvm":true}',
        ];
        $info = OrvexNodes::installInfo($node, $now);
        $this->assertFalse($info['registered']);
        $this->assertSame($node['registration_token'], $info['token']);
        $this->assertSame(3600, $info['expires_in']);
        $this->assertSame(['kvm' => true], $info['agent']);
        $this->assertNull($info['endpoint']);
        $this->assertStringStartsWith('https://raw.githubusercontent.com/', $info['installer']['url']);

        $expired = OrvexNodes::installInfo($node, $now + 7200);
        $this->assertNull($expired['token']);
        $this->assertNull($expired['expires_at']);
        $this->assertNull($expired['expires_in']);

        $connected = OrvexNodes::installInfo(array_merge($node, ['registered_at' => '2026-11-20 10:00:00', 'fqdn' => '203.0.113.10', 'port' => 8006, 'scheme' => 'https']), $now);
        $this->assertTrue($connected['registered']);
        $this->assertSame('https://203.0.113.10:8006', $connected['endpoint']);
    }

    public function testInstallerSourceFollowsEnvironment(): void
    {
        $previousRepo = getenv('ORVEX_REPO');
        $previousBranch = getenv('ORVEX_BRANCH');
        try {
            putenv('ORVEX_REPO=someone/Fork');
            putenv('ORVEX_BRANCH=feature/nodes');
            $source = OrvexNodes::installerSource();
            $this->assertSame('https://raw.githubusercontent.com/someone/Fork/feature/nodes/install.sh', $source['url']);

            putenv('ORVEX_REPO=bad repo');
            putenv('ORVEX_BRANCH=../../etc');
            $source = OrvexNodes::installerSource();
            $this->assertSame(OrvexNodes::DEFAULT_REPO, $source['repo']);
            $this->assertSame(OrvexNodes::DEFAULT_BRANCH, $source['branch']);
        } finally {
            putenv($previousRepo === false ? 'ORVEX_REPO' : 'ORVEX_REPO=' . $previousRepo);
            putenv($previousBranch === false ? 'ORVEX_BRANCH' : 'ORVEX_BRANCH=' . $previousBranch);
        }
    }

    /**
     * @return array<string, mixed>
     */
    private function payload(): array
    {
        return [
            'address' => '203.0.113.10',
            'port' => 8006,
            'api_user' => 'orvex@orvex',
            'api_token_id' => 'panel',
            'api_token_secret' => '3f0f6c1e-2b7a-4d39-9f1e-6c2d7f8a9b10',
            'node_name' => 'node1',
            'agent_version' => '1.1.0',
            'tls_fingerprint' => implode(':', array_fill(0, 32, 'AB')),
            'public_ipv4' => '203.0.113.10',
            'kvm' => true,
            'storage_pool' => 'default',
            'backup_storage' => 'backups',
            'nat' => ['subnet' => '10.77.0.0/24', 'gateway' => '10.77.0.1', 'ssh_port_base' => 22000, 'port_range_base' => 30000, 'port_range_size' => 20],
            'templates' => [
                ['vmid' => 9000, 'name' => 'ubuntu-24.04-kvm', 'type' => 'qemu', 'description' => 'Ubuntu 24.04 LTS (KVM)'],
                ['vmid' => 9102, 'name' => 'debian-12-lxc', 'type' => 'lxc'],
            ],
            'host' => ['hostname' => 'node1.example.com', 'cpus' => 8],
        ];
    }
}
