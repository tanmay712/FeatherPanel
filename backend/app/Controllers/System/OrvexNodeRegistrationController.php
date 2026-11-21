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

namespace App\Controllers\System;

use App\App;
use App\Chat\VmNode;
use App\Chat\Activity;
use App\Helpers\ApiResponse;
use App\Services\Vm\OrvexNodes;
use App\CloudFlare\CloudFlareRealIP;
use App\Plugins\Events\Events\VdsNodeEvent;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * POST /api/remote/orvex/register: an OrveX VPS Node connects itself to the panel.
 *
 * Called by `orvex-node register` (run by `install.sh vps-node --panel URL --token T`).
 * The bearer token is the one-time token of the install command shown in
 * Admin > VDS Nodes; the body describes how the panel reaches the node and what the
 * node offers. Public route, rate limited per IP.
 */
class OrvexNodeRegistrationController
{
    public function register(Request $request): Response
    {
        $ip = CloudFlareRealIP::getRealIP();
        $raw = (string) $request->getContent();
        if (strlen($raw) > OrvexNodes::MAX_PAYLOAD_BYTES) {
            return ApiResponse::error('Registration data is too large', 'PAYLOAD_TOO_LARGE', 413);
        }
        $payload = json_decode($raw, true);
        if (!is_array($payload)) {
            return ApiResponse::error('Invalid JSON in request body', 'INVALID_JSON', 400);
        }

        $token = self::bearerToken($request);
        if ($token === '' && is_string($payload['token'] ?? null)) {
            $token = trim($payload['token']);
        }
        $parsed = OrvexNodes::parseToken($token);
        $node = $parsed !== null ? VmNode::getVmNodeById($parsed[0]) : null;
        if ($node === null || !OrvexNodes::isOrvex($node) || !OrvexNodes::tokenMatches($node, $token)) {
            App::getInstance(true)->getLogger()->warning('OrveX node registration refused from ' . $ip . ' (node ' . ($parsed[0] ?? '?') . '): invalid or expired token');

            return ApiResponse::error(
                'This install command is invalid, expired or already used. Create a new one in the panel: Admin > Nodes (VPS) > your node > Connect.',
                'INVALID_REGISTRATION_TOKEN',
                401
            );
        }

        [$registration, $errors, $warnings] = OrvexNodes::validateRegistration($payload);
        if ($errors !== []) {
            return ApiResponse::error('Invalid registration data: ' . implode('; ', $errors), 'INVALID_REGISTRATION', 422, ['errors' => $errors]);
        }

        $summary = OrvexNodes::applyRegistration($node, $registration, $ip);
        if ($summary === null) {
            return ApiResponse::error('The panel could not save the node registration', 'REGISTRATION_FAILED', 500);
        }

        $node = VmNode::getVmNodeById((int) $node['id']) ?? $node;
        $reach = OrvexNodes::checkReachable($node);

        Activity::createActivity([
            'user_uuid' => null,
            'name' => 'orvex_node_registered',
            'context' => 'OrveX node ' . ($node['name'] ?? $node['id']) . ' connected from ' . $ip . ' (' . $registration['address'] . ':' . $registration['port'] . ')',
            'ip_address' => $ip,
        ]);

        global $eventManager;
        if (isset($eventManager) && $eventManager !== null) {
            try {
                $eventManager->emit(VdsNodeEvent::onVdsNodeUpdated(), [
                    'user_uuid' => null,
                    'vm_node_id' => (int) $node['id'],
                    'vm_node' => VmNode::sanitizeForAdminResponse($node),
                    'changed_fields' => ['registered_at', 'fqdn', 'port', 'agent_info'],
                    'context' => ['source' => 'orvex-node-register'],
                ]);
            } catch (\Throwable $e) {
                App::getInstance(true)->getLogger()->warning('VDS node event failed after OrveX registration: ' . $e->getMessage());
            }
        }

        return ApiResponse::success([
            'node' => ['id' => (int) $node['id'], 'name' => (string) ($node['name'] ?? '')],
            'templates_imported' => $summary['templates_imported'],
            'templates_total' => $summary['templates_total'],
            'ips_added' => $summary['ips_added'],
            'reachable' => $reach['ok'],
            'reach_error' => $reach['error'],
            'warnings' => $warnings,
        ], 'Node connected', 200);
    }

    private static function bearerToken(Request $request): string
    {
        $header = trim((string) $request->headers->get('Authorization', ''));
        if (stripos($header, 'Bearer ') === 0) {
            return trim(substr($header, 7));
        }

        return '';
    }
}
