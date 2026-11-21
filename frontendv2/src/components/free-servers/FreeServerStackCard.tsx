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

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Layers } from 'lucide-react';
import { PageCard } from '@/components/featherui/PageCard';
import { Button } from '@/components/featherui/Button';
import { StackPicker } from '@/components/free-servers/StackPicker';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { useTranslation } from '@/contexts/TranslationContext';
import { getApiErrorMessage } from '@/lib/api-errors';
import { freeServersApi, isFreeServerStack, type FreeServerStackKey } from '@/lib/free-servers';
import type { ServerFreeServerInfo } from '@/types/server';

interface FreeServerStackCardProps {
    uuidShort: string;
    info: ServerFreeServerInfo;
    /** Called after the switch started, so the page can load the server again. */
    onChanged: () => Promise<void> | void;
}

/** Server settings card that switches a free server to another stack (the create page's step 01). */
export function FreeServerStackCard({ uuidShort, info, onChanged }: FreeServerStackCardProps) {
    const { t } = useTranslation();
    const [available, setAvailable] = useState<FreeServerStackKey[] | null>(null);
    const [target, setTarget] = useState<FreeServerStackKey | null>(null);
    const [switching, setSwitching] = useState(false);
    const current = isFreeServerStack(info.stack) ? info.stack : null;

    useEffect(() => {
        let cancelled = false;
        freeServersApi
            .options()
            .then((options) => {
                if (!cancelled) setAvailable(options.stacks.filter((s) => s.available).map((s) => s.key));
            })
            .catch(() => {
                if (!cancelled) setAvailable([]);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const confirm = async () => {
        if (!target) return;
        setSwitching(true);
        try {
            await freeServersApi.changeStack(uuidShort, target);
            toast.success(t('freeServers.stack_card.changed', { stack: t(`freeServers.stacks.${target}.title`) }));
            setTarget(null);
            await onChanged();
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'freeServers.stack_card.failed'));
        } finally {
            setSwitching(false);
        }
    };

    const others = (available ?? []).filter((key) => key !== current);

    return (
        <PageCard
            title={t('freeServers.stack_card.title')}
            description={t('freeServers.stack_card.description')}
            icon={Layers}
        >
            {available === null ? (
                <div className='grid grid-cols-1 gap-3 sm:grid-cols-2' aria-busy='true'>
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className='bg-muted/40 h-20 animate-pulse rounded-2xl' />
                    ))}
                </div>
            ) : others.length === 0 ? (
                <p className='text-muted-foreground text-sm'>{t('freeServers.stack_card.none')}</p>
            ) : (
                <StackPicker
                    available={current ? [current, ...others] : others}
                    value={target}
                    current={current}
                    onChange={setTarget}
                    disabled={switching}
                    label={t('freeServers.stack_card.title')}
                    compact
                />
            )}

            <Dialog open={target !== null} onOpenChange={(open) => !open && !switching && setTarget(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {target
                                ? t('freeServers.stack_card.confirm_title', {
                                      stack: t(`freeServers.stacks.${target}.title`),
                                  })
                                : null}
                        </DialogTitle>
                        <DialogDescription>
                            {target
                                ? t('freeServers.stack_card.confirm_body', {
                                      stack: t(`freeServers.stacks.${target}.title`),
                                  })
                                : null}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant='ghost' onClick={() => setTarget(null)} disabled={switching}>
                            {t('common.cancel')}
                        </Button>
                        <Button onClick={() => void confirm()} loading={switching}>
                            {t('freeServers.stack_card.confirm')}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </PageCard>
    );
}
