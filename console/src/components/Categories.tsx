'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type Category, type Product } from '@/lib/api';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';
import { EmojiPicker, splitLeadingEmoji } from './EmojiPicker';
import { MobileRecordDetails } from './MobileRecordDetails';

type CategoryDraft = {
  id: number | null;
  name: string;
  icon: string;
  sort_order: number;
  is_active: boolean;
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
    const title = `Delete "${cat.name}"?`;
    const msg = 'Products inside will remain in store under Others.';

    if (!(await confirm(title, msg, 'Delete', true))) {
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

  async function toggleActive(cat: Category) {
    const willHide = Boolean(cat.is_active);
    const title = willHide ? `Hide "${cat.name}"?` : `Activate "${cat.name}"?`;
    const msg = willHide
      ? 'Customers will not see this category in the bot.'
      : 'Make this category visible to customers in the bot.';
    const label = willHide ? 'Hide' : 'Activate';

    if (!(await confirm(title, msg, label, willHide))) {
      return;
    }

    try {
      await api.updateCategory(cat.id, {
        name: cat.name,
        icon: cat.icon || '',
        sort_order: cat.sort_order,
        is_active: willHide ? 0 : 1,
        is_pinned: 0,
        has_validity_filter: cat.has_validity_filter ? 1 : 0,
        custom_emoji_id: cat.custom_emoji_id,
      });
      say(willHide ? 'Category hidden.' : 'Category active.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  function editCategory(cat: Category) {
    const name = splitLeadingEmoji(cat.name);
    const customEmojiId = cat.custom_emoji_id || '';
    setDraft({
      id: cat.id,
      name: name.emoji ? name.text : cat.name,
      icon: customEmojiId ? '' : cat.icon || name.emoji,
      sort_order: cat.sort_order,
      is_active: Boolean(cat.is_active),
      has_validity_filter: Boolean(cat.has_validity_filter),
      custom_emoji_id: customEmojiId,
    });
  }

  const [filter, setFilter] = useState<'all' | 'active' | 'hidden'>('all');

  const totalCount = categories?.length ?? 0;
  const activeCount = (categories ?? []).filter((c) => Boolean(c.is_active)).length;
  const hiddenCount = (categories ?? []).filter((c) => !c.is_active).length;

  const shown = (categories ?? []).filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === 'active' && !c.is_active) return false;
    if (filter === 'hidden' && c.is_active) return false;
    return true;
  });

  return (
    <>
      {confirmDialog}

      <section className="panel">
        <header className="category-toolbar">
          <div className="segmented category-filter-tabs" role="group" aria-label="Filter categories">
            <button
              type="button"
              className={filter === 'all' ? 'active' : ''}
              aria-pressed={filter === 'all'}
              onClick={() => setFilter('all')}
            >
              All ({totalCount})
            </button>
            <button
              type="button"
              className={filter === 'active' ? 'active' : ''}
              aria-pressed={filter === 'active'}
              onClick={() => setFilter('active')}
            >
              Active ({activeCount})
            </button>
            <button
              type="button"
              className={filter === 'hidden' ? 'active' : ''}
              aria-pressed={filter === 'hidden'}
              onClick={() => setFilter('hidden')}
            >
              Hidden ({hiddenCount})
            </button>
          </div>
          <div className="filters category-search">
            <input
              type="search"
              placeholder="Search categories..."
              aria-label="Search categories"
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
                icon: '',
                sort_order: 0,
                is_active: true,
                has_validity_filter: false,
                custom_emoji_id: '',
              })
            }
          >
            New category
          </button>
        </header>

        <div className="app-list-heading"><span>{shown.length} {shown.length === 1 ? 'category' : 'categories'}</span></div>
        <ul className="app-record-list category-feed" aria-label="Categories">
          {shown.map(cat => {
            const count = (products ?? []).filter(product => product.category_id === cat.id).length;
            return <li key={cat.id}>
              <MobileRecordDetails title={cat.name} subtitle={`${count} ${count === 1 ? 'product' : 'products'}`} amount="" status={cat.is_active ? 'Active' : 'Hidden'} tone={cat.is_active ? 'good' : 'neutral'} icon={cat.icon || undefined} label={`Manage category ${cat.name}`} fields={[
                ['Category', cat.name], ['Products', count], ['Status', cat.is_active ? 'Active' : 'Hidden'],
                ['Sort order', cat.sort_order], ['Validity filter', cat.has_validity_filter ? 'On' : 'Off'],
              ]}>
                <button type="button" className="btn" onClick={() => editCategory(cat)}>Edit category</button>
                <button type="button" className="btn ghost" onClick={() => void toggleActive(cat)}>{cat.is_active ? 'Hide category' : 'Activate category'}</button>
                <button type="button" className="btn ghost danger" onClick={() => void deleteCat(cat)}>Delete category</button>
              </MobileRecordDetails>
            </li>;
          })}
          {!categories || !shown.length ? <li className="app-list-empty">{!categories ? 'Loading categories…' : 'No categories match your search.'}</li> : null}
        </ul>
        <div className="scroll desktop-record-scroll">
          <table className="category-admin-table">
            <thead>
              <tr>
                <th style={{ minWidth: '160px' }}>Category Name</th>
                <th style={{ width: '110px' }}>Products</th>
                <th style={{ width: '130px' }}>Validity Filter</th>
                <th style={{ width: '70px', textAlign: 'center' }}>Order</th>
                <th style={{ width: '100px', textAlign: 'center' }}>Status</th>
                <th className="right" style={{ width: '140px', whiteSpace: 'nowrap' }} aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((cat) => {
                const catProducts = (products ?? []).filter((p) => p.category_id === cat.id);
                return (
                  <tr key={cat.id}>
                    <td className="name">
                      <div style={{ display: 'flex', alignItems: 'center' }}>
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
                    <td className="right" style={{ width: '140px', whiteSpace: 'nowrap' }}>
                      <div className="row-actions" style={{ flexWrap: 'nowrap' }}>
                        <button
                          type="button"
                          className="mini"
                          onClick={() => editCategory(cat)}
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
                <EmptyRow columns={6}>
                  {search ? 'Nothing matches.' : 'No categories yet'}
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
    const enteredName = form.name.trim();
    const leading = splitLeadingEmoji(enteredName);
    const customEmojiId = form.custom_emoji_id.trim();
    const payload = {
      name: leading.emoji && leading.text ? leading.text : enteredName,
      icon: customEmojiId ? '' : form.icon.trim() || leading.emoji,
      sort_order: form.sort_order,
      is_active: form.is_active ? 1 : 0,
      is_pinned: 0,
      has_validity_filter: form.has_validity_filter ? 1 : 0,
      custom_emoji_id: customEmojiId,
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
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
        />
      </label>

      <div className="field">
        <EmojiPicker
          value={form.custom_emoji_id}
          icon={form.icon}
          onChange={({ icon, customEmojiId }) =>
            set({ icon, custom_emoji_id: customEmojiId })
          }
        />
      </div>

      <label className="field">
        <span style={{ userSelect: 'none' }}>Sort Order</span>
        <input
          type="number"
          min="0"
          value={form.sort_order}
          onChange={(e) => set({ sort_order: e.target.value === '' ? ('' as any) : Math.max(0, parseInt(e.target.value, 10) || 0) })}
        />
      </label>

      <FlagRow
        label="Filter by Validity"
        on={form.has_validity_filter}
        onChange={(on) => set({ has_validity_filter: on })}
      />

      <FlagRow
        label="Active"
        on={form.is_active}
        onChange={(on) => set({ is_active: on })}
      />
    </Modal>
  );
}
