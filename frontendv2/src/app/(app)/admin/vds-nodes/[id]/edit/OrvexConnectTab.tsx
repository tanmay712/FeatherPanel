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

import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
    AlertTriangle,
    CheckCircle2,
    Copy,
    Cpu,
    Globe,
    HardDrive,
    Layers,
    Link2,
    Loader2,
    RefreshCw,
    Server,
    ShieldCheck,
    Terminal,
    Zap,
} from 'lucide-react';
import { PageCard } from '@/components/featherui/PageCard';
import { Button } from '@/components/featherui/Button';
import { Input } from '@/components/featherui/Input';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/contexts/TranslationContext';
import { copyToClipboard } from '@/lib/utils';
import { getApiErrorMessage } from '@/lib/api-errors';

export interface OrvexAgentInfo {
    node_name?: string;
    address?: string;
    port?: number;
    public_ipv4?: string;
    tls_fingerprint?: string;
    kvm?: boolean;
    nat?: { subnet: string; gateway: string; ssh_port_base: number; port_range_base: number; port_range_size: number };
    storage_pool?: string;
    templates?: number;
    host?: { hostname?: string; os?: string; kernel?: string; cpu?: string; cpus?: number; memory_mb?: number };
    registered_from?: string;
    synced_at?: string;
}

export interface OrvexState {
    node_type: 'orvex';
    registered: boolean;
    registered_at: string | null;
    token: string | null;
    expires_at: string | null;
    expires_in: number | null;
    installer: { repo: string; branch: string; default_branch: string; url: string };
    agent_version: string | null;
    agent: OrvexAgentInfo | null;
    endpoint: string | null;
}

interface OrvexConnectTabProps {
    nodeId: string;
    /** Called when the node connects (or re-pairs) so the page can reload the node. */
    onConnected: () => void;
}

const PANEL_URL_PATTERN = /^https?:\/\/[A-Za-z0-9.-]+(?::\d{1,5})?(?:\/[A-Za-z0-9._~/-]*)?$/;
const LOCAL_HOST_PATTERN = /^https?:\/\/(localhost|127\.\d+\.\d+\.\d+|\[::1\]|0\.0\.0\.0)(?::\d+)?(\/|$)/i;

function maskToken(command: string, token: string): string {
    return command.split(token).join(token.replace(/_[A-Za-z0-9]{48}$/, '_' + '\u2022'.repeat(12)));
}

function CommandBox({ label, command, token }: { label: string; command: string; token: string }) {
    const { t } = useTranslation();

    return (
        <div className='overflow-hidden rounded-xl border border-[var(--fp-surface-border)] bg-zinc-950'>
            <div className='flex flex-wrap items-center justify-between gap-2 border-b border-[var(--fp-surface-border)] bg-zinc-900 px-3 py-2'>
                <p className='text-[11px] text-zinc-400'>{label}</p>
                <Button
                    type='button'
                    variant='plain'
                    size='sm'
                    className='border border-[var(--fp-surface-border)] bg-zinc-800 text-zinc-100 hover:bg-zinc-700 hover:text-white'
                    onClick={() => copyToClipboard(command, t)}
                >
                    <Copy className='mr-2 h-4 w-4 shrink-0' />
                    {t('admin.vdsNodes.orvex.copy_command')}
                </Button>
            </div>
            <pre className='overflow-x-auto p-4 font-mono text-xs leading-relaxed break-all whitespace-pre-wrap text-zinc-300'>
                {maskToken(command, token)}
            </pre>
        </div>
    );
}

function DetailRow({ icon: Icon, label, value }: { icon: typeof Server; label: string; value: React.ReactNode }) {
    return (
        <div className='flex items-start gap-3 py-2.5'>
            <Icon className='text-muted-foreground mt-0.5 h-4 w-4 shrink-0' />
            <div className='min-w-0 flex-1'>
                <div className='text-muted-foreground text-xs'>{label}</div>
                <div className='text-sm font-medium break-words'>{value}</div>
            </div>
        </div>
    );
}

export function OrvexConnectTab({ nodeId, onConnected }: OrvexConnectTabProps) {
    const { t } = useTranslation();
    const [state, setState] = useState<OrvexState | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [panelUrl, setPanelUrl] = useState(() => (typeof window === 'undefined' ? '' : window.location.origin));
    const [busy, setBusy] = useState<'token' | 'sync' | null>(null);
    const lastRegisteredAt = useRef<string | null | undefined>(undefined);

    const load = useCallback(async () => {
        try {
            const { data } = await axios.get(`/api/admin/vm-nodes/${nodeId}/orvex`);
            setState(data.data?.orvex ?? null);
            setLoadError(null);
        } catch (error) {
            setLoadError(getApiErrorMessage(error, t, 'admin.vdsNodes.orvex.load_failed'));
        }
    }, [nodeId, t]);

    useEffect(() => {
        void load();
    }, [load]);

    // While an install command is waiting to be used, check every few seconds.
    const waiting = state !== null && (!state.registered || state.token !== null);
    useEffect(() => {
        if (!waiting) return;
        const timer = setInterval(() => void load(), 5000);
        return () => clearInterval(timer);
    }, [waiting, load]);

    // The node connected (or re-paired) since the page was opened.
    useEffect(() => {
        if (!state) return;
        const previous = lastRegisteredAt.current;
        if (previous !== undefined && state.registered_at && state.registered_at !== previous) {
            toast.success(t('admin.vdsNodes.orvex.connected_toast'));
            onConnected();
        }
        lastRegisteredAt.current = state.registered_at;
    }, [state, onConnected, t]);

    const newToken = async () => {
        setBusy('token');
        try {
            const { data } = await axios.post(`/api/admin/vm-nodes/${nodeId}/orvex/token`);
            setState(data.data?.orvex ?? null);
            toast.success(t('admin.vdsNodes.orvex.new_token_done'));
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'admin.vdsNodes.orvex.load_failed'));
        } finally {
            setBusy(null);
        }
    };

    const sync = async () => {
        setBusy('sync');
        try {
            const { data } = await axios.post(`/api/admin/vm-nodes/${nodeId}/orvex/sync`);
            setState(data.data?.orvex ?? null);
            toast.success(t('admin.vdsNodes.orvex.sync_done', { count: String(data.data?.templates_imported ?? 0) }));
        } catch (error) {
            toast.error(getApiErrorMessage(error, t, 'admin.vdsNodes.orvex.sync_failed'));
        } finally {
            setBusy(null);
        }
    };

    if (loadError) {
        return (
            <PageCard title={t('admin.vdsNodes.orvex.title_pending')} icon={Zap}>
                <div className='flex flex-wrap items-center gap-3'>
                    <AlertTriangle className='h-5 w-5 text-red-500' />
                    <span className='text-sm'>{loadError}</span>
                    <Button size='sm' variant='outline' onClick={() => void load()}>
                        <RefreshCw className='mr-2 h-4 w-4' />
                        {t('admin.vdsNodes.orvex.retry')}
                    </Button>
                </div>
            </PageCard>
        );
    }

    if (!state) {
        return (
            <div className='flex min-h-[200px] items-center justify-center'>
                <Loader2 className='text-primary h-6 w-6 animate-spin' />
            </div>
        );
    }

    const url = panelUrl.trim().replace(/\/+$/, '');
    const urlValid = PANEL_URL_PATTERN.test(url);
    const branchFlag =
        state.installer.branch !== state.installer.default_branch ? ` --branch ${state.installer.branch}` : '';
    const token = state.token;
    const installCommand = token
        ? `curl -fsSL ${state.installer.url} | sudo bash -s -- vps-node --panel ${url} --token ${token}${branchFlag} -y`
        : '';
    const registerCommand = token ? `orvex-node register --panel ${url} --token ${token}` : '';
    const hours = state.expires_in !== null ? Math.floor(state.expires_in / 3600) : 0;
    const agent = state.agent ?? {};

    const commandSection = token ? (
        <div className='space-y-5'>
            <div className='space-y-2'>
                <Label className='text-sm font-semibold'>{t('admin.vdsNodes.orvex.panel_url_label')}</Label>
                <Input value={panelUrl} onChange={(e) => setPanelUrl(e.target.value)} error={!urlValid} />
                <p className='text-muted-foreground text-xs'>
                    {urlValid ? t('admin.vdsNodes.orvex.panel_url_help') : t('admin.vdsNodes.orvex.panel_url_invalid')}
                </p>
                {urlValid && url.startsWith('http://') && !LOCAL_HOST_PATTERN.test(url) && (
                    <p className='flex items-start gap-2 text-xs text-orange-500'>
                        <AlertTriangle className='mt-0.5 h-3.5 w-3.5 shrink-0' />
                        {t('admin.vdsNodes.orvex.warn_http')}
                    </p>
                )}
                {LOCAL_HOST_PATTERN.test(url) && (
                    <p className='flex items-start gap-2 text-xs text-orange-500'>
                        <AlertTriangle className='mt-0.5 h-3.5 w-3.5 shrink-0' />
                        {t('admin.vdsNodes.orvex.warn_local')}
                    </p>
                )}
            </div>

            {urlValid && (
                <>
                    {!state.registered && (
                        <CommandBox
                            label={t('admin.vdsNodes.orvex.step_install')}
                            command={installCommand}
                            token={token}
                        />
                    )}
                    <CommandBox
                        label={
                            state.registered
                                ? t('admin.vdsNodes.orvex.repair_command')
                                : t('admin.vdsNodes.orvex.step_register')
                        }
                        command={registerCommand}
                        token={token}
                    />
                    {state.registered && (
                        <CommandBox
                            label={t('admin.vdsNodes.orvex.step_install')}
                            command={installCommand}
                            token={token}
                        />
                    )}
                </>
            )}

            <div className='flex flex-wrap items-center justify-between gap-3'>
                <p className='text-muted-foreground text-xs'>
                    {t('admin.vdsNodes.orvex.token_hidden')}{' '}
                    {hours >= 1
                        ? t('admin.vdsNodes.orvex.expires', { hours: String(hours) })
                        : t('admin.vdsNodes.orvex.expires_soon')}
                </p>
                <Button size='sm' variant='outline' onClick={() => void newToken()} loading={busy === 'token'}>
                    <RefreshCw className='mr-2 h-4 w-4' />
                    {t('admin.vdsNodes.orvex.new_token')}
                </Button>
            </div>

            <div className='bg-primary/5 border-primary/20 flex items-start gap-3 rounded-xl border p-4'>
                <Loader2 className='text-primary mt-0.5 h-4 w-4 shrink-0 animate-spin' />
                <div className='space-y-1'>
                    <p className='text-sm font-semibold'>{t('admin.vdsNodes.orvex.waiting')}</p>
                    <p className='text-muted-foreground text-xs leading-relaxed'>
                        {t('admin.vdsNodes.orvex.waiting_help')}
                    </p>
                </div>
            </div>
        </div>
    ) : null;

    if (!state.registered) {
        return (
            <PageCard
                title={t('admin.vdsNodes.orvex.title_pending')}
                description={t('admin.vdsNodes.orvex.desc_pending')}
                icon={Terminal}
            >
                {commandSection}
            </PageCard>
        );
    }

    return (
        <div className='space-y-6'>
            <PageCard
                title={t('admin.vdsNodes.orvex.title_connected')}
                description={
                    state.registered_at
                        ? t('admin.vdsNodes.orvex.connected_since', { date: state.registered_at })
                        : undefined
                }
                icon={CheckCircle2}
                action={
                    <div className='flex flex-wrap gap-2'>
                        <Button size='sm' variant='outline' onClick={() => void sync()} loading={busy === 'sync'}>
                            <RefreshCw className='mr-2 h-4 w-4' />
                            {t('admin.vdsNodes.orvex.sync')}
                        </Button>
                        {!token && (
                            <Button
                                size='sm'
                                variant='outline'
                                onClick={() => void newToken()}
                                loading={busy === 'token'}
                            >
                                <Link2 className='mr-2 h-4 w-4' />
                                {t('admin.vdsNodes.orvex.repair')}
                            </Button>
                        )}
                    </div>
                }
            >
                <div className='divide-border/50 grid grid-cols-1 gap-x-8 md:grid-cols-2'>
                    <DetailRow
                        icon={Link2}
                        label={t('admin.vdsNodes.orvex.endpoint')}
                        value={<span className='font-mono'>{state.endpoint}</span>}
                    />
                    <DetailRow
                        icon={Zap}
                        label={t('admin.vdsNodes.orvex.agent_version')}
                        value={state.agent_version ?? t('common.nA')}
                    />
                    <DetailRow
                        icon={Cpu}
                        label={t('admin.vdsNodes.orvex.kvm')}
                        value={
                            agent.kvm ? (
                                <span className='text-green-500'>{t('admin.vdsNodes.orvex.kvm_yes')}</span>
                            ) : (
                                <span className='text-orange-500'>{t('admin.vdsNodes.orvex.kvm_no')}</span>
                            )
                        }
                    />
                    <DetailRow
                        icon={Globe}
                        label={t('admin.vdsNodes.orvex.public_ip')}
                        value={<span className='font-mono'>{agent.public_ipv4 ?? t('common.nA')}</span>}
                    />
                    <DetailRow
                        icon={Globe}
                        label={t('admin.vdsNodes.orvex.shared_ip')}
                        value={
                            agent.nat ? (
                                <span className='font-mono'>
                                    {t('admin.vdsNodes.orvex.shared_ip_value', {
                                        subnet: agent.nat.subnet,
                                        gateway: agent.nat.gateway,
                                        ssh: String(agent.nat.ssh_port_base),
                                    })}
                                </span>
                            ) : (
                                t('common.nA')
                            )
                        }
                    />
                    <DetailRow
                        icon={Layers}
                        label={t('admin.vdsNodes.orvex.templates')}
                        value={String(agent.templates ?? 0)}
                    />
                    <DetailRow
                        icon={Server}
                        label={t('admin.vdsNodes.orvex.host')}
                        value={
                            [
                                agent.host?.hostname,
                                agent.host?.os,
                                agent.host?.cpus
                                    ? t('admin.vdsNodes.orvex.cpus', { count: String(agent.host.cpus) })
                                    : null,
                                agent.host?.memory_mb
                                    ? t('admin.vdsNodes.orvex.memory', {
                                          gb: String(Math.round((agent.host.memory_mb / 1024) * 10) / 10),
                                      })
                                    : null,
                            ]
                                .filter(Boolean)
                                .join(' \u00b7 ') || t('common.nA')
                        }
                    />
                    <DetailRow
                        icon={HardDrive}
                        label={t('admin.vdsNodes.orvex.storage')}
                        value={<span className='font-mono'>{agent.storage_pool ?? t('common.nA')}</span>}
                    />
                    <DetailRow
                        icon={ShieldCheck}
                        label={t('admin.vdsNodes.orvex.fingerprint')}
                        value={
                            <span className='font-mono text-xs break-all'>
                                {agent.tls_fingerprint ?? t('common.nA')}
                            </span>
                        }
                    />
                </div>
            </PageCard>

            {token && (
                <PageCard
                    title={t('admin.vdsNodes.orvex.repair')}
                    description={t('admin.vdsNodes.orvex.repair_help')}
                    icon={Link2}
                >
                    {commandSection}
                </PageCard>
            )}
        </div>
    );
}
