'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Plus, Search, X } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
  badge?: string | number;
  icon?: React.ReactNode;
  disabled?: boolean;
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
  emptyValue?: string;
  ariaLabel?: string;
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
  creatable = false,
  customPlaceholder,
  onCreateOption,
  clearable = false,
  onClear,
  emptyValue,
  ariaLabel,
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [query, setQuery] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [customVal, setCustomVal] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const customInputRef = useRef<HTMLInputElement>(null);

  const selectedOption = useMemo(
    () => options.find((opt) => String(opt.value) === String(value)),
    [options, value]
  );

  const isDefaultOrEmpty = selectedOption
    ? (emptyValue !== undefined ? String(selectedOption.value) === String(emptyValue) : false)
    : (!value || (emptyValue !== undefined && String(value) === String(emptyValue)));

  const displayValue = isTyping
    ? query
    : selectedOption && !isDefaultOrEmpty
    ? selectedOption.label
    : '';

  const filteredOptions = useMemo(() => {
    if (!isTyping || !query.trim()) return options;
    const q = query.trim().toLowerCase();
    return options.filter((opt) => opt.label.toLowerCase().includes(q));
  }, [options, isTyping, query]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setIsTyping(false);
        setQuery('');
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
        setIsTyping(false);
        setQuery('');
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

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

  const handleSelect = (val: string) => {
    if (options.find((option) => String(option.value) === val)?.disabled) return;
    onChange(val);
    setIsOpen(false);
    setActiveIndex(-1);
    setIsTyping(false);
    setQuery('');
  };

  const handleClear = () => {
    if (onClear) {
      onClear();
    } else {
      onChange(emptyValue !== undefined ? emptyValue : '');
    }
    setQuery('');
    setIsTyping(false);
    setIsOpen(false);
  };

  const handleBoxClick = (e: React.MouseEvent) => {
    if (searchable && e.target === inputRef.current) {
      if (!isOpen) setIsOpen(true);
      return;
    }

    setIsOpen((prev) => {
      const next = !prev;
      if (next && searchable) {
        setTimeout(() => {
          inputRef.current?.focus();
          inputRef.current?.select();
        }, 20);
      } else if (!next) {
        setIsTyping(false);
        setQuery('');
      }
      return next;
    });
  };

  const close = () => {
    setIsOpen(false);
    setIsTyping(false);
    setQuery('');
    setActiveIndex(-1);
  };

  const handleKeys = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setActiveIndex(filteredOptions.findIndex(option => !option.disabled));
        return;
      }
      const count = filteredOptions.length;
      if (!count) return;
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setActiveIndex((current) => {
        for (let offset = 1; offset <= count; offset++) {
          const index = (current + step * offset + count * 2) % count;
          if (!filteredOptions[index].disabled) return index;
        }
        return -1;
      });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setActiveIndex(filteredOptions.findIndex(option => !option.disabled));
        return;
      }
      const chosen = filteredOptions[activeIndex] ?? filteredOptions.find(option => !option.disabled);
      if (chosen) handleSelect(String(chosen.value));
    } else if (e.key === ' ' && !searchable) {
      e.preventDefault();
      isOpen ? close() : (setIsOpen(true), setActiveIndex(filteredOptions.findIndex(option => !option.disabled)));
    } else if (e.key === 'Escape') {
      e.preventDefault();
      if (isOpen) e.stopPropagation();
      close();
    } else if (e.key === 'Tab' && isOpen) {
      close();
    }
  };

  const handleInputKeyDown = handleKeys;

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
      <div
        className={`custom-select-trigger${isOpen ? ' open' : ''}`}
        role={searchable ? undefined : 'combobox'}
        aria-label={searchable ? undefined : (ariaLabel || placeholder)}
        aria-expanded={searchable ? undefined : isOpen}
        aria-haspopup={searchable ? undefined : 'listbox'}
        aria-controls={!searchable && isOpen ? listId : undefined}
        aria-activedescendant={!searchable && isOpen && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
        tabIndex={searchable ? -1 : 0}
        onClick={handleBoxClick}
        onKeyDown={searchable ? undefined : handleKeys}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', minWidth: 0, flex: 1 }}>
          {selectedOption?.icon ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--accent)', flexShrink: 0 }}>
              {selectedOption.icon}
            </span>
          ) : searchable && (isDefaultOrEmpty || isTyping) ? (
            <Search size={14} style={{ color: 'var(--muted)', flexShrink: 0 }} />
          ) : null}

          {searchable ? (
            <input
              ref={inputRef}
              type="text"
              role="combobox"
              aria-label={ariaLabel || placeholder}
              aria-expanded={isOpen}
              aria-controls={isOpen ? listId : undefined}
              aria-autocomplete="list"
              aria-activedescendant={isOpen && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
              value={displayValue}
              placeholder={placeholder}
              onClick={(e) => {
                e.stopPropagation();
                if (!isOpen) setIsOpen(true);
              }}
              onFocus={(e) => {
                if (!isOpen) setIsOpen(true);
                if (searchable) {
                  e.currentTarget.select();
                }
              }}
              onChange={(e) => {
                setIsTyping(true);
                setQuery(e.target.value);
                setActiveIndex(-1);
                if (!isOpen) setIsOpen(true);
              }}
              onKeyDown={handleInputKeyDown}
              style={{
                border: 'none',
                borderRadius: 0,
                boxShadow: 'none',
                background: 'transparent',
                outline: 'none',
                minHeight: 'unset',
                height: 'auto',
                maxHeight: '100%',
                fontSize: '13.5px',
                fontWeight: 500,
                color: isTyping || (selectedOption && !isDefaultOrEmpty) ? 'var(--text)' : 'var(--muted)',
                width: '100%',
                cursor: 'text',
                padding: 0,
                margin: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            />
          ) : (
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '13.5px', fontWeight: 500, color: selectedOption ? 'var(--text)' : 'var(--muted)' }}>
              {selectedOption ? selectedOption.label : (value ? String(value) : placeholder)}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
          {((isTyping && query.trim()) || (clearable && selectedOption && !isDefaultOrEmpty)) && (
            <span
              role="button"
              className="custom-select-clear"
              onClick={(e) => {
                e.stopPropagation();
                if (isTyping && query.trim()) {
                  setQuery('');
                  inputRef.current?.focus();
                } else {
                  handleClear();
                }
              }}
              title={isTyping && query.trim() ? 'Clear search' : 'Clear selection'}
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
              pointerEvents: 'none',
            }}
          />
        </div>
      </div>

      {isOpen && (
        <div className="custom-select-dropdown">
          <div id={listId} className="custom-select-scroll" role="listbox" aria-label={ariaLabel || placeholder}>
            {filteredOptions.length === 0 ? (
              <div style={{ padding: '10px 12px', fontSize: '12px', color: 'var(--muted)', textAlign: 'center' }}>
                No options found
              </div>
            ) : (
              filteredOptions.map((opt, index) => {
                const isSelected = String(opt.value) === String(value);

                return (
                  <div
                    key={String(opt.value)}
                    id={`${listId}-${index}`}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={opt.disabled || undefined}
                    className={`custom-select-option${isSelected ? ' selected' : ''}${index === activeIndex ? ' active' : ''}`}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => handleSelect(String(opt.value))}
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
              <span>Add validity...</span>
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
