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

'use client';

import { useCallback, useMemo } from 'react';
import { usePathname } from 'next/navigation';
import { useTranslation } from '@/contexts/TranslationContext';
import {
    productForPathname,
    translateForVps,
    VM_PRODUCT_NODE_TYPE,
    VM_PRODUCT_ROUTES,
    type VmNodeType,
    type VmProduct,
    type VmProductRoutes,
} from '@/lib/vm-products';

/**
 * Virtual server product of the current page: 'vps' on VPS pages (/vps/{id}, /dashboard/vps,
 * /admin/vps-nodes, /admin/vps-servers), otherwise 'vds'. The VDS and VPS pages share their
 * components; this is how a component knows which one it is rendering.
 */
export function useVmProduct(): { product: VmProduct; nodeType: VmNodeType; routes: VmProductRoutes } {
    const pathname = usePathname();
    const product = productForPathname(pathname) ?? 'vds';
    return useMemo(
        () => ({ product, nodeType: VM_PRODUCT_NODE_TYPE[product], routes: VM_PRODUCT_ROUTES[product] }),
        [product],
    );
}

/**
 * `useTranslation()` for components shared by VDS and VPS pages. On VDS pages it is the plain
 * translation function. On VPS pages strings say "VPS" instead of "VDS", and strings that talk
 * about Proxmox are replaced by their `vps.text.<key>` version (see `translateForVps`).
 */
export function useVmTranslation() {
    const translation = useTranslation();
    const { product } = useVmProduct();
    const { t: baseT, translations } = translation;

    const t = useCallback(
        (key: string, params?: Record<string, string>): string => {
            if (product !== 'vps') return baseT(key, params);
            return translateForVps(translations, key, params) ?? baseT(key, params);
        },
        [product, baseT, translations],
    );

    return useMemo(() => ({ ...translation, t, product }), [translation, t, product]);
}
