'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Clock, Search, X } from 'lucide-react';

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
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmedValue = value.trim();

  // Combine provided presets with defaults, avoiding duplicates
  const allPresets = useMemo(() => {
    const list = presets.length > 0 ? presets : DEFAULT_PRESETS;
    const unique = new Set<string>();
    for (const p of list) {
      if (p.trim()) unique.add(p.trim());
    }
    // Also if user has a custom value currently selected, ensure it's acknowledged
    return Array.from(unique);
  }, [presets]);

  // Filter presets based on query
  const filteredPresets = useMemo(() => {
    if (!query.trim()) return allPresets;
    const q = query.trim().toLowerCase();
    return allPresets.filter((p) => p.toLowerCase().includes(q));
  }, [allPresets, query]);

  // Close on click outside or Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  // Auto focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery('');
    }
  }, [isOpen]);

  const handleSelect = (selected: string) => {
    onChange(selected);
    setIsOpen(false);
  };

  const handleCustomSubmit = () => {
    if (query.trim()) {
      onChange(query.trim());
      setIsOpen(false);
    }
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%' }}>
      {/* Field Label */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
          Validity / Duration <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
        </span>
        {trimmedValue ? (
          <button
            type="button"
            className="mini ghost"
            style={{ fontSize: '11px', color: 'var(--danger)', padding: '0 4px', display: 'inline-flex', alignItems: 'center', gap: '2px' }}
            onClick={(e) => {
              e.stopPropagation();
              onChange('');
            }}
          >
            <X size={12} /> Clear
          </button>
        ) : null}
      </div>

      {/* Dropdown Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          height: '38px',
          padding: '0 12px',
          background: 'var(--surface)',
          border: isOpen ? '1px solid var(--accent)' : '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: trimmedValue ? 'var(--text)' : 'var(--muted)',
          fontSize: '13px',
          cursor: 'pointer',
          outline: 'none',
          boxShadow: isOpen ? '0 0 0 2px var(--accent-soft)' : 'none',
          transition: 'border-color 150ms ease, box-shadow 150ms ease',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
          <Clock size={15} style={{ color: trimmedValue ? 'var(--accent)' : 'var(--muted)', flexShrink: 0 }} />
          {trimmedValue ? (
            <span style={{ fontWeight: 600, color: 'var(--text)' }}>{trimmedValue}</span>
          ) : (
            <span style={{ color: 'var(--muted)' }}>Select validity or type duration…</span>
          )}
        </div>

        <ChevronDown
          size={16}
          style={{
            color: 'var(--muted)',
            transition: 'transform 180ms ease',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            flexShrink: 0,
          }}
        />
      </button>

      {/* Floating Dropdown Menu */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 100,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-raised)',
            padding: '8px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            maxHeight: '260px',
            animation: 'rise-in 140ms ease',
          }}
        >
          {/* Quick Search & Custom Entry Input */}
          <div style={{ position: 'relative', width: '100%' }}>
            <Search
              size={13}
              style={{
                position: 'absolute',
                left: 9,
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--muted)',
                pointerEvents: 'none',
              }}
            />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search or type custom (e.g. 15 Days)..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleCustomSubmit();
                }
              }}
              style={{
                width: '100%',
                height: '32px',
                padding: '4px 8px 4px 28px',
                fontSize: '12px',
                borderRadius: '6px',
                background: 'var(--surface-2)',
                border: '1px solid var(--line-strong)',
              }}
            />
          </div>

          {/* Preset Options Scrollable List */}
          <div
            style={{
              overflowY: 'auto',
              maxHeight: '160px',
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
            }}
          >
            {/* Clear / No Validity Option */}
            <button
              type="button"
              onClick={() => handleSelect('')}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 10px',
                fontSize: '12px',
                borderRadius: '6px',
                border: 'none',
                background: !trimmedValue ? 'var(--accent-soft)' : 'transparent',
                color: !trimmedValue ? 'var(--accent)' : 'var(--muted)',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <span>No duration / Lifetime</span>
              {!trimmedValue ? <Check size={13} /> : null}
            </button>

            {filteredPresets.map((preset) => {
              const isSelected = trimmedValue.toLowerCase() === preset.toLowerCase();
              return (
                <button
                  key={preset}
                  type="button"
                  onClick={() => handleSelect(preset)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    fontSize: '12.5px',
                    fontWeight: isSelected ? 600 : 500,
                    borderRadius: '6px',
                    border: 'none',
                    background: isSelected ? 'var(--accent-soft)' : 'transparent',
                    color: isSelected ? 'var(--accent)' : 'var(--text)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'background 100ms ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.background = 'var(--surface-2)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Clock size={13} style={{ color: isSelected ? 'var(--accent)' : 'var(--muted)' }} />
                    <span>{preset}</span>
                  </div>
                  {isSelected ? <Check size={14} style={{ color: 'var(--accent)' }} /> : null}
                </button>
              );
            })}

            {/* If user typed something not in presets, offer "Use custom: ..." */}
            {query.trim() && !allPresets.some((p) => p.toLowerCase() === query.trim().toLowerCase()) ? (
              <button
                type="button"
                onClick={handleCustomSubmit}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '7px 10px',
                  fontSize: '12px',
                  fontWeight: 600,
                  borderRadius: '6px',
                  border: '1px dashed var(--accent)',
                  background: 'var(--accent-soft)',
                  color: 'var(--accent)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  marginTop: '4px',
                }}
              >
                <span>Use custom duration: &ldquo;{query.trim()}&rdquo;</span>
                <span style={{ fontSize: '11px', background: 'var(--surface)', padding: '1px 6px', borderRadius: '4px' }}>
                  ↵ Enter
                </span>
              </button>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
