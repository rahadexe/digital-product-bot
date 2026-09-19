'use client';

import { useMemo } from 'react';
import { CustomSelect, type SelectOption } from './CustomSelect';

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
}

export function ValidityPicker({ value = '', onChange, presets = [] }: ValidityPickerProps) {
  const options: SelectOption[] = useMemo(() => {
    const list = presets.length > 0 ? presets : DEFAULT_PRESETS;
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
  }, [presets, value]);

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
        minWidth="100%"
      />
    </div>
  );
}
