'use client';

import { useCallback, useEffect, useState } from 'react';
import { FolderTree, Pin, Plus } from 'lucide-react';
import { api, type Category, type Product } from '@/lib/api';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';
import { EmojiPicker } from './EmojiPicker';

type CategoryDraft = {
  id: number | null;
  name: string;
  sort_order: number;
  is_active: boolean;
  is_pinned: boolean;
  has_validity_filter: boolean;
  custom_emoji_id: string;
};

export function Categories({ say }: { say: Say }) {
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState<CategoryDraft | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(async () => {
    try {
      const [cats, prods] = await Promise.all([
        api.categories(),
        api.products(),
      ]);
      setCategories(cats);
      setProducts(prods);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function deleteCat(cat: Category) {
    const catProducts = (products ?? []).filter((p) => p.category_id === cat.id);
    const msg = catProducts.length > 0
      ? `This category contains ${catProducts.length} product(s). If deleted, those products will remain in the store but will become uncategorized.`
      : 'Products in this category will remain, but will become uncategorized.';

    if (!(await confirm(`Delete category "${cat.name}"?`, msg, 'Delete category'))) {
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
    const willPin = !cat.is_pinned;
    const title = willPin ? `Pin "${cat.name}" to Menu?` : `Unpin "${cat.name}" from Menu?`;
    const msg = willPin
      ? `Show "${cat.name}" directly on the customer's Telegram reply keyboard menu for 1-tap access?`
      : `Move "${cat.name}" into the "Other Products" list instead of the main Telegram keyboard?`;
    const label = willPin ? 'Pin to Menu' : 'Unpin';

    if (!(await confirm(title, msg, label))) {
      return;
    }

    try {
      await api.updateCategory(cat.id, {
        name: cat.name,
        sort_order: cat.sort_order,
        is_active: cat.is_active,
        is_pinned: willPin ? 1 : 0,
        has_validity_filter: cat.has_validity_filter ? 1 : 0,
        custom_emoji_id: cat.custom_emoji_id,
      });
      say(willPin ? 'Pinned to Telegram reply keyboard!' : 'Unpinned from menu.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  async function toggleActive(cat: Category) {
    const willHide = Boolean(cat.is_active);
    const title = willHide ? `Hide category "${cat.name}"?` : `Activate category "${cat.name}"?`;
    const msg = willHide
      ? `Are you sure you want to hide "${cat.name}"? Customers will not see this category or its products in the Telegram bot store.`
      : `Are you sure you want to activate "${cat.name}"? It will become visible and available for customers in the Telegram bot.`;
    const label = willHide ? 'Hide Category' : 'Activate Category';

    if (!(await confirm(title, msg, label))) {
      return;
    }

    try {
      await api.updateCategory(cat.id, {
        name: cat.name,
        sort_order: cat.sort_order,
        is_active: willHide ? 0 : 1,
        is_pinned: cat.is_pinned,
        has_validity_filter: cat.has_validity_filter ? 1 : 0,
        custom_emoji_id: cat.custom_emoji_id,
      });
      say(willHide ? 'Category hidden.' : 'Category active.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  const [filter, setFilter] = useState<'all' | 'active' | 'hidden' | 'pinned'>('all');

  const totalCount = categories?.length ?? 0;
  const activeCount = (categories ?? []).filter((c) => Boolean(c.is_active)).length;
  const hiddenCount = (categories ?? []).filter((c) => !c.is_active).length;
  const pinnedCount = (categories ?? []).filter((c) => Boolean(c.is_pinned)).length;

  const shown = (categories ?? []).filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === 'active' && !c.is_active) return false;
    if (filter === 'hidden' && c.is_active) return false;
    if (filter === 'pinned' && !c.is_pinned) return false;
    return true;
  });

  return (
    <>
      {confirmDialog}

      {/* Segmented Filter Bar */}
      <div className="segmented" role="tablist" style={{ marginBottom: '1.25rem' }}>
        <button
          type="button"
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          All ({totalCount})
        </button>
        <button
          type="button"
          className={filter === 'active' ? 'active' : ''}
          onClick={() => setFilter('active')}
        >
          Active ({activeCount})
        </button>
        <button
          type="button"
          className={filter === 'hidden' ? 'active' : ''}
          onClick={() => setFilter('hidden')}
        >
          Hidden ({hiddenCount})
        </button>
        <button
          type="button"
          className={filter === 'pinned' ? 'active' : ''}
          onClick={() => setFilter('pinned')}
        >
          Pinned to Menu ({pinnedCount})
        </button>
      </div>

      <section className="panel">
        <header>
          <div className="filters">
            <input
              type="search"
              placeholder="Search..."
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
                has_validity_filter: false,
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
                <th style={{ minWidth: '160px' }}>Category Name</th>
                <th style={{ width: '110px' }}>Products</th>
                <th style={{ width: '150px' }}>Menu Location</th>
                <th style={{ width: '130px' }}>Validity Filter</th>
                <th style={{ width: '70px', textAlign: 'center' }}>Order</th>
                <th style={{ width: '100px', textAlign: 'center' }}>Status</th>
                <th className="right" style={{ width: '140px' }} aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((cat) => {
                const catProducts = (products ?? []).filter((p) => p.category_id === cat.id);
                return (
                  <tr key={cat.id}>
                    <td className="name">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FolderTree size={16} color="var(--accent)" />
                        <strong>{cat.name}</strong>
                      </div>
                    </td>
                    <td>
                      {catProducts.length > 0 ? (
                        <span
                          className="pill good"
                          style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 600 }}
                        >
                          {catProducts.length} product{catProducts.length !== 1 ? 's' : ''}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>0 products</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={`mini ${cat.is_pinned ? 'btn' : 'ghost'}`}
                        onClick={() => togglePin(cat)}
                        style={{
                          fontSize: '11px',
                          padding: '3px 8px',
                          width: '132px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          boxSizing: 'border-box',
                        }}
                        title="Click to toggle between pinned keyboard and other products"
                      >
                        {cat.is_pinned ? (
                          <>
                            <Pin size={11} style={{ display: 'inline', verticalAlign: '-1px', marginRight: 4, flexShrink: 0 }} />
                            <span>Pinned to Menu</span>
                          </>
                        ) : (
                          <span>In Other Products</span>
                        )}
                      </button>
                    </td>
                    <td>
                      {cat.has_validity_filter ? (
                        <span
                          className="pill good"
                          style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 600 }}
                        >
                          With Validity
                        </span>
                      ) : (
                        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>Standard</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>{cat.sort_order}</td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        onClick={() => toggleActive(cat)}
                        className={`pill ${cat.is_active ? 'good' : 'bad'}`}
                        style={{
                          cursor: 'pointer',
                          fontSize: '11.5px',
                          padding: '3px 8px',
                          fontWeight: 600,
                          border: 'none',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '6px',
                          width: '78px',
                          boxSizing: 'border-box',
                        }}
                        title={cat.is_active ? 'Click to hide category' : 'Click to activate category'}
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: cat.is_active ? 'var(--positive)' : 'var(--danger)',
                            flexShrink: 0,
                          }}
                        />
                        <span>{cat.is_active ? 'Active' : 'Hidden'}</span>
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
                              has_validity_filter: Boolean(cat.has_validity_filter),
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
                );
              })}
              {categories && shown.length === 0 ? (
                <EmptyRow columns={7}>
                  {search ? 'Nothing matches.' : 'No categories yet. Click "New category" above.'}
                </EmptyRow>
              ) : null}
              {!categories ? <EmptyRow columns={7}>Loading…</EmptyRow> : null}
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
      has_validity_filter: form.has_validity_filter ? 1 : 0,
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
          placeholder="e.g. VPN Services or Streaming"
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
        />
      </label>

      <div className="field">
        <EmojiPicker
          value={form.custom_emoji_id}
          onChange={(id) => set({ custom_emoji_id: id })}
        />
      </div>

      <label className="field">
        <span>Sort Order</span>
        <input
          type="number"
          min="0"
          value={form.sort_order}
          onChange={(e) => set({ sort_order: Math.max(0, parseInt(e.target.value, 10) || 0) })}
        />
        <small>Smaller number shows first in bot</small>
      </label>

      <FlagRow
        label="Pin to Menu"
        hint="Show on Telegram keyboard"
        on={form.is_pinned}
        onChange={(on) => set({ is_pinned: on })}
      />

      <FlagRow
        label="Filter by Validity"
        hint="Ask user for duration first"
        on={form.has_validity_filter}
        onChange={(on) => set({ has_validity_filter: on })}
      />

      <FlagRow
        label="Active"
        hint="Visible in bot store"
        on={form.is_active}
        onChange={(on) => set({ is_active: on })}
      />
    </Modal>
  );
}
