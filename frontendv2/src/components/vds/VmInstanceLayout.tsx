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

import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { cookies } from 'next/headers';
import DashboardShell from '@/components/layout/DashboardShell';
import ChatbotWidget from '@/components/ai/ChatbotWidget';
import { getBaseUrl } from '@/lib/settings-api';
import { VmInstanceProvider, VmInstance } from '@/contexts/VmInstanceContext';
import { VdsSuspendedWrapper } from '@/components/vds/VdsSuspendedWrapper';
import { VdsReauthProvider } from '@/components/vds/VdsReauth';
import { VmProductGuard } from '@/components/vds/VmProductGuard';
import type { VmProduct } from '@/lib/vm-products';

/**
 * Server-side layout shared by the VDS (/vds/{id}) and VPS (/vps/{id}) server pages.
 * Layout files may only export what Next.js expects, so the shared parts live here.
 */
export async function getVmInstance(id: string): Promise<VmInstance | null> {
    try {
        const cookieStore = await cookies();
        const allCookies = cookieStore.getAll();
        const cookieHeader = allCookies.map((c) => `${c.name}=${c.value}`).join('; ');

        const baseUrl = getBaseUrl();
        const url = `${baseUrl}/api/user/vm-instances/${id}`;

        const res = await fetch(url, {
            headers: {
                Cookie: cookieHeader,
                Accept: 'application/json',
            },
            cache: 'no-store', // per-user data, never cached
        });

        if (!res.ok) return null;

        const data = await res.json();
        return data.success ? data.data.instance : null;
    } catch {
        return null;
    }
}

export async function vmInstanceMetadata(product: VmProduct, id: string): Promise<Metadata> {
    const instance = await getVmInstance(id);
    const title = instance?.hostname || `${product === 'vps' ? 'VPS' : 'VDS'} #${id}`;
    return {
        title,
        openGraph: { title },
    };
}

export async function VmInstanceLayout({
    product,
    id,
    children,
}: {
    product: VmProduct;
    id: string;
    children: ReactNode;
}) {
    const instance = await getVmInstance(id);

    return (
        <VmInstanceProvider instanceId={parseInt(id, 10)} initialInstance={instance}>
            <DashboardShell>
                <VmProductGuard product={product}>
                    <VdsReauthProvider>
                        <VdsSuspendedWrapper>{children}</VdsSuspendedWrapper>
                    </VdsReauthProvider>
                </VmProductGuard>
            </DashboardShell>
            <ChatbotWidget />
        </VmInstanceProvider>
    );
}
