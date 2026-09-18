'use client';

import { useCallback, useEffect, useState } from 'react';
import { Bookmark, FolderTree, Layers, Pin, Plus } from 'lucide-react';
import { api, type Category } from '@/lib/api';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

type CategoryDraft = {
  id: number | null;
  name: string;
  sort_order: number;
  is_active: boolean;
  is_pinned: boolean;
  custom_emoji_id: string;
};

export function Categories({ say }: { say: Say }) {
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState<CategoryDraft | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(async () => {
    try {
      const cats = await api.categories();
      setCategories(cats);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function deleteCat(cat: Category) {
    if (!(await confirm(`Delete category "${cat.name}"?`, 'Products in this category will remain, but will become uncategorized.', 'Delete category'))) {
      return;
    }
    try {
      await api.deleteCategory(cat.id);
      say('Category deleted.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  async function togglePin(cat: Category) {
    try {
      await api.updateCategory(cat.id, {
        name: cat.name,
        sort_order: cat.sort_order,
        is_active: cat.is_active,
        is_pinned: cat.is_pinned ? 0 : 1,
        custom_emoji_id: cat.custom_emoji_id,
      });
      say(cat.is_pinned ? 'Unpinned from menu.' : '📌 Pinned to Telegram reply keyboard!');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  async function toggleActive(cat: Category) {
    try {
      await api.updateCategory(cat.id, {
        name: cat.name,
        sort_order: cat.sort_order,
        is_active: cat.is_active ? 0 : 1,
        is_pinned: cat.is_pinned,
        custom_emoji_id: cat.custom_emoji_id,
      });
      say(cat.is_active ? 'Category hidden.' : 'Category active.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  const pinnedCount = (categories ?? []).filter((c) => Boolean(c.is_pinned)).length;
  const unpinnedCount = (categories ?? []).filter((c) => !c.is_pinned).length;
  const activeCount = (categories ?? []).filter((c) => Boolean(c.is_active)).length;

  const shown = (categories ?? []).filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <>
      {confirmDialog}

      {/* Summary Stat Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Categories</span>
            <FolderTree className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{categories?.length ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Pinned to Bottom Keyboard</span>
            <Pin className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{pinnedCount}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">In Other Products</span>
            <Bookmark className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{unpinnedCount}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Active</span>
            <Layers className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{activeCount}</div>
        </div>
      </div>

      <section className="panel">
        <header>
          <div className="filters">
            <input
              type="search"
              placeholder="Search categories"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn"
            onClick={() =>
              setDraft({
                id: null,
                name: '',
                sort_order: 0,
                is_active: true,
                is_pinned: false,
                custom_emoji_id: '',
              })
            }
          >
            <Plus size={16} style={{ marginRight: 4 }} /> New category
          </button>
        </header>

        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Category Name</th>
                <th>Menu Location</th>
                <th>Telegram Emoji ID</th>
                <th>Order</th>
                <th>Status</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((cat) => (
                <tr key={cat.id}>
                  <td className="name">
                    <strong>{cat.name}</strong>
                    <small>ID: #{cat.id}</small>
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`mini ${cat.is_pinned ? 'btn' : 'ghost'}`}
                      onClick={() => togglePin(cat)}
                      style={{ fontSize: '11px', padding: '3px 10px' }}
                      title="Click to toggle between pinned keyboard and other products"
                    >
                      {cat.is_pinned ? '📌 Pinned to Menu' : '💎 In Other Products'}
                    </button>
                  </td>
                  <td>
                    {cat.custom_emoji_id ? (
                      <code style={{ fontSize: '11px', background: 'var(--subtle)', padding: '2px 6px', borderRadius: 4 }}>
                        {cat.custom_emoji_id}
                      </code>
                    ) : (
                      <span style={{ color: 'var(--muted)', fontSize: '12px' }}>Standard icon</span>
                    )}
                  </td>
                  <td>{cat.sort_order}</td>
                  <td>
                    <button
                      type="button"
                      className="mini"
                      onClick={() => toggleActive(cat)}
                      style={{ fontSize: '11px', padding: '2px 8px' }}
                    >
                      <span className={`pill ${cat.is_active ? 'good' : 'bad'}`}>
                        {cat.is_active ? 'Active' : 'Hidden'}
                      </span>
                    </button>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="mini"
                        onClick={() =>
                          setDraft({
                            id: cat.id,
                            name: cat.name,
                            sort_order: cat.sort_order,
                            is_active: Boolean(cat.is_active),
                            is_pinned: Boolean(cat.is_pinned),
                            custom_emoji_id: cat.custom_emoji_id || '',
                          })
                        }
                      >
                        Edit
                      </button>
                      <button type="button" className="mini danger" onClick={() => deleteCat(cat)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {categories && shown.length === 0 ? (
                <EmptyRow columns={6}>
                  {search ? 'Nothing matches.' : 'No categories yet. Click "New category" above.'}
                </EmptyRow>
              ) : null}
              {!categories ? <EmptyRow columns={6}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
      </section>

      {draft ? (
        <CategoryFormModal
          draft={draft}
          say={say}
          onClose={() => setDraft(null)}
          onSaved={async () => {
            setDraft(null);
            await load();
          }}
        />
      ) : null}
    </>
  );
}

function CategoryFormModal({
  draft,
  say,
  onClose,
  onSaved,
}: {
  draft: CategoryDraft;
  say: Say;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState(draft);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<CategoryDraft>) => setForm((c) => ({ ...c, ...patch }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      sort_order: form.sort_order,
      is_active: form.is_active ? 1 : 0,
      is_pinned: form.is_pinned ? 1 : 0,
      custom_emoji_id: form.custom_emoji_id ? form.custom_emoji_id.trim() : '',
    };
    try {
      if (form.id) await api.updateCategory(form.id, payload);
      else await api.createCategory(payload);
      say(form.id ? 'Category updated.' : 'Category created.');
      await onSaved();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={form.id ? 'Edit Category' : 'New Category'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={busy}>
            {form.id ? 'Save' : 'Create Category'}
          </button>
        </>
      }
    >
      <label className="field">
        <span>Category Name</span>
        <input
          type="text"
          required
          placeholder="e.g. 🌐 Proxy Shop or 🚀 VPN Shop"
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
        />
      </label>

      <label className="field">
        <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Telegram Custom Emoji ID <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
        </span>
        <input
          type="text"
          placeholder="e.g. 5368324170671202286"
          value={form.custom_emoji_id}
          onChange={(e) => set({ custom_emoji_id: e.target.value })}
        />
        <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: 2 }}>
          Send any Telegram emoji to your bot in Telegram to get its ID.
        </small>
      </label>

      <label className="field">
        <span>Sort Order</span>
        <input
          type="number"
          value={form.sort_order}
          onChange={(e) => set({ sort_order: parseInt(e.target.value, 10) || 0 })}
        />
      </label>

      <FlagRow
        label="Pin to Bottom Menu (Reply Keyboard)"
        on={form.is_pinned}
        onChange={(on) => set({ is_pinned: on })}
      />

      <FlagRow
        label="Active in Store"
        on={form.is_active}
        onChange={(on) => set({ is_active: on })}
      />
    </Modal>
  );
}
