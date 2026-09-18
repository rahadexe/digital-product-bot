'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Layers, Package } from 'lucide-react';
import { api, type Category, type Product } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

// Older products kept their emoji apart from the name; the form edits them as one text.
function editableName(name: string, icon?: string) {
  const prefix = icon?.trim();
  return prefix && !name.trimStart().startsWith(prefix) ? `${prefix} ${name}` : name;
}

type Draft = {
  id: number | null;
  category_id: number | null;
  title: string;
  description: string;
  price: number;
  duration_label: string;
  sort_order: number;
  is_active: boolean;
  delivery_type: 'stock' | 'manual';
  custom_emoji_id: string;
};
type ProductFilter = 'all' | 'in_stock' | 'out_of_stock' | 'hidden';

export function Products({ say }: { say: Say }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<ProductFilter>('all');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  const load = useCallback(async () => {
    try {
      const [prods, cats] = await Promise.all([api.products(), api.categories()]);
      setProducts(prods);
      setCategories(cats);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function archive(product: Product) {
    if (!(await confirm(`Archive ${product.title}?`, 'Its orders and stock will be kept, but customers will no longer see it.', 'Archive product'))) return;
    try {
      await api.deleteProduct(product.id);
      say('Archived.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  async function announce(product: Product) {
    try {
      await api.announceProduct(product.id);
      say('Posted to the channel.');
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  const inStockCount = (products ?? []).filter((p) => (p.stock ?? 0) > 0).length;
  const outOfStockCount = (products ?? []).filter((p) => (p.stock ?? 0) === 0).length;
  const hiddenCount = (products ?? []).filter((p) => !p.is_active).length;
  const totalStockUnits = (products ?? []).reduce((sum, p) => sum + (p.stock ?? 0), 0);

  const shown = (products ?? []).filter((product) => {
    if (search && !product.title.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === 'in_stock') return (product.stock ?? 0) > 0;
    if (filter === 'out_of_stock') return (product.stock ?? 0) === 0;
    if (filter === 'hidden') return !product.is_active;
    return true;
  });

  return (
    <>
      {confirmDialog}

      {/* Product Metric Summary Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Products</span>
            <Package className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{products?.length ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">In Stock</span>
            <CheckCircle2 className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{inStockCount}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Out of Stock</span>
            <AlertCircle className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{outOfStockCount}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Stock Units</span>
            <Layers className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{totalStockUnits}</div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="segmented" role="tablist" style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          All ({products?.length ?? 0})
        </button>
        <button
          type="button"
          className={filter === 'in_stock' ? 'active' : ''}
          onClick={() => setFilter('in_stock')}
        >
          In Stock ({inStockCount})
        </button>
        <button
          type="button"
          className={filter === 'out_of_stock' ? 'active' : ''}
          onClick={() => setFilter('out_of_stock')}
        >
          Out of Stock ({outOfStockCount})
        </button>
        <button
          type="button"
          className={filter === 'hidden' ? 'active' : ''}
          onClick={() => setFilter('hidden')}
        >
          Hidden ({hiddenCount})
        </button>
      </div>

      <section className="panel">
        <header>
          <div className="filters">
            <input type="search" placeholder="Search products" value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn ghost"
              onClick={() => { window.location.hash = 'categories'; }}
            >
              📁 Categories ({categories.length})
            </button>
            <button
              type="button"
              className="btn"
              onClick={() =>
                setDraft({
                  id: null,
                  category_id: null,
                  title: '',
                  description: '',
                  price: 1,
                  duration_label: '1 Month',
                  sort_order: 0,
                  is_active: true,
                  delivery_type: 'stock',
                  custom_emoji_id: '',
                })
              }
            >
              New product
            </button>
          </div>
        </header>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Price</th>
                <th>Stock / Delivery</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((product) => {
                const cat = categories.find((c) => c.id === product.category_id);
                return (
                  <tr key={product.id}>
                    <td className="name">
                      {product.icon ? `${product.icon} ` : ''}
                      {product.title}
                      <small>
                        {cat ? (
                          <span style={{ color: 'var(--primary, #3b82f6)', fontWeight: 600, marginRight: 6 }}>
                            [{cat.name}]
                          </span>
                        ) : null}
                        {product.duration_label || 'Instant'}
                        {product.is_active ? '' : ' · hidden'}
                      </small>
                    </td>
                    <td className="money">{money(product.price)}</td>
                    <td>
                      {product.delivery_type === 'manual' ? (
                        <span className="pill info" style={{ fontWeight: 600 }}>
                          ⏱️ Manual
                        </span>
                      ) : (
                        <span className={`pill ${product.stock ? 'good' : 'bad'}`}>{product.stock ? product.stock : 'out'}</span>
                      )}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="mini" onClick={() => announce(product)}>
                          Post
                        </button>
                        <button
                          type="button"
                          className="mini"
                          onClick={() =>
                            setDraft({
                              id: product.id,
                              category_id: product.category_id ?? null,
                              title: editableName(product.title, product.icon),
                              description: product.description,
                              price: product.price,
                              duration_label: product.duration_label,
                              sort_order: product.sort_order,
                              is_active: Boolean(product.is_active),
                              delivery_type: product.delivery_type || 'stock',
                              custom_emoji_id: product.custom_emoji_id || '',
                            })
                          }
                        >
                          Edit
                        </button>
                        <button type="button" className="mini danger" onClick={() => archive(product)}>
                          Archive
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {products && shown.length === 0 ? <EmptyRow columns={4}>{search ? 'Nothing matches.' : 'No products yet.'}</EmptyRow> : null}
              {!products ? <EmptyRow columns={4}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
      </section>

      {draft ? (
        <ProductForm
          draft={draft}
          categories={categories}
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

function ProductForm({
  draft,
  categories,
  say,
  onClose,
  onSaved,
}: {
  draft: Draft;
  categories: Category[];
  say: Say;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [validityPresets, setValidityPresets] = useState<string[]>([
    '3 Days', '7 Days', '14 Days', '30 Days', '90 Days', '1 Year'
  ]);

  useEffect(() => {
    api.settings().then((sets) => {
      if (sets && sets.validity_presets) {
        const parsed = sets.validity_presets.split(',').map((s) => s.trim()).filter(Boolean);
        if (parsed.length > 0) setValidityPresets(parsed);
      }
    }).catch(() => {});
  }, []);

  const set = (patch: Partial<Draft>) => setForm((current) => ({ ...current, ...patch }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const payload = {
      category_id: form.category_id ?? undefined,
      title: form.title.trim(),
      description: form.description,
      price: form.price,
      icon: '',
      duration_label: form.duration_label,
      sort_order: form.sort_order,
      is_active: form.is_active ? 1 : 0,
      delivery_type: form.delivery_type,
      custom_emoji_id: form.custom_emoji_id ? form.custom_emoji_id.trim() : '',
    };
    try {
      if (form.id) await api.updateProduct(form.id, payload);
      else await api.createProduct(payload);
      say(form.id ? 'Saved.' : 'Product added.');
      await onSaved();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={form.id ? 'Edit product' : 'New product'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={busy}>
            {form.id ? 'Save' : 'Add product'}
          </button>
        </>
      }
    >
      <label className="field">
        <span>Name</span>
        <input type="text" required placeholder="⚡ Gemini Pro" value={form.title} onChange={(event) => set({ title: event.target.value })} />
      </label>

      <label className="field">
        <span>Category <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
        <select
          value={form.category_id ?? ''}
          onChange={(event) => set({ category_id: event.target.value ? Number(event.target.value) : null })}
        >
          <option value="">None (Uncategorized)</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} {c.is_pinned ? '📌 [Pinned to Menu]' : ''}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Price</span>
        <input type="number" step="any" min="0" required value={form.price} onChange={(event) => set({ price: parseFloat(event.target.value) || 0 })} />
      </label>

      <label className="field">
        <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Validity / Duration <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
          {form.duration_label ? (
            <button
              type="button"
              className="mini ghost"
              style={{ fontSize: '11px', color: 'var(--danger)', padding: '0 4px' }}
              onClick={() => set({ duration_label: '' })}
            >
              Clear
            </button>
          ) : null}
        </span>
        <input
          type="text"
          placeholder="e.g. 3 Days, 1 Month, 1 Year"
          value={form.duration_label}
          onChange={(event) => set({ duration_label: event.target.value })}
        />
        {validityPresets.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
            {validityPresets.map((preset) => {
              const isSelected = form.duration_label.trim().toLowerCase() === preset.toLowerCase();
              return (
                <button
                  key={preset}
                  type="button"
                  className={`mini ${isSelected ? 'btn' : 'ghost'}`}
                  style={{
                    fontSize: '11px',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                  onClick={() => set({ duration_label: isSelected ? '' : preset })}
                >
                  {preset}
                </button>
              );
            })}
          </div>
        ) : null}
      </label>

      <label className="field">
        <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Telegram Custom Emoji ID <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
        </span>
        <input
          type="text"
          placeholder="e.g. 5368324170671202286"
          value={form.custom_emoji_id}
          onChange={(event) => set({ custom_emoji_id: event.target.value })}
        />
        <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: 2 }}>
          Shows as a 3D/Premium icon in Telegram. Tip: Send any custom emoji to your bot in Telegram to get its ID!
        </small>
      </label>

      <div className="field">
        <span>Delivery Method</span>
        <div className="delivery-method-grid">
          <button
            type="button"
            className={`delivery-method-card ${form.delivery_type === 'stock' ? 'active' : ''}`}
            onClick={() => set({ delivery_type: 'stock' })}
          >
            <div className="delivery-method-header">
              <span className="delivery-method-icon">⚡</span>
              <span className="delivery-method-title">Instant Stock</span>
            </div>
            <span className="delivery-method-desc">Auto-delivered from uploaded stock keys/accounts</span>
          </button>
          <button
            type="button"
            className={`delivery-method-card ${form.delivery_type === 'manual' ? 'active' : ''}`}
            onClick={() => set({ delivery_type: 'manual' })}
          >
            <div className="delivery-method-header">
              <span className="delivery-method-icon">⏱️</span>
              <span className="delivery-method-title">Manual Delivery</span>
            </div>
            <span className="delivery-method-desc">Admin fulfills manually in Orders tab</span>
          </button>
        </div>
      </div>

      <label className="field">
        <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Description</span>
          <small style={{ fontWeight: 'normal', color: 'var(--muted)', fontSize: '11px' }}>
            {form.description.length}/300
          </small>
        </span>
        <textarea
          rows={3}
          maxLength={300}
          placeholder="What it includes, how to activate, warranty (Max 300 characters)"
          value={form.description}
          onChange={(event) => set({ description: event.target.value.slice(0, 300) })}
        />
      </label>
      <FlagRow label="Show in the store" on={form.is_active} onChange={(on) => set({ is_active: on })} />
    </Modal>
  );
}


