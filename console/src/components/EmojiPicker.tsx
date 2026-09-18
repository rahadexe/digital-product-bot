'use client';

import { useMemo, useState } from 'react';
import { Check, Search, X } from 'lucide-react';

export interface EmojiItem {
  name: string;
  id: string;
  icon: string;
}

// Verified official VPN custom emojis from Telegram pack
export const PRESET_EMOJIS: EmojiItem[] = [
  { name: 'NordVPN', id: '5796345694969140339', icon: '🏔️' },
  { name: 'ExpressVPN', id: '5796153709931009517', icon: '🔴' },
  { name: 'Surfshark', id: '5796592771552777710', icon: '🦈' },
  { name: 'Proton VPN', id: '5794298344188678751', icon: '🛡️' },
  { name: 'CyberGhost', id: '5796309230696797985', icon: '👻' },
  { name: 'HMA VPN', id: '5796595022115639741', icon: '🕶️' },
  { name: 'Bitdefender', id: '5793973558761756143', icon: '🛡️' },
  { name: 'Windscribe', id: '5794045349140108622', icon: '🟢' },
  { name: 'PureVPN', id: '5794156713347126602', icon: '🟣' },
  { name: 'Turbo VPN', id: '5796633857209931262', icon: '🟠' },
  { name: 'PotatoVPN', id: '5796403831646458962', icon: '🟡' },
  { name: 'PandaVPN', id: '5796561774773801876', icon: '🐼' },
  { name: 'VyprVPN', id: '5796381996032725483', icon: '🦎' },
  { name: 'X-VPN', id: '5794376731636798062', icon: '⬜' },
];

interface EmojiPickerProps {
  value?: string;
  onChange: (id: string) => void;
}

export function EmojiPicker({ value = '', onChange }: EmojiPickerProps) {
  const [search, setSearch] = useState('');

  const trimmedValue = value.trim();

  // Find currently matched preset if any
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

  return (
    <div className="emoji-picker-container" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {/* Header with Title, Selected Badge & Clear Button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
            VPN Custom Emoji
          </span>
          <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 'normal' }}>
            (1-Click Select)
          </span>
        </div>

        {trimmedValue ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '999px',
                background: 'var(--accent-soft)',
                color: 'var(--accent)',
                fontWeight: 600,
                border: '1px solid rgba(15, 118, 110, 0.25)',
              }}
            >
              <span>{matchedPreset ? matchedPreset.icon : '✨'}</span>
              <span>{matchedPreset ? matchedPreset.name : 'Custom ID'}</span>
            </span>
            <button
              type="button"
              className="mini ghost"
              style={{
                fontSize: '11px',
                color: 'var(--danger)',
                padding: '2px 6px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '2px',
              }}
              onClick={() => onChange('')}
              title="Clear Emoji"
            >
              <X size={12} /> Clear
            </button>
          </div>
        ) : null}
      </div>

      {/* Quick Search */}
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
          type="text"
          placeholder="Filter VPN icons (e.g. Nord, Surfshark, Proton)..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            padding: '5px 8px 5px 28px',
            fontSize: '12px',
            borderRadius: '6px',
            width: '100%',
          }}
        />
      </div>

      {/* 1-Click VPN Emoji Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
          gap: '6px',
          maxHeight: '160px',
          overflowY: 'auto',
          padding: '6px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
        }}
      >
        {filteredEmojis.map((item) => {
          const isSelected = trimmedValue === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange(isSelected ? '' : item.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 8px',
                fontSize: '12px',
                fontWeight: isSelected ? 600 : 500,
                textAlign: 'left',
                borderRadius: '6px',
                background: isSelected ? 'var(--accent-soft)' : 'var(--surface)',
                color: isSelected ? 'var(--accent)' : 'var(--text)',
                border: isSelected ? '1px solid var(--accent)' : '1px solid var(--line-strong)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title={`${item.name} (${item.id})`}
            >
              <span style={{ fontSize: '14px', lineHeight: 1 }}>{item.icon}</span>
              <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {item.name}
              </span>
              {isSelected ? <Check size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} /> : null}
            </button>
          );
        })}

        {filteredEmojis.length === 0 ? (
          <div style={{ gridColumn: '1 / -1', padding: '12px', textAlign: 'center', color: 'var(--muted)', fontSize: '12px' }}>
            No VPN matches &quot;{search}&quot;
          </div>
        ) : null}
      </div>

      {/* Manual ID Input (Fallback for any custom ID) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <input
          type="text"
          placeholder="e.g. 5796345694969140339 (or paste custom Telegram Emoji ID)"
          value={value}
          onChange={(e) => onChange(e.target.value.trim())}
          style={{
            fontSize: '12px',
            padding: '6px 10px',
            borderRadius: '6px',
            fontFamily: 'var(--mono)',
            flex: 1,
          }}
        />
      </div>
    </div>
  );
}
