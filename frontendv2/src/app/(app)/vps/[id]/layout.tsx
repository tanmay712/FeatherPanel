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

import { Metadata } from 'next';
import { VmInstanceLayout, vmInstanceMetadata } from '@/components/vds/VmInstanceLayout';

type Props = {
    params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { id } = await params;
    return vmInstanceMetadata('vps', id);
}

/** VPS servers (OrveX nodes). They share the server pages with VDS, minus the Proxmox-only ones. */
export default async function VpsLayout({
    children,
    params,
}: {
    children: React.ReactNode;
    params: Promise<{ id: string }>;
}) {
    const { id } = await params;

    return (
        <VmInstanceLayout product='vps' id={id}>
            {children}
        </VmInstanceLayout>
    );
}
