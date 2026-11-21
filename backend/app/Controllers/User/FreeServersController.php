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

namespace App\Controllers\User;

use App\Helpers\ApiResponse;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use App\Services\FreeServers\FreeServerService;

/**
 * Free servers for the signed-in user: what can be created, creating one, the user's list and
 * restoring a server from storage.
 */
class FreeServersController
{
    #[OA\Get(
        path: '/api/user/free-servers/options',
        summary: 'Free server options',
        description: 'Stacks, resources, the per-user limit and the inactivity rule shown on the create page.',
        tags: ['User - Free servers'],
        responses: [
            new OA\Response(response: 200, description: 'Options loaded'),
            new OA\Response(response: 401, description: 'Unauthorized'),
        ]
    )]
    public function options(Request $request): Response
    {
        $user = $request->attributes->get('user');
        if (!is_array($user)) {
            return ApiResponse::error('User not authenticated', 'UNAUTHORIZED', 401);
        }

        return ApiResponse::success((new FreeServerService())->optionsFor($user), 'Free server options loaded');
    }

    #[OA\Get(
        path: '/api/user/free-servers',
        summary: 'List my free servers',
        description: 'The free servers owned by the current user, with where each one is in the inactivity flow.',
        tags: ['User - Free servers'],
        responses: [
            new OA\Response(response: 200, description: 'Free servers loaded'),
            new OA\Response(response: 401, description: 'Unauthorized'),
        ]
    )]
    public function index(Request $request): Response
    {
        $user = $request->attributes->get('user');
        if (!is_array($user)) {
            return ApiResponse::error('User not authenticated', 'UNAUTHORIZED', 401);
        }

        return ApiResponse::success(['servers' => (new FreeServerService())->listFor($user)], 'Free servers loaded');
    }

    #[OA\Post(
        path: '/api/user/free-servers',
        summary: 'Create a free server',
        description: 'Creates a free server with the picked stack. It is placed on a node automatically.',
        tags: ['User - Free servers'],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                required: ['stack', 'name'],
                properties: [
                    new OA\Property(property: 'stack', type: 'string', description: 'nodejs, python, bun, java, csharp, rust, lua, mongodb, mariadb, postgresql or redis'),
                    new OA\Property(property: 'name', type: 'string', maxLength: 60),
                    new OA\Property(property: 'description', type: 'string', maxLength: 500, nullable: true),
                ]
            )
        ),
        responses: [
            new OA\Response(response: 201, description: 'Server created'),
            new OA\Response(response: 403, description: 'Free servers are turned off'),
            new OA\Response(response: 409, description: 'Free server limit reached'),
            new OA\Response(response: 422, description: 'Invalid stack or name'),
            new OA\Response(response: 503, description: 'No room on the free nodes right now'),
        ]
    )]
    public function create(Request $request): Response
    {
        $user = $request->attributes->get('user');
        if (!is_array($user)) {
            return ApiResponse::error('User not authenticated', 'UNAUTHORIZED', 401);
        }
        $data = json_decode($request->getContent(), true);
        if (!is_array($data)) {
            return ApiResponse::error('Invalid request body', 'INVALID_REQUEST_BODY', 400);
        }
        $result = (new FreeServerService())->create($user, $data);
        if (!$result['ok']) {
            return ApiResponse::error($result['message'], $result['code'], $result['status']);
        }
        unset($result['ok']);

        return ApiResponse::success(['server' => $result], 'Free server created', 201);
    }

    #[OA\Get(
        path: '/api/user/free-servers/{uuidShort}',
        summary: 'Free server details',
        description: 'Stack and inactivity state of one of your free servers. 404 when the server is not a free server you own.',
        tags: ['User - Free servers'],
        parameters: [new OA\Parameter(name: 'uuidShort', in: 'path', required: true, schema: new OA\Schema(type: 'string'))],
        responses: [
            new OA\Response(response: 200, description: 'Free server loaded'),
            new OA\Response(response: 404, description: 'Not a free server you own'),
        ]
    )]
    public function show(Request $request, string $uuidShort): Response
    {
        $user = $request->attributes->get('user');
        if (!is_array($user)) {
            return ApiResponse::error('User not authenticated', 'UNAUTHORIZED', 401);
        }
        $server = (new FreeServerService())->showFor($user, $uuidShort);
        if ($server === null) {
            return ApiResponse::error('Free server not found', 'FREE_SERVER_NOT_FOUND', 404);
        }

        return ApiResponse::success(['server' => $server], 'Free server loaded');
    }

    #[OA\Post(
        path: '/api/user/free-servers/{uuidShort}/stack',
        summary: 'Change the stack of a free server',
        description: 'Switches the server to another free stack and reinstalls it. Files are kept unless the new install replaces them.',
        tags: ['User - Free servers'],
        parameters: [new OA\Parameter(name: 'uuidShort', in: 'path', required: true, schema: new OA\Schema(type: 'string'))],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(required: ['stack'], properties: [new OA\Property(property: 'stack', type: 'string')])
        ),
        responses: [
            new OA\Response(response: 200, description: 'Stack changed, reinstall started'),
            new OA\Response(response: 404, description: 'Free server not found'),
            new OA\Response(response: 409, description: 'Same stack, or the server is in storage'),
            new OA\Response(response: 422, description: 'Stack not available'),
        ]
    )]
    public function changeStack(Request $request, string $uuidShort): Response
    {
        $user = $request->attributes->get('user');
        if (!is_array($user)) {
            return ApiResponse::error('User not authenticated', 'UNAUTHORIZED', 401);
        }
        $data = json_decode($request->getContent(), true);
        if (!is_array($data)) {
            return ApiResponse::error('Invalid request body', 'INVALID_REQUEST_BODY', 400);
        }
        $result = (new FreeServerService())->changeStack($user, $uuidShort, $data['stack'] ?? null);
        if (!$result['ok']) {
            return ApiResponse::error($result['message'], $result['code'], $result['status']);
        }
        unset($result['ok']);

        return ApiResponse::success($result, 'Free server stack changed');
    }

    #[OA\Post(
        path: '/api/user/free-servers/{uuidShort}/restore',
        summary: 'Restore a free server from storage',
        description: 'Lifts the storage suspension of one of your free servers and starts it.',
        tags: ['User - Free servers'],
        parameters: [new OA\Parameter(name: 'uuidShort', in: 'path', required: true, schema: new OA\Schema(type: 'string'))],
        responses: [
            new OA\Response(response: 200, description: 'Server restored'),
            new OA\Response(response: 403, description: 'Suspended by staff'),
            new OA\Response(response: 404, description: 'Free server not found'),
            new OA\Response(response: 409, description: 'Not in storage'),
        ]
    )]
    public function restore(Request $request, string $uuidShort): Response
    {
        $user = $request->attributes->get('user');
        if (!is_array($user)) {
            return ApiResponse::error('User not authenticated', 'UNAUTHORIZED', 401);
        }
        $result = (new FreeServerService())->restore($user, $uuidShort);
        if (!$result['ok']) {
            return ApiResponse::error($result['message'], $result['code'], $result['status']);
        }
        unset($result['ok']);

        return ApiResponse::success($result, 'Free server restored');
    }
}
