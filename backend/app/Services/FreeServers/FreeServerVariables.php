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

/**
 * Startup variable values for a new free server. The user only picks a stack, so every
 * variable takes the spell's default, except passwords: each server gets its own random one
 * instead of the shared default from the egg (database eggs ship well-known defaults).
 */
final class FreeServerVariables
{
    /**
     * @param list<array<string, mixed>> $spellVariables Rows with env_variable, default_value and rules
     * @param callable(int): string|null $random Returns a random password of the given length
     *
     * @return array{values: array<string, string>, missing: list<string>}
     */
    public static function build(array $spellVariables, ?callable $random = null): array
    {
        $random ??= [self::class, 'randomSecret'];
        $values = [];
        $missing = [];
        foreach ($spellVariables as $variable) {
            $env = trim((string) ($variable['env_variable'] ?? ''));
            if ($env === '') {
                continue;
            }
            $rules = self::rules($variable['rules'] ?? '');
            $value = (string) ($variable['default_value'] ?? '');
            if (self::isSecret($env)) {
                $max = self::maxLength($rules);
                $value = (string) $random(max(8, min(24, $max ?? 24)));
            }
            if (trim($value) === '' && in_array('required', $rules, true)) {
                $missing[] = $env;
                continue;
            }
            $values[$env] = $value;
        }

        return ['values' => $values, 'missing' => $missing];
    }

    /** True for variables holding a password or other secret the user should not share with others. */
    public static function isSecret(string $env): bool
    {
        return (bool) preg_match('/(PASS(WORD)?|SECRET)$|_PASS_|PASSWORD/i', $env);
    }

    /** Letters and digits only, so the value is safe inside startup commands and config files. */
    public static function randomSecret(int $length): string
    {
        $alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
        $max = strlen($alphabet) - 1;
        $out = '';
        for ($i = 0; $i < $length; ++$i) {
            $out .= $alphabet[random_int(0, $max)];
        }

        return $out;
    }

    /**
     * @return list<string>
     */
    private static function rules(mixed $rules): array
    {
        $list = is_array($rules) ? $rules : explode('|', (string) $rules);

        return array_values(array_filter(array_map(static fn ($r): string => trim((string) $r), $list), static fn (string $r): bool => $r !== ''));
    }

    /** @param list<string> $rules */
    private static function maxLength(array $rules): ?int
    {
        foreach ($rules as $rule) {
            if (preg_match('/^max:(\d+)$/', $rule, $m)) {
                return (int) $m[1];
            }
        }

        return null;
    }
}
