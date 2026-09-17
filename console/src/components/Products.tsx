'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Layers, Package } from 'lucide-react';
import { api, type Product } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

// Older products kept their emoji apart from the name; the form edits them as one text.
function editableName(name: string, icon?: string) {
  const prefix = icon?.trim();
  return prefix && !name.trimStart().startsWith(prefix) ? `${prefix} ${name}` : name;
}

type Draft = { id: number | null; title: string; description: string; price: number; duration_label: string; sort_order: number; is_active: boolean };
type ProductFilter = 'all' | 'in_stock' | 'out_of_stock' | 'hidden';

export function Products({ say }: { say: Say }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<ProductFilter>('all');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  const load = useCallback(async () => {
    try {
      const prods = await api.products();
      setProducts(prods);
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
          <button
            type="button"
            className="btn"
            onClick={() =>
              setDraft({ id: null, title: '', description: '', price: 1, duration_label: '1 Month', sort_order: 0, is_active: true })
            }
          >
            New product
          </button>
        </header>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Price</th>
                <th>Stock</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((product) => (
                <tr key={product.id}>
                  <td className="name">
                    {product.icon ? `${product.icon} ` : ''}
                    {product.title}
                    <small>
                      {product.duration_label || 'Instant'}
                      {product.is_active ? '' : ' · hidden'}
                    </small>
                  </td>
                  <td className="money">{money(product.price)}</td>
                  <td>
                    <span className={`pill ${product.stock ? 'good' : 'bad'}`}>{product.stock ? product.stock : 'out'}</span>
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
                            title: editableName(product.title, product.icon),
                            description: product.description,
                            price: product.price,
                            duration_label: product.duration_label,
                            sort_order: product.sort_order,
                            is_active: Boolean(product.is_active),
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
              ))}
              {products && shown.length === 0 ? <EmptyRow columns={4}>{search ? 'Nothing matches.' : 'No products yet.'}</EmptyRow> : null}
              {!products ? <EmptyRow columns={4}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
      </section>

      {draft ? (
        <ProductForm
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

function ProductForm({ draft, say, onClose, onSaved }: { draft: Draft; say: Say; onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState(draft);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<Draft>) => setForm((current) => ({ ...current, ...patch }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const payload = {
      title: form.title.trim(),
      description: form.description,
      price: form.price,
      icon: '',
      duration_label: form.duration_label,
      sort_order: form.sort_order,
      is_active: form.is_active ? 1 : 0,
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
      <div className="field-row">
        <label className="field">
          <span>Price</span>
          <input type="number" step="any" min="0" required value={form.price} onChange={(event) => set({ price: parseFloat(event.target.value) || 0 })} />
        </label>
        <label className="field">
          <span>Duration</span>
          <input type="text" placeholder="1 Month" value={form.duration_label} onChange={(event) => set({ duration_label: event.target.value })} />
        </label>
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
