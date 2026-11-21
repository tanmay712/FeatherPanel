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

namespace App\Cron;

/**
 * Free server inactivity: stops free servers whose owner has not logged in for the configured
 * number of days and later moves them to storage (suspended, nothing deleted). Also clears the
 * stop once the owner is back. Does nothing while free servers were never set up.
 */

use App\App;
use App\Chat\TimedTask;
use App\Cli\Utils\MinecraftColorCodeSupport;
use App\Services\FreeServers\FreeServerPolicy;
use App\Services\FreeServers\FreeServerInactivity;

class ZFreeServerInactivity implements TimeTask
{
    public function run()
    {
        $cron = new Cron('free-server-inactivity', '1H');
        $force = getenv('FP_CRON_FORCE') === '1';
        try {
            $cron->runIfDue(function () {
                // Runs while free servers are turned off too, so servers created before stay covered.
                $service = new FreeServerInactivity(FreeServerPolicy::get());
                $result = $service->execute($service->plan());
                $summary = json_encode($result['applied']) . ', failed ' . $result['failed'];
                MinecraftColorCodeSupport::sendOutputWithNewLine('&aFree server inactivity: ' . $summary);
                TimedTask::markRun('free-server-inactivity', $result['failed'] === 0, 'Free server inactivity ' . $summary);
            }, $force);
        } catch (\Throwable $e) {
            App::getInstance(false, true)->getLogger()->error('Free server inactivity failed: ' . $e->getMessage());
            TimedTask::markRun('free-server-inactivity', false, $e->getMessage());
        }
    }
}
