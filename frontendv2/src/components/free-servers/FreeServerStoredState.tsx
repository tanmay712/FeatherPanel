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

import { useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { Archive, ArrowLeft, RotateCcw } from 'lucide-react';
import { Button } from '@/components/featherui/Button';
import { StackIcon } from '@/components/free-servers/StackIcon';
import { useTranslation } from '@/contexts/TranslationContext';
import { getApiErrorMessage } from '@/lib/api-errors';
import { freeServersApi, isFreeServerStack } from '@/lib/free-servers';
import type { ServerFreeServerInfo } from '@/types/server';

interface FreeServerStoredStateProps {
    uuidShort: string;
    name: string;
    info: ServerFreeServerInfo;
    /** Called after a successful restore so the page can load the server again. */
    onRestored: () => Promise<void> | void;
}

/**
 * Shown instead of the server pages while a free server is in storage (its owner did not log in
 * for a long time). Nothing was deleted; the owner brings it back with one click.
 */
export function FreeServerStoredState({ uuidShort, name, info, onRestored }: FreeServerStoredStateProps) {
    const { t } = useTranslation();
    const [restoring, setRestoring] = useState(false);

    const restore = async () => {
        setRestoring(true);
        try {
            const result = await freeServersApi.restore(uuidShort);
            toast.success(
                result.started ? t('freeServers.stored.restored') : t('freeServers.stored.restored_not_started'),
            );
            await onRestored();
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'freeServers.stored.restore_failed'));
        } finally {
            setRestoring(false);
        }
    };

    const body = !info.restorable
        ? t('freeServers.stored.staff')
        : info.is_owner
          ? t('freeServers.stored.body')
          : t('freeServers.stored.body_subuser');

    return (
        <div className='flex min-h-[60vh] items-center justify-center px-4 py-10'>
            <section className='border-border bg-card text-card-foreground w-full max-w-lg overflow-hidden rounded-xl border'>
                <div className='p-6 sm:p-8'>
                    <div className='flex min-w-0 items-center gap-2.5'>
                        <span className='inline-flex shrink-0 items-center gap-1.5 rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400'>
                            <Archive className='h-3 w-3' aria-hidden />
                            {t('freeServers.stored.badge')}
                        </span>
                        <span className='text-muted-foreground min-w-0 truncate font-mono text-xs'>{name}</span>
                        {isFreeServerStack(info.stack) && <StackIcon stack={info.stack} className='ml-auto h-5 w-5' />}
                    </div>
                    <h2 className='mt-4 text-xl font-semibold tracking-tight'>{t('freeServers.stored.title')}</h2>
                    <p className='text-muted-foreground mt-2 text-sm leading-relaxed'>{body}</p>
                </div>
                <div className='border-border bg-muted/30 flex flex-col-reverse gap-2 border-t px-6 py-4 sm:flex-row sm:justify-end sm:px-8'>
                    <Button asChild variant='outline' size='sm'>
                        <Link href='/dashboard/servers'>
                            <ArrowLeft className='mr-1.5 h-3.5 w-3.5' aria-hidden />
                            {t('freeServers.page.back')}
                        </Link>
                    </Button>
                    {info.restorable && info.is_owner && (
                        <Button size='sm' onClick={() => void restore()} loading={restoring}>
                            {!restoring && <RotateCcw className='mr-1.5 h-3.5 w-3.5' aria-hidden />}
                            {restoring ? t('freeServers.stored.restoring') : t('freeServers.stored.restore')}
                        </Button>
                    )}
                </div>
            </section>
        </div>
    );
}
