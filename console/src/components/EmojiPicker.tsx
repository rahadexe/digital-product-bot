'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Info, Search, Sparkles, X } from 'lucide-react';

export interface EmojiPreset {
  name: string;
  id: string;
  icon: string;
  category: 'popular' | 'vpn';
}

// Complete library of verified Telegram custom emojis for store categories and VPNs
export const PRESET_EMOJIS: EmojiPreset[] = [
  // Popular Store Categories
  { name: 'VPN / Security', id: '5190447043545438788', icon: '🛡️', category: 'popular' },
  { name: 'Proxy Hub', id: '5334590977837403844', icon: '🌐', category: 'popular' },
  { name: 'Mail Box', id: '5253742260054409879', icon: '✉️', category: 'popular' },
  { name: 'Premium Crown', id: '6102443543094105763', icon: '👑', category: 'popular' },
  { name: 'VIP Diamond', id: '6084472820107057290', icon: '💎', category: 'popular' },
  { name: 'Instant / Fast', id: '6084566793991494246', icon: '⚡', category: 'popular' },
  { name: 'Products / Shop', id: '6084664543152183861', icon: '🛍️', category: 'popular' },
  { name: 'Rocket Boost', id: '5352597830089347330', icon: '🚀', category: 'popular' },
  { name: 'Hot Deals', id: '6084435123179100660', icon: '🔥', category: 'popular' },
  { name: 'Software / PC', id: '6251457360414382759', icon: '💻', category: 'popular' },
  { name: 'License Key', id: '6105118564690172709', icon: '🔐', category: 'popular' },
  { name: 'Support / Help', id: '5438511323631609540', icon: '🎧', category: 'popular' },
  { name: 'Special Star', id: '5337102391244263212', icon: '🌟', category: 'popular' },
  { name: 'Sparkles', id: '5325547803936572038', icon: '✨', category: 'popular' },

  // VPN Brands
  { name: 'NordVPN', id: '5796345694969140339', icon: '🛡️', category: 'vpn' },
  { name: 'ExpressVPN', id: '5796153709931009517', icon: '🛡️', category: 'vpn' },
  { name: 'Surfshark', id: '5796592771552777710', icon: '🦈', category: 'vpn' },
  { name: 'Proton VPN', id: '5794298344188678751', icon: '🛡️', category: 'vpn' },
  { name: 'CyberGhost', id: '5796309230696797985', icon: '👻', category: 'vpn' },
  { name: 'Windscribe', id: '5794045349140108622', icon: '🛡️', category: 'vpn' },
  { name: 'Bitdefender', id: '5793973558761756143', icon: '🛡️', category: 'vpn' },
  { name: 'HMA VPN', id: '5796595022115639741', icon: '🦙', category: 'vpn' },
  { name: 'PureVPN', id: '5794156713347126602', icon: '🛡️', category: 'vpn' },
  { name: 'Turbo VPN', id: '5796633857209931262', icon: '⚡', category: 'vpn' },
  { name: 'PotatoVPN', id: '5796403831646458962', icon: '🥔', category: 'vpn' },
  { name: 'PandaVPN', id: '5796561774773801876', icon: '🐼', category: 'vpn' },
  { name: 'VyprVPN', id: '5796381996032725483', icon: '🦎', category: 'vpn' },
  { name: 'X-VPN', id: '5794376731636798062', icon: '🛡️', category: 'vpn' },
];

// Quick 1-click chips for the most frequent categories
const QUICK_CHIPS = [
  { label: 'VPN', id: '5190447043545438788', icon: '🛡️' },
  { label: 'Proxy', id: '5334590977837403844', icon: '🌐' },
  { label: 'Mail', id: '5253742260054409879', icon: '✉️' },
  { label: 'Crown', id: '6102443543094105763', icon: '👑' },
  { label: 'VIP', id: '6084472820107057290', icon: '💎' },
  { label: 'Fast', id: '6084566793991494246', icon: '⚡' },
  { label: 'Shop', id: '6084664543152183861', icon: '🛍️' },
];

interface EmojiPickerProps {
  value?: string;
  onChange: (id: string) => void;
}

export function EmojiPicker({ value = '', onChange }: EmojiPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'popular' | 'vpn'>('all');
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const trimmedValue = value ? String(value).trim() : '';

  // Matched preset item if any
  const matchedPreset = useMemo(() => {
    if (!trimmedValue) return null;
    return PRESET_EMOJIS.find((p) => p.id === trimmedValue);
  }, [trimmedValue]);

  // Filter presets based on search and tab
  const filteredEmojis = useMemo(() => {
    const q = search.trim().toLowerCase();
    return PRESET_EMOJIS.filter((item) => {
      const matchesTab = activeTab === 'all' || item.category === activeTab;
      if (!matchesTab) return false;
      if (!q) return true;
      return (
        item.name.toLowerCase().includes(q) ||
        item.id.includes(q) ||
        item.icon.includes(q)
      );
    });
  }, [search, activeTab]);

  // Check if search query looks like a custom ID or new custom emoji
  const searchIsCustomId = useMemo(() => {
    const q = search.trim();
    if (!q) return false;
    const exists = PRESET_EMOJIS.some((p) => p.id === q || p.name.toLowerCase() === q.toLowerCase());
    return !exists;
  }, [search]);

  // Close on outside click or escape
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

  // Focus search input when popover opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    } else {
      setSearch('');
      setActiveTab('all');
    }
  }, [isOpen]);

  const selectEmoji = (id: string) => {
    onChange(id);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="emoji-picker-container">
      {/* Field Label & Clear Button */}
      <div className="emoji-picker-header">
        <span className="emoji-picker-title">
          Custom Emoji <small className="emoji-picker-optional">(Optional)</small>
        </span>
        {trimmedValue ? (
          <button
            type="button"
            className="mini ghost emoji-clear-btn"
            onClick={(e) => {
              e.stopPropagation();
              onChange('');
            }}
            title="Remove Custom Emoji"
          >
            <X size={12} /> Clear
          </button>
        ) : null}
      </div>

      {/* Main Trigger Bar */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`emoji-picker-trigger ${isOpen ? 'open' : ''} ${trimmedValue ? 'has-value' : ''}`}
        aria-expanded={isOpen}
      >
        <div className="emoji-trigger-left">
          {matchedPreset ? (
            <div className="emoji-selected-pill">
              <span className="emoji-icon-badge">{matchedPreset.icon}</span>
              <strong className="emoji-name-strong">{matchedPreset.name}</strong>
              <code className="emoji-id-tag">#{matchedPreset.id.slice(-6)}</code>
            </div>
          ) : trimmedValue ? (
            <div className="emoji-selected-pill">
              <span className="emoji-icon-badge">✨</span>
              <span className="emoji-name-strong">Custom ID:</span>
              <code className="emoji-id-tag">{trimmedValue}</code>
            </div>
          ) : (
            <div className="emoji-placeholder-wrap">
              <Sparkles size={15} className="emoji-placeholder-icon" />
              <span className="emoji-placeholder-text">Select icon or paste Telegram ID...</span>
            </div>
          )}
        </div>

        <div className="emoji-trigger-right">
          {trimmedValue ? (
            <span
              className="emoji-trigger-clear-icon"
              title="Clear"
              onClick={(e) => {
                e.stopPropagation();
                onChange('');
              }}
            >
              <X size={14} />
            </span>
          ) : null}
          <ChevronDown
            size={16}
            className={`emoji-chevron ${isOpen ? 'open' : ''}`}
          />
        </div>
      </button>

      {/* 1-Click Quick Chips Row */}
      <div className="emoji-quick-row">
        <span className="emoji-quick-label">Quick:</span>
        {QUICK_CHIPS.map((chip) => {
          const isSelected = trimmedValue === chip.id;
          return (
            <button
              key={chip.id}
              type="button"
              className={`emoji-quick-chip ${isSelected ? 'active' : ''}`}
              onClick={() => onChange(isSelected ? '' : chip.id)}
              title={`${chip.label} (${chip.icon})`}
            >
              <span className="emoji-quick-icon">{chip.icon}</span>
              <span>{chip.label}</span>
              {isSelected ? <Check size={11} className="emoji-quick-check" /> : null}
            </button>
          );
        })}
      </div>

      {/* Floating Popover Picker */}
      {isOpen && (
        <div className="emoji-popover">
          {/* Unified Search & Custom ID Input */}
          <div className="emoji-search-wrap">
            <Search size={14} className="emoji-search-icon" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Search icon or paste Telegram ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (search.trim()) {
                    selectEmoji(search.trim());
                  }
                }
              }}
              className="emoji-search-input"
            />
            {search ? (
              <button
                type="button"
                className="emoji-search-clear"
                onClick={() => setSearch('')}
              >
                <X size={13} />
              </button>
            ) : null}
          </div>

          {/* Category Tabs */}
          <div className="emoji-tabs-row">
            <button
              type="button"
              className={`emoji-tab-btn ${activeTab === 'all' ? 'active' : ''}`}
              onClick={() => setActiveTab('all')}
            >
              All ({PRESET_EMOJIS.length})
            </button>
            <button
              type="button"
              className={`emoji-tab-btn ${activeTab === 'popular' ? 'active' : ''}`}
              onClick={() => setActiveTab('popular')}
            >
              ⭐ Popular
            </button>
            <button
              type="button"
              className={`emoji-tab-btn ${activeTab === 'vpn' ? 'active' : ''}`}
              onClick={() => setActiveTab('vpn')}
            >
              🛡️ VPN Brands
            </button>
          </div>

          {/* Options Container */}
          <div className="emoji-options-scroll">
            {/* Direct Custom ID Button if user typed something */}
            {searchIsCustomId && (
              <button
                type="button"
                className="emoji-custom-apply-card"
                onClick={() => selectEmoji(search.trim())}
              >
                <div className="emoji-custom-apply-icon">✨</div>
                <div className="emoji-custom-apply-content">
                  <span className="emoji-custom-apply-title">
                    Use Telegram ID: <strong>&ldquo;{search.trim()}&rdquo;</strong>
                  </span>
                  <span className="emoji-custom-apply-hint">Click or press Enter to apply</span>
                </div>
                <span className="emoji-custom-apply-key">↵ Enter</span>
              </button>
            )}

            {/* Clear / None Option */}
            <button
              type="button"
              className={`emoji-option-card none-option ${!trimmedValue ? 'active' : ''}`}
              onClick={() => selectEmoji('')}
            >
              <div className="emoji-card-icon-box">🚫</div>
              <div className="emoji-card-text">
                <span className="emoji-card-title">None (Standard Icon)</span>
                <span className="emoji-card-sub">Default bot button style</span>
              </div>
              {!trimmedValue ? <Check size={14} className="emoji-card-check" /> : null}
            </button>

            {/* Grid of Preset Emojis */}
            <div className="emoji-grid">
              {filteredEmojis.map((item) => {
                const isSelected = trimmedValue === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`emoji-option-card ${isSelected ? 'active' : ''}`}
                    onClick={() => selectEmoji(item.id)}
                  >
                    <div className="emoji-card-icon-box">{item.icon}</div>
                    <div className="emoji-card-text">
                      <span className="emoji-card-title">{item.name}</span>
                      <span className="emoji-card-id">#{item.id.slice(-6)}</span>
                    </div>
                    {isSelected ? <Check size={14} className="emoji-card-check" /> : null}
                  </button>
                );
              })}
            </div>

            {filteredEmojis.length === 0 && !searchIsCustomId ? (
              <div className="emoji-empty-state">
                No icons found matching &quot;{search}&quot;
              </div>
            ) : null}
          </div>

          {/* Footer Note */}
          <div className="emoji-popover-footer">
            <Info size={12} className="emoji-footer-icon" />
            <span>Pastes any 64-bit Telegram custom emoji ID directly into search</span>
          </div>
        </div>
      )}
    </div>
  );
}
