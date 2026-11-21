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

namespace App\Services\FreeServers;

use App\Chat\Realm;
use App\Chat\Spell;
use App\Controllers\Admin\SpellsController;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\File\UploadedFile;

/**
 * One-click setup: imports the bundled free-tier spells (storage/eggs/free-tier) into the
 * "Free servers" realm through the normal spell import, and maps each stack to its spell.
 * A spell that is already there (same uuid) is reused instead of imported twice.
 */
class FreeServerSpellInstaller
{
    public const REALM_NAME = 'Free servers';

    /**
     * @param list<string> $stacks Stack keys to set up; empty means every stack without a working spell
     *
     * @return array{mapped: array<string, int>, imported: list<string>, reused: list<string>, failed: array<string, string>}
     */
    public function install(array $admin, array $stacks = []): array
    {
        $policy = FreeServerPolicy::get();
        if ($stacks === []) {
            $current = Spell::getSpellsByIds(array_values($policy['stacks']));
            foreach (FreeServerStacks::keys() as $key) {
                $spellId = $policy['stacks'][$key] ?? null;
                if ($spellId === null || !isset($current[$spellId])) {
                    $stacks[] = $key;
                }
            }
        }

        $mapped = [];
        $imported = [];
        $reused = [];
        $failed = [];
        $realmId = null;
        foreach (array_values(array_unique($stacks)) as $key) {
            if (!FreeServerStacks::isValid($key)) {
                continue;
            }
            $existing = $this->spellByUuid(FreeServerStacks::CATALOG[$key]['uuid']);
            if ($existing !== null) {
                $mapped[$key] = (int) $existing['id'];
                $reused[] = $key;
                continue;
            }
            $path = FreeServerStacks::eggPath($key);
            if ($path === null) {
                $failed[$key] = 'The bundled spell file is missing';
                continue;
            }
            $realmId ??= $this->realmId();
            if ($realmId === null) {
                $failed[$key] = 'The Free servers realm could not be created';
                continue;
            }
            $result = $this->import($admin, $realmId, $path);
            if ($result['ok']) {
                $mapped[$key] = $result['spell_id'];
                $imported[] = $key;
            } else {
                $failed[$key] = $result['message'];
            }
        }

        if ($mapped !== []) {
            foreach ($mapped as $key => $spellId) {
                $policy['stacks'][$key] = $spellId;
            }
            FreeServerPolicy::save($policy);
        }

        return ['mapped' => $mapped, 'imported' => $imported, 'reused' => $reused, 'failed' => $failed];
    }

    protected function spellByUuid(string $uuid): ?array
    {
        return Spell::getSpellByUuid($uuid);
    }

    /** The "Free servers" realm, created when it does not exist yet. */
    protected function realmId(): ?int
    {
        foreach (Realm::getAll(self::REALM_NAME, 50, 0) as $realm) {
            if (strcasecmp((string) $realm['name'], self::REALM_NAME) === 0) {
                return (int) $realm['id'];
            }
        }
        $id = Realm::create(['name' => self::REALM_NAME, 'description' => 'Runtimes and databases offered as free servers.']);

        return $id === false ? null : (int) $id;
    }

    /**
     * Import one egg file through the admin spell import.
     *
     * @return array{ok: bool, spell_id?: int, message?: string}
     */
    protected function import(array $admin, int $realmId, string $path): array
    {
        $request = new Request();
        $request->request->set('realm_id', (string) $realmId);
        $request->files->set('file', new UploadedFile($path, basename($path), 'application/json', null, true));
        $request->attributes->set('user', $admin);
        $response = (new SpellsController())->import($request);
        $body = json_decode((string) $response->getContent(), true);
        if ($response->getStatusCode() < 400 && isset($body['data']['spell']['id'])) {
            return ['ok' => true, 'spell_id' => (int) $body['data']['spell']['id']];
        }

        return ['ok' => false, 'message' => (string) ($body['message'] ?? 'The spell could not be imported')];
    }
}
