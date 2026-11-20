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
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\RouteCollection;
use App\Controllers\System\OrvexNodeRegistrationController;

return function (RouteCollection $routes): void {
    // Public: an OrveX VPS Node connects itself (`orvex-node register`). It is
    // authenticated by the one-time token of the install command; rate limited per IP.
    App::getInstance(true)->registerApiRoute(
        $routes,
        'orvex-node-register',
        '/api/remote/orvex/register',
        function (Request $request) {
            return (new OrvexNodeRegistrationController())->register($request);
        },
        ['POST'],
        Rate::perMinute(10),
        'orvex-node-register'
    );
};
