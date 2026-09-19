'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Plus, Search, X } from 'lucide-react';

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
  width?: number | string;
  minWidth?: number | string;
  maxWidth?: number | string;
  searchable?: boolean;
  searchPlaceholder?: string;
  align?: 'left' | 'right';
  creatable?: boolean;
  customPlaceholder?: string;
  onCreateOption?: (val: string) => void;
  clearable?: boolean;
  onClear?: () => void;
  fullWidthDropdown?: boolean;
}

export function CustomSelect({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  style,
  className = '',
  width,
  minWidth = 180,
  maxWidth,
  searchable = false,
  searchPlaceholder,
  align = 'left',
  creatable = false,
  customPlaceholder,
  onCreateOption,
  clearable = false,
  onClear,
  fullWidthDropdown,
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [customVal, setCustomVal] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const customInputRef = useRef<HTMLInputElement>(null);

  const isFullWidth = fullWidthDropdown ?? (minWidth === '100%' || width === '100%');

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

  useEffect(() => {
    if (!isOpen) {
      setIsCreating(false);
      setCustomVal('');
    }
  }, [isOpen]);

  useEffect(() => {
    if (isCreating) {
      setTimeout(() => customInputRef.current?.focus(), 50);
    }
  }, [isCreating]);

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredOptions.length > 0) {
        onChange(String(filteredOptions[0].value));
        setIsOpen(false);
        setSearch('');
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (search) {
        setSearch('');
      } else {
        setIsOpen(false);
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className={`custom-select-container ${className}`}
      style={{
        position: 'relative',
        display: 'inline-block',
        width: width,
        minWidth: minWidth,
        maxWidth: maxWidth,
        flexShrink: 0,
        zIndex: isOpen ? 100 : undefined,
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
          padding: '0 10px 0 12px',
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
          transition: 'border-color 120ms ease, box-shadow 120ms ease',
          boxSizing: 'border-box',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', minWidth: 0, flex: 1 }}>
          {selectedOption?.icon && (
            <span style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--accent)', flexShrink: 0 }}>
              {selectedOption.icon}
            </span>
          )}
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selectedOption ? selectedOption.label : (value ? String(value) : placeholder)}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
          {clearable && onClear && value && value !== '0' && (
            <span
              role="button"
              onClick={(e) => {
                e.stopPropagation();
                onClear();
              }}
              title="Clear"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--muted)',
                cursor: 'pointer',
                padding: '2px',
                borderRadius: '4px',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--danger)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
            >
              <X size={13} />
            </span>
          )}

          <ChevronDown
            size={14}
            style={{
              color: 'var(--muted)',
              flexShrink: 0,
              transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
              transform: isOpen ? 'rotate(180deg)' : 'none',
            }}
          />
        </div>
      </button>

      {isOpen && (
        <div
          className={`custom-select-dropdown ${align === 'right' ? 'align-right' : ''} ${isFullWidth ? 'full-width' : ''}`}
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
                <Search size={13} style={{ color: 'var(--muted)', flexShrink: 0 }} />
                <input
                  ref={searchInputRef}
                  type="text"
                  placeholder={searchPlaceholder || 'Filter...'}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    outline: 'none',
                    fontSize: '12px',
                    width: '100%',
                    color: 'var(--text)',
                    padding: 0,
                    minWidth: 0,
                  }}
                />
                {search && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSearch('');
                      searchInputRef.current?.focus();
                    }}
                    style={{
                      border: 'none',
                      background: 'transparent',
                      color: 'var(--muted)',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px',
                      borderRadius: '4px',
                    }}
                    title="Clear search"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            </div>
          )}

          <div
            className="custom-select-scroll"
            style={{
              maxHeight: searchable ? '280px' : '340px',
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
                      gap: '12px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      cursor: 'pointer',
                      fontWeight: isSelected ? 600 : 400,
                      color: isSelected ? 'var(--accent)' : 'var(--text)',
                      background: isSelected ? 'var(--accent-soft)' : 'transparent',
                      transition: 'background-color 0.12s ease',
                      boxSizing: 'border-box',
                      minWidth: 0,
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--surface-2)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1, overflow: 'hidden' }}>
                      {opt.icon && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', color: isSelected ? 'var(--accent)' : 'var(--muted)', flexShrink: 0 }}>
                          {opt.icon}
                        </span>
                      )}
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
                        {opt.label}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0, marginInlineStart: 'auto' }}>
                      {opt.badge !== undefined && (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '1.5px 7px',
                            borderRadius: '10px',
                            background: isSelected ? 'rgba(15, 118, 110, 0.15)' : 'var(--surface-2)',
                            color: isSelected ? 'var(--accent)' : 'var(--muted)',
                            fontWeight: 600,
                            flexShrink: 0,
                          }}
                        >
                          {opt.badge}
                        </span>
                      )}
                      {isSelected && <Check size={14} style={{ color: 'var(--accent)', strokeWidth: 2.5, flexShrink: 0 }} />}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {creatable && !isCreating && (
            <div
              onClick={(e) => {
                e.stopPropagation();
                setIsCreating(true);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: '6px',
                fontSize: '13px',
                color: 'var(--accent)',
                cursor: 'pointer',
                marginTop: '3px',
                borderTop: '1px dashed var(--line)',
                fontWeight: 500,
                transition: 'background-color 0.12s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'var(--surface-2)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              <Plus size={13} style={{ strokeWidth: 2.5 }} />
              <span>Custom duration...</span>
            </div>
          )}

          {creatable && isCreating && (
            <div
              style={{
                padding: '8px 10px',
                borderTop: '1px solid var(--line)',
                marginTop: '3px',
                background: 'var(--surface-2)',
                borderRadius: '6px',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <input
                  ref={customInputRef}
                  type="text"
                  placeholder={customPlaceholder || 'e.g. 15 Days, 2 Months...'}
                  value={customVal}
                  onChange={(e) => setCustomVal(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      const trimmed = customVal.trim();
                      if (trimmed) {
                        if (onCreateOption) onCreateOption(trimmed);
                        onChange(trimmed);
                        setIsOpen(false);
                        setIsCreating(false);
                        setCustomVal('');
                      }
                    } else if (e.key === 'Escape') {
                      e.stopPropagation();
                      setIsCreating(false);
                      setCustomVal('');
                    }
                  }}
                  style={{
                    flex: 1,
                    height: '30px',
                    padding: '0 8px',
                    fontSize: '12.5px',
                    border: '1px solid var(--accent)',
                    borderRadius: '5px',
                    background: 'var(--surface)',
                    color: 'var(--text)',
                    outline: 'none',
                    minWidth: 0,
                  }}
                />
                <button
                  type="button"
                  className="btn"
                  style={{ height: '30px', padding: '0 10px', fontSize: '12px', whiteSpace: 'nowrap' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    const trimmed = customVal.trim();
                    if (trimmed) {
                      if (onCreateOption) onCreateOption(trimmed);
                      onChange(trimmed);
                      setIsOpen(false);
                      setIsCreating(false);
                      setCustomVal('');
                    }
                  }}
                >
                  Set
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  style={{ height: '30px', padding: '0 6px', fontSize: '12px', color: 'var(--muted)' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsCreating(false);
                    setCustomVal('');
                  }}
                >
                  ✕
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
