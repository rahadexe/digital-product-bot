'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Copy, Lock, Plus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { api, type EmojiLibraryItem, type EmojiLibraryResponse } from '@/lib/api';
import { errorText, Modal, useConfirm, type Say } from './ui';
import { invalidateEmojiCache } from './EmojiPicker';

export function Emojis({ say }: { say: Say }) {
  const [data, setData] = useState<EmojiLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterTab, setFilterTab] = useState<'all' | 'custom' | 'system'>('all');
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [form, setForm] = useState({ name: '', emoji_id: '' });
  const [saving, setSaving] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await api.emojis();
      setData(res);
    } catch (cause) {
      const message = errorText(cause);
      setLoadError(message);
      say(message, 'bad');
    } finally {
      setLoading(false);
    }
  }, [say]);

  useEffect(() => {
    void load();
  }, [load]);

  const copyId = (id: string) => {
    void navigator.clipboard.writeText(id);
    setCopiedId(id);
    say('Emoji ID copied to clipboard.');
    setTimeout(() => setCopiedId(null), 1500);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.emoji_id.trim()) return;

    setSaving(true);
    try {
      await api.createEmoji({
        name: form.name.trim(),
        emoji_id: form.emoji_id.trim(),
      });
      say(`Added custom emoji '${form.name.trim()}'.`);
      invalidateEmojiCache();
      setAddModalOpen(false);
      setForm({ name: '', emoji_id: '' });
      void load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: EmojiLibraryItem) => {
    if (item.is_system) return;
    const confirmed = await confirm(
      `Delete Emoji '${item.name}'?`,
      `This will remove the emoji ID '${item.emoji_id}' from your library.`,
      'Delete',
      true,
    );
    if (!confirmed) return;

    try {
      await api.deleteEmoji(item.id || item.emoji_id);
      invalidateEmojiCache();
      say(`Deleted emoji '${item.name}'.`);
      void load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  };

  const allItems = useMemo(() => {
    if (!data) return [];
    return [...(data.system || []), ...(data.custom || [])];
  }, [data]);
  const systemCount = data?.system.length ?? 0;
  const customCount = data?.custom.length ?? 0;

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allItems.filter((item) => {
      if (filterTab === 'system' && !item.is_system) return false;
      if (filterTab === 'custom' && item.is_system) return false;

      // Search filter
      if (q) {
        return item.name.toLowerCase().includes(q) || item.emoji_id.includes(q);
      }
      return true;
    });
  }, [allItems, filterTab, search]);

  return (
    <>
      {confirmDialog}

      <section className="emoji-library panel" aria-label="Emoji library">
        <header className="emoji-library-toolbar">
          <div className="emoji-library-filters" role="group" aria-label="Filter emoji library by source">
            {(['all', 'system', 'custom'] as const).map((filter) => {
              const label = filter === 'all' ? 'All' : filter === 'system' ? 'System' : 'Custom';
              const count = filter === 'all' ? allItems.length : filter === 'system' ? systemCount : customCount;
              return (
                <button
                  key={filter}
                  type="button"
                  className={filterTab === filter ? 'active' : ''}
                  aria-pressed={filterTab === filter}
                  aria-label={`${label}: ${count} ${count === 1 ? 'emoji' : 'emojis'}`}
                  onClick={() => setFilterTab(filter)}
                >
                  {label}<span className="emoji-filter-count" aria-hidden="true">{count}</span>
                </button>
              );
            })}
          </div>

          <label className="emoji-library-search">
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              aria-label="Search emoji names or IDs"
              placeholder="Search name or ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>

          <div className="actions emoji-library-toolbar-actions">
            <button
              type="button"
              className="mini ghost emoji-refresh"
              onClick={() => void load()}
              disabled={loading}
              aria-label="Refresh emoji library"
              title="Refresh"
            >
              <RefreshCw size={13} className={loading ? 'spin' : ''} />
            </button>
            <button
              type="button"
              className="btn mini"
              onClick={() => setAddModalOpen(true)}
              aria-label="Add emoji"
              title="Add emoji"
            >
              <Plus size={13} />
              Add emoji
            </button>
          </div>
        </header>

        <div className="scroll emoji-library-scroll">
          <table className="mobile-records emoji-list">
              <thead>
                <tr>
                  <th scope="col">Emoji name</th>
                  <th scope="col">Emoji ID</th>
                  <th scope="col" className="emoji-actions-heading">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={3} className="empty emoji-library-empty">
                      <strong aria-live="polite">
                        {loading
                          ? 'Loading emojis…'
                          : loadError
                            ? 'Unable to load emojis'
                            : 'No emojis found'}
                      </strong>
                      {loadError ? (
                        <>
                          <span>{loadError}</span>
                          <button type="button" className="mini ghost" onClick={() => void load()}>
                            Retry
                          </button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((item) => (
                    <tr key={item.emoji_id}>
                      <td data-label="Emoji name">
                        <div className="emoji-library-name">
                          <strong>{item.name}</strong>
                        </div>
                      </td>
                      <td data-label="Emoji ID">
                        <button
                          type="button"
                          className="copy-chip"
                          onClick={() => copyId(item.emoji_id)}
                          aria-label={`Copy emoji ID for ${item.name}`}
                          title="Copy ID"
                        >
                          <code>{item.emoji_id}</code>
                          {copiedId === item.emoji_id ? (
                            <Check size={12} style={{ color: '#059669' }} />
                          ) : (
                            <Copy size={12} style={{ color: 'var(--muted)' }} />
                          )}
                        </button>
                      </td>
                      <td className="emoji-library-actions">
                        {item.is_system ? (
                          <span
                            className="emoji-protected"
                            title="System emoji is protected"
                            aria-label="System emoji is protected"
                          >
                            <Lock size={13} />
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="mini ghost emoji-delete"
                            onClick={() => void handleDelete(item)}
                            aria-label={`Delete custom emoji ${item.name}`}
                            title="Delete custom emoji"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
          </table>
        </div>
      </section>

      {/* Add emoji modal */}
      {addModalOpen && (
        <Modal
          title="Add emoji"
          onClose={() => setAddModalOpen(false)}
          onSubmit={handleCreate}
          footer={
            <>
              <button
                type="button"
                className="btn ghost mini"
                onClick={() => setAddModalOpen(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn mini"
                disabled={saving || !form.name.trim() || !form.emoji_id.trim()}
              >
                {saving ? 'Saving...' : 'Add emoji'}
              </button>
            </>
          }
        >
          <div className="stack" style={{ gap: '14px' }}>
            <label className="field">
              <span>Emoji name</span>
              <input
                type="text"
                required
                autoFocus
                placeholder="Netflix, Spotify, Disney+"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
            </label>

            <label className="field">
              <span>Emoji ID</span>
              <input
                type="text"
                required
                inputMode="numeric"
                placeholder="5379742233853451967"
                value={form.emoji_id}
                onChange={(e) => setForm((p) => ({ ...p, emoji_id: e.target.value }))}
              />
            </label>
          </div>
        </Modal>
      )}
    </>
  );
}
