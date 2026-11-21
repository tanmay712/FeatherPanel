/*
This file is part of FeatherPanel.

Copyright (C) 2025 MythicalSystems Studios
Copyright (C) 2025 FeatherPanel Contributors
Copyright (C) 2025 Cassian Gherman (aka NaysKutzu)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

See the LICENSE file or <https://www.gnu.org/licenses/>.
*/

import axios from 'axios';

/** Stacks a free server can run, in the order the create page lists them. Matches FreeServerStacks.php. */
export const FREE_SERVER_STACKS = [
    { key: 'nodejs', group: 'runtime' },
    { key: 'python', group: 'runtime' },
    { key: 'bun', group: 'runtime' },
    { key: 'java', group: 'runtime' },
    { key: 'csharp', group: 'runtime' },
    { key: 'rust', group: 'runtime' },
    { key: 'lua', group: 'runtime' },
    { key: 'mongodb', group: 'database' },
    { key: 'mariadb', group: 'database' },
    { key: 'postgresql', group: 'database' },
    { key: 'redis', group: 'database' },
] as const;

export type FreeServerStackKey = (typeof FREE_SERVER_STACKS)[number]['key'];
export type FreeServerStackGroup = 'runtime' | 'database';
export type FreeServerStage = 'stopped' | 'stored' | null;

export const FREE_SERVER_NAME_MAX = 60;
export const FREE_SERVER_DESCRIPTION_MAX = 500;

export function isFreeServerStack(value: unknown): value is FreeServerStackKey {
    return typeof value === 'string' && FREE_SERVER_STACKS.some((s) => s.key === value);
}

export interface FreeServerOptions {
    enabled: boolean;
    resources: { memory: number; disk: number; cpu: number };
    limit: { max: number; used: number; reached: boolean };
    stacks: { key: FreeServerStackKey; group: FreeServerStackGroup; available: boolean }[];
    capacity: boolean;
    inactivity: { enabled: boolean; stop_after_days: number; store_after_days: number };
    notes: { ads: boolean };
}

export interface FreeServerInfo {
    server_id: number;
    uuid_short: string;
    name: string;
    stack: FreeServerStackKey;
    stage: FreeServerStage;
    stage_at: string | null;
    suspended: boolean;
    restorable: boolean;
    created_at: string;
    stop_at: string | null;
    store_at: string | null;
}

export interface CreatedFreeServer {
    server_id: number;
    uuid_short: string;
    name: string;
    stack: FreeServerStackKey;
}

interface Envelope<T> {
    success: boolean;
    data: T;
}

export const freeServersApi = {
    async options(): Promise<FreeServerOptions> {
        const { data } = await axios.get<Envelope<FreeServerOptions>>('/api/user/free-servers/options');
        return data.data;
    },
    async list(): Promise<FreeServerInfo[]> {
        const { data } = await axios.get<Envelope<{ servers: FreeServerInfo[] }>>('/api/user/free-servers');
        return data.data.servers;
    },
    /** The free server details, or null when the server is not a free server owned by the user. */
    async show(uuidShort: string): Promise<FreeServerInfo | null> {
        try {
            const { data } = await axios.get<Envelope<{ server: FreeServerInfo }>>(
                `/api/user/free-servers/${encodeURIComponent(uuidShort)}`,
            );
            return data.data.server;
        } catch (error) {
            if (axios.isAxiosError(error) && (error.response?.status === 404 || error.response?.status === 403)) {
                return null;
            }
            throw error;
        }
    },
    async create(input: { stack: FreeServerStackKey; name: string; description: string }): Promise<CreatedFreeServer> {
        const { data } = await axios.post<Envelope<{ server: CreatedFreeServer }>>('/api/user/free-servers', input);
        return data.data.server;
    },
    async changeStack(uuidShort: string, stack: FreeServerStackKey): Promise<void> {
        await axios.post(`/api/user/free-servers/${encodeURIComponent(uuidShort)}/stack`, { stack });
    },
    async restore(uuidShort: string): Promise<{ started: boolean }> {
        const { data } = await axios.post<Envelope<{ started: boolean }>>(
            `/api/user/free-servers/${encodeURIComponent(uuidShort)}/restore`,
        );
        return data.data;
    },
};

const NAME_ADJECTIVES = [
    'Swift',
    'Cosmic',
    'Silent',
    'Lucky',
    'Brave',
    'Clever',
    'Mighty',
    'Sunny',
    'Frosty',
    'Electric',
    'Golden',
    'Hidden',
    'Turbo',
    'Pixel',
    'Neon',
    'Rapid',
    'Quiet',
    'Wild',
    'Tiny',
    'Stellar',
];

const NAME_NOUNS = [
    'Falcon',
    'Otter',
    'Comet',
    'Panda',
    'Rocket',
    'Fox',
    'Badger',
    'Nebula',
    'Koala',
    'Golem',
    'Phoenix',
    'Raven',
    'Beacon',
    'Penguin',
    'Lynx',
    'Gecko',
    'Orbit',
    'Puffin',
    'Wizard',
    'Kraken',
];

/** A random friendly server name, for the shuffle button. Never returns `current`. */
export function randomServerName(current = '', random: () => number = Math.random): string {
    for (let i = 0; i < 10; i++) {
        const adjective = NAME_ADJECTIVES[Math.floor(random() * NAME_ADJECTIVES.length)];
        const noun = NAME_NOUNS[Math.floor(random() * NAME_NOUNS.length)];
        const name = `${adjective} ${noun}`;
        if (name !== current) return name;
    }
    return `${NAME_ADJECTIVES[0]} ${NAME_NOUNS[0]}`;
}

/** "512 MB" or "1 GB" (whole gigabytes from 1024 MB up). */
export function formatFreeServerMb(mb: number): string {
    if (mb >= 1024 && mb % 1024 === 0) return `${mb / 1024} GB`;
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    return `${mb} MB`;
}
