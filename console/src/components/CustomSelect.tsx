'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
  badge?: string | number;
  icon?: React.ReactNode;
}

export interface CustomSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  style?: React.CSSProperties;
  className?: string;
  minWidth?: number | string;
  maxWidth?: number | string;
  searchable?: boolean;
  align?: 'left' | 'right';
}

export function CustomSelect({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  style,
  className = '',
  minWidth = 170,
  maxWidth,
  searchable = false,
  align = 'left',
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selectedOption = useMemo(
    () => options.find((opt) => String(opt.value) === String(value)),
    [options, value]
  );

  const filteredOptions = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.trim().toLowerCase();
    return options.filter((opt) => opt.label.toLowerCase().includes(q));
  }, [options, search]);

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

  useEffect(() => {
    if (isOpen && searchable) {
      setTimeout(() => searchInputRef.current?.focus(), 50);
    } else {
      setSearch('');
    }
  }, [isOpen, searchable]);

  return (
    <div
      ref={containerRef}
      className={`custom-select-container ${className}`}
      style={{
        position: 'relative',
        display: 'inline-block',
        minWidth: minWidth,
        maxWidth: maxWidth,
        userSelect: 'none',
        ...style,
      }}
    >
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        style={{
          width: '100%',
          minHeight: '38px',
          height: '38px',
          padding: '0 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          background: 'var(--surface)',
          border: `1px solid ${isOpen ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: '8px',
          color: selectedOption ? 'var(--text)' : 'var(--muted)',
          fontSize: '13.5px',
          fontWeight: 500,
          cursor: 'pointer',
          outline: 'none',
          boxShadow: isOpen
            ? '0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent)'
            : '0 1px 2px rgba(0, 0, 0, 0.02)',
          transition: 'all 0.15s ease',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selectedOption?.icon && (
            <span style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--accent)' }}>
              {selectedOption.icon}
            </span>
          )}
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          {selectedOption?.badge !== undefined && (
            <span
              style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: '10px',
                background: 'var(--surface-2)',
                color: 'var(--text-dim)',
                fontWeight: 600,
              }}
            >
              {selectedOption.badge}
            </span>
          )}
        </div>

        <ChevronDown
          size={14}
          style={{
            color: 'var(--muted)',
            flexShrink: 0,
            transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
            transform: isOpen ? 'rotate(180deg)' : 'none',
          }}
        />
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 5px)',
            [align === 'right' ? 'right' : 'left']: 0,
            minWidth: '100%',
            width: 'max-content',
            maxWidth: '320px',
            maxHeight: '280px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            boxShadow: '0 10px 30px -4px rgba(24, 33, 30, 0.14), 0 4px 12px -2px rgba(24, 33, 30, 0.06)',
            padding: '5px',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {searchable && (
            <div style={{ padding: '4px 6px 6px 6px', borderBottom: '1px solid var(--line)' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'var(--surface-2)',
                  borderRadius: '6px',
                  padding: '4px 8px',
                }}
              >
                <Search size={13} style={{ color: 'var(--muted)' }} />
                <input
                  ref={searchInputRef}
                  type="text"
                  placeholder="Filter..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    outline: 'none',
                    fontSize: '12px',
                    width: '100%',
                    color: 'var(--text)',
                    padding: 0,
                  }}
                />
              </div>
            </div>
          )}

          <div
            style={{
              overflowY: 'auto',
              maxHeight: searchable ? '220px' : '260px',
              padding: '2px 0',
            }}
          >
            {filteredOptions.length === 0 ? (
              <div style={{ padding: '10px 12px', fontSize: '12px', color: 'var(--muted)', textAlign: 'center' }}>
                No options found
              </div>
            ) : (
              filteredOptions.map((opt) => {
                const isSelected = String(opt.value) === String(value);

                return (
                  <div
                    key={String(opt.value)}
                    onClick={() => {
                      onChange(String(opt.value));
                      setIsOpen(false);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      cursor: 'pointer',
                      fontWeight: isSelected ? 600 : 400,
                      color: isSelected ? 'var(--accent)' : 'var(--text)',
                      background: isSelected ? 'var(--accent-soft)' : 'transparent',
                      transition: 'background-color 0.12s ease',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--surface-2)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                      {opt.icon && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', color: isSelected ? 'var(--accent)' : 'var(--muted)' }}>
                          {opt.icon}
                        </span>
                      )}
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {opt.label}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                      {opt.badge !== undefined && (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '1px 6px',
                            borderRadius: '10px',
                            background: isSelected ? 'rgba(15, 118, 110, 0.15)' : 'var(--surface-2)',
                            color: isSelected ? 'var(--accent)' : 'var(--muted)',
                            fontWeight: 600,
                          }}
                        >
                          {opt.badge}
                        </span>
                      )}
                      {isSelected && <Check size={14} style={{ color: 'var(--accent)', strokeWidth: 2.5 }} />}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
