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
use App\Permissions;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\RouteCollection;
use App\Controllers\Admin\FreeServersController;

return function (RouteCollection $routes): void {
    $app = App::getInstance(true);

    $app->registerAdminRoute($routes, 'admin-free-servers-settings', '/api/admin/free-servers/settings', fn (Request $r) => (new FreeServersController())->settings($r), Permissions::ADMIN_SERVERS_VIEW, ['GET']);
    $app->registerAdminRoute($routes, 'admin-free-servers-settings-update', '/api/admin/free-servers/settings', fn (Request $r) => (new FreeServersController())->updateSettings($r), Permissions::ADMIN_SERVERS_CREATE, ['PUT']);
    $app->registerAdminRoute($routes, 'admin-free-servers-install-spells', '/api/admin/free-servers/install-spells', fn (Request $r) => (new FreeServersController())->installSpells($r), Permissions::ADMIN_SPELLS_CREATE, ['POST']);
    $app->registerAdminRoute($routes, 'admin-free-servers-servers', '/api/admin/free-servers/servers', fn (Request $r) => (new FreeServersController())->servers($r), Permissions::ADMIN_SERVERS_VIEW, ['GET']);
    $app->registerAdminRoute($routes, 'admin-free-servers-run', '/api/admin/free-servers/run', fn (Request $r) => (new FreeServersController())->run($r), Permissions::ADMIN_SERVERS_EDIT, ['POST']);
};
