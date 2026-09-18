'use client';

import { useMemo, useState } from 'react';
import { Check, Search, X } from 'lucide-react';

export interface EmojiItem {
  name: string;
  id: string;
  icon: string;
  category: 'VPN' | 'AI' | 'Streaming' | 'Proxy' | 'Payment' | 'Navigation';
}

export const PRESET_EMOJIS: EmojiItem[] = [
  // VPNs
  { name: 'NordVPN', id: '5796345694969140339', icon: '🏔️', category: 'VPN' },
  { name: 'ExpressVPN', id: '5796153709931009517', icon: '🔴', category: 'VPN' },
  { name: 'Surfshark', id: '5796592771552777710', icon: '🦈', category: 'VPN' },
  { name: 'Proton VPN', id: '5794298344188678751', icon: '🛡️', category: 'VPN' },
  { name: 'CyberGhost', id: '5796309230696797985', icon: '👻', category: 'VPN' },
  { name: 'HMA VPN', id: '5796595022115639741', icon: '🕶️', category: 'VPN' },
  { name: 'Bitdefender', id: '5793973558761756143', icon: '🛡️', category: 'VPN' },
  { name: 'IPVanish', id: '5796567478490371776', icon: '🔒', category: 'VPN' },
  { name: 'Windscribe', id: '5794045349140108622', icon: '🟢', category: 'VPN' },
  { name: 'PureVPN', id: '5794156713347126602', icon: '🟣', category: 'VPN' },
  { name: 'Turbo VPN', id: '5796633857209931262', icon: '🟠', category: 'VPN' },
  { name: 'AdGuard', id: '5796674118233363546', icon: '✈️', category: 'VPN' },
  { name: 'PotatoVPN', id: '5796403831646458962', icon: '🟡', category: 'VPN' },
  { name: 'PandaVPN', id: '5796561774773801876', icon: '🐼', category: 'VPN' },
  { name: 'VyprVPN', id: '5796381996032725483', icon: '🦎', category: 'VPN' },
  { name: 'X-VPN', id: '5794376731636798062', icon: '⬜', category: 'VPN' },

  // AI & Dev Tools
  { name: 'ChatGPT Plus', id: '6084700423308975252', icon: '🤖', category: 'AI' },
  { name: 'Claude Pro', id: '5278628322769654561', icon: '🧠', category: 'AI' },
  { name: 'Google Gemini', id: '5325547803936572038', icon: '✨', category: 'AI' },
  { name: 'Midjourney', id: '5190751148704833975', icon: '🎨', category: 'AI' },
  { name: 'GitHub Copilot', id: '6251457360414382759', icon: '💻', category: 'AI' },
  { name: 'Canva Pro', id: '5352552689983067014', icon: '✨', category: 'AI' },

  // Streaming & Media
  { name: 'Telegram Premium', id: '6082362698379565136', icon: '⭐', category: 'Streaming' },
  { name: 'Netflix UHD', id: '5960740614810112719', icon: '🍿', category: 'Streaming' },
  { name: 'Spotify Premium', id: '5463107823946717464', icon: '🎵', category: 'Streaming' },
  { name: 'YouTube Premium', id: '5264919878082509254', icon: '📺', category: 'Streaming' },
  { name: 'CapCut Pro', id: '5269514462297104098', icon: '🎬', category: 'Streaming' },
  { name: 'Mail Box', id: '5253742260054409879', icon: '✉️', category: 'Streaming' },

  // Proxies & Network
  { name: 'Residential Proxy', id: '5334590977837403844', icon: '🌐', category: 'Proxy' },
  { name: 'Residential Proxy 5GB', id: '5336972142066047577', icon: '🌐', category: 'Proxy' },
  { name: 'ISP Static Proxy', id: '6084566793991494246', icon: '⚡', category: 'Proxy' },
  { name: '4G/5G Mobile Proxy', id: '5355208818017999139', icon: '📱', category: 'Proxy' },
  { name: 'Datacenter Proxy', id: '5352597830089347330', icon: '🚀', category: 'Proxy' },

  // Payment & Banking
  { name: 'Deposit / bKash / Nagad', id: '6233367447789899509', icon: '💰', category: 'Payment' },
  { name: 'Card / Bank Pay', id: '6102735781258861018', icon: '💳', category: 'Payment' },
  { name: 'Binance Pay / Crypto', id: '6251368935627692476', icon: '🪙', category: 'Payment' },
  { name: 'Instant Pay (ZiniPay)', id: '6084566793991494246', icon: '⚡', category: 'Payment' },
  { name: 'Cash / Money', id: '5956180995924300841', icon: '💵', category: 'Payment' },
  { name: 'Spent Balance', id: '5348469219761626211', icon: '💸', category: 'Payment' },
  { name: 'Golden Money Bag', id: '5798411690202632933', icon: '💰', category: 'Payment' },
  { name: 'Golden Crypto Coin', id: '5798751117173068169', icon: '🪙', category: 'Payment' },

  // Navigation & System
  { name: 'Shop / Products', id: '6084664543152183861', icon: '🛍️', category: 'Navigation' },
  { name: 'Shopping Cart', id: '6102911544205515696', icon: '🛒', category: 'Navigation' },
  { name: 'Refer & Earn', id: '5379742233853451967', icon: '🔗', category: 'Navigation' },
  { name: 'Orders History', id: '6084747049473940188', icon: '🎁', category: 'Navigation' },
  { name: 'My Profile', id: '5208604387156448480', icon: '👤', category: 'Navigation' },
  { name: 'VIP Diamond', id: '6084472820107057290', icon: '💎', category: 'Navigation' },
  { name: 'Premium Crown', id: '6102443543094105763', icon: '👑', category: 'Navigation' },
  { name: 'Support Help', id: '5438511323631609540', icon: '🎧', category: 'Navigation' },
  { name: 'Channel Updates', id: '6082236434930998087', icon: '📢', category: 'Navigation' },
  { name: 'Reseller Panel', id: '5312361253610475399', icon: '💼', category: 'Navigation' },
  { name: 'Lock / Key', id: '6105118564690172709', icon: '🔐', category: 'Navigation' },
  { name: 'Timer / Clock', id: '5386367538735104399', icon: '⌛', category: 'Navigation' },
];

const CATEGORIES = [
  { key: 'all', label: 'All' },
  { key: 'VPN', label: 'VPNs' },
  { key: 'AI', label: 'AI Tools' },
  { key: 'Streaming', label: 'Streaming' },
  { key: 'Proxy', label: 'Proxies' },
  { key: 'Payment', label: 'Payment' },
  { key: 'Navigation', label: 'Menu & Nav' },
] as const;

interface EmojiPickerProps {
  value?: string;
  onChange: (id: string) => void;
}

export function EmojiPicker({ value = '', onChange }: EmojiPickerProps) {
  const [selectedCat, setSelectedCat] = useState<string>('all');
  const [search, setSearch] = useState('');

  const trimmedValue = value.trim();

  // Find currently matched preset if any
  const matchedPreset = useMemo(() => {
    if (!trimmedValue) return null;
    return PRESET_EMOJIS.find((p) => p.id === trimmedValue);
  }, [trimmedValue]);

  // Filter emojis based on category and search query
  const filteredEmojis = useMemo(() => {
    return PRESET_EMOJIS.filter((item) => {
      if (selectedCat !== 'all' && item.category !== selectedCat) {
        return false;
      }
      if (search.trim()) {
        const q = search.trim().toLowerCase();
        return item.name.toLowerCase().includes(q) || item.id.includes(q);
      }
      return true;
    });
  }, [selectedCat, search]);

  return (
    <div className="emoji-picker-container" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {/* Header with Selected Badge & Clear Button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
            Telegram Custom Emoji
          </span>
          <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 'normal' }}>
            (Optional)
          </span>
        </div>

        {trimmedValue ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '999px',
                background: 'var(--accent-soft)',
                color: 'var(--accent)',
                fontWeight: 600,
                border: '1px solid rgba(15, 118, 110, 0.2)',
              }}
            >
              <span>{matchedPreset ? matchedPreset.icon : '✨'}</span>
              <span>{matchedPreset ? matchedPreset.name : 'Custom ID'}</span>
            </span>
            <button
              type="button"
              className="mini ghost"
              style={{ fontSize: '11px', color: 'var(--danger)', padding: '2px 6px', display: 'inline-flex', alignItems: 'center', gap: '2px' }}
              onClick={() => onChange('')}
              title="Clear Emoji"
            >
              <X size={12} /> Clear
            </button>
          </div>
        ) : null}
      </div>

      {/* Filter Tabs & Quick Search */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', flex: 1 }}>
          {CATEGORIES.map((cat) => {
            const isCatActive = selectedCat === cat.key;
            return (
              <button
                key={cat.key}
                type="button"
                className={`mini ${isCatActive ? 'btn' : 'ghost'}`}
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: '6px',
                  lineHeight: '1.2',
                }}
                onClick={() => setSelectedCat(cat.key)}
              >
                {cat.label}
              </button>
            );
          })}
        </div>

        <div style={{ position: 'relative', width: '130px' }}>
          <Search size={12} style={{ position: 'absolute', left: 7, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
          <input
            type="text"
            placeholder="Search icon..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              padding: '3px 6px 3px 24px',
              fontSize: '11px',
              borderRadius: '6px',
              width: '100%',
              height: '26px',
            }}
          />
        </div>
      </div>

      {/* 1-Click Emoji Grid */}
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
              key={`${item.category}-${item.id}`}
              type="button"
              onClick={() => onChange(isSelected ? '' : item.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '5px 8px',
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
            No icons match &quot;{search}&quot;
          </div>
        ) : null}
      </div>

      {/* Manual ID Input (Fallback / Custom Sticker ID) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <input
          type="text"
          placeholder="e.g. 5796345694969140339 (or paste any Telegram Emoji ID)"
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
