'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Sparkles, X } from 'lucide-react';
import { api } from '@/lib/api';

export interface EmojiItem {
  name: string;
  id: string;
  category?: string;
  is_system?: boolean;
}

// Verified Telegram VPN Custom Emojis (default built-in fallback)
export const PRESET_EMOJIS: EmojiItem[] = [
  { name: 'NordVPN', id: '5796345694969140339', category: 'VPN', is_system: true },
  { name: 'ExpressVPN', id: '5796153709931009517', category: 'VPN', is_system: true },
  { name: 'Surfshark', id: '5796592771552777710', category: 'VPN', is_system: true },
  { name: 'Proton VPN', id: '5794298344188678751', category: 'VPN', is_system: true },
  { name: 'CyberGhost', id: '5796309230696797985', category: 'VPN', is_system: true },
  { name: 'HMA VPN', id: '5796595022115639741', category: 'VPN', is_system: true },
  { name: 'Bitdefender', id: '5793973558761756143', category: 'VPN', is_system: true },
  { name: 'Windscribe', id: '5794045349140108622', category: 'VPN', is_system: true },
  { name: 'PureVPN', id: '5794156713347126602', category: 'VPN', is_system: true },
  { name: 'Turbo VPN', id: '5796633857209931262', category: 'VPN', is_system: true },
  { name: 'PotatoVPN', id: '5796403831646458962', category: 'VPN', is_system: true },
  { name: 'PandaVPN', id: '5796561774773801876', category: 'VPN', is_system: true },
  { name: 'IPVanish', id: '5796381996032725483', category: 'VPN', is_system: true },
  { name: 'X-VPN', id: '5794376731636798062', category: 'VPN', is_system: true },

  // Payment Methods
  { name: 'bKash', id: '6217678000977089090', category: 'Payment', is_system: true },
  { name: 'Nagad', id: '6217625168584380551', category: 'Payment', is_system: true },
  { name: 'Rocket', id: '4911601033496494993', category: 'Payment', is_system: true },
  { name: 'Binance', id: '5348212415077064131', category: 'Payment', is_system: true },
  { name: 'Bybit', id: '5348372939479751825', category: 'Payment', is_system: true },

  // Services & Platforms
  { name: 'ChatGPT', id: '5453962468478962129', category: 'Services', is_system: true },
  { name: 'Gemini', id: '5262838511161076891', category: 'Services', is_system: true },
  { name: 'YouTube', id: '5796637619601283518', category: 'Services', is_system: true },
  { name: 'Spotify', id: '5796304385973686816', category: 'Services', is_system: true },
  { name: 'TradingView', id: '5796502474160346077', category: 'Services', is_system: true },
  { name: 'Netflix', id: '5796522630441867305', category: 'Services', is_system: true },
  { name: 'ChatGPT (Icon)', id: '5796185041717433060', category: 'Services', is_system: true },
  { name: 'Canva', id: '5796214303329620386', category: 'Services', is_system: true },
  { name: 'Disney+', id: '5794147784110117479', category: 'Services', is_system: true },
  { name: 'Crunchyroll', id: '5796297333637387376', category: 'Services', is_system: true },
  { name: 'Telegram (Badge)', id: '6264777724741556322', category: 'Services', is_system: true },
  { name: 'CapCut', id: '5244855659186383242', category: 'Services', is_system: true },
  { name: 'YouTube (Alt)', id: '5334769042886533147', category: 'Services', is_system: true },
  { name: 'Newspaper', id: '5336879280578138635', category: 'Services', is_system: true },
  { name: 'Telegram (Plane)', id: '5269215244810491516', category: 'Services', is_system: true },
];

export const VPN_EMOJIS = PRESET_EMOJIS;

let cachedLibrary: EmojiItem[] | null = null;
let fetchPromise: Promise<EmojiItem[]> | null = null;

export function invalidateEmojiCache() {
  cachedLibrary = null;
}

async function fetchLibraryEmojis(): Promise<EmojiItem[]> {
  if (cachedLibrary) return cachedLibrary;
  if (fetchPromise) return fetchPromise;

  fetchPromise = (async () => {
    try {
      const res = await api.emojis();
      const list: EmojiItem[] = (res.all || []).map((item) => ({
        name: item.name,
        id: item.emoji_id,
        category: item.category,
        is_system: item.is_system,
      }));
      cachedLibrary = list;
      return list;
    } catch {
      return PRESET_EMOJIS;
    } finally {
      fetchPromise = null;
    }
  })();

  return fetchPromise;
}

interface EmojiPickerProps {
  value?: string;
  onChange: (id: string) => void;
}

export function EmojiPicker({ value = '', onChange }: EmojiPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [emojis, setEmojis] = useState<EmojiItem[]>(cachedLibrary || PRESET_EMOJIS);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load from API on mount
  useEffect(() => {
    let active = true;
    void fetchLibraryEmojis().then((list) => {
      if (active && list && list.length > 0) {
        setEmojis(list);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const trimmedValue = value ? String(value).trim() : '';

  // Matched emoji item if any
  const matchedEmoji = useMemo(() => {
    if (!trimmedValue) return null;
    return emojis.find((p) => p.id === trimmedValue);
  }, [emojis, trimmedValue]);

  // Display text in the input box:
  // When typing: show query.
  // When not typing: show emoji name, or custom ID, or empty.
  const displayValue = isTyping
    ? query
    : matchedEmoji
    ? matchedEmoji.name
    : trimmedValue;

  // Filter emojis based on query
  const filteredEmojis = useMemo(() => {
    if (!isTyping || !query.trim()) return emojis;
    const q = query.trim().toLowerCase();
    return emojis.filter(
      (item) => item.name.toLowerCase().includes(q) || item.id.includes(q) || (item.category && item.category.toLowerCase().includes(q))
    );
  }, [emojis, isTyping, query]);

  // Is typed query a custom ID or something not matching presets
  const isCustomQuery = useMemo(() => {
    if (!isTyping || !query.trim()) return false;
    const q = query.trim().toLowerCase();
    return !emojis.some(
      (item) => item.name.toLowerCase() === q || item.id === query.trim()
    );
  }, [emojis, isTyping, query]);

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

  const handleBoxClick = (e: React.MouseEvent) => {
    if (e.target === inputRef.current) {
      if (!isOpen) {
        setIsOpen(true);
      }
      return;
    }

    setIsOpen((prev) => {
      const next = !prev;
      if (next) {
        setTimeout(() => inputRef.current?.focus(), 10);
      }
      return next;
    });
  };

  return (
    <div
      ref={containerRef}
      className="emoji-combobox-wrap"
      style={{
        position: 'relative',
        width: '100%',
        minWidth: 0,
        zIndex: isOpen ? 100 : 1,
        userSelect: 'none',
      }}
    >
      <span
        style={{
          fontSize: '12.5px',
          fontWeight: 600,
          color: 'var(--text-dim)',
          marginBottom: '5px',
          display: 'block',
          userSelect: 'none',
        }}
      >
        Custom Emoji <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
      </span>

      {/* Styled Box matching CustomSelect */}
      <div
        className="emoji-input-box"
        onClick={handleBoxClick}
        style={{
          width: '100%',
          minHeight: '40px',
          height: '40px',
          padding: '0 10px 0 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          background: '#fbfcfb',
          border: `1px solid ${isOpen ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          outline: 'none',
          boxShadow: isOpen
            ? '0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent)'
            : 'none',
          transition: 'border-color 120ms ease, box-shadow 120ms ease',
          boxSizing: 'border-box',
          userSelect: 'none',
        }}
      >
        <input
          ref={inputRef}
          type="text"
          className="emoji-combobox-field"
          value={displayValue}
          placeholder="Select icon or enter custom ID..."
          onClick={(e) => {
            e.stopPropagation();
            if (!isOpen) {
              setIsOpen(true);
            }
          }}
          onFocus={() => {
            if (!isOpen) {
              setIsOpen(true);
            }
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
                const match = emojis.find(
                  (p) => p.name.toLowerCase() === query.trim().toLowerCase()
                );
                handleSelect(match ? match.id : query.trim());
              }
            } else if (e.key === 'Escape') {
              e.preventDefault();
              setIsOpen(false);
              setIsTyping(false);
              setQuery('');
            }
          }}
          style={{ cursor: 'text', userSelect: 'text' }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0, userSelect: 'none' }}>
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

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--muted)',
              pointerEvents: 'none',
            }}
          >
            <ChevronDown
              size={14}
              style={{
                transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                transform: isOpen ? 'rotate(180deg)' : 'none',
              }}
            />
          </div>
        </div>
      </div>

      {/* Floating Popover Menu matching CustomSelect */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 5px)',
            left: 0,
            right: 0,
            width: '100%',
            maxHeight: '280px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            boxShadow: '0 12px 36px -4px rgba(0, 0, 0, 0.16), 0 4px 12px -2px rgba(0, 0, 0, 0.06)',
            padding: '5px',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
          }}
        >
          <div className="emoji-dropdown-scroll" style={{ maxHeight: '270px', overflowY: 'auto' }}>
            {/* If user typed a custom ID / text not in list */}
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
                  boxSizing: 'border-box',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  Use custom ID: &ldquo;{query.trim()}&rdquo;
                </span>
                <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 'normal', flexShrink: 0 }}>
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
                boxSizing: 'border-box',
                userSelect: 'none',
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
                <Check size={14} style={{ color: 'var(--accent)', strokeWidth: 2.5, flexShrink: 0 }} />
              )}
            </div>

            {/* Emoji List */}
            {filteredEmojis.map((opt) => {
              const isSelected = trimmedValue === opt.id;
              const isCustom = opt.category === 'Custom' || !opt.is_system;

              return (
                <div
                  key={`${opt.category || 'all'}-${opt.id}`}
                  onClick={() => handleSelect(opt.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '10px',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '13px',
                    cursor: 'pointer',
                    fontWeight: isSelected ? 600 : 400,
                    color: isSelected ? 'var(--accent)' : 'var(--text)',
                    background: isSelected ? 'var(--accent-soft)' : 'transparent',
                    transition: 'background-color 0.12s ease',
                    whiteSpace: 'nowrap',
                    boxSizing: 'border-box',
                    userSelect: 'none',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--surface-2)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, overflow: 'hidden' }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {opt.name}
                    </span>
                    <span
                      style={{
                        fontSize: '10px',
                        padding: '1px 6px',
                        borderRadius: '999px',
                        fontWeight: 600,
                        background: isCustom
                          ? 'color-mix(in srgb, var(--accent) 15%, transparent)'
                          : 'var(--surface-2)',
                        color: isCustom ? 'var(--accent)' : 'var(--muted)',
                        flexShrink: 0,
                      }}
                    >
                      {opt.category || (isCustom ? 'Custom' : 'Preset')}
                    </span>
                  </div>
                  {isSelected && (
                    <Check size={14} style={{ color: 'var(--accent)', strokeWidth: 2.5, flexShrink: 0 }} />
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
                No matching emojis found
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
