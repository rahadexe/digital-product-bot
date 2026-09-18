'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search, ShieldCheck, X } from 'lucide-react';

export interface EmojiItem {
  name: string;
  id: string;
}

// Verified official VPN custom emojis from Telegram pack (clean names, no keyboard emojis)
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

interface EmojiPickerProps {
  value?: string;
  onChange: (id: string) => void;
}

export function EmojiPicker({ value = '', onChange }: EmojiPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const trimmedValue = value.trim();

  // Matched preset item if any
  const matchedPreset = useMemo(() => {
    if (!trimmedValue) return null;
    return PRESET_EMOJIS.find((p) => p.id === trimmedValue);
  }, [trimmedValue]);

  // Filter emojis based on search query
  const filteredEmojis = useMemo(() => {
    if (!search.trim()) return PRESET_EMOJIS;
    const q = search.trim().toLowerCase();
    return PRESET_EMOJIS.filter(
      (item) => item.name.toLowerCase().includes(q) || item.id.includes(q)
    );
  }, [search]);

  // Close dropdown on outside click
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

  // Focus search input when opening
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    } else {
      setSearch('');
    }
  }, [isOpen]);

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%' }}>
      {/* Label */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
          Custom Emoji <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
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
          {matchedPreset ? (
            <>
              <ShieldCheck size={15} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <strong style={{ color: 'var(--text)', fontWeight: 600 }}>{matchedPreset.name}</strong>
              <code style={{ fontSize: '11px', color: 'var(--muted)', background: 'var(--surface-2)', padding: '1px 5px', borderRadius: '4px' }}>
                {matchedPreset.id.slice(-6)}…
              </code>
            </>
          ) : trimmedValue ? (
            <>
              <ShieldCheck size={15} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <span style={{ color: 'var(--text)' }}>Custom ID: {trimmedValue}</span>
            </>
          ) : (
            <span style={{ color: 'var(--muted)' }}>Select VPN Emoji…</span>
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

      {/* Floating Dropdown Popover */}
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
            gap: '8px',
            maxHeight: '280px',
            animation: 'rise-in 140ms ease',
          }}
        >
          {/* Search Bar inside Dropdown */}
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
              ref={searchInputRef}
              type="text"
              placeholder="Search VPN (Nord, Express, Surfshark)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                height: '30px',
                padding: '4px 8px 4px 28px',
                fontSize: '12px',
                borderRadius: '6px',
                background: 'var(--surface-2)',
                border: '1px solid var(--line-strong)',
              }}
            />
          </div>

          {/* Options List */}
          <div
            style={{
              overflowY: 'auto',
              maxHeight: '160px',
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
            }}
          >
            {/* Clear / Default Option */}
            <button
              type="button"
              onClick={() => {
                onChange('');
                setIsOpen(false);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '7px 10px',
                fontSize: '12px',
                borderRadius: '6px',
                border: 'none',
                background: !trimmedValue ? 'var(--accent-soft)' : 'transparent',
                color: !trimmedValue ? 'var(--accent)' : 'var(--muted)',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <span>None (Standard Icon)</span>
              {!trimmedValue ? <Check size={13} /> : null}
            </button>

            {filteredEmojis.map((item) => {
              const isSelected = trimmedValue === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onChange(item.id);
                    setIsOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '7px 10px',
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
                    <ShieldCheck size={13} style={{ color: isSelected ? 'var(--accent)' : 'var(--muted)', flexShrink: 0 }} />
                    <span>{item.name}</span>
                  </div>
                  {isSelected ? <Check size={14} style={{ color: 'var(--accent)' }} /> : null}
                </button>
              );
            })}

            {filteredEmojis.length === 0 ? (
              <div style={{ padding: '8px', textAlign: 'center', fontSize: '12px', color: 'var(--muted)' }}>
                No VPN matches &quot;{search}&quot;
              </div>
            ) : null}
          </div>

          {/* Custom ID input at bottom */}
          <div
            style={{
              borderTop: '1px solid var(--line)',
              paddingTop: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <input
              type="text"
              placeholder="Or paste custom Telegram ID..."
              value={trimmedValue}
              onChange={(e) => onChange(e.target.value.trim())}
              style={{
                flex: 1,
                height: '28px',
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '4px',
                fontFamily: 'var(--mono)',
              }}
            />
            {trimmedValue && !matchedPreset ? (
              <button
                type="button"
                className="mini btn"
                style={{ fontSize: '11px', height: '28px', padding: '0 8px' }}
                onClick={() => setIsOpen(false)}
              >
                Done
              </button>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
