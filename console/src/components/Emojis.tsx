'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Copy, Lock, Plus, RefreshCw, Search, Sparkles, Trash2 } from 'lucide-react';
import { api, type EmojiLibraryItem, type EmojiLibraryResponse } from '@/lib/api';
import { errorText, Modal, useConfirm, type Say } from './ui';
import { invalidateEmojiCache } from './EmojiPicker';

export function Emojis({ say }: { say: Say }) {
  const [data, setData] = useState<EmojiLibraryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [filterTab, setFilterTab] = useState<'all' | 'custom' | 'vpn' | 'system'>('all');
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [form, setForm] = useState({ name: '', emoji_id: '' });
  const [saving, setSaving] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.emojis();
      setData(res);
    } catch (cause) {
      say(errorText(cause), 'bad');
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
      `This will remove the custom emoji ID '${item.emoji_id}' from your library.`,
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
    return data.all || [...(data.custom || []), ...(data.system || [])];
  }, [data]);

  const vpnCount = useMemo(() => {
    return allItems.filter((i) => i.category === 'VPN').length;
  }, [allItems]);

  const systemCount = useMemo(() => {
    return allItems.filter((i) => i.category === 'System').length;
  }, [allItems]);

  const customCount = useMemo(() => {
    return (data?.custom || []).length;
  }, [data]);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allItems.filter((item) => {
      // Tab filter
      if (filterTab === 'custom' && item.is_system) return false;
      if (filterTab === 'vpn' && item.category !== 'VPN') return false;
      if (filterTab === 'system' && item.category !== 'System') return false;

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

      {/* Top Metric Cards */}
      <div className="stat-cards-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginBottom: '16px' }}>
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Emojis</span>
            <Sparkles className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{allItems.length}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Custom Added</span>
            <Sparkles className="stat-card-icon" style={{ color: 'var(--accent)' }} />
          </div>
          <div className="stat-card-value" style={{ color: 'var(--accent)' }}>{customCount}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Built-in Presets</span>
            <Lock className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{vpnCount + systemCount}</div>
        </div>
      </div>

      <div className="panel">
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h2>Emoji Library</h2>
          </div>
          <div className="actions">
            <button
              type="button"
              className="mini ghost"
              onClick={() => void load()}
              disabled={loading}
              title="Refresh"
            >
              <RefreshCw size={13} className={loading ? 'spin' : ''} />
            </button>
            <button
              type="button"
              className="btn mini"
              onClick={() => setAddModalOpen(true)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            >
              <Plus size={13} />
              Add Emoji
            </button>
          </div>
        </header>

        <div className="panel-body stack" style={{ gap: '14px' }}>
          {/* Search and Category Filter Tabs */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
            {/* Filter Tabs */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className={`mini ${filterTab === 'all' ? 'btn' : 'ghost'}`}
                onClick={() => setFilterTab('all')}
              >
                All ({allItems.length})
              </button>
              <button
                type="button"
                className={`mini ${filterTab === 'custom' ? 'btn' : 'ghost'}`}
                onClick={() => setFilterTab('custom')}
              >
                Custom ({customCount})
              </button>
              <button
                type="button"
                className={`mini ${filterTab === 'vpn' ? 'btn' : 'ghost'}`}
                onClick={() => setFilterTab('vpn')}
              >
                VPN ({vpnCount})
              </button>
              <button
                type="button"
                className={`mini ${filterTab === 'system' ? 'btn' : 'ghost'}`}
                onClick={() => setFilterTab('system')}
              >
                System ({systemCount})
              </button>
            </div>

            {/* Search Input */}
            <div style={{ position: 'relative', width: '260px', maxWidth: '100%' }}>
              <Search
                size={13}
                style={{
                  position: 'absolute',
                  left: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--muted)',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="text"
                placeholder="Search name or ID..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  paddingLeft: '30px',
                  paddingRight: '10px',
                  paddingBlock: '6px',
                  fontSize: '13px',
                }}
              />
            </div>
          </div>

          {/* Emojis Table */}
          <div className="scroll" style={{ border: '1px solid var(--border)', borderRadius: '8px' }}>
            <table>
              <thead>
                <tr>
                  <th>Emoji Name</th>
                  <th>Category</th>
                  <th>Type</th>
                  <th>Telegram Custom Emoji ID</th>
                  <th style={{ textAlign: 'right', width: '90px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="empty" style={{ textAlign: 'center', padding: '24px', color: 'var(--muted)' }}>
                      {search ? 'No matching emojis found.' : 'No emojis available.'}
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((item) => (
                    <tr key={item.emoji_id}>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text)' }}>
                          {item.name}
                        </div>
                      </td>
                      <td>
                        <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                          {item.category || 'General'}
                        </span>
                      </td>
                      <td>
                        {item.is_system ? (
                          <span className="pill" style={{ background: 'var(--surface-2)', color: 'var(--muted)' }}>
                            Built-in
                          </span>
                        ) : (
                          <span className="pill good">Custom</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => copyId(item.emoji_id)}
                          title="Click to copy Emoji ID"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            background: 'var(--surface-2)',
                            border: '1px solid var(--border)',
                            borderRadius: '6px',
                            padding: '3px 8px',
                            fontSize: '12.5px',
                            fontFamily: 'var(--mono)',
                            color: 'var(--text)',
                            cursor: 'pointer',
                          }}
                        >
                          <code>{item.emoji_id}</code>
                          {copiedId === item.emoji_id ? (
                            <Check size={12} style={{ color: '#059669' }} />
                          ) : (
                            <Copy size={12} style={{ color: 'var(--muted)' }} />
                          )}
                        </button>
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {item.is_system ? (
                          <span
                            title="Protected system emoji (cannot be edited or deleted)"
                            style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--muted)', padding: '4px 8px' }}
                          >
                            <Lock size={13} />
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="mini ghost"
                            onClick={() => void handleDelete(item)}
                            title="Delete custom emoji"
                            style={{ padding: '4px 6px', color: 'var(--danger)' }}
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
        </div>
      </div>

      {/* Add Emoji Modal */}
      {addModalOpen && (
        <Modal
          title="Add Custom Emoji"
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
                {saving ? 'Saving...' : 'Add Emoji'}
              </button>
            </>
          }
        >
          <div className="stack" style={{ gap: '14px' }}>
            <label className="field">
              <span>Emoji Name</span>
              <input
                type="text"
                required
                autoFocus
                placeholder="e.g. Netflix, Spotify, Disney+"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
              <small>Display name to recognize this emoji in selector</small>
            </label>

            <label className="field">
              <span>Telegram Custom Emoji ID</span>
              <input
                type="text"
                required
                placeholder="e.g. 5379742233853451967"
                value={form.emoji_id}
                onChange={(e) => setForm((p) => ({ ...p, emoji_id: e.target.value }))}
              />
              <small>Numeric Telegram Document ID of the custom emoji</small>
            </label>
          </div>
        </Modal>
      )}
    </>
  );
}
