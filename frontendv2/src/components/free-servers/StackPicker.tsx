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

import { useRef, type KeyboardEvent } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/contexts/TranslationContext';
import { FREE_SERVER_STACKS, type FreeServerStackGroup, type FreeServerStackKey } from '@/lib/free-servers';
import { StackIcon } from '@/components/free-servers/StackIcon';

const GROUPS: FreeServerStackGroup[] = ['runtime', 'database'];

interface StackPickerProps {
    /** Stacks that can be picked; the others are not shown. */
    available: FreeServerStackKey[];
    value: FreeServerStackKey | null;
    onChange: (stack: FreeServerStackKey) => void;
    /** Stack the server runs now (marked, and not pickable). */
    current?: FreeServerStackKey | null;
    disabled?: boolean;
    /** Accessible name of the radio group. */
    label: string;
    /** Fewer columns, for narrow places such as a settings card. */
    compact?: boolean;
    className?: string;
}

/** Runtime and database cards, grouped like the create page shows them. Works as a radio group. */
export function StackPicker({
    available,
    value,
    onChange,
    current,
    disabled,
    label,
    compact,
    className,
}: StackPickerProps) {
    const { t } = useTranslation();
    const refs = useRef(new Map<FreeServerStackKey, HTMLButtonElement>());
    const shown = FREE_SERVER_STACKS.filter((s) => available.includes(s.key));
    const pickable = shown.filter((s) => s.key !== current).map((s) => s.key);
    // Roving tab stop: the picked card, or the first pickable one.
    const tabStop = value && pickable.includes(value) ? value : (pickable[0] ?? null);

    const move = (from: FreeServerStackKey, step: number) => {
        const index = pickable.indexOf(from);
        if (index === -1 || pickable.length === 0) return;
        const next = pickable[(index + step + pickable.length) % pickable.length];
        onChange(next);
        refs.current.get(next)?.focus();
    };

    const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, key: FreeServerStackKey) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            event.preventDefault();
            move(key, 1);
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            event.preventDefault();
            move(key, -1);
        }
    };

    return (
        <div role='radiogroup' aria-label={label} className={cn('space-y-6', className)}>
            {GROUPS.map((group) => {
                const stacks = shown.filter((s) => s.group === group);
                if (stacks.length === 0) return null;
                return (
                    <div key={group} className='space-y-3'>
                        <p className='text-muted-foreground text-xs font-semibold tracking-[0.2em] uppercase'>
                            {t(`freeServers.groups.${group}`)}
                        </p>
                        <div
                            className={cn(
                                'grid grid-cols-1 gap-3 sm:grid-cols-2',
                                compact ? '2xl:grid-cols-3' : 'lg:grid-cols-3 xl:grid-cols-4',
                            )}
                        >
                            {stacks.map(({ key }) => {
                                const isCurrent = key === current;
                                const checked = key === value;
                                return (
                                    <button
                                        key={key}
                                        ref={(el) => {
                                            if (el) refs.current.set(key, el);
                                            else refs.current.delete(key);
                                        }}
                                        type='button'
                                        role='radio'
                                        aria-checked={checked}
                                        disabled={disabled || isCurrent}
                                        tabIndex={key === tabStop ? 0 : -1}
                                        onClick={() => onChange(key)}
                                        onKeyDown={(e) => onKeyDown(e, key)}
                                        className={cn(
                                            'group relative flex min-h-24 items-center gap-4 rounded-2xl border p-4 text-left transition-all sm:p-5',
                                            'focus-visible:ring-primary/50 focus-visible:ring-2 focus-visible:outline-none',
                                            checked
                                                ? 'border-primary bg-primary/10 ring-primary/40 ring-1'
                                                : 'border-border/70 bg-card/40 hover:border-primary/40 hover:bg-card/70',
                                            (disabled || isCurrent) && 'cursor-not-allowed',
                                            disabled && !isCurrent && 'opacity-60',
                                        )}
                                    >
                                        <span className='border-border/70 bg-background/60 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border'>
                                            <StackIcon stack={key} className='h-7 w-7' />
                                        </span>
                                        <span className='min-w-0 flex-1'>
                                            <span className='block text-base font-semibold'>
                                                {t(`freeServers.stacks.${key}.title`)}
                                            </span>
                                            <span className='text-muted-foreground block text-sm leading-snug'>
                                                {t(`freeServers.stacks.${key}.description`)}
                                            </span>
                                        </span>
                                        {isCurrent && (
                                            <span className='bg-muted text-muted-foreground absolute top-2 right-2 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase'>
                                                {t('freeServers.stack_card.current')}
                                            </span>
                                        )}
                                        {checked && !isCurrent && (
                                            <span className='bg-primary text-primary-foreground absolute top-2 right-2 flex h-5 w-5 items-center justify-center rounded-full'>
                                                <Check className='h-3 w-3' aria-hidden />
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
