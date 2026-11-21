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

import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Download, Gift, PlayCircle, Save, Search, Settings2 } from 'lucide-react';
import { useTranslation } from '@/contexts/TranslationContext';
import { useSession } from '@/contexts/SessionContext';
import { useDateFormatOptions } from '@/contexts/PreferencesContext';
import { formatDateTimeInTz, formatRelativeTime } from '@/lib/dateUtils';
import { getApiErrorMessage } from '@/lib/api-errors';
import Permissions from '@/lib/permissions';
import { cn } from '@/lib/utils';
import { FREE_SERVER_STACKS, isFreeServerStack, type FreeServerStackKey } from '@/lib/free-servers';
import { Button } from '@/components/featherui/Button';
import { Input } from '@/components/featherui/Input';
import { DataTable } from '@/components/featherui/DataTable';
import { ListEmptyState } from '@/components/featherui/ListEmptyState';
import { ListPagination } from '@/components/featherui/ListPagination';
import { TableSkeleton } from '@/components/featherui/TableSkeleton';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Select } from '@/components/ui/select-native';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsTrigger } from '@/components/ui/tabs';
import { ScrollableTabsList } from '@/components/ui/scrollable-tabs-list';
import { StackIcon } from '@/components/free-servers/StackIcon';

interface Policy {
    enabled: boolean;
    memory: number;
    disk: number;
    cpu: number;
    swap: number;
    io: number;
    database_limit: number;
    backup_limit: number;
    allocation_limit: number;
    max_per_user: number;
    node_ids: number[];
    stacks: Partial<Record<FreeServerStackKey, number>>;
    inactivity_enabled: boolean;
    stop_after_days: number;
    store_after_days: number;
    show_ads_note: boolean;
}

interface NodeOption {
    id: number;
    name: string;
    location: string | null;
    memory: number;
    memory_used: number;
    disk: number;
    free_allocations: number;
    maintenance: boolean;
}

interface SpellOption {
    id: number;
    name: string;
    realm: string | null;
}

interface StackStatus {
    key: string;
    spell_id: number | null;
    bundled: boolean;
    problem: 'spell_missing' | 'variables_missing' | null;
}

interface SettingsPayload {
    policy: Policy;
    nodes: NodeOption[];
    spells: SpellOption[];
    stacks: StackStatus[];
}

type Stage = 'running' | 'stopped' | 'stored';

interface FreeServerRow {
    server_id: number;
    uuid_short: string;
    name: string;
    owner_username: string | null;
    stack: string;
    stage: 'stopped' | 'stored' | null;
    stage_at: string | null;
    last_active_at: string | null;
    idle_days: number;
    step: string | null;
    stop_at: string | null;
    store_at: string | null;
}

const STAGE_TONE: Record<Stage, string> = {
    running: 'text-green-500 bg-green-500/10 border-green-500/20',
    stopped: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
    stored: 'text-orange-500 bg-orange-500/10 border-orange-500/20',
};

/** PHP sends an empty map as []; the UI always works with an object. */
function normalizePolicy(policy: Policy): Policy {
    return { ...policy, stacks: Array.isArray(policy.stacks) ? {} : policy.stacks };
}

function Row({ id, label, hint, children }: { id?: string; label: string; hint?: string; children: React.ReactNode }) {
    return (
        <div className='flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4'>
            <label htmlFor={id} className='min-w-0 text-sm'>
                <span className='block font-medium'>{label}</span>
                {hint && <span className='text-muted-foreground block text-xs'>{hint}</span>}
            </label>
            <div className='flex shrink-0 items-center gap-2'>{children}</div>
        </div>
    );
}

function NumberInput({
    id,
    value,
    min,
    max,
    suffix,
    disabled,
    onChange,
}: {
    id: string;
    value: number;
    min: number;
    max: number;
    suffix: string;
    disabled?: boolean;
    onChange: (value: number) => void;
}) {
    return (
        <>
            <Input
                id={id}
                type='number'
                min={min}
                max={max}
                value={value}
                disabled={disabled}
                className='h-9 w-28'
                onChange={(e) => onChange(Number(e.target.value))}
            />
            <span className='text-muted-foreground w-12 text-xs'>{suffix}</span>
        </>
    );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
    return (
        <section className='space-y-1'>
            <h3 className='text-base font-semibold'>{title}</h3>
            {hint && <p className='text-muted-foreground text-xs'>{hint}</p>}
            <div className='divide-border/60 divide-y'>{children}</div>
        </section>
    );
}

function SettingsTab({ onSaved }: { onSaved: () => void }) {
    const { t } = useTranslation();
    const { hasPermission } = useSession();
    const canEdit = hasPermission(Permissions.ADMIN_SERVERS_CREATE);
    const canInstall = hasPermission(Permissions.ADMIN_SPELLS_CREATE);
    const [data, setData] = useState<SettingsPayload | null>(null);
    const [policy, setPolicy] = useState<Policy | null>(null);
    const [saving, setSaving] = useState(false);
    const [installing, setInstalling] = useState(false);

    const apply = useCallback((payload: SettingsPayload) => {
        setData(payload);
        setPolicy(normalizePolicy(payload.policy));
    }, []);

    const load = useCallback(async () => {
        try {
            const { data: res } = await axios.get('/api/admin/free-servers/settings');
            apply(res.data);
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'adminFreeServers.loadFailed'));
        }
    }, [apply, t]);

    useEffect(() => {
        void load();
    }, [load]);

    if (!data || !policy) return <TableSkeleton count={6} />;

    const set = <K extends keyof Policy>(key: K, value: Policy[K]) => setPolicy({ ...policy, [key]: value });
    const toggleNode = (id: number) =>
        set(
            'node_ids',
            policy.node_ids.includes(id) ? policy.node_ids.filter((n) => n !== id) : [...policy.node_ids, id],
        );
    const setStack = (key: FreeServerStackKey, spellId: number | null) => {
        const stacks = { ...policy.stacks };
        if (spellId) stacks[key] = spellId;
        else delete stacks[key];
        set('stacks', stacks);
    };

    const save = async () => {
        setSaving(true);
        try {
            const { data: res } = await axios.put('/api/admin/free-servers/settings', policy);
            apply(res.data);
            toast.success(t('adminFreeServers.saved'));
            onSaved();
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'adminFreeServers.saveFailed'));
        } finally {
            setSaving(false);
        }
    };

    const install = async () => {
        setInstalling(true);
        try {
            const { data: res } = await axios.post('/api/admin/free-servers/install-spells', {});
            const r = res.data as {
                imported: string[];
                reused: string[];
                failed: Record<string, string>;
                settings: SettingsPayload;
            };
            apply(r.settings);
            const failed = Object.keys(r.failed ?? {}).length;
            const message = t('adminFreeServers.installed', {
                imported: String(r.imported.length),
                reused: String(r.reused.length),
                failed: String(failed),
            });
            if (failed > 0) toast.warning(message);
            else toast.success(message);
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'adminFreeServers.installFailed'));
        } finally {
            setInstalling(false);
        }
    };

    const statusFor = (key: FreeServerStackKey) => data.stacks.find((s) => s.key === key);
    const spellsByRealm = data.spells.reduce<Record<string, SpellOption[]>>((acc, spell) => {
        const realm = spell.realm ?? '-';
        (acc[realm] ??= []).push(spell);
        return acc;
    }, {});

    return (
        <div className='max-w-3xl space-y-8'>
            <Section title={t('adminFreeServers.sections.general')}>
                <Row
                    id='fs-enabled'
                    label={t('adminFreeServers.fields.enabled')}
                    hint={t('adminFreeServers.hints.enabled')}
                >
                    <Switch
                        id='fs-enabled'
                        checked={policy.enabled}
                        onCheckedChange={(v) => set('enabled', v)}
                        disabled={!canEdit}
                    />
                </Row>
                <Row id='fs-max' label={t('adminFreeServers.fields.max_per_user')}>
                    <NumberInput
                        id='fs-max'
                        value={policy.max_per_user}
                        min={1}
                        max={50}
                        suffix=''
                        disabled={!canEdit}
                        onChange={(v) => set('max_per_user', v)}
                    />
                </Row>
                <Row
                    id='fs-ads'
                    label={t('adminFreeServers.fields.show_ads_note')}
                    hint={t('adminFreeServers.hints.ads')}
                >
                    <Switch
                        id='fs-ads'
                        checked={policy.show_ads_note}
                        onCheckedChange={(v) => set('show_ads_note', v)}
                        disabled={!canEdit}
                    />
                </Row>
            </Section>

            <Section title={t('adminFreeServers.sections.resources')} hint={t('adminFreeServers.hints.resources')}>
                {(
                    [
                        ['memory', 128, 65536, 'MB'],
                        ['disk', 128, 1048576, 'MB'],
                        ['cpu', 1, 1000, '%'],
                        ['swap', 0, 65536, 'MB'],
                        ['io', 10, 1000, ''],
                        ['database_limit', 0, 50, ''],
                        ['backup_limit', 0, 50, ''],
                        ['allocation_limit', 1, 50, ''],
                    ] as const
                ).map(([key, min, max, suffix]) => (
                    <Row key={key} id={`fs-${key}`} label={t(`adminFreeServers.fields.${key}`)}>
                        <NumberInput
                            id={`fs-${key}`}
                            value={policy[key]}
                            min={min}
                            max={max}
                            suffix={suffix}
                            disabled={!canEdit}
                            onChange={(v) => set(key, v)}
                        />
                    </Row>
                ))}
            </Section>

            <Section title={t('adminFreeServers.sections.nodes')} hint={t('adminFreeServers.hints.nodes')}>
                {data.nodes.length === 0 ? (
                    <p className='text-muted-foreground py-3 text-sm'>{t('adminFreeServers.noNodes')}</p>
                ) : (
                    data.nodes.map((node) => (
                        <label key={node.id} className='flex cursor-pointer items-center gap-3 py-3 text-sm'>
                            <input
                                type='checkbox'
                                className='accent-primary h-4 w-4'
                                checked={policy.node_ids.includes(node.id)}
                                disabled={!canEdit}
                                onChange={() => toggleNode(node.id)}
                            />
                            <span className='min-w-0 flex-1'>
                                <span className='block font-medium'>
                                    {node.name}
                                    {node.location ? (
                                        <span className='text-muted-foreground font-normal'> · {node.location}</span>
                                    ) : null}
                                </span>
                                <span className='text-muted-foreground block text-xs'>
                                    {t('adminFreeServers.nodeStats', {
                                        free: String(node.free_allocations),
                                        used: String(node.memory_used),
                                        total: String(node.memory),
                                    })}
                                </span>
                            </span>
                            {node.maintenance && (
                                <span className='rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-500'>
                                    {t('adminFreeServers.maintenance')}
                                </span>
                            )}
                        </label>
                    ))
                )}
            </Section>

            <Section title={t('adminFreeServers.sections.stacks')} hint={t('adminFreeServers.hints.stacks')}>
                {canInstall && (
                    <div className='py-3'>
                        <Button variant='outline' size='sm' onClick={() => void install()} loading={installing}>
                            {!installing && <Download className='mr-1.5 h-4 w-4' />}
                            {t('adminFreeServers.installSpells')}
                        </Button>
                        <p className='text-muted-foreground mt-1.5 text-xs'>{t('adminFreeServers.hints.install')}</p>
                    </div>
                )}
                {FREE_SERVER_STACKS.map(({ key }) => {
                    const status = statusFor(key);
                    return (
                        <div key={key} className='flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:gap-4'>
                            <div className='flex min-w-0 flex-1 items-center gap-3'>
                                <span className='border-border/70 bg-background/60 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border'>
                                    <StackIcon stack={key} className='h-5 w-5' />
                                </span>
                                <span className='min-w-0'>
                                    <span className='block text-sm font-medium'>
                                        {t(`freeServers.stacks.${key}.title`)}
                                    </span>
                                    {status?.problem && (
                                        <span className='block text-xs text-red-500'>
                                            {t(`adminFreeServers.problems.${status.problem}`)}
                                        </span>
                                    )}
                                </span>
                            </div>
                            <Select
                                aria-label={t(`freeServers.stacks.${key}.title`)}
                                value={policy.stacks[key] ? String(policy.stacks[key]) : ''}
                                disabled={!canEdit}
                                className='rounded-xl sm:w-72'
                                onChange={(e) => setStack(key, e.target.value ? Number(e.target.value) : null)}
                            >
                                <option value=''>{t('adminFreeServers.notOffered')}</option>
                                {Object.entries(spellsByRealm).map(([realm, spells]) => (
                                    <optgroup key={realm} label={realm}>
                                        {spells.map((spell) => (
                                            <option key={spell.id} value={spell.id}>
                                                {spell.name}
                                            </option>
                                        ))}
                                    </optgroup>
                                ))}
                            </Select>
                        </div>
                    );
                })}
            </Section>

            <Section title={t('adminFreeServers.sections.inactivity')} hint={t('adminFreeServers.hints.inactivity')}>
                <Row id='fs-inactivity' label={t('adminFreeServers.fields.inactivity_enabled')}>
                    <Switch
                        id='fs-inactivity'
                        checked={policy.inactivity_enabled}
                        onCheckedChange={(v) => set('inactivity_enabled', v)}
                        disabled={!canEdit}
                    />
                </Row>
                <Row id='fs-stop' label={t('adminFreeServers.fields.stop_after_days')}>
                    <NumberInput
                        id='fs-stop'
                        value={policy.stop_after_days}
                        min={1}
                        max={365}
                        suffix={t('adminFreeServers.daysSuffix')}
                        disabled={!canEdit || !policy.inactivity_enabled}
                        onChange={(v) => set('stop_after_days', v)}
                    />
                </Row>
                <Row
                    id='fs-store'
                    label={t('adminFreeServers.fields.store_after_days')}
                    hint={t('adminFreeServers.hints.store')}
                >
                    <NumberInput
                        id='fs-store'
                        value={policy.store_after_days}
                        min={2}
                        max={3650}
                        suffix={t('adminFreeServers.daysSuffix')}
                        disabled={!canEdit || !policy.inactivity_enabled}
                        onChange={(v) => set('store_after_days', v)}
                    />
                </Row>
            </Section>

            {canEdit && (
                <Button onClick={() => void save()} loading={saving}>
                    {!saving && <Save className='mr-1.5 h-4 w-4' />}
                    {t('common.save')}
                </Button>
            )}
        </div>
    );
}

function ServersTab({ refreshKey }: { refreshKey: number }) {
    const { t } = useTranslation();
    const dateOpts = useDateFormatOptions();
    const { hasPermission } = useSession();
    const canRun = hasPermission(Permissions.ADMIN_SERVERS_EDIT);
    const [rows, setRows] = useState<FreeServerRow[] | null>(null);
    const [counts, setCounts] = useState<Record<Stage, number>>({ running: 0, stopped: 0, stored: 0 });
    const [stage, setStage] = useState<'' | Stage>('');
    const [search, setSearch] = useState('');
    const [query, setQuery] = useState('');
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [running, setRunning] = useState(false);

    useEffect(() => {
        const timer = setTimeout(() => {
            setQuery(search.trim());
            setPage(1);
        }, 300);
        return () => clearTimeout(timer);
    }, [search]);

    const load = useCallback(async () => {
        try {
            const { data } = await axios.get('/api/admin/free-servers/servers', {
                params: { page, limit: 20, stage: stage || undefined, search: query || undefined },
            });
            setRows(data.data.items);
            setCounts({ running: 0, stopped: 0, stored: 0, ...data.data.counts });
            setTotalPages(data.data.pagination.total_pages);
        } catch (error) {
            setRows([]);
            toast.error(getApiErrorMessage(error, t, 'adminFreeServers.loadFailed'));
        }
    }, [page, stage, query, t]);

    useEffect(() => {
        void load();
    }, [load, refreshKey]);

    const run = async () => {
        setRunning(true);
        try {
            const { data } = await axios.post('/api/admin/free-servers/run', {});
            const r = data.data as { applied: Record<string, number>; failed: number };
            const applied = Object.values(r.applied ?? {}).reduce((a, b) => a + b, 0);
            toast.success(t('adminFreeServers.ran', { applied: String(applied), failed: String(r.failed) }));
            void load();
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'adminFreeServers.runFailed'));
        } finally {
            setRunning(false);
            setConfirmOpen(false);
        }
    };

    const stageOf = (row: FreeServerRow): Stage => row.stage ?? 'running';
    const next = (row: FreeServerRow): string => {
        if (row.step) return t(`adminFreeServers.steps.${row.step}`);
        if (row.stage === null && row.stop_at) {
            return t('adminFreeServers.stopsAt', { time: formatDateTimeInTz(row.stop_at, dateOpts) });
        }
        if (row.stage === 'stopped' && row.store_at) {
            return t('adminFreeServers.storesAt', { time: formatDateTimeInTz(row.store_at, dateOpts) });
        }
        return '-';
    };
    const badge = (row: FreeServerRow) => (
        <span className={cn('rounded-md border px-2 py-0.5 text-xs whitespace-nowrap', STAGE_TONE[stageOf(row)])}>
            {t(`adminFreeServers.stages.${stageOf(row)}`)}
        </span>
    );
    const stackCell = (row: FreeServerRow) => (
        <span className='flex items-center gap-2'>
            {isFreeServerStack(row.stack) && <StackIcon stack={row.stack} className='h-4 w-4' />}
            {isFreeServerStack(row.stack) ? t(`freeServers.stacks.${row.stack}.title`) : row.stack}
        </span>
    );

    return (
        <div className='space-y-4'>
            <div className='flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between'>
                <div className='flex flex-wrap gap-2'>
                    {(Object.keys(STAGE_TONE) as Stage[]).map((s) => (
                        <span key={s} className={cn('rounded-md border px-2 py-0.5 text-xs', STAGE_TONE[s])}>
                            {t(`adminFreeServers.stages.${s}`)} · {counts[s] ?? 0}
                        </span>
                    ))}
                </div>
                <div className='flex flex-wrap items-center gap-2'>
                    <label className='relative flex items-center'>
                        <Search className='text-muted-foreground pointer-events-none absolute left-3 h-4 w-4' />
                        <Input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder={t('adminFreeServers.search')}
                            aria-label={t('adminFreeServers.search')}
                            className='h-9 w-56 pl-9'
                        />
                    </label>
                    <Select
                        aria-label={t('adminFreeServers.stageFilter')}
                        value={stage}
                        className='h-9 rounded-xl'
                        onChange={(e) => {
                            setStage(e.target.value as '' | Stage);
                            setPage(1);
                        }}
                    >
                        <option value=''>{t('adminFreeServers.allStages')}</option>
                        {(Object.keys(STAGE_TONE) as Stage[]).map((s) => (
                            <option key={s} value={s}>
                                {t(`adminFreeServers.stages.${s}`)}
                            </option>
                        ))}
                    </Select>
                    {canRun && (
                        <Button size='sm' onClick={() => setConfirmOpen(true)}>
                            <PlayCircle className='mr-1.5 h-4 w-4' />
                            {t('adminFreeServers.runNow')}
                        </Button>
                    )}
                </div>
            </div>

            {rows === null ? (
                <TableSkeleton count={4} />
            ) : rows.length === 0 ? (
                <ListEmptyState
                    icon={Gift}
                    title={t('adminFreeServers.emptyTitle')}
                    description={t('adminFreeServers.emptyDescription')}
                />
            ) : (
                <DataTable
                    rows={rows}
                    rowKey={(row) => row.server_id}
                    columns={[
                        {
                            key: 'server',
                            header: t('adminFreeServers.columns.server'),
                            cell: (row) => (
                                <div className='min-w-0'>
                                    <a
                                        href={`/admin/servers/${row.server_id}/edit`}
                                        className='font-medium underline-offset-4 hover:underline'
                                    >
                                        {row.name}
                                    </a>
                                    <p className='text-muted-foreground text-xs'>{row.owner_username ?? '-'}</p>
                                </div>
                            ),
                        },
                        { key: 'stack', header: t('adminFreeServers.columns.stack'), cell: stackCell },
                        {
                            key: 'login',
                            header: t('adminFreeServers.columns.lastLogin'),
                            className: 'whitespace-nowrap',
                            cell: (row) => (
                                <div>
                                    <p>{t('adminFreeServers.idleDays', { count: String(row.idle_days) })}</p>
                                    {row.last_active_at && (
                                        <p className='text-muted-foreground text-xs'>
                                            {formatRelativeTime(row.last_active_at, dateOpts)}
                                        </p>
                                    )}
                                </div>
                            ),
                        },
                        {
                            key: 'stage',
                            header: t('adminFreeServers.columns.stage'),
                            cell: (row) => (
                                <div className='space-y-1'>
                                    {badge(row)}
                                    <p className='text-muted-foreground text-xs'>{next(row)}</p>
                                </div>
                            ),
                        },
                    ]}
                    mobileCard={(row) => (
                        <div className='min-w-0 space-y-1.5'>
                            <div className='flex items-center justify-between gap-2'>
                                <span className='truncate font-medium'>{row.name}</span>
                                {badge(row)}
                            </div>
                            <p className='text-muted-foreground text-xs'>
                                {row.owner_username ?? '-'} ·{' '}
                                {t('adminFreeServers.idleDays', { count: String(row.idle_days) })}
                            </p>
                            <div className='text-xs'>{stackCell(row)}</div>
                            <p className='text-muted-foreground text-xs'>{next(row)}</p>
                        </div>
                    )}
                />
            )}
            {totalPages > 1 && <ListPagination page={page} totalPages={totalPages} onPageChange={setPage} />}

            <ConfirmDialog
                open={confirmOpen}
                onOpenChange={setConfirmOpen}
                title={t('adminFreeServers.confirmRunTitle')}
                description={t('adminFreeServers.confirmRunDescription')}
                confirmLabel={t('adminFreeServers.runNow')}
                cancelLabel={t('common.cancel')}
                onConfirm={run}
                loading={running}
            />
        </div>
    );
}

/** Admin > Free servers: the free tier policy, the bundled spells and the list of free servers. */
export function FreeServersPanel() {
    const { t } = useTranslation();
    const [tab, setTab] = useState('settings');
    const [refreshKey, setRefreshKey] = useState(0);
    const changed = useCallback(() => setRefreshKey((k) => k + 1), []);

    return (
        <section className='fp-surface rounded-2xl border p-4 sm:p-5'>
            <Tabs value={tab} onValueChange={setTab}>
                <ScrollableTabsList wrapperClassName='mb-4 max-w-full'>
                    <TabsTrigger value='settings'>
                        <Settings2 className='mr-1.5 h-3.5 w-3.5' />
                        {t('adminFreeServers.tabs.settings')}
                    </TabsTrigger>
                    <TabsTrigger value='servers'>
                        <Gift className='mr-1.5 h-3.5 w-3.5' />
                        {t('adminFreeServers.tabs.servers')}
                    </TabsTrigger>
                </ScrollableTabsList>
                <TabsContent value='settings'>
                    <SettingsTab onSaved={changed} />
                </TabsContent>
                <TabsContent value='servers'>
                    <ServersTab refreshKey={refreshKey} />
                </TabsContent>
            </Tabs>
        </section>
    );
}
