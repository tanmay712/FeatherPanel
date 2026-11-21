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

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { ArrowLeft, Megaphone, Rocket, ServerOff, ShieldAlert, Shuffle, Timer, TriangleAlert } from 'lucide-react';
import { PageHeader } from '@/components/featherui/PageHeader';
import { Button } from '@/components/featherui/Button';
import { StackPicker } from '@/components/free-servers/StackPicker';
import { StackIcon } from '@/components/free-servers/StackIcon';
import { useTranslation } from '@/contexts/TranslationContext';
import { getApiErrorCode, getApiErrorMessage } from '@/lib/api-errors';
import {
    FREE_SERVER_DESCRIPTION_MAX,
    FREE_SERVER_NAME_MAX,
    formatFreeServerMb,
    freeServersApi,
    randomServerName,
    type FreeServerOptions,
    type FreeServerStackKey,
} from '@/lib/free-servers';

function StepHeading({ number, title, subtitle }: { number: string; title: string; subtitle?: string }) {
    return (
        <div className='space-y-2'>
            <div className='flex items-baseline gap-3'>
                <span className='text-muted-foreground font-mono text-sm tabular-nums'>{number}</span>
                <h2 className='text-xl font-bold tracking-tight sm:text-2xl'>{title}</h2>
            </div>
            {subtitle && <p className='text-muted-foreground text-sm sm:text-base'>{subtitle}</p>}
        </div>
    );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
    return (
        <div className='flex items-center justify-between gap-4'>
            <dt className='text-muted-foreground'>{label}</dt>
            <dd className='font-semibold tabular-nums'>{value}</dd>
        </div>
    );
}

function Note({ icon: Icon, children }: { icon: typeof Timer; children: ReactNode }) {
    return (
        <li className='flex gap-3'>
            <Icon className='mt-0.5 h-4 w-4 shrink-0' aria-hidden />
            <span>{children}</span>
        </li>
    );
}

function Banner({ tone, children }: { tone: 'warning' | 'error'; children: ReactNode }) {
    return (
        <div
            role='status'
            className={
                tone === 'error'
                    ? 'flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-500'
                    : 'flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-600 dark:text-amber-400'
            }
        >
            <TriangleAlert className='mt-0.5 h-4 w-4 shrink-0' aria-hidden />
            <div className='min-w-0 flex-1'>{children}</div>
        </div>
    );
}

export default function CreateFreeServerPage() {
    const { t } = useTranslation();
    const router = useRouter();
    const [options, setOptions] = useState<FreeServerOptions | null>(null);
    const [loadFailed, setLoadFailed] = useState(false);
    const [stack, setStack] = useState<FreeServerStackKey | null>(null);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [creating, setCreating] = useState(false);

    const load = useCallback(async () => {
        try {
            setOptions(await freeServersApi.options());
            setLoadFailed(false);
        } catch {
            setLoadFailed(true);
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const available = useMemo(() => (options?.stacks ?? []).filter((s) => s.available).map((s) => s.key), [options]);

    const trimmedName = name.trim();
    const blocked = !options || !options.enabled || options.limit.reached || !options.capacity;
    const valid =
        !blocked &&
        stack !== null &&
        available.includes(stack) &&
        trimmedName !== '' &&
        trimmedName.length <= FREE_SERVER_NAME_MAX;

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        if (!valid || !stack || creating) return;
        setCreating(true);
        try {
            const server = await freeServersApi.create({ stack, name: trimmedName, description: description.trim() });
            toast.success(t('freeServers.created', { name: server.name || trimmedName }));
            router.push(server.uuid_short ? `/server/${server.uuid_short}` : '/dashboard/servers');
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'freeServers.create_failed'));
            const code = getApiErrorCode(error);
            if (
                code === 'FREE_SERVER_LIMIT_REACHED' ||
                code === 'FREE_SERVER_NO_CAPACITY' ||
                code === 'FREE_SERVERS_DISABLED'
            ) {
                void load();
            }
            setCreating(false);
        }
    };

    const inactivityPeriod = useMemo(() => {
        const days = options?.inactivity.stop_after_days ?? 14;
        if (days % 7 === 0) {
            const weeks = days / 7;
            return weeks === 1
                ? t('freeServers.notes.period_week')
                : t('freeServers.notes.period_weeks', { count: String(weeks) });
        }
        return days === 1
            ? t('freeServers.notes.period_day')
            : t('freeServers.notes.period_days', { count: String(days) });
    }, [options, t]);

    const header = (
        <PageHeader
            title={t('freeServers.page.title')}
            description={t('freeServers.page.description')}
            icon={Rocket}
            actions={
                <Button asChild variant='outline' size='sm'>
                    <Link href='/dashboard/servers'>
                        <ArrowLeft className='mr-1.5 h-4 w-4' aria-hidden />
                        {t('freeServers.page.back')}
                    </Link>
                </Button>
            }
        />
    );

    if (!options) {
        return (
            <div className='space-y-6 pb-12'>
                {header}
                {loadFailed ? (
                    <Banner tone='error'>
                        <p>{t('freeServers.state.load_failed')}</p>
                        <button type='button' onClick={() => void load()} className='mt-2 font-semibold underline'>
                            {t('common.retry')}
                        </button>
                    </Banner>
                ) : (
                    <div className='space-y-4' aria-busy='true'>
                        <div className='bg-muted/50 h-8 w-64 animate-pulse rounded-lg' />
                        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4'>
                            {Array.from({ length: 8 }, (_, i) => (
                                <div key={i} className='bg-muted/40 h-24 animate-pulse rounded-2xl' />
                            ))}
                        </div>
                    </div>
                )}
            </div>
        );
    }

    if (!options.enabled || available.length === 0) {
        return (
            <div className='space-y-6 pb-12'>
                {header}
                <div className='border-border/60 bg-card/40 flex flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-14 text-center'>
                    <div className='bg-muted mb-5 flex h-16 w-16 items-center justify-center rounded-2xl'>
                        <ServerOff className='text-muted-foreground h-8 w-8' aria-hidden />
                    </div>
                    <h3 className='mb-2 text-xl font-bold'>{t('freeServers.state.disabled_title')}</h3>
                    <p className='text-muted-foreground max-w-md text-sm'>
                        {options.enabled ? t('freeServers.state.no_stacks') : t('freeServers.state.disabled_body')}
                    </p>
                </div>
            </div>
        );
    }

    const stackTitle = stack ? t(`freeServers.stacks.${stack}.title`) : null;

    return (
        <div className='space-y-6 pb-12'>
            {header}

            {options.limit.reached && (
                <Banner tone='warning'>
                    <p>
                        {t('freeServers.state.limit_reached', {
                            used: String(options.limit.used),
                            max: String(options.limit.max),
                        })}
                    </p>
                    <Link href='/dashboard/servers' className='mt-1 inline-block font-semibold underline'>
                        {t('freeServers.state.view_servers')}
                    </Link>
                </Banner>
            )}
            {!options.limit.reached && !options.capacity && (
                <Banner tone='warning'>
                    <p>{t('freeServers.state.no_capacity')}</p>
                </Banner>
            )}

            <section className='space-y-5'>
                <StepHeading
                    number='01'
                    title={t('freeServers.step1.title')}
                    subtitle={t('freeServers.step1.subtitle')}
                />
                <StackPicker
                    available={available}
                    value={stack}
                    onChange={setStack}
                    disabled={creating}
                    label={t('freeServers.step1.title')}
                />
            </section>

            <form onSubmit={submit} className='space-y-6 pt-4' noValidate>
                <section className='space-y-5'>
                    <StepHeading number='02' title={t('freeServers.step2.title')} />

                    <div className='space-y-2'>
                        <label htmlFor='free-server-name' className='block text-sm font-semibold'>
                            {t('freeServers.step2.name')}
                        </label>
                        <div className='flex gap-2'>
                            <input
                                id='free-server-name'
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                maxLength={FREE_SERVER_NAME_MAX}
                                placeholder={t('freeServers.step2.name_placeholder')}
                                autoComplete='off'
                                aria-describedby='free-server-name-help'
                                disabled={creating}
                                className='border-border/70 bg-background/60 focus:border-primary/60 focus:ring-primary/30 h-12 min-w-0 flex-1 rounded-xl border px-4 text-base transition-colors outline-none focus:ring-2 disabled:opacity-60'
                            />
                            <button
                                type='button'
                                onClick={() => setName((current) => randomServerName(current.trim()))}
                                disabled={creating}
                                aria-label={t('freeServers.step2.shuffle')}
                                title={t('freeServers.step2.shuffle')}
                                className='border-border/70 bg-background/60 hover:border-primary/40 hover:text-primary focus-visible:ring-primary/50 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60'
                            >
                                <Shuffle className='h-5 w-5' aria-hidden />
                            </button>
                        </div>
                        <p id='free-server-name-help' className='text-muted-foreground text-sm'>
                            {t('freeServers.step2.name_help')}
                        </p>
                    </div>

                    <div className='space-y-2'>
                        <label htmlFor='free-server-description' className='block text-sm font-semibold'>
                            {t('freeServers.step2.description')}{' '}
                            <span className='text-muted-foreground font-medium'>{t('freeServers.step2.optional')}</span>
                        </label>
                        <textarea
                            id='free-server-description'
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            maxLength={FREE_SERVER_DESCRIPTION_MAX}
                            rows={3}
                            placeholder={t('freeServers.step2.description_placeholder')}
                            disabled={creating}
                            className='border-border/70 bg-background/60 focus:border-primary/60 focus:ring-primary/30 block w-full resize-y rounded-xl border px-4 py-3 text-base transition-colors outline-none focus:ring-2 disabled:opacity-60'
                        />
                    </div>
                </section>

                <section
                    aria-label={t('freeServers.summary.label')}
                    className='border-border/70 bg-card/40 rounded-2xl border p-5 sm:p-8'
                >
                    <div className='flex items-center gap-4'>
                        <span className='border-border/70 bg-background/60 flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border'>
                            {stack && <StackIcon stack={stack} className='h-8 w-8' />}
                        </span>
                        <div className='min-w-0'>
                            <p className='truncate text-lg font-bold sm:text-xl'>
                                {trimmedName || t('freeServers.summary.untitled')}
                            </p>
                            <p className='text-muted-foreground truncate'>
                                {stackTitle ?? t('freeServers.summary.no_stack')}
                            </p>
                        </div>
                    </div>

                    <dl className='mt-6 space-y-4 text-sm sm:text-base'>
                        <SummaryRow
                            label={t('freeServers.summary.memory')}
                            value={formatFreeServerMb(options.resources.memory)}
                        />
                        <SummaryRow
                            label={t('freeServers.summary.disk')}
                            value={formatFreeServerMb(options.resources.disk)}
                        />
                        <SummaryRow label={t('freeServers.summary.cpu')} value={`${options.resources.cpu}%`} />
                        <SummaryRow label={t('freeServers.summary.price')} value={t('freeServers.summary.free')} />
                    </dl>

                    <Button type='submit' size='lg' className='mt-6 w-full' disabled={!valid} loading={creating}>
                        {creating ? t('freeServers.summary.creating') : t('freeServers.summary.create')}
                    </Button>

                    <ul className='border-border/70 text-muted-foreground mt-6 space-y-3 border-t pt-5 text-sm'>
                        {options.inactivity.enabled && (
                            <Note icon={Timer}>
                                {t('freeServers.notes.inactivity', {
                                    period: inactivityPeriod,
                                    store: String(options.inactivity.store_after_days),
                                })}
                            </Note>
                        )}
                        {options.notes.ads && <Note icon={Megaphone}>{t('freeServers.notes.ads')}</Note>}
                        <Note icon={ShieldAlert}>{t('freeServers.notes.rules')}</Note>
                    </ul>
                </section>
            </form>
        </div>
    );
}
