'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';

export interface EmojiItem {
  name: string;
  id: string;
}

// Verified Telegram VPN Custom Emojis (clean list, no basic/generic emojis)
export const PRESET_EMOJIS: EmojiItem[] = [
  { name: 'NordVPN', id: '5796345694969140339' },
  { name: 'ExpressVPN', id: '5796153709931009517' },
  { name: 'Surfshark', id: '5796592771552777710' },
  { name: 'Proton VPN', id: '5794298344188678751' },
  { name: 'CyberGhost', id: '5796309230696797985' },
  { name: 'HMA VPN', id: '5796595022115639741' },
  { name: 'Bitdefender', id: '5793973558761756143' },
  { name: 'Windscribe', id: '5794045349140108622' },
  { name: 'PureVPN', id: '5794156713347126602' },
  { name: 'Turbo VPN', id: '5796633857209931262' },
  { name: 'PotatoVPN', id: '5796403831646458962' },
  { name: 'PandaVPN', id: '5796561774773801876' },
  { name: 'VyprVPN', id: '5796381996032725483' },
  { name: 'X-VPN', id: '5794376731636798062' },
];

export const VPN_EMOJIS = PRESET_EMOJIS;

interface EmojiPickerProps {
  value?: string;
  onChange: (id: string) => void;
}

export function EmojiPicker({ value = '', onChange }: EmojiPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmedValue = value ? String(value).trim() : '';

  // Matched preset item if any
  const matchedPreset = useMemo(() => {
    if (!trimmedValue) return null;
    return PRESET_EMOJIS.find((p) => p.id === trimmedValue);
  }, [trimmedValue]);

  // Display text in the input box:
  // When typing: show query.
  // When not typing: show preset name or custom ID or empty.
  const displayValue = isTyping
    ? query
    : matchedPreset
    ? matchedPreset.name
    : trimmedValue;

  // Filter emojis based on query
  const filteredEmojis = useMemo(() => {
    if (!isTyping || !query.trim()) return PRESET_EMOJIS;
    const q = query.trim().toLowerCase();
    return PRESET_EMOJIS.filter(
      (item) => item.name.toLowerCase().includes(q) || item.id.includes(q)
    );
  }, [isTyping, query]);

  // Is typed query something not in presets (e.g. custom telegram ID)
  const isCustomQuery = useMemo(() => {
    if (!isTyping || !query.trim()) return false;
    const q = query.trim().toLowerCase();
    return !PRESET_EMOJIS.some(
      (item) => item.name.toLowerCase() === q || item.id === query.trim()
    );
  }, [isTyping, query]);

  // Close on outside click
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

  const handleSelect = (selectedId: string) => {
    onChange(selectedId);
    setIsOpen(false);
    setIsTyping(false);
    setQuery('');
  };

  const handleClear = () => {
    onChange('');
    setQuery('');
    setIsTyping(false);
    inputRef.current?.focus();
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%' }}>
      <label className="field" style={{ margin: 0 }}>
        <span>
          Custom Emoji <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
        </span>

        {/* Input box styled exactly like CustomSelect in media_1789760956330.png */}
        <div
          onClick={() => {
            setIsOpen(true);
            inputRef.current?.focus();
          }}
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
            cursor: 'text',
            outline: 'none',
            boxShadow: isOpen
              ? '0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent)'
              : '0 1px 2px rgba(0, 0, 0, 0.02)',
            transition: 'all 0.15s ease',
          }}
        >
          <input
            ref={inputRef}
            type="text"
            value={displayValue}
            placeholder="Select VPN Emoji or paste custom ID..."
            onFocus={() => {
              setIsOpen(true);
            }}
            onChange={(e) => {
              setIsTyping(true);
              setQuery(e.target.value);
              if (!isOpen) setIsOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                if (query.trim()) {
                  const match = PRESET_EMOJIS.find(
                    (p) => p.name.toLowerCase() === query.trim().toLowerCase()
                  );
                  handleSelect(match ? match.id : query.trim());
                }
              }
            }}
            style={{
              width: '100%',
              border: 'none',
              background: 'transparent',
              outline: 'none',
              fontSize: '13.5px',
              fontWeight: 500,
              color: 'var(--text)',
              padding: 0,
            }}
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
            {trimmedValue ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClear();
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
                  background: 'none',
                  border: 'none',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--danger)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
              >
                <X size={14} />
              </button>
            ) : null}

            <ChevronDown
              size={14}
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen((prev) => !prev);
              }}
              style={{
                color: 'var(--muted)',
                cursor: 'pointer',
                flexShrink: 0,
                transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                transform: isOpen ? 'rotate(180deg)' : 'none',
              }}
            />
          </div>
        </div>
      </label>

      {/* Dropdown Menu - EXACTLY matching CustomSelect in media_1789760956330.png */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 5px)',
            left: 0,
            right: 0,
            width: '100%',
            maxHeight: '260px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            boxShadow: '0 12px 36px -4px rgba(0, 0, 0, 0.16), 0 4px 12px -2px rgba(0, 0, 0, 0.06)',
            padding: '5px',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            overflowY: 'auto',
          }}
        >
          {/* If user typed a custom ID / text not in presets, show "Use custom ID" option */}
          {isCustomQuery && (
            <div
              onClick={() => handleSelect(query.trim())}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '10px',
                padding: '8px 12px',
                borderRadius: '6px',
                fontSize: '13px',
                cursor: 'pointer',
                fontWeight: 600,
                color: 'var(--accent)',
                background: 'var(--accent-soft)',
                marginBottom: '4px',
                border: '1px dashed var(--accent)',
              }}
            >
              <span>Use custom ID: &ldquo;{query.trim()}&rdquo;</span>
              <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 'normal' }}>
                ↵ Enter
              </span>
            </div>
          )}

          {/* None option */}
          <div
            onClick={() => handleSelect('')}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '14px',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '13px',
              cursor: 'pointer',
              fontWeight: !trimmedValue ? 600 : 400,
              color: !trimmedValue ? 'var(--accent)' : 'var(--text)',
              background: !trimmedValue ? 'var(--accent-soft)' : 'transparent',
              transition: 'background-color 0.12s ease',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={(e) => {
              if (trimmedValue) e.currentTarget.style.backgroundColor = 'var(--surface-2)';
            }}
            onMouseLeave={(e) => {
              if (trimmedValue) e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <span>None</span>
            {!trimmedValue && (
              <Check size={14} style={{ color: 'var(--accent)', strokeWidth: 2.5 }} />
            )}
          </div>

          {/* VPN Presets list */}
          {filteredEmojis.map((opt) => {
            const isSelected = trimmedValue === opt.id;

            return (
              <div
                key={opt.id}
                onClick={() => handleSelect(opt.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '14px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '13px',
                  cursor: 'pointer',
                  fontWeight: isSelected ? 600 : 400,
                  color: isSelected ? 'var(--accent)' : 'var(--text)',
                  background: isSelected ? 'var(--accent-soft)' : 'transparent',
                  transition: 'background-color 0.12s ease',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--surface-2)';
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <span>{opt.name}</span>
                {isSelected && (
                  <Check size={14} style={{ color: 'var(--accent)', strokeWidth: 2.5 }} />
                )}
              </div>
            );
          })}

          {filteredEmojis.length === 0 && !isCustomQuery && (
            <div
              style={{
                padding: '10px 12px',
                fontSize: '12px',
                color: 'var(--muted)',
                textAlign: 'center',
              }}
            >
              No matching VPN emojis
            </div>
          )}
        </div>
      )}
    </div>
  );
}
