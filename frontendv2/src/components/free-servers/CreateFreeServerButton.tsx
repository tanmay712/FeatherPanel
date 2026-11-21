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

import Link from 'next/link';
import { Plus } from 'lucide-react';
import { cn, isEnabled } from '@/lib/utils';
import { isModuleEnabled } from '@/lib/modules';
import { useSettings } from '@/contexts/SettingsContext';
import { useTranslation } from '@/contexts/TranslationContext';
import { Button } from '@/components/featherui/Button';

export const FREE_SERVER_CREATE_PATH = '/dashboard/servers/create';

/** True when users can create free servers (Admin > Free servers turned them on). */
export function useFreeServersEnabled(): boolean {
    const { settings } = useSettings();
    return isModuleEnabled(settings, 'game') && isEnabled(settings?.free_servers_enabled);
}

interface CreateFreeServerButtonProps {
    /** `default` for page headers and empty states, `toolbar` for the small dashboard toolbar. */
    variant?: 'default' | 'toolbar';
    className?: string;
}

/** "Create server" link to the free server create page. Renders nothing while free servers are off. */
export function CreateFreeServerButton({ variant = 'default', className }: CreateFreeServerButtonProps) {
    const { t } = useTranslation();
    const enabled = useFreeServersEnabled();
    if (!enabled) return null;

    if (variant === 'toolbar') {
        return (
            <Link
                href={FREE_SERVER_CREATE_PATH}
                className={cn(
                    'bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold transition-colors',
                    className,
                )}
            >
                <Plus className='h-3.5 w-3.5' aria-hidden />
                {t('freeServers.create_button')}
            </Link>
        );
    }

    return (
        <Button asChild size='sm' className={className}>
            <Link href={FREE_SERVER_CREATE_PATH}>
                <Plus className='mr-1.5 h-4 w-4' aria-hidden />
                {t('freeServers.create_button')}
            </Link>
        </Button>
    );
}
