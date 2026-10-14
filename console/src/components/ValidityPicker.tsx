'use client';

import { useMemo } from 'react';
import { CustomSelect, type SelectOption } from './CustomSelect';

interface ValidityPickerProps {
  value?: string;
  onChange: (val: string) => void;
  presets: string[];
  onAddPreset: (newPreset: string) => void;
}

export function ValidityPicker({ value = '', onChange, presets, onAddPreset }: ValidityPickerProps) {
  const handleCreateOption = (newVal: string) => {
    const trimmed = newVal.trim();
    if (!trimmed) return;

    onAddPreset(trimmed);
  };

  const options: SelectOption[] = useMemo(() => {
    const unique = new Set<string>();
    const opts: SelectOption[] = [
      { value: '', label: 'None (Instant / Lifetime)' },
    ];

    for (const p of presets) {
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
  }, [presets, value]);

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
        Validity <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
      </span>
      <CustomSelect
        value={value}
        onChange={onChange}
        options={options}
        placeholder="None (Instant / Lifetime)"
        creatable={true}
        customPlaceholder="15 Days, 2 Months..."
        onCreateOption={handleCreateOption}
        minWidth="100%"
      />
    </div>
  );
}
