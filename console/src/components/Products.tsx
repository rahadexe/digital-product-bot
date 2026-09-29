'use client';

import { useCallback, useEffect, useState } from 'react';
import { Clock, Zap } from 'lucide-react';
import { api, type Category, type Product } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';
import { EmojiPicker } from './EmojiPicker';
import { ValidityPicker } from './ValidityPicker';
import { CustomSelect } from './CustomSelect';

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
  reseller_price?: number | null;
  duration_label: string;
  sort_order: number;
  is_active: boolean;
  delivery_type: 'stock' | 'manual';
  custom_emoji_id: string;
  upstream_product_id?: number | null;
  supplier_code?: string | null;
  upstream_devices?: number;
  upstream_share_hours?: number;
};
type ProductFilter = 'all' | 'in_stock' | 'low_stock' | 'out_of_stock' | 'supplier' | 'hidden';

const LOW_STOCK_MAX = 3;

export function Products({ say }: { say: Say }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<ProductFilter>('all');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [previewProduct, setPreviewProduct] = useState<Product | null>(null);
  const [posting, setPosting] = useState(false);
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

  async function remove(product: Product) {
    if (
      !(await confirm(
        `Delete "${product.title}"?`,
        'Permanently delete this product?',
        'Delete',
        true
      ))
    )
      return;
    try {
      await api.deleteProduct(product.id);
      say('Product deleted.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  async function toggleActive(product: Product) {
    const nextActive = !product.is_active;
    const title = nextActive ? `Activate "${product.title}"?` : `Hide "${product.title}"?`;
    const message = nextActive ? 'Show in store?' : 'Hide from store?';
    const actionLabel = nextActive ? 'Activate' : 'Hide';

    if (!(await confirm(title, message, actionLabel, !nextActive))) return;

    try {
      await api.updateProduct(product.id, { is_active: nextActive ? 1 : 0 });
      say(nextActive ? `${product.title} is now Active.` : `${product.title} is now Hidden.`);
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  const inStockCount = (products ?? []).filter((p) => p.delivery_type === 'manual' || (p.stock ?? 0) > 0 || Boolean(p.upstream_product_id)).length;
  const lowStockCount = (products ?? []).filter((p) => !p.upstream_product_id && p.delivery_type !== 'manual' && (p.stock ?? 0) > 0 && (p.stock ?? 0) <= LOW_STOCK_MAX).length;
  const outOfStockCount = (products ?? []).filter((p) => !p.upstream_product_id && p.delivery_type !== 'manual' && (p.stock ?? 0) === 0).length;
  const supplierCount = (products ?? []).filter((p) => Boolean(p.upstream_product_id)).length;
  const hiddenCount = (products ?? []).filter((p) => !p.is_active).length;
  const totalStockUnits = (products ?? []).reduce((sum, p) => sum + (p.stock ?? 0), 0);

  const shown = (products ?? []).filter((product) => {
    if (search && !product.title.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === 'in_stock') return product.delivery_type === 'manual' || (product.stock ?? 0) > 0 || Boolean(product.upstream_product_id);
    if (filter === 'low_stock') return !product.upstream_product_id && product.delivery_type !== 'manual' && (product.stock ?? 0) > 0 && (product.stock ?? 0) <= LOW_STOCK_MAX;
    if (filter === 'out_of_stock') return !product.upstream_product_id && product.delivery_type !== 'manual' && (product.stock ?? 0) === 0;
    if (filter === 'supplier') return Boolean(product.upstream_product_id);
    if (filter === 'hidden') return !product.is_active;
    return true;
  });

  return (
    <>
      {confirmDialog}

      {/* Filter Tabs */}
      <div className="segmented" role="group" aria-label="Filter products" style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          aria-pressed={filter === 'all'}
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          All ({products?.length ?? 0})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'in_stock'}
          className={filter === 'in_stock' ? 'active' : ''}
          onClick={() => setFilter('in_stock')}
        >
          Available ({inStockCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'supplier'}
          className={filter === 'supplier' ? 'active' : ''}
          onClick={() => setFilter('supplier')}
        >
          ⚡ Supplier ({supplierCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'low_stock'}
          className={filter === 'low_stock' ? 'active' : ''}
          onClick={() => setFilter('low_stock')}
        >
          Low Stock ({lowStockCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'out_of_stock'}
          className={filter === 'out_of_stock' ? 'active' : ''}
          onClick={() => setFilter('out_of_stock')}
        >
          Out of Stock ({outOfStockCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'hidden'}
          className={filter === 'hidden' ? 'active' : ''}
          onClick={() => setFilter('hidden')}
        >
          Hidden ({hiddenCount})
        </button>
      </div>

      <section className="panel">
        <header>
          <div className="filters">
            <input type="search" aria-label="Search products" placeholder="Search products" value={search} onChange={(event) => setSearch(event.target.value)} />
            <span className="muted">{totalStockUnits} stock units</span>
          </div>
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
                reseller_price: null,
                duration_label: '1 Month',
                sort_order: 0,
                is_active: true,
                delivery_type: 'stock',
                custom_emoji_id: '',
                upstream_product_id: null,
                supplier_code: 'digital_mart',
                upstream_devices: 1,
                upstream_share_hours: 24,
              })
            }
          >
            New product
          </button>
        </header>
        <div className="scroll">
          <table className="mobile-records products-list">
            <thead>
              <tr>
                <th>Product</th>
                <th>Price</th>
                <th>Stock / Delivery</th>
                <th style={{ width: '100px', textAlign: 'center' }}>Status</th>
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
                      <small>{[cat?.name, product.duration_label].filter(Boolean).join(' · ')}</small>
                    </td>
                    <td className="money">
                      <div>{money(product.price)}</div>
                      {product.reseller_price != null && product.reseller_price > 0 ? (
                        <small style={{ color: 'var(--accent)', fontSize: '11px', fontWeight: 600, display: 'block' }}>
                          Reseller: {money(product.reseller_price)}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      {product.upstream_product_id ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', alignItems: 'flex-start' }}>
                          <span
                            className="pill info"
                            style={{
                              fontWeight: 600,
                              background: 'rgba(14, 165, 233, 0.12)',
                              color: '#0284c7',
                              border: '1px solid rgba(14, 165, 233, 0.25)',
                            }}
                            title={`Fulfilled automatically by Upstream Supplier (ID: #${product.upstream_product_id})`}
                          >
                            <Zap size={12} style={{ display: 'inline', verticalAlign: '-1px', marginRight: 4 }} />
                            Supplier
                          </span>
                          {(product.upstream_devices ?? 1) > 1 ? (
                            <span
                              style={{
                                fontSize: '11px',
                                color: '#16a34a',
                                fontWeight: 600,
                                background: 'rgba(22, 163, 74, 0.1)',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                border: '1px solid rgba(22, 163, 74, 0.2)',
                              }}
                              title={`${product.upstream_devices} devices per account, ${product.upstream_share_hours ?? 24}h sharing window`}
                            >
                              {product.upstream_devices} Devices ({product.stock ?? 0} seats pool)
                            </span>
                          ) : null}
                        </div>
                      ) : product.delivery_type === 'manual' ? (
                        <span className="pill info" style={{ fontWeight: 600 }}>
                          <Clock size={12} style={{ display: 'inline', verticalAlign: '-1px', marginRight: 4 }} />
                          Manual
                        </span>
                      ) : (
                        <span
                          className={`pill ${!product.stock ? 'bad' : product.stock <= LOW_STOCK_MAX ? 'warn' : 'good'}`}
                          title={product.stock && product.stock <= LOW_STOCK_MAX ? `Low stock (≤ ${LOW_STOCK_MAX} remaining)` : undefined}
                        >
                          {product.stock ? `${product.stock} in stock` : 'out of stock'}
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        onClick={() => toggleActive(product)}
                        className={`pill ${product.is_active ? 'good' : 'bad'}`}
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
                        title={product.is_active ? 'Click to hide product' : 'Click to activate product'}
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: product.is_active ? 'var(--positive)' : 'var(--danger)',
                            flexShrink: 0,
                          }}
                        />
                        <span>{product.is_active ? 'Active' : 'Hidden'}</span>
                      </button>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="mini" onClick={() => setPreviewProduct(product)}>
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
                              reseller_price: product.reseller_price ?? null,
                              duration_label: product.duration_label,
                              sort_order: product.sort_order,
                              is_active: Boolean(product.is_active),
                              delivery_type: product.delivery_type || 'stock',
                              custom_emoji_id: product.custom_emoji_id || '',
                              upstream_product_id: product.upstream_product_id ?? null,
                              supplier_code: product.supplier_code || 'digital_mart',
                              upstream_devices: product.upstream_devices ?? 1,
                              upstream_share_hours: product.upstream_share_hours ?? 24,
                            })
                          }
                        >
                          Edit
                        </button>
                        <button type="button" className="mini danger" onClick={() => remove(product)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {products && shown.length === 0 ? (
                <EmptyRow columns={5}>
                  {search
                    ? 'Nothing matches.'
                    : filter === 'low_stock'
                    ? 'No low stock products right now.'
                    : 'No products yet.'}
                </EmptyRow>
              ) : null}
              {!products ? <EmptyRow columns={5}>Loading…</EmptyRow> : null}
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

      {previewProduct ? (
        <Modal
          title="Channel Post Preview"
          onClose={() => !posting && setPreviewProduct(null)}
          footer={
            <>
              <button
                type="button"
                className="btn ghost"
                disabled={posting}
                onClick={() => setPreviewProduct(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn"
                disabled={posting}
                onClick={async () => {
                  setPosting(true);
                  try {
                    await api.announceProduct(previewProduct.id);
                    say('Posted to the channel.');
                    setPreviewProduct(null);
                  } catch (cause) {
                    say(errorText(cause), 'bad');
                  } finally {
                    setPosting(false);
                  }
                }}
              >
                {posting ? 'Posting...' : 'Post to Channel'}
              </button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <span style={{ fontSize: '12.5px', color: 'var(--muted)' }}>
              How this announcement will appear in your Telegram channel:
            </span>

            {/* Telegram message card preview */}
            <div
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: '12px',
                padding: '14px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                fontSize: '13px',
                lineHeight: 1.45,
                color: 'var(--text)',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)',
                userSelect: 'none',
              }}
            >
              <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🔥</span>
                <span>Featured Product</span>
              </div>
              <div style={{ height: '1px', background: 'var(--line)', margin: '2px 0' }} />

              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                <span>👑</span>
                <div>
                  <strong>Product: </strong>
                  <span>{previewProduct.icon ? `${previewProduct.icon} ` : '⚡ '}{previewProduct.title}</span>
                </div>
              </div>

              {previewProduct.description ? (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', color: 'var(--muted)' }}>
                  <span>📝</span>
                  <span style={{ whiteSpace: 'pre-wrap' }}>{previewProduct.description}</span>
                </div>
              ) : null}

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>🏪</span>
                <div>
                  <strong>Available Stock: </strong>
                  <code style={{ background: 'var(--surface)', padding: '1px 5px', borderRadius: '4px', fontSize: '12px' }}>
                    {previewProduct.delivery_type === 'manual' ? 'Manual Delivery' : `${previewProduct.stock ?? 0} units`}
                  </code>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>💳</span>
                <div>
                  <strong>Price: </strong>
                  <code style={{ background: 'var(--surface)', padding: '1px 5px', borderRadius: '4px', fontSize: '12px' }}>
                    {money(previewProduct.price)}
                  </code>
                  {previewProduct.reseller_price != null && previewProduct.reseller_price > 0 ? (
                    <span style={{ marginLeft: '8px', color: 'var(--accent)', fontWeight: 600, fontSize: '12px' }}>
                      (Reseller: {money(previewProduct.reseller_price)})
                    </span>
                  ) : null}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>✅</span>
                <div>
                  <strong>Delivery: </strong>
                  <span>{previewProduct.delivery_type === 'manual' ? 'Manual Delivery' : 'Instant Automatic Delivery'}</span>
                </div>
              </div>

              {/* Mock Telegram button */}
              <div
                style={{
                  marginTop: '6px',
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  textAlign: 'center',
                  fontWeight: 600,
                  fontSize: '12.5px',
                  color: 'var(--accent)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <span>🛍️</span>
                <span>Order {previewProduct.title}</span>
              </div>
            </div>
          </div>
        </Modal>
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
  const [validityPresets, setValidityPresets] = useState<string[]>([]);

  useEffect(() => {
    api.settings().then((sets) => {
      if (sets && typeof sets.validity_presets === 'string') {
        const parsed = sets.validity_presets.split(',').map((s) => s.trim()).filter(Boolean);
        setValidityPresets(parsed);
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
      description: (form.description || '').trim(),
      price: form.price,
      reseller_price: form.reseller_price != null && form.reseller_price > 0 ? form.reseller_price : null,
      icon: '',
      duration_label: form.duration_label,
      sort_order: form.sort_order,
      is_active: form.is_active ? 1 : 0,
      delivery_type: form.delivery_type,
      custom_emoji_id: form.custom_emoji_id ? form.custom_emoji_id.trim() : '',
      upstream_product_id: form.upstream_product_id || null,
      supplier_code: form.upstream_product_id ? (form.supplier_code || 'digital_mart') : null,
      upstream_devices: form.upstream_devices ?? 1,
      upstream_share_hours: form.upstream_share_hours ?? 24,
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
      {form.upstream_product_id ? (
        <>
          <div
            style={{
              background: 'rgba(14, 165, 233, 0.08)',
              border: '1px solid rgba(14, 165, 233, 0.25)',
              borderRadius: '8px',
              padding: '10px 14px',
              fontSize: '12.5px',
              color: 'var(--text)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '12px',
            }}
          >
            <Zap size={18} style={{ color: '#0284c7', flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>
                  Connected to {form.supplier_code === 'safwan_tiger' ? 'Safwan Tiger Shop' : 'Digital Mart'} (#{form.upstream_product_id})
                </strong>
                <button
                  type="button"
                  className="btn ghost mini"
                  style={{ padding: '2px 8px', fontSize: '11px' }}
                  onClick={() => set({ upstream_product_id: null })}
                  title="Disconnect from upstream supplier"
                >
                  Disconnect
                </button>
              </div>
              <div style={{ color: 'var(--muted)', fontSize: '11.5px', marginTop: '2px' }}>
                Orders are fulfilled automatically via {form.supplier_code === 'safwan_tiger' ? 'Safwan Tiger Shop API (USDT)' : 'Digital Mart wholesale API (BDT)'}. Custom name, emoji, duration, and prices are preserved across catalog syncs.
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Supplier Provider</span>
              <select
                value={form.supplier_code || 'digital_mart'}
                onChange={(e) => set({ supplier_code: e.target.value })}
              >
                <option value="digital_mart">Digital Mart (BDT)</option>
                <option value="safwan_tiger">Safwan Tiger Shop (USDT)</option>
              </select>
            </label>
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Supplier Product ID</span>
              <input
                type="number"
                min="1"
                required
                value={form.upstream_product_id ?? ''}
                onChange={(e) => set({ upstream_product_id: parseInt(e.target.value) || 1 })}
              />
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Devices per Account <small style={{ color: 'var(--muted)' }}>(Pool)</small></span>
              <input
                type="number"
                min="1"
                max="50"
                required
                value={form.upstream_devices ?? 1}
                onChange={(e) => set({ upstream_devices: parseInt(e.target.value) || 1 })}
              />
              <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: '2px', display: 'block' }}>
                e.g. 7 for shared VPN. Customers 2-7 receive seats from local pool at ৳0 extra supplier cost.
              </small>
            </label>
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Share Window (Hours) <small style={{ color: 'var(--muted)' }}>(Expiry)</small></span>
              <input
                type="number"
                min="1"
                max="720"
                required
                value={form.upstream_share_hours ?? 24}
                onChange={(e) => set({ upstream_share_hours: parseInt(e.target.value) || 24 })}
              />
              <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: '2px', display: 'block' }}>
                Unused seats expire after this duration. New orders will trigger fresh supplier purchase.
              </small>
            </label>
          </div>
        </>
      ) : null}

      <label className="field">
        <span>Name</span>
        <input type="text" required placeholder="e.g. NordVPN 30 Days" value={form.title} onChange={(event) => set({ title: event.target.value })} />
      </label>

      <div className="field">
        <EmojiPicker
          value={form.custom_emoji_id}
          onChange={(id) => set({ custom_emoji_id: id })}
        />
      </div>

      <div className="field">
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
          Category <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
        </span>
        <CustomSelect
          value={String(form.category_id ?? '')}
          onChange={(val) => set({ category_id: val ? Number(val) : null })}
          options={[
            { value: '', label: 'None (Uncategorized)' },
            ...categories.map((c) => ({
              value: String(c.id),
              label: c.name,
              badge: c.is_pinned ? 'Pinned' : undefined,
            })),
          ]}
          minWidth="100%"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <label className="field" style={{ margin: 0 }}>
          <span>Regular Price</span>
          <input type="number" step="any" min="0" required value={form.price} onChange={(event) => set({ price: parseFloat(event.target.value) || 0 })} />
        </label>
        <label className="field" style={{ margin: 0 }}>
          <span>Reseller Price <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
          <input
            type="number"
            step="any"
            min="0"
            placeholder="0.00"
            value={form.reseller_price ?? ''}
            onChange={(event) => set({ reseller_price: event.target.value === '' ? null : (parseFloat(event.target.value) || 0) })}
          />
        </label>
      </div>

      <div className="field">
        <ValidityPicker
          value={form.duration_label}
          onChange={(val) => set({ duration_label: val })}
          presets={validityPresets}
          onAddPreset={async (newPreset) => {
            const exists = validityPresets.some((p) => p.toLowerCase() === newPreset.toLowerCase());
            if (!exists) {
              const updated = [...validityPresets, newPreset];
              setValidityPresets(updated);
              try {
                await api.updateSettings({ validity_presets: updated.join(', ') });
                say(`"${newPreset}" added to validity presets.`);
              } catch (e) {
                console.error('Failed to update validity presets:', e);
              }
            }
          }}
        />
      </div>

      <div className="field">
        <span>Delivery Method</span>
        {form.upstream_product_id ? (
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '10px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '13px',
              fontWeight: 600,
              color: '#0284c7',
            }}
          >
            <Zap size={16} />
            <span>Automated Supplier Dropshipping (Zero Local Stock Required)</span>
          </div>
        ) : (
          <div className="delivery-method-grid">
            <button
              type="button"
              className={`delivery-method-card ${form.delivery_type === 'stock' ? 'active' : ''}`}
              onClick={() => set({ delivery_type: 'stock' })}
            >
              <span className="delivery-method-icon"><Zap size={14} /></span>
              <span className="delivery-method-title">Instant Stock</span>
            </button>
            <button
              type="button"
              className={`delivery-method-card ${form.delivery_type === 'manual' ? 'active' : ''}`}
              onClick={() => set({ delivery_type: 'manual' })}
            >
              <span className="delivery-method-icon"><Clock size={14} /></span>
              <span className="delivery-method-title">Manual Delivery</span>
            </button>
          </div>
        )}
      </div>

      <label className="field">
        <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Description <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
          <small style={{ fontWeight: 'normal', color: 'var(--muted)', fontSize: '11px' }}>
            {(form.description || '').length}/300
          </small>
        </span>
        <textarea
          rows={3}
          maxLength={300}
          placeholder="What it includes, warranty, etc. (Optional, Max 300 chars)"
          value={form.description || ''}
          onChange={(event) => set({ description: event.target.value.slice(0, 300) })}
        />
      </label>
      <FlagRow
        label={form.is_active ? 'Active' : 'Hidden'}
        hint={form.is_active ? 'Visible in bot store' : 'Hidden from customers in store'}
        on={form.is_active}
        onChange={(on) => set({ is_active: on })}
      />
    </Modal>
  );
}


