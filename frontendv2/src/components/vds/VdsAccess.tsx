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

import * as React from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowRightLeft, Check, Copy, Eye, EyeOff, KeyRound, Terminal, Wand2 } from 'lucide-react';
import { useVmTranslation } from '@/hooks/useVmProduct';
import { Button } from '@/components/featherui/Button';
import { Input } from '@/components/featherui/Input';
import { PageCard } from '@/components/featherui/PageCard';
import { Dialog, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { isReauthCancelled, useVdsReauth } from '@/components/vds/VdsReauth';
import { getApiErrorMessage, getApiErrorMessageFromPayload } from '@/lib/api-errors';
import { cn, copyToClipboard } from '@/lib/utils';

/** Connection details reported by OrveX VPS Nodes in `status.orvex`. */
export interface VdsOrvexStatus {
    network_mode?: 'nat' | 'dedicated' | null;
    nic_mode?: 'nat' | 'routed' | 'bridged' | null;
    ssh?: { host: string; port: number; user?: string } | null;
    forwards?: { protocol: string; public_port: string; private_port: string; purpose: 'ssh' | 'services' | string }[];
    public_ipv4?: string | null;
    private_ipv4?: string | null;
    type?: 'kvm' | 'lxc';
    vnc?: boolean;
    pending_changes?: boolean;
}

export function sshCommand(user: string, host: string, port: number): string {
    return port && port !== 22 ? `ssh -p ${port} ${user}@${host}` : `ssh ${user}@${host}`;
}

function CopyButton({ value, label }: { value: string; label: string }) {
    const { t } = useVmTranslation();
    const [copied, setCopied] = React.useState(false);
    return (
        <Button
            variant='outline'
            size='icon'
            className='h-9 w-9 shrink-0'
            aria-label={label}
            title={label}
            onClick={async () => {
                await copyToClipboard(value, t);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
            }}
        >
            {copied ? <Check className='h-4 w-4 text-emerald-500' /> : <Copy className='h-4 w-4' />}
        </Button>
    );
}

function Row({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
    return (
        <div className='border-border/40 flex items-center justify-between gap-3 border-b py-2 last:border-b-0'>
            <dt className='text-muted-foreground shrink-0 text-xs font-medium'>{label}</dt>
            <dd className={cn('min-w-0 truncate text-sm font-medium', mono && 'font-mono tabular-nums')}>{value}</dd>
        </div>
    );
}

interface SshAccessCardProps {
    ip: string | null | undefined;
    username: string | null | undefined;
    orvex?: VdsOrvexStatus | null;
    className?: string;
    /** Header action, e.g. the "Change password" button. */
    action?: React.ReactNode;
}

/** "Connect over SSH" card: host, port, user, ready-to-copy command and NAT port forwards. */
export function VdsSshAccessCard({ ip, username, orvex, className, action }: SshAccessCardProps) {
    const { t } = useVmTranslation();
    const user = orvex?.ssh?.user || username || 'root';
    const host = orvex?.ssh?.host || ip || '';
    const port = orvex?.ssh?.port || 22;
    const isNat = orvex?.network_mode === 'nat';
    const services = (orvex?.forwards ?? []).filter((f) => f.purpose !== 'ssh');

    return (
        <PageCard
            title={t('vds.access.ssh_title')}
            description={t('vds.access.ssh_description')}
            icon={Terminal}
            className={className}
            action={action}
        >
            {host ? (
                <>
                    <div className='flex items-center gap-2'>
                        <div className='border-border/50 bg-muted/20 flex h-10 min-w-0 flex-1 items-center rounded-lg border px-3'>
                            <code className='truncate font-mono text-sm'>{sshCommand(user, host, port)}</code>
                        </div>
                        <CopyButton value={sshCommand(user, host, port)} label={t('common.copy')} />
                    </div>
                    <dl className='grid grid-cols-1 gap-x-6 sm:grid-cols-2'>
                        <Row label={t('vds.access.host')} value={host} />
                        <Row label={t('vds.access.port')} value={String(port)} />
                        <Row label={t('vds.access.username')} value={user} />
                        <Row
                            label={t('vds.access.network_type')}
                            value={isNat ? t('vds.access.shared_ipv4') : t('vds.access.dedicated_ipv4')}
                            mono={false}
                        />
                        {isNat && orvex?.private_ipv4 ? (
                            <Row label={t('vds.access.private_ip')} value={orvex.private_ipv4} />
                        ) : null}
                    </dl>
                    {isNat && services.length > 0 ? (
                        <div className='border-border/40 bg-muted/30 space-y-1 rounded-lg border px-3 py-2'>
                            <p className='flex items-center gap-1.5 text-xs font-medium'>
                                <ArrowRightLeft className='text-primary h-3.5 w-3.5' />
                                {t('vds.access.forwards_title')}
                            </p>
                            {services.map((f) => (
                                <p key={`${f.protocol}-${f.public_port}`} className='text-muted-foreground text-xs'>
                                    <span className='text-foreground font-mono'>
                                        {host}:{f.public_port}
                                    </span>{' '}
                                    ({f.protocol.toUpperCase()}) {t('vds.access.forward_same_ports')}
                                </p>
                            ))}
                        </div>
                    ) : null}
                    <p className='text-muted-foreground text-xs'>{t('vds.access.password_hint')}</p>
                </>
            ) : (
                <p className='text-muted-foreground text-sm'>{t('vds.access.no_ip')}</p>
            )}
        </PageCard>
    );
}

/** Port forwards of a shared-IPv4 (NAT) server, for the network page. */
export function VdsNatForwardsCard({ vmId }: { vmId: number }) {
    const { t } = useVmTranslation();
    const [orvex, setOrvex] = React.useState<VdsOrvexStatus | null>(null);

    React.useEffect(() => {
        let cancelled = false;
        axios
            .get(`/api/user/vm-instances/${vmId}/status`)
            .then(({ data }) => {
                if (!cancelled && data?.success) setOrvex((data.data?.status?.orvex as VdsOrvexStatus) ?? null);
            })
            .catch(() => undefined);
        return () => {
            cancelled = true;
        };
    }, [vmId]);

    if (!orvex || orvex.network_mode !== 'nat' || !orvex.forwards?.length) return null;
    const publicIp = orvex.public_ipv4 ?? orvex.ssh?.host ?? '';

    return (
        <PageCard
            title={t('vds.access.forwards_title')}
            description={t('vds.access.forwards_description', { ip: publicIp })}
            icon={ArrowRightLeft}
        >
            <div className='overflow-x-auto'>
                <table className='w-full text-sm'>
                    <thead>
                        <tr className='text-muted-foreground border-border/40 border-b text-left text-xs'>
                            <th className='py-2 pr-4 font-medium'>{t('vds.access.public_endpoint')}</th>
                            <th className='py-2 pr-4 font-medium'>{t('vds.access.protocol')}</th>
                            <th className='py-2 pr-4 font-medium'>{t('vds.access.private_endpoint')}</th>
                            <th className='py-2 font-medium'>{t('vds.access.purpose')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orvex.forwards.map((f) => (
                            <tr
                                key={`${f.protocol}-${f.public_port}`}
                                className='border-border/40 border-b last:border-b-0'
                            >
                                <td className='py-2 pr-4 font-mono'>
                                    {publicIp}:{f.public_port}
                                </td>
                                <td className='py-2 pr-4 font-mono text-xs'>{f.protocol.toUpperCase()}</td>
                                <td className='py-2 pr-4 font-mono'>
                                    {orvex.private_ipv4}:{f.private_port}
                                </td>
                                <td className='py-2'>
                                    {f.purpose === 'ssh'
                                        ? t('vds.access.forward_ssh')
                                        : t('vds.access.forward_services')}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <p className='text-muted-foreground text-xs'>{t('vds.access.forward_note')}</p>
        </PageCard>
    );
}

function generatePassword(length = 16): string {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#%^*-_+=';
    const bytes = new Uint32Array(length);
    window.crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}

interface ChangePasswordDialogProps {
    vmId: number;
    username: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onChanged?: () => void;
}

/** Sets a new login password (root for containers, the cloud-init user for KVM). */
export function VdsChangePasswordDialog({ vmId, username, open, onOpenChange, onChanged }: ChangePasswordDialogProps) {
    const { t } = useVmTranslation();
    const withReauth = useVdsReauth();
    const [password, setPassword] = React.useState('');
    const [confirm, setConfirm] = React.useState('');
    const [show, setShow] = React.useState(false);
    const [saving, setSaving] = React.useState(false);

    React.useEffect(() => {
        if (open) {
            setPassword('');
            setConfirm('');
            setShow(false);
        }
    }, [open]);

    const tooShort = password.length > 0 && password.length < 8;
    const mismatch = confirm.length > 0 && confirm !== password;
    const canSubmit = password.length >= 8 && password.length <= 128 && password === confirm && !saving;

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!canSubmit) return;
        setSaving(true);
        try {
            const { data } = await withReauth((headers) =>
                axios.post(`/api/user/vm-instances/${vmId}/password`, { password }, { headers }),
            );
            if (!data?.success) {
                toast.error(getApiErrorMessageFromPayload(data, t, 'vds.access.change_failed'));
                return;
            }
            toast.success(
                data.data?.applied === 'immediate' ? t('vds.access.changed_now') : t('vds.access.changed_next_boot'),
            );
            onOpenChange(false);
            onChanged?.();
        } catch (err) {
            if (!isReauthCancelled(err)) toast.error(getApiErrorMessage(err, t, 'vds.access.change_failed'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <form onSubmit={submit} className='space-y-4'>
                <DialogHeader>
                    <DialogTitle className='flex items-center gap-2'>
                        <KeyRound className='text-primary h-4 w-4' />
                        {t('vds.access.change_password_title')}
                    </DialogTitle>
                    <DialogDescription>
                        {t('vds.access.change_password_description', { user: username })}
                    </DialogDescription>
                </DialogHeader>
                <div className='space-y-2'>
                    <label className='text-sm font-medium' htmlFor='vds-new-password'>
                        {t('vds.access.new_password')}
                    </label>
                    <div className='flex items-center gap-2'>
                        <Input
                            id='vds-new-password'
                            type={show ? 'text' : 'password'}
                            autoComplete='new-password'
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            maxLength={128}
                            className='font-mono'
                        />
                        <Button
                            type='button'
                            variant='outline'
                            size='icon'
                            className='shrink-0'
                            onClick={() => setShow((v) => !v)}
                            aria-label={show ? t('common.hide') : t('common.show')}
                        >
                            {show ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
                        </Button>
                        <Button
                            type='button'
                            variant='outline'
                            size='icon'
                            className='shrink-0'
                            title={t('vds.access.generate')}
                            aria-label={t('vds.access.generate')}
                            onClick={() => {
                                const generated = generatePassword();
                                setPassword(generated);
                                setConfirm(generated);
                                setShow(true);
                            }}
                        >
                            <Wand2 className='h-4 w-4' />
                        </Button>
                    </div>
                    {tooShort ? <p className='text-xs text-red-500'>{t('vds.access.password_too_short')}</p> : null}
                </div>
                <div className='space-y-2'>
                    <label className='text-sm font-medium' htmlFor='vds-confirm-password'>
                        {t('vds.access.confirm_password')}
                    </label>
                    <Input
                        id='vds-confirm-password'
                        type={show ? 'text' : 'password'}
                        autoComplete='new-password'
                        value={confirm}
                        onChange={(e) => setConfirm(e.target.value)}
                        maxLength={128}
                        className='font-mono'
                    />
                    {mismatch ? <p className='text-xs text-red-500'>{t('vds.access.password_mismatch')}</p> : null}
                </div>
                <DialogFooter>
                    <Button type='button' variant='outline' onClick={() => onOpenChange(false)} disabled={saving}>
                        {t('common.cancel')}
                    </Button>
                    <Button type='submit' disabled={!canSubmit} loading={saving}>
                        {t('vds.access.change_password')}
                    </Button>
                </DialogFooter>
            </form>
        </Dialog>
    );
}
