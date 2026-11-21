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

import { useEffect, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useTranslation } from '@/contexts/TranslationContext';
import { useVmInstance } from '@/contexts/VmInstanceContext';
import { VdsPageLoading } from '@/components/vds/VdsPageLoading';
import { productForNodeType, swapVmProductPath, type VmProduct } from '@/lib/vm-products';

/**
 * VDS servers (Proxmox nodes) live under /vds/{id} and VPS servers (OrveX nodes) under /vps/{id}.
 * A link with the other product's address (an old bookmark, a notification from before the split)
 * goes to the same page of the right product instead of showing the wrong product's pages.
 */
export function VmProductGuard({ product, children }: { product: VmProduct; children: ReactNode }) {
    const { t } = useTranslation();
    const { instance } = useVmInstance();
    const pathname = usePathname();
    const router = useRouter();

    // Only a server that reported its node type is moved (the suspended placeholder has none).
    const actual = instance?.node_type ? productForNodeType(instance.node_type) : product;
    const target = actual !== product && pathname ? swapVmProductPath(pathname, actual) : null;

    useEffect(() => {
        if (target) router.replace(`${target}${window.location.search}${window.location.hash}`);
    }, [target, router]);

    if (target) return <VdsPageLoading label={t('common.loading')} />;

    return <>{children}</>;
}
