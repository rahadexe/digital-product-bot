'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';
import { api } from '@/lib/api';

export interface EmojiItem {
  name: string;
  id: string;
  emoji?: string | null;
  is_system?: boolean;
}

export type EmojiSelection = {
  icon: string;
  customEmojiId: string;
};

export function splitLeadingEmoji(text: string): { emoji: string; text: string } {
  const trimmed = text.trimStart();
  if (!trimmed) return { emoji: '', text };
  const segments = Array.from(
    new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(trimmed)
  );
  const candidate = segments[0]?.segment || '';
  if (
    !candidate ||
    !/[\p{Extended_Pictographic}\p{Regional_Indicator}]/u.test(candidate)
  ) {
    return { emoji: '', text };
  }
  return { emoji: candidate, text: trimmed.slice(candidate.length).trimStart() };
}

// Verified Telegram custom emojis used when the library API is unavailable.
export const PRESET_EMOJIS: EmojiItem[] = [
  { name: 'NordVPN', id: '5796345694969140339', is_system: true },
  { name: 'ExpressVPN', id: '5796153709931009517', is_system: true },
  { name: 'Surfshark', id: '5796592771552777710', is_system: true },
  { name: 'Proton VPN', id: '5794298344188678751', is_system: true },
  { name: 'CyberGhost', id: '5796309230696797985', is_system: true },
  { name: 'HMA VPN', id: '5796595022115639741', is_system: true },
  { name: 'Bitdefender', id: '5793973558761756143', is_system: true },
  { name: 'Windscribe', id: '5794045349140108622', is_system: true },
  { name: 'PureVPN', id: '5794156713347126602', is_system: true },
  { name: 'Turbo VPN', id: '5796633857209931262', is_system: true },
  { name: 'PotatoVPN', id: '5796403831646458962', is_system: true },
  { name: 'PandaVPN', id: '5796561774773801876', is_system: true },
  { name: 'IPVanish', id: '5796381996032725483', is_system: true },
  { name: 'X VPN', id: '5794376731636798062', is_system: true },
  { name: 'bKash', id: '6217678000977089090', is_system: true },
  { name: 'Nagad', id: '6217625168584380551', is_system: true },
  { name: 'Rocket', id: '4911601033496494993', is_system: true },
  { name: 'Binance', id: '5348212415077064131', is_system: true },
  { name: 'Bybit', id: '5348372939479751825', is_system: true },
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
  icon?: string;
  onChange: (selection: EmojiSelection) => void;
}

export function EmojiPicker({
  value = '',
  icon = '',
  onChange,
}: EmojiPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [selectionError, setSelectionError] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const [emojis, setEmojis] = useState<EmojiItem[]>(cachedLibrary || PRESET_EMOJIS);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const activeOptionRef = useRef<HTMLButtonElement>(null);
  const inputId = useId();
  const listId = useId();

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

  const trimmedIcon = icon.trim();

  // Display text in the input box:
  // When typing: show query.
  // When not typing: show emoji name, or custom ID, or empty.
  const displayValue = isTyping
    ? query
    : trimmedIcon
    ? trimmedIcon
    : trimmedValue
    ? matchedEmoji?.name ?? 'Custom emoji'
    : '';

  const graphemes = useMemo(() => {
    const input = query.trim();
    if (!input) return [];
    return Array.from(
      new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(input)
    );
  }, [query]);
  const isBasicEmojiQuery =
    graphemes.length === 1 &&
    /[\p{Extended_Pictographic}\p{Regional_Indicator}]/u.test(query.trim());
  const isCustomIdQuery = /^\d{1,64}$/.test(query.trim());

  // Filter emojis based on query
  const filteredEmojis = useMemo(() => {
    if (!isTyping || !query.trim()) return emojis;
    const q = query.trim().toLowerCase();
    return emojis.filter((item) => item.name.toLowerCase().includes(q) || item.id.includes(q));
  }, [emojis, isTyping, query]);

  const isPresetQuery = useMemo(() => {
    const q = query.trim().toLowerCase();
    return emojis.some((item) => item.name.toLowerCase() === q || item.id === query.trim());
  }, [emojis, query]);

  const dropdownOptions = useMemo(() => {
    const options: { id: string; label: string; value: string }[] = [];
    if (isTyping && isBasicEmojiQuery && !isPresetQuery) {
      options.push({ id: 'custom-emoji', label: `Use emoji ${query.trim()}`, value: query.trim() });
    }
    if (isTyping && isCustomIdQuery && !isPresetQuery) {
      options.push({ id: 'custom-id', label: 'Use entered Telegram emoji ID', value: query.trim() });
    }
    options.push({ id: 'none', label: 'None', value: '' });
    for (const item of filteredEmojis) {
      options.push({ id: item.id, label: item.name, value: item.id });
    }
    return options;
  }, [filteredEmojis, isBasicEmojiQuery, isCustomIdQuery, isPresetQuery, isTyping, query]);

  useEffect(() => {
    if (isOpen && activeIndex >= 0) {
      activeOptionRef.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex, isOpen]);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setIsTyping(false);
        setQuery('');
        setActiveIndex(-1);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
        setIsTyping(false);
        setQuery('');
        setActiveIndex(-1);
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
    const selection = selectedId.trim();
    setSelectionError('');
    if (!selection) {
      onChange({ icon: '', customEmojiId: '' });
    } else {
      const preset = emojis.find(
        (item) =>
          item.id === selection ||
          item.name.toLowerCase() === selection.toLowerCase()
      );
      if (preset) {
        onChange({ icon: '', customEmojiId: preset.id });
      } else if (/^\d{1,64}$/.test(selection)) {
        onChange({ icon: '', customEmojiId: selection });
      } else {
        const candidateSegments = Array.from(
          new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(selection)
        );
        if (
          candidateSegments.length === 1 &&
          /[\p{Extended_Pictographic}\p{Regional_Indicator}]/u.test(selection)
        ) {
          onChange({ icon: selection, customEmojiId: '' });
        } else {
          setSelectionError('Choose one emoji, a preset, or a numeric Telegram emoji ID.');
          return;
        }
      }
    }
    setIsOpen(false);
    setIsTyping(false);
    setQuery('');
    setActiveIndex(-1);
  };

  const handleClear = () => {
    onChange({ icon: '', customEmojiId: '' });
    setSelectionError('');
    setQuery('');
    setIsTyping(false);
    setActiveIndex(-1);
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

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) setIsOpen(true);
      if (!dropdownOptions.length) return;
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setActiveIndex((current) => {
        if (current < 0) {
          if (step > 0 && query.trim()) {
            const firstMatch = dropdownOptions.findIndex((option) => option.id !== 'none');
            if (firstMatch >= 0) return firstMatch;
          }
          return step > 0 ? 0 : dropdownOptions.length - 1;
        }
        return (current + step + dropdownOptions.length) % dropdownOptions.length;
      });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const activeOption = dropdownOptions[activeIndex];
      if (activeOption) {
        handleSelect(activeOption.value);
      } else if (query.trim()) {
        const exactMatch = emojis.find(
          (item) =>
            item.name.toLowerCase() === query.trim().toLowerCase() ||
            item.id === query.trim()
        );
        if (exactMatch) {
          handleSelect(exactMatch.id);
        } else if (isBasicEmojiQuery || isCustomIdQuery || filteredEmojis.length === 0) {
          handleSelect(query.trim());
        } else {
          handleSelect(filteredEmojis[0].id);
        }
      } else {
        handleSelect('');
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      setIsOpen(false);
      setIsTyping(false);
      setQuery('');
      setActiveIndex(-1);
    } else if (e.key === 'Tab' && isOpen) {
      setIsOpen(false);
      setIsTyping(false);
      setQuery('');
      setActiveIndex(-1);
    }
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
      <label className="emoji-picker-label" htmlFor={inputId}>
        Icon <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
      </label>

      <div
        className={`emoji-input-box${isOpen ? ' open' : ''}`}
        onClick={handleBoxClick}
      >
        <input
          id={inputId}
          ref={inputRef}
          type="text"
          className="emoji-combobox-field"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          aria-controls={isOpen ? listId : undefined}
          aria-activedescendant={
            isOpen && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined
          }
          aria-invalid={selectionError ? true : undefined}
          aria-describedby={selectionError ? `${inputId}-error` : undefined}
          value={displayValue}
          placeholder="Search or paste an emoji or ID..."
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
            const input = e.target.value;
            setIsTyping(true);
            setQuery(input);
            setSelectionError('');
            setActiveIndex(-1);
            const pasted = input.trim();
            const segments = pasted
              ? Array.from(
                  new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(pasted)
                )
              : [];
            const preset = emojis.find(
              (item) =>
                item.name.toLowerCase() === pasted.toLowerCase() ||
                item.id === pasted
            );
            if (preset) {
              onChange({ icon: '', customEmojiId: preset.id });
            } else if (/^\d{1,64}$/.test(pasted)) {
              onChange({ icon: '', customEmojiId: pasted });
            } else if (
              segments.length === 1 &&
              /[\p{Extended_Pictographic}\p{Regional_Indicator}]/u.test(pasted)
            ) {
              onChange({ icon: pasted, customEmojiId: '' });
            }
            if (!isOpen) setIsOpen(true);
          }}
          onKeyDown={handleInputKeyDown}
        />

        <div className="emoji-picker-actions">
          {trimmedValue ? (
            <button
              type="button"
              className="emoji-picker-clear"
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
              onMouseDown={(e) => e.preventDefault()}
              aria-label="Clear icon selection"
              title="Clear"
            >
              <X size={14} aria-hidden="true" />
            </button>
          ) : null}

          <ChevronDown
            size={14}
            className={`emoji-picker-chevron${isOpen ? ' open' : ''}`}
            aria-hidden="true"
          />
        </div>
      </div>
      {selectionError ? (
        <small id={`${inputId}-error`} className="emoji-picker-error" role="alert">
          {selectionError}
        </small>
      ) : null}

      {isOpen && (
        <div className="emoji-dropdown">
          <div id={listId} className="emoji-dropdown-scroll" role="listbox" aria-label="Available icons">
            {dropdownOptions.map((option, index) => {
              const isSelected =
                option.id === 'none'
                  ? !trimmedValue && !trimmedIcon
                  : option.id === 'custom-emoji'
                    ? trimmedIcon === option.value
                    : trimmedValue === option.value;
              const isActive = activeIndex === index;
              return (
                <button
                  key={option.id}
                  id={`${listId}-${index}`}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  tabIndex={-1}
                  className={`custom-select-option emoji-dropdown-option${isSelected ? ' selected' : ''}${isActive ? ' active' : ''}`}
                  ref={isActive ? activeOptionRef : null}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseMove={() => setActiveIndex(index)}
                  onClick={() => handleSelect(option.value)}
                >
                  <span>{option.label}</span>
                  {isSelected ? <Check size={14} aria-hidden="true" /> : null}
                </button>
              );
            })}
            {filteredEmojis.length === 0 && !isBasicEmojiQuery && !isCustomIdQuery ? (
              <div className="emoji-dropdown-empty">No emojis found</div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
