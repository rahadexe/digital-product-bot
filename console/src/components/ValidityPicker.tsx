'use client';

import { useEffect, useMemo, useState } from 'react';
import { CustomSelect, type SelectOption } from './CustomSelect';
import { api } from '@/lib/api';

const DEFAULT_PRESETS = [
  '3 Days',
  '7 Days',
  '14 Days',
  '30 Days',
  '90 Days',
  '1 Month',
  '3 Months',
  '6 Months',
  '1 Year',
  'Lifetime',
];

interface ValidityPickerProps {
  value?: string;
  onChange: (val: string) => void;
  presets?: string[];
  onAddPreset?: (newPreset: string) => void;
}

export function ValidityPicker({ value = '', onChange, presets = [], onAddPreset }: ValidityPickerProps) {
  const [localPresets, setLocalPresets] = useState<string[]>(presets.length > 0 ? presets : DEFAULT_PRESETS);

  useEffect(() => {
    if (presets.length > 0) {
      setLocalPresets((prev) => {
        const set = new Set<string>();
        const merged: string[] = [];
        for (const p of [...presets, ...prev]) {
          const lower = p.trim().toLowerCase();
          if (lower && !set.has(lower)) {
            set.add(lower);
            merged.push(p.trim());
          }
        }
        return merged;
      });
    }
  }, [presets]);

  const handleCreateOption = async (newVal: string) => {
    const trimmed = newVal.trim();
    if (!trimmed) return;

    setLocalPresets((prev) => {
      const exists = prev.some((p) => p.toLowerCase() === trimmed.toLowerCase());
      if (exists) return prev;
      return [...prev, trimmed];
    });

    if (onAddPreset) {
      onAddPreset(trimmed);
    } else {
      try {
        const sets = await api.settings();
        const currentList = sets?.validity_presets
          ? sets.validity_presets.split(',').map((s) => s.trim()).filter(Boolean)
          : DEFAULT_PRESETS;
        const exists = currentList.some((p) => p.toLowerCase() === trimmed.toLowerCase());
        if (!exists) {
          const updated = [...currentList, trimmed];
          await api.updateSettings({ validity_presets: updated.join(', ') });
        }
      } catch (err) {
        console.error('Failed to auto-save preset:', err);
      }
    }
  };

  const options: SelectOption[] = useMemo(() => {
    const list = localPresets.length > 0 ? localPresets : DEFAULT_PRESETS;
    const unique = new Set<string>();
    const opts: SelectOption[] = [
      { value: '', label: 'None (Instant / Lifetime)' },
    ];

    for (const p of list) {
      const trimmed = p.trim();
      if (trimmed && !unique.has(trimmed.toLowerCase())) {
        unique.add(trimmed.toLowerCase());
        opts.push({ value: trimmed, label: trimmed });
      }
    }

    const currentVal = value.trim();
    if (currentVal && !unique.has(currentVal.toLowerCase())) {
      opts.push({ value: currentVal, label: currentVal });
    }

    return opts;
  }, [localPresets, value]);

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
        Validity / Duration <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
      </span>
      <CustomSelect
        value={value}
        onChange={onChange}
        options={options}
        placeholder="None (Instant / Lifetime)"
        creatable={true}
        customPlaceholder="e.g. 15 Days, 2 Months..."
        onCreateOption={handleCreateOption}
        minWidth="100%"
      />
    </div>
  );
}
