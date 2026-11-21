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

/**
 * The two virtual server products of OrveX Panel:
 *
 * - VDS: virtual servers on Proxmox VE nodes (node_type "proxmox").
 * - VPS: virtual servers on OrveX nodes, the panel's own node system (node_type "orvex").
 *
 * Both share one engine (API, pages and components). Routes, module switches and wording
 * tell them apart. Plain functions only, so server components can import this file too;
 * the React hooks live in `@/hooks/useVmProduct`.
 */

export type VmProduct = 'vds' | 'vps';
export type VmNodeType = 'proxmox' | 'orvex';

export const VM_PRODUCTS: VmProduct[] = ['vds', 'vps'];

export const VM_PRODUCT_NODE_TYPE: Record<VmProduct, VmNodeType> = { vds: 'proxmox', vps: 'orvex' };

export interface VmProductRoutes {
    /** Base of one server's pages: `${instance}/{id}`. */
    instance: string;
    /** The user's list of servers. */
    list: string;
    adminNodes: string;
    adminServers: string;
}

export const VM_PRODUCT_ROUTES: Record<VmProduct, VmProductRoutes> = {
    vds: {
        instance: '/vds',
        list: '/dashboard/vms',
        adminNodes: '/admin/vds-nodes',
        adminServers: '/admin/vm-instances',
    },
    vps: {
        instance: '/vps',
        list: '/dashboard/vps',
        adminNodes: '/admin/vps-nodes',
        adminServers: '/admin/vps-servers',
    },
};

/**
 * Server pages that only exist for VDS: Proxmox features OrveX nodes do not have (the guest
 * firewall, and boot order with ISO mounting).
 */
export const VDS_ONLY_INSTANCE_PAGES = ['firewall', 'boot'] as const;

/** Product of a node type. Missing or unknown types are Proxmox nodes, as before node types existed. */
export function productForNodeType(nodeType?: string | null): VmProduct {
    return nodeType === 'orvex' ? 'vps' : 'vds';
}

/** `/vds/{id}` or `/vps/{id}`, plus an optional sub page (`settings`, `backups`, ...). */
export function vmInstanceBase(product: VmProduct, id: number | string, subPath = ''): string {
    const sub = subPath.replace(/^\/+/, '');
    return `${VM_PRODUCT_ROUTES[product].instance}/${id}${sub ? `/${sub}` : ''}`;
}

/** Link to a server's pages, picked by the type of the node it runs on. */
export function vmInstanceHref(vm: { id: number | string; node_type?: string | null }, subPath = ''): string {
    return vmInstanceBase(productForNodeType(vm.node_type), vm.id, subPath);
}

/** Admin edit page of a server: VDS servers or VPS servers, picked by the node type. */
export function vmAdminEditHref(vm: { id: number | string; node_type?: string | null }): string {
    return `${VM_PRODUCT_ROUTES[productForNodeType(vm.node_type)].adminServers}/${vm.id}/edit`;
}

function matchesPrefix(pathname: string, prefix: string): boolean {
    return pathname === prefix || pathname.startsWith(prefix + '/');
}

/** Product a pathname belongs to (server pages, user list, admin nodes and servers), or null. */
export function productForPathname(pathname?: string | null): VmProduct | null {
    if (!pathname) return null;
    for (const product of VM_PRODUCTS) {
        const routes = VM_PRODUCT_ROUTES[product];
        if (
            [routes.instance, routes.list, routes.adminNodes, routes.adminServers].some((p) =>
                matchesPrefix(pathname, p),
            )
        ) {
            return product;
        }
    }
    return null;
}

/** `/vds/12/settings` -> { product: 'vds', id: '12', rest: '/settings' }; null for other paths. */
export function parseVmInstancePath(pathname?: string | null): { product: VmProduct; id: string; rest: string } | null {
    if (!pathname) return null;
    const match = /^\/(vds|vps)\/([^/]+)(\/.*)?$/.exec(pathname);
    if (!match) return null;
    return { product: match[1] as VmProduct, id: match[2]!, rest: match[3] ?? '' };
}

export function isVmInstancePath(pathname?: string | null): boolean {
    return parseVmInstancePath(pathname) !== null;
}

/**
 * The same page for the other product: server pages, user list and admin pages. Server
 * pages that do not exist for VPS fall back to the server's overview.
 */
export function swapVmProductPath(pathname: string, to: VmProduct): string | null {
    const instance = parseVmInstancePath(pathname);
    if (instance) {
        if (instance.product === to) return pathname;
        const page = instance.rest.split('/')[1] ?? '';
        const rest = to === 'vps' && (VDS_ONLY_INSTANCE_PAGES as readonly string[]).includes(page) ? '' : instance.rest;
        return `${VM_PRODUCT_ROUTES[to].instance}/${instance.id}${rest}`;
    }
    const from = productForPathname(pathname);
    if (!from) return null;
    if (from === to) return pathname;
    const source = VM_PRODUCT_ROUTES[from];
    const target = VM_PRODUCT_ROUTES[to];
    for (const key of ['list', 'adminNodes', 'adminServers'] as const) {
        if (matchesPrefix(pathname, source[key])) return target[key] + pathname.slice(source[key].length);
    }
    return null;
}

/**
 * VPS wording for a shared (VDS) string: "VDS" becomes "VPS". Applied to the translation
 * template before parameters are filled in, so host names and other values stay as they are.
 */
export function toVpsWording(text: string): string {
    return text.replace(/\bVDS(?=(?:es|s)?\b)/g, 'VPS');
}

/** Fills `{name}` and `{{name}}` placeholders like the translation context does. */
export function fillTranslationParams(template: string, params?: Record<string, string>): string {
    if (!params) return template;
    return template.replace(/\{\{\s*(\w+)\s*\}\}|\{(\w+)\}/g, (match, doubleKey, singleKey) => {
        const value = (params as Record<string, unknown>)[doubleKey ?? singleKey];
        return value === undefined || value === null ? match : String(value);
    });
}

/** Prefix of the translation keys that replace a shared string on VPS pages (`vps.text.<key>`). */
export const VPS_TEXT_PREFIX = 'vps.text.';

/** String at a dotted key of a translation catalog, or undefined. */
export function lookupTranslation(translations: Record<string, unknown>, key: string): string | undefined {
    let value: unknown = translations;
    for (const part of key.split('.')) {
        if (value && typeof value === 'object' && part in (value as Record<string, unknown>)) {
            value = (value as Record<string, unknown>)[part];
        } else {
            return undefined;
        }
    }
    return typeof value === 'string' ? value : undefined;
}

/**
 * Translation for a VPS page: the `vps.text.<key>` override when there is one (used where the
 * shared string talks about Proxmox), otherwise the shared string with VPS wording.
 * Returns undefined when neither exists, so the caller can fall back to its usual handling.
 */
export function translateForVps(
    translations: Record<string, unknown>,
    key: string,
    params?: Record<string, string>,
): string | undefined {
    const override = lookupTranslation(translations, VPS_TEXT_PREFIX + key);
    if (override !== undefined) return fillTranslationParams(override, params);
    const shared = lookupTranslation(translations, key);
    if (shared === undefined) return undefined;
    return fillTranslationParams(toVpsWording(shared), params);
}
