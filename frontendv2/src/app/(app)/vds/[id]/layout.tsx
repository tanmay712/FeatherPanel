/*
This file is part of FeatherPanel.

Copyright (C) 2025 MythicalSystems Studio
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
    return vmInstanceMetadata('vds', id);
}

/** VDS servers (Proxmox VE nodes). VPS servers on OrveX nodes use /vps/{id} with the same pages. */
export default async function VdsLayout({
    children,
    params,
}: {
    children: React.ReactNode;
    params: Promise<{ id: string }>;
}) {
    const { id } = await params;

    return (
        <VmInstanceLayout product='vds' id={id}>
            {children}
        </VmInstanceLayout>
    );
}
