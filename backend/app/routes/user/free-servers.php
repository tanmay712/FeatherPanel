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

use App\App;
use RateLimit\Rate;
use App\Helpers\ApiResponse;
use Symfony\Component\HttpFoundation\Request;
use App\Controllers\User\FreeServersController;
use Symfony\Component\Routing\RouteCollection;

return function (RouteCollection $routes): void {
    $app = App::getInstance(true);
    $withUuid = static fn (callable $fn) => static function (Request $request, array $args) use ($fn) {
        $uuidShort = $args['uuidShort'] ?? null;
        if (!is_string($uuidShort) || !preg_match('/^[a-f0-9]{8}$/i', $uuidShort)) {
            return ApiResponse::error('Missing or invalid UUID short', 'INVALID_UUID_SHORT', 400);
        }

        return $fn($request, $uuidShort);
    };

    $app->registerAuthRoute(
        $routes,
        'user-free-servers-options',
        '/api/user/free-servers/options',
        fn (Request $request) => (new FreeServersController())->options($request),
        ['GET'],
        Rate::perMinute(30), // Default: Admin can override in ratelimit.json
        'user-free-servers'
    );

    $app->registerAuthRoute(
        $routes,
        'user-free-servers-list',
        '/api/user/free-servers',
        fn (Request $request) => (new FreeServersController())->index($request),
        ['GET'],
        Rate::perMinute(30), // Default: Admin can override in ratelimit.json
        'user-free-servers'
    );

    $app->registerAuthRoute(
        $routes,
        'user-free-servers-create',
        '/api/user/free-servers',
        fn (Request $request) => (new FreeServersController())->create($request),
        ['POST'],
        Rate::perMinute(3), // Default: Admin can override in ratelimit.json
        'user-free-servers-create'
    );

    $app->registerAuthRoute(
        $routes,
        'user-free-servers-show',
        '/api/user/free-servers/{uuidShort}',
        $withUuid(fn (Request $request, string $uuidShort) => (new FreeServersController())->show($request, $uuidShort)),
        ['GET'],
        Rate::perMinute(60), // Default: Admin can override in ratelimit.json
        'user-free-servers'
    );

    $app->registerAuthRoute(
        $routes,
        'user-free-servers-stack',
        '/api/user/free-servers/{uuidShort}/stack',
        $withUuid(fn (Request $request, string $uuidShort) => (new FreeServersController())->changeStack($request, $uuidShort)),
        ['POST'],
        Rate::perMinute(3), // Default: Admin can override in ratelimit.json
        'user-free-servers-stack'
    );

    $app->registerAuthRoute(
        $routes,
        'user-free-servers-restore',
        '/api/user/free-servers/{uuidShort}/restore',
        $withUuid(fn (Request $request, string $uuidShort) => (new FreeServersController())->restore($request, $uuidShort)),
        ['POST'],
        Rate::perMinute(5), // Default: Admin can override in ratelimit.json
        'user-free-servers-restore'
    );
};
