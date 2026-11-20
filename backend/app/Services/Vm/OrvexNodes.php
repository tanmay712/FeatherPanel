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

use App\App;
use App\Chat\VmIp;
use App\Chat\VmNode;
use App\Chat\Database;
use App\Chat\VmTemplate;

/**
 * OrveX VPS Nodes: the panel's own VPS node system (vps-node/ in this repository).
 *
 * An admin creates an OrveX node in the panel and gets a one-time install command.
 * The installer sets the server up and calls the public registration endpoint with
 * that token. The node reports how the panel reaches it (address, port, API token),
 * its templates, storage and shared-IPv4 (NAT) network, and the panel configures the
 * node, its templates and its IP pool automatically. No Proxmox is involved: the
 * agent runs KVM and LXC guests through Incus and speaks the API the panel uses.
 */
final class OrvexNodes
{
    public const TYPE = 'orvex';
    public const TYPE_PROXMOX = 'proxmox';

    /** Placeholder host of a node that has not registered yet (".invalid" never resolves). */
    public const PENDING_FQDN = 'pending.invalid';

    /** Lifetime of an install command / registration token. */
    public const TOKEN_TTL_SECONDS = 86400;

    public const MAX_TEMPLATES = 200;
    public const MAX_POOL_ADDRESSES = 1024;
    public const MAX_PAYLOAD_BYTES = 262144;

    public const DEFAULT_REPO = 'tanmay712/FeatherPanel';
    public const DEFAULT_BRANCH = 'develop';

    /** Notes put on the shared-IPv4 addresses the panel adds for a node. */
    public const POOL_NOTE = 'Shared IPv4 (NAT) - added by the OrveX node';

    /**
     * Columns owned by the registration. Generic node updates never change them on
     * OrveX nodes (and never set the registration columns on Proxmox nodes).
     *
     * @var array<int, string>
     */
    public const MANAGED_FIELDS = [
        'fqdn', 'scheme', 'port', 'user', 'token_id', 'secret', 'tls_no_verify',
        'node_type', 'registration_token', 'registration_expires_at', 'registered_at',
        'agent_version', 'agent_info',
    ];

    /** @var array<int, string> */
    public const REGISTRATION_FIELDS = [
        'node_type', 'registration_token', 'registration_expires_at', 'registered_at', 'agent_version', 'agent_info',
    ];

    private const TOKEN_PATTERN = '/^orvx_([1-9][0-9]{0,9})_([A-Za-z0-9]{48})$/';
    private const NAME_PATTERN = '/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/';
    private const FINGERPRINT_PATTERN = '/^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$/';

    /**
     * @param array<string, mixed> $node
     */
    public static function isOrvex(array $node): bool
    {
        if (strtolower(trim((string) ($node['node_type'] ?? ''))) === self::TYPE) {
            return true;
        }

        // Nodes added by hand with the values printed by `orvex-node info`.
        return str_ends_with(strtolower(trim((string) ($node['user'] ?? ''))), '@orvex');
    }

    /**
     * An OrveX node that was created in the panel but has not connected yet.
     *
     * @param array<string, mixed> $node
     */
    public static function isPending(array $node): bool
    {
        return self::isOrvex($node) && empty($node['registered_at']);
    }

    /**
     * Connection placeholders for a new OrveX node. The node replaces them when it
     * registers, so the admin never types Proxmox-style credentials.
     *
     * @param array<string, mixed> $data
     *
     * @return array<string, mixed>
     */
    public static function newNodeDefaults(array $data): array
    {
        foreach (array_merge(self::MANAGED_FIELDS, ['addional_headers', 'additional_params', 'feathertail_enabled', 'feathertail_url', 'feathertail_tls_no_verify']) as $field) {
            unset($data[$field]);
        }

        $data['node_type'] = self::TYPE;
        $data['fqdn'] = self::PENDING_FQDN;
        $data['scheme'] = 'https';
        $data['port'] = 8006;
        $data['user'] = 'orvex@orvex';
        $data['token_id'] = 'panel';
        $data['secret'] = bin2hex(random_bytes(24));
        $data['tls_no_verify'] = 'true';

        return $data;
    }

    public static function generateToken(int $nodeId): string
    {
        $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        $max = strlen($chars) - 1;
        $random = '';
        for ($i = 0; $i < 48; ++$i) {
            $random .= $chars[random_int(0, $max)];
        }

        return 'orvx_' . $nodeId . '_' . $random;
    }

    /**
     * @return array{0: int, 1: string}|null [node id, token]
     */
    public static function parseToken(string $token): ?array
    {
        $token = trim($token);
        if (!preg_match(self::TOKEN_PATTERN, $token, $match)) {
            return null;
        }

        return [(int) $match[1], $token];
    }

    /**
     * Whether $token is the node's current, unexpired registration token.
     *
     * @param array<string, mixed> $node decrypted node row
     */
    public static function tokenMatches(array $node, string $token, ?int $now = null): bool
    {
        $stored = (string) ($node['registration_token'] ?? '');
        if ($stored === '' || $token === '' || !hash_equals($stored, $token)) {
            return false;
        }

        return !self::tokenExpired($node, $now);
    }

    /**
     * @param array<string, mixed> $node
     */
    public static function tokenExpired(array $node, ?int $now = null): bool
    {
        $expires = (string) ($node['registration_expires_at'] ?? '');
        if ($expires === '') {
            return true;
        }
        $timestamp = strtotime($expires);

        return $timestamp === false || $timestamp <= ($now ?? time());
    }

    /**
     * Issue a new one-time registration token (valid for TOKEN_TTL_SECONDS).
     *
     * @return array{token: string, expires_at: string}|null
     */
    public static function issueToken(int $nodeId): ?array
    {
        $token = self::generateToken($nodeId);
        $expires = date('Y-m-d H:i:s', time() + self::TOKEN_TTL_SECONDS);
        if (!VmNode::updateVmNodeById($nodeId, ['registration_token' => $token, 'registration_expires_at' => $expires])) {
            return null;
        }

        return ['token' => $token, 'expires_at' => $expires];
    }

    /**
     * Where the node install command downloads the installer from. Docker installs
     * made by install.sh pass ORVEX_REPO / ORVEX_BRANCH, so the command matches the
     * code the panel runs.
     *
     * @return array{repo: string, branch: string, default_branch: string, url: string}
     */
    public static function installerSource(): array
    {
        $repo = self::env('ORVEX_REPO');
        if (!preg_match('#^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$#', $repo)) {
            $repo = self::DEFAULT_REPO;
        }
        $branch = self::env('ORVEX_BRANCH');
        if (!preg_match('#^[A-Za-z0-9._/-]{1,200}$#', $branch) || str_contains($branch, '..')) {
            $branch = self::DEFAULT_BRANCH;
        }

        return [
            'repo' => $repo,
            'branch' => $branch,
            'default_branch' => self::DEFAULT_BRANCH,
            'url' => 'https://raw.githubusercontent.com/' . $repo . '/' . $branch . '/install.sh',
        ];
    }

    /**
     * Connection state and install details for the admin UI.
     *
     * @param array<string, mixed> $node decrypted node row
     *
     * @return array<string, mixed>
     */
    public static function installInfo(array $node, ?int $now = null): array
    {
        $registered = !self::isPending($node);
        $tokenValid = !self::tokenExpired($node, $now) && (string) ($node['registration_token'] ?? '') !== '';

        return [
            'node_type' => self::TYPE,
            'registered' => $registered,
            'registered_at' => $node['registered_at'] ?? null,
            'token' => $tokenValid ? (string) $node['registration_token'] : null,
            'expires_at' => $tokenValid ? ($node['registration_expires_at'] ?? null) : null,
            // Seconds left, so the UI does not depend on the server's timezone.
            'expires_in' => $tokenValid ? max(0, (int) strtotime((string) $node['registration_expires_at']) - ($now ?? time())) : null,
            'installer' => self::installerSource(),
            'agent_version' => $node['agent_version'] ?? null,
            'agent' => self::decodeAgentInfo($node['agent_info'] ?? null),
            'endpoint' => $registered ? (($node['scheme'] ?? 'https') . '://' . ($node['fqdn'] ?? '') . ':' . (int) ($node['port'] ?? 8006)) : null,
        ];
    }

    /**
     * @return array<string, mixed>|null
     */
    public static function decodeAgentInfo(mixed $raw): ?array
    {
        if (is_array($raw)) {
            return $raw;
        }
        if (!is_string($raw) || $raw === '') {
            return null;
        }
        $decoded = json_decode($raw, true);

        return is_array($decoded) ? $decoded : null;
    }

    /**
     * Host names and addresses the panel may connect to. Private networks are fine
     * (panel and node on one LAN); loopback, link-local, multicast and other
     * reserved addresses are not, so a token cannot point the panel at itself.
     */
    public static function isAllowedAddress(string $address): bool
    {
        $address = strtolower(trim($address));
        if ($address === '' || strlen($address) > 253) {
            return false;
        }

        if (filter_var($address, FILTER_VALIDATE_IP) !== false) {
            if (filter_var($address, FILTER_VALIDATE_IP, FILTER_FLAG_NO_RES_RANGE) === false) {
                return false;
            }
            if (filter_var($address, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) !== false) {
                $first = (int) explode('.', $address)[0];

                // 224.0.0.0/4 multicast, 240.0.0.0/4 reserved, 0.0.0.0/8 and 127.0.0.0/8.
                return $first !== 0 && $first !== 127 && $first < 224;
            }
            $packed = inet_pton($address);
            if ($packed === false) {
                return false;
            }
            $firstByte = ord($packed[0]);
            $secondByte = ord($packed[1]);

            // ff00::/8 multicast, fe80::/10 link-local, :: and ::1.
            return $firstByte !== 0xFF
                && !($firstByte === 0xFE && ($secondByte & 0xC0) === 0x80)
                && $packed !== inet_pton('::')
                && $packed !== inet_pton('::1');
        }

        if ($address === 'localhost' || str_ends_with($address, '.localhost') || str_ends_with($address, '.invalid')) {
            return false;
        }

        return (bool) preg_match('/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/', $address);
    }

    /**
     * Validate the JSON an OrveX node sends when it registers. Connection fields are
     * strict (errors reject the registration); the descriptive node report is
     * lenient: invalid parts are skipped and returned as warnings.
     *
     * @param array<string, mixed> $payload
     *
     * @return array{0: array<string, mixed>, 1: array<int, string>, 2: array<int, string>} [clean data, errors, warnings]
     */
    public static function validateRegistration(array $payload): array
    {
        $errors = [];
        $clean = [];

        $address = is_string($payload['address'] ?? null) ? strtolower(trim($payload['address'])) : '';
        if (!self::isAllowedAddress($address)) {
            $errors[] = 'address must be a public or private IP address or a host name the panel can reach';
        }
        $clean['address'] = $address;

        $port = $payload['port'] ?? 8006;
        if (!is_numeric($port) || (int) $port < 1 || (int) $port > 65535 || (string) (int) $port !== trim((string) $port)) {
            $errors[] = 'port must be between 1 and 65535';
        }
        $clean['port'] = (int) $port;

        $user = is_string($payload['api_user'] ?? null) ? trim($payload['api_user']) : 'orvex@orvex';
        if (!preg_match('/^[A-Za-z0-9._-]{1,64}@orvex$/', $user)) {
            $errors[] = 'api_user must look like name@orvex';
        }
        $clean['api_user'] = $user;

        $tokenId = is_string($payload['api_token_id'] ?? null) ? trim($payload['api_token_id']) : 'panel';
        if (!preg_match(self::NAME_PATTERN, $tokenId)) {
            $errors[] = 'api_token_id is invalid';
        }
        $clean['api_token_id'] = $tokenId;

        $secret = is_string($payload['api_token_secret'] ?? null) ? $payload['api_token_secret'] : '';
        if (!preg_match('/^[\x21-\x7E]{16,255}$/', $secret)) {
            $errors[] = 'api_token_secret must be 16 to 255 printable characters';
        }
        $clean['api_token_secret'] = $secret;

        [$report, $warnings] = self::validateNodeReport($payload);

        return [array_merge($report, $clean), $errors, $warnings];
    }

    /**
     * Validate what a node reports about itself (registration and "Sync from node").
     *
     * @param array<string, mixed> $payload
     *
     * @return array{0: array<string, mixed>, 1: array<int, string>} [clean data, warnings]
     */
    public static function validateNodeReport(array $payload): array
    {
        $warnings = [];
        $clean = [];

        $clean['node_name'] = self::optionalMatch($payload['node_name'] ?? null, '/^[a-z0-9][a-z0-9._-]{0,62}$/', 'node_name', $warnings);
        $clean['agent_version'] = self::optionalMatch($payload['agent_version'] ?? null, '/^[0-9A-Za-z.+_-]{1,32}$/', 'agent_version', $warnings);
        $fingerprint = is_string($payload['tls_fingerprint'] ?? null) ? strtoupper(trim($payload['tls_fingerprint'])) : null;
        $clean['tls_fingerprint'] = self::optionalMatch($fingerprint, self::FINGERPRINT_PATTERN, 'tls_fingerprint', $warnings);

        $publicIp = $payload['public_ipv4'] ?? null;
        $clean['public_ipv4'] = null;
        if (is_string($publicIp) && $publicIp !== '') {
            if (filter_var($publicIp, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false) {
                $warnings[] = 'public_ipv4 is not an IPv4 address';
            } else {
                $clean['public_ipv4'] = $publicIp;
            }
        }

        $clean['kvm'] = filter_var($payload['kvm'] ?? false, FILTER_VALIDATE_BOOLEAN);
        $clean['storage_pool'] = self::optionalMatch($payload['storage_pool'] ?? null, self::NAME_PATTERN, 'storage_pool', $warnings) ?? 'default';
        $clean['backup_storage'] = self::optionalMatch($payload['backup_storage'] ?? null, self::NAME_PATTERN, 'backup_storage', $warnings) ?? 'backups';

        $clean['nat'] = null;
        $nat = $payload['nat'] ?? null;
        if ($nat !== null) {
            if (!is_array($nat) || !self::validNat((string) ($nat['subnet'] ?? ''), (string) ($nat['gateway'] ?? ''))) {
                $warnings[] = 'nat was ignored: it needs an IPv4 subnet (/16 to /30) and a gateway inside it';
            } else {
                $clean['nat'] = [
                    'subnet' => self::normaliseSubnet((string) $nat['subnet']),
                    'gateway' => (string) $nat['gateway'],
                    'ssh_port_base' => self::boundedInt($nat['ssh_port_base'] ?? 22000, 1, 65535, 22000),
                    'port_range_base' => self::boundedInt($nat['port_range_base'] ?? 30000, 1, 65535, 30000),
                    'port_range_size' => self::boundedInt($nat['port_range_size'] ?? 20, 0, 1000, 20),
                ];
            }
        }

        $clean['templates'] = [];
        $templates = $payload['templates'] ?? [];
        if (!is_array($templates)) {
            $warnings[] = 'templates was ignored: it must be a list';
            $templates = [];
        }
        if (count($templates) > self::MAX_TEMPLATES) {
            $warnings[] = 'only the first ' . self::MAX_TEMPLATES . ' templates were used';
            $templates = array_slice($templates, 0, self::MAX_TEMPLATES);
        }
        $seen = [];
        foreach (array_values($templates) as $index => $template) {
            $vmid = is_array($template) ? ($template['vmid'] ?? null) : null;
            $name = is_array($template) && is_string($template['name'] ?? null) ? trim($template['name']) : '';
            $type = is_array($template) ? strtolower(trim((string) ($template['type'] ?? 'qemu'))) : '';
            if (!is_int($vmid) && !(is_string($vmid) && ctype_digit($vmid))) {
                $warnings[] = "templates[{$index}] skipped: vmid must be a number";
                continue;
            }
            $vmid = (int) $vmid;
            if ($vmid < 100 || $vmid > 999999999 || isset($seen[$vmid])) {
                $warnings[] = "templates[{$index}] skipped: vmid {$vmid} is out of range or duplicated";
                continue;
            }
            if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/', $name) || !in_array($type, ['qemu', 'lxc'], true)) {
                $warnings[] = "templates[{$index}] skipped: it needs a name and a type of qemu or lxc";
                continue;
            }
            $description = is_array($template) && is_string($template['description'] ?? null) ? self::plainText($template['description'], 120) : '';
            $seen[$vmid] = true;
            $clean['templates'][] = [
                'vmid' => $vmid,
                'name' => $name,
                'type' => $type,
                'description' => $description !== '' ? $description : $name,
            ];
        }

        $host = is_array($payload['host'] ?? null) ? $payload['host'] : [];
        $clean['host'] = array_filter([
            'hostname' => is_string($host['hostname'] ?? null) ? self::plainText($host['hostname'], 253) : null,
            'os' => is_string($host['os'] ?? null) ? self::plainText($host['os'], 128) : null,
            'kernel' => is_string($host['kernel'] ?? null) ? self::plainText($host['kernel'], 128) : null,
            'cpu' => is_string($host['cpu'] ?? null) ? self::plainText($host['cpu'], 128) : null,
            'cpus' => isset($host['cpus']) && is_numeric($host['cpus']) ? max(0, min(100000, (int) $host['cpus'])) : null,
            'memory_mb' => isset($host['memory_mb']) && is_numeric($host['memory_mb']) ? max(0, min(1 << 30, (int) $host['memory_mb'])) : null,
        ], static fn ($value): bool => $value !== null && $value !== '');

        return [$clean, $warnings];
    }

    /**
     * Addresses of the shared-IPv4 subnet the panel puts in the IP pool: every host
     * address except the gateway, capped at $limit.
     *
     * @return array<int, string>
     */
    public static function poolAddresses(string $subnet, string $gateway, int $limit = self::MAX_POOL_ADDRESSES): array
    {
        if (!self::validNat($subnet, $gateway)) {
            return [];
        }
        [$network, $prefix] = explode('/', self::normaliseSubnet($subnet));
        $base = ip2long($network);
        $size = 1 << (32 - (int) $prefix);
        $gatewayLong = ip2long($gateway);
        $out = [];
        for ($offset = 1; $offset < $size - 1 && count($out) < $limit; ++$offset) {
            $address = $base + $offset;
            if ($address === $gatewayLong) {
                continue;
            }
            $out[] = long2ip($address);
        }

        return $out;
    }

    /**
     * Agent details kept on the node (agent_info) and shown in the admin UI.
     *
     * @param array<string, mixed> $reg validated registration
     *
     * @return array<string, mixed>
     */
    public static function agentInfo(array $reg, ?string $sourceIp = null): array
    {
        return array_filter([
            'node_name' => $reg['node_name'] ?? null,
            'address' => $reg['address'] ?? null,
            'port' => $reg['port'] ?? null,
            'public_ipv4' => $reg['public_ipv4'] ?? null,
            'tls_fingerprint' => $reg['tls_fingerprint'] ?? null,
            'kvm' => (bool) ($reg['kvm'] ?? false),
            'nat' => $reg['nat'] ?? null,
            'storage_pool' => $reg['storage_pool'] ?? null,
            'backup_storage' => $reg['backup_storage'] ?? null,
            'templates' => count($reg['templates'] ?? []),
            'host' => ($reg['host'] ?? []) ?: null,
            'registered_from' => $sourceIp,
            'synced_at' => date('Y-m-d H:i:s'),
        ], static fn ($value): bool => $value !== null);
    }

    /**
     * Save a validated registration: connection details, agent info, templates and
     * the shared-IPv4 pool. The token is single-use and is cleared here.
     *
     * @param array<string, mixed> $node decrypted node row
     * @param array<string, mixed> $reg validated registration
     *
     * @return array{templates_imported: int, templates_total: int, ips_added: int}|null
     */
    public static function applyRegistration(array $node, array $reg, ?string $sourceIp = null): ?array
    {
        $nodeId = (int) $node['id'];
        $update = [
            'node_type' => self::TYPE,
            'fqdn' => $reg['address'],
            'scheme' => 'https',
            'port' => $reg['port'],
            'user' => $reg['api_user'],
            'token_id' => $reg['api_token_id'],
            'secret' => $reg['api_token_secret'],
            // The node uses a self-signed certificate; its fingerprint is kept in agent_info.
            'tls_no_verify' => 'true',
            'registered_at' => date('Y-m-d H:i:s'),
            'registration_token' => null,
            'registration_expires_at' => null,
            'agent_version' => $reg['agent_version'],
            'agent_info' => json_encode(self::agentInfo($reg, $sourceIp), JSON_UNESCAPED_SLASHES),
        ];
        if (trim((string) ($node['storage_backups'] ?? '')) === '') {
            $update['storage_backups'] = $reg['backup_storage'];
        }
        if (!VmNode::updateVmNodeById($nodeId, $update)) {
            return null;
        }

        $imported = self::importTemplates($nodeId, $reg['templates'], (string) $reg['storage_pool'], (bool) $reg['kvm']);
        $ips = is_array($reg['nat'] ?? null) ? self::addNatPool($nodeId, $reg['nat']) : 0;

        return [
            'templates_imported' => $imported,
            'templates_total' => count($reg['templates']),
            'ips_added' => $ips,
        ];
    }

    /**
     * Refresh the agent details of a connected node and add the templates it offers
     * that the panel does not know yet ("Sync from node" in the admin UI).
     *
     * @param array<string, mixed> $node decrypted node row
     *
     * @return array{ok: bool, error: string|null, templates_imported: int, templates_total: int, warnings: array<int, string>}
     */
    public static function syncFromNode(array $node): array
    {
        $fail = static fn (string $error): array => [
            'ok' => false, 'error' => mb_substr($error, 0, 300), 'templates_imported' => 0, 'templates_total' => 0, 'warnings' => [],
        ];
        try {
            $client = VmInstanceUtil::buildProxmoxClientForNode($node);
            $nodes = $client->getNodes();
            $pveNode = (string) ($nodes['nodes'][0]['node'] ?? '');
            if (!($nodes['ok'] ?? false) || $pveNode === '') {
                return $fail((string) ($nodes['error'] ?? 'the node did not answer'));
            }
            $result = $client->apiGet('/api2/json/nodes/' . rawurlencode($pveNode) . '/orvex/info');
        } catch (\Throwable $e) {
            return $fail($e->getMessage());
        }
        if (!($result['ok'] ?? false) || !is_array($result['data'] ?? null)) {
            return $fail((string) ($result['error'] ?? 'the node did not return its details'));
        }

        $info = $result['data'];
        $info['node_name'] ??= $info['node'] ?? null;
        $info['agent_version'] ??= $info['version'] ?? null;
        [$report, $warnings] = self::validateNodeReport($info);

        $previous = self::decodeAgentInfo($node['agent_info'] ?? null) ?? [];
        $agent = self::agentInfo(array_merge($report, [
            'address' => (string) ($node['fqdn'] ?? ''),
            'port' => (int) ($node['port'] ?? 8006),
            'tls_fingerprint' => $report['tls_fingerprint'] ?? ($previous['tls_fingerprint'] ?? null),
        ]), isset($previous['registered_from']) ? (string) $previous['registered_from'] : null);
        VmNode::updateVmNodeById((int) $node['id'], [
            'agent_version' => $report['agent_version'] ?? ($node['agent_version'] ?? null),
            'agent_info' => json_encode($agent, JSON_UNESCAPED_SLASHES),
        ]);
        $imported = self::importTemplates((int) $node['id'], $report['templates'], (string) $report['storage_pool'], (bool) $report['kvm']);

        return [
            'ok' => true,
            'error' => null,
            'templates_imported' => $imported,
            'templates_total' => count($report['templates']),
            'warnings' => $warnings,
        ];
    }

    /**
     * Add the node's templates that the panel does not know yet. KVM templates are
     * added inactive when the server has no hardware virtualization.
     *
     * @param array<int, array<string, mixed>> $templates validated templates
     */
    public static function importTemplates(int $nodeId, array $templates, string $storage, bool $kvm): int
    {
        $known = [];
        foreach (VmTemplate::getByNodeId($nodeId) as $existing) {
            $known[(string) ($existing['template_file'] ?? '')] = true;
        }

        $created = 0;
        foreach ($templates as $template) {
            $vmid = (string) (int) $template['vmid'];
            if (isset($known[$vmid])) {
                continue;
            }
            try {
                VmTemplate::create([
                    'name' => (string) ($template['description'] ?: $template['name']),
                    'description' => (string) $template['name'],
                    'guest_type' => $template['type'] === 'lxc' ? 'lxc' : 'qemu',
                    'os_type' => null,
                    'storage' => $storage !== '' ? $storage : 'default',
                    'template_file' => $vmid,
                    'vm_node_id' => $nodeId,
                    'is_active' => ($template['type'] === 'qemu' && !$kvm) ? 'false' : 'true',
                ]);
                $known[$vmid] = true;
                ++$created;
            } catch (\Throwable $e) {
                App::getInstance(true)->getLogger()->warning('OrveX node ' . $nodeId . ': could not add template ' . $vmid . ': ' . $e->getMessage());
            }
        }

        return $created;
    }

    /**
     * Put the node's shared-IPv4 subnet into its IP pool, unless the pool already
     * has addresses from that subnet (the admin manages them from then on).
     *
     * @param array<string, mixed> $nat validated nat block
     */
    public static function addNatPool(int $nodeId, array $nat): int
    {
        $subnet = (string) ($nat['subnet'] ?? '');
        $gateway = (string) ($nat['gateway'] ?? '');
        if (!self::validNat($subnet, $gateway)) {
            return 0;
        }

        $pdo = Database::getPdoConnection();
        $stmt = $pdo->prepare('SELECT ip FROM featherpanel_vm_ips WHERE vm_node_id = :id');
        $stmt->execute(['id' => $nodeId]);
        foreach ($stmt->fetchAll(\PDO::FETCH_COLUMN) as $ip) {
            if (self::ipInSubnet((string) $ip, $subnet)) {
                return 0;
            }
        }

        $prefix = (int) explode('/', self::normaliseSubnet($subnet))[1];
        $added = 0;
        $pdo->beginTransaction();
        try {
            foreach (self::poolAddresses($subnet, $gateway) as $address) {
                $created = VmIp::create([
                    'vm_node_id' => $nodeId,
                    'ip' => $address,
                    'cidr' => $prefix,
                    'gateway' => $gateway,
                    'address_scope' => 'private',
                    'assignment_mode' => 'static',
                    'notes' => self::POOL_NOTE,
                ]);
                if ($created) {
                    ++$added;
                }
            }
            $pdo->commit();
        } catch (\Throwable $e) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            App::getInstance(true)->getLogger()->error('OrveX node ' . $nodeId . ': could not add the shared IPv4 pool: ' . $e->getMessage());

            return 0;
        }

        return $added;
    }

    /**
     * Quick check that the panel reaches the node API with the stored token.
     *
     * @param array<string, mixed> $node decrypted node row
     *
     * @return array{ok: bool, error: string|null, duration_ms: int|null}
     */
    public static function checkReachable(array $node, int $timeout = 10): array
    {
        $probe = $node;
        $probe['timeout'] = $timeout;
        try {
            $result = VmInstanceUtil::buildProxmoxClientForNode($probe)->testConnection();
            $ok = (bool) ($result['ok'] ?? false);

            return [
                'ok' => $ok,
                'error' => $ok ? null : mb_substr((string) ($result['error'] ?? 'unknown error'), 0, 300),
                'duration_ms' => isset($result['duration_ms']) ? (int) $result['duration_ms'] : null,
            ];
        } catch (\Throwable $e) {
            return ['ok' => false, 'error' => mb_substr($e->getMessage(), 0, 300), 'duration_ms' => null];
        }
    }

    /**
     * Remove the templates and IP pool of an OrveX node that has no servers left, so
     * the node itself can be deleted.
     */
    public static function deleteNodeResources(int $nodeId): void
    {
        $pdo = Database::getPdoConnection();
        $pdo->prepare('DELETE FROM featherpanel_vm_ips WHERE vm_node_id = :id')->execute(['id' => $nodeId]);
        $pdo->prepare('DELETE FROM featherpanel_vm_templates WHERE vm_node_id = :id')->execute(['id' => $nodeId]);
    }

    public static function validNat(string $subnet, string $gateway): bool
    {
        if (!preg_match('#^(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})$#', trim($subnet), $match)) {
            return false;
        }
        $prefix = (int) $match[2];
        if (filter_var($match[1], FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false || $prefix < 16 || $prefix > 30) {
            return false;
        }
        if (filter_var($gateway, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false || !self::ipInSubnet($gateway, $subnet)) {
            return false;
        }
        [$network] = explode('/', self::normaliseSubnet($subnet));
        $broadcast = ip2long($network) + (1 << (32 - $prefix)) - 1;

        return $gateway !== $network && ip2long($gateway) !== $broadcast;
    }

    public static function ipInSubnet(string $ip, string $subnet): bool
    {
        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false || !str_contains($subnet, '/')) {
            return false;
        }
        [$network, $prefix] = explode('/', $subnet, 2);
        if (filter_var($network, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false || !ctype_digit($prefix) || (int) $prefix > 32) {
            return false;
        }
        $mask = (int) $prefix === 0 ? 0 : (~0 << (32 - (int) $prefix)) & 0xFFFFFFFF;

        return (ip2long($ip) & $mask) === (ip2long($network) & $mask);
    }

    /**
     * Same lookup order as App::env() ($_ENV, $_SERVER, then the process environment).
     */
    private static function env(string $key): string
    {
        $value = $_ENV[$key] ?? $_SERVER[$key] ?? getenv($key);

        return is_string($value) ? trim($value, " \t\"'") : '';
    }

    private static function normaliseSubnet(string $subnet): string
    {
        [$network, $prefix] = explode('/', trim($subnet), 2);
        $mask = (~0 << (32 - (int) $prefix)) & 0xFFFFFFFF;

        return long2ip(ip2long($network) & $mask) . '/' . (int) $prefix;
    }

    /**
     * @param array<int, string> $errors
     */
    private static function optionalMatch(mixed $value, string $pattern, string $field, array &$errors): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }
        if (!is_string($value) || !preg_match($pattern, trim($value))) {
            $errors[] = $field . ' is invalid';

            return null;
        }

        return trim($value);
    }

    private static function boundedInt(mixed $value, int $min, int $max, int $default): int
    {
        if (!is_numeric($value)) {
            return $default;
        }

        return max($min, min($max, (int) $value));
    }

    private static function plainText(string $value, int $max): string
    {
        $value = preg_replace('/[\x00-\x1F\x7F]+/', ' ', $value) ?? '';

        return mb_substr(trim(strip_tags($value)), 0, $max);
    }
}
