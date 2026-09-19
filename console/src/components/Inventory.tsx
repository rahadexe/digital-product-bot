'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Clock, Layers, PackageCheck } from 'lucide-react';
import { api, type InventoryItem, type InventorySummary, type Product } from '@/lib/api';
import { EmptyRow, Modal, Pager, errorText, when, type Say } from './ui';
import { CustomSelect } from './CustomSelect';

const PAGE = 100;

export function Inventory({ say }: { say: Say }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [offset, setOffset] = useState(0);
  const [productId, setProductId] = useState(0);
  const [status, setStatus] = useState('available');
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<InventoryItem | null>(null);
  const [removing, setRemoving] = useState<InventoryItem | null>(null);

  const loadProducts = useCallback(() => api.products().then(setProducts).catch((cause) => say(errorText(cause), 'bad')), [say]);

  const load = useCallback(async () => {
    try {
      const result = await api.inventory(productId || undefined, status || undefined, offset);
      setItems(result.items);
      setTotal(result.total);
      if (result.summary) setSummary(result.summary);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [productId, status, offset, say]);

  useEffect(() => {
    void loadProducts();
  }, [loadProducts]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmRemove() {
    if (!removing) return;
    try {
      await api.deleteInventoryItem(removing.id);
      setRemoving(null);
      say('Removed.');
      await Promise.all([load(), loadProducts()]);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  return (
    <>
      {/* Inventory Metric Summary Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Available Stock</span>
            <CheckCircle2 className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.available_units ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Sold Units</span>
            <PackageCheck className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.sold_units ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Expired Units</span>
            <AlertCircle className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.expired_units ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Products in Stock</span>
            <Layers className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.in_stock_products ?? 0}</div>
        </div>
      </div>

      <section className="panel">
        <header>
          <div className="filters">
            <CustomSelect
              value={String(productId)}
              onChange={(val) => { setProductId(Number(val)); setOffset(0); }}
              options={[
                { value: '0', label: 'All products' },
                ...products.map((p) => ({
                  value: String(p.id),
                  label: p.title,
                  badge: p.stock ?? 0,
                })),
              ]}
              minWidth={210}
              searchable={products.length > 6}
            />
            <CustomSelect
              value={status}
              onChange={(val) => { setStatus(val); setOffset(0); }}
              options={[
                { value: 'available', label: 'In stock' },
                { value: 'sold', label: 'Sold' },
                { value: 'expired', label: 'Expired' },
                { value: '', label: 'Everything' },
              ]}
              minWidth={135}
            />
          </div>
          <button type="button" className="btn" onClick={() => setAdding(true)}>
            Add stock
          </button>
        </header>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Status</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {(items ?? []).map((item) => {
                const isExpired = item.status === 'expired' || (Boolean(item.expires_at) && new Date(item.expires_at!) < new Date() && item.status !== 'sold');
                return (
                  <tr key={item.id}>
                    <td className="name">
                      {item.product_title}
                      <small>
                        #{item.id} · added {when(item.created_at)}
                      </small>
                    </td>
                    <td>
                      {isExpired ? (
                        <span className="pill bad">expired</span>
                      ) : item.status === 'available' ? (
                        <span className="pill good">in stock</span>
                      ) : (
                        <span className="pill">{item.uses ? 'sold' : 'off sale'}</span>
                      )}
                      {item.expires_at ? (
                        <small style={{ display: 'block', opacity: 0.8 }}>
                          {new Date(item.expires_at) < new Date() ? 'expired ' : 'expires '}
                          {when(item.expires_at)}
                        </small>
                      ) : null}
                      {item.max_uses > 1 ? (
                        <small>
                          {item.uses} of {item.max_uses} customers
                        </small>
                      ) : item.order_id ? (
                        <small>order #{item.order_id}</small>
                      ) : null}
                    </td>
                    <td>
                      <div className="row-actions">
                        {item.status === 'available' && !isExpired ? (
                          <>
                            <button type="button" className="mini" onClick={() => setEditing(item)}>
                              Edit
                            </button>
                            <button type="button" className="mini danger" onClick={() => setRemoving(item)}>
                              Remove
                            </button>
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {items && items.length === 0 ? <EmptyRow columns={3}>Nothing here.</EmptyRow> : null}
              {!items ? <EmptyRow columns={3}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
      </section>

      {editing ? (
        <EditStock
          item={editing}
          say={say}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await Promise.all([load(), loadProducts()]);
          }}
        />
      ) : null}

      {adding ? (
        <AddStock
          products={products}
          initialProduct={productId || products[0]?.id || 0}
          say={say}
          onClose={() => setAdding(false)}
          onAdded={async () => {
            setAdding(false);
            await Promise.all([load(), loadProducts()]);
          }}
        />
      ) : null}

      {removing ? (
        <Modal
          title={removing.uses ? 'Stop selling this item?' : 'Remove item from stock?'}
          onClose={() => setRemoving(null)}
          footer={
            <>
              <button type="button" className="btn ghost" onClick={() => setRemoving(null)}>
                Cancel
              </button>
              <button type="button" className="btn danger" onClick={() => void confirmRemove()}>
                Remove item
              </button>
            </>
          }
        >
          <p className="hint">
            {removing.product_title} · item #{removing.id}
          </p>
          <p className="modal-message">
            {removing.uses ? 'Customers who already received this item will keep it. It will no longer be offered to new customers.' : 'This item will be removed from available stock.'}
          </p>
        </Modal>
      ) : null}
    </>
  );
}

function AddStock({ products, initialProduct, say, onClose, onAdded }: { products: Product[]; initialProduct: number; say: Say; onClose: () => void; onAdded: () => Promise<void> }) {
  const [productId, setProductId] = useState(initialProduct);
  const [text, setText] = useState('');
  const [seats, setSeats] = useState(1);
  const [expiresAt, setExpiresAt] = useState('');
  const [busy, setBusy] = useState(false);
  const count = text.split('\n').filter((line) => line.trim()).length;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!productId || !count) return;
    setBusy(true);
    try {
      const expiresIso = expiresAt ? new Date(expiresAt).toISOString() : undefined;
      const result = await api.bulkAddStock(productId, text, seats, expiresIso);
      say(result.skipped_count ? `${result.added_count} added. ${result.skipped_count} already in stock, skipped.` : `${result.added_count} added.`);
      await onAdded();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Add stock"
      wide
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={busy || !count || !productId}>
            {busy ? 'Adding…' : count ? `Add ${count}` : 'Add'}
          </button>
        </>
      }
    >
      <div className="field">
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>Product</span>
        <CustomSelect
          value={String(productId)}
          onChange={(val) => setProductId(Number(val))}
          options={products.map((p) => ({
            value: String(p.id),
            label: p.title,
            badge: `${p.stock ?? 0} in stock`,
          }))}
          minWidth="100%"
          searchable={products.length > 6}
        />
      </div>
      <label className="field">
        <span>One item per line</span>
        <textarea className="mono" rows={8} placeholder={'email@example.com:password\nKEY-1234-5678'} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <label className="field">
        <span>Customers per item</span>
        <input type="number" min={1} max={1000} step={1} value={seats} onChange={(event) => setSeats(Math.max(1, Math.min(1000, parseInt(event.target.value, 10) || 1)))} />
        <small>1 for a key used once. 7 for an account seven people share: each line goes to seven customers, in turn.</small>
      </label>
      <ExpiryPicker value={expiresAt} onChange={setExpiresAt} />
    </Modal>
  );
}

function EditStock({ item, say, onClose, onSaved }: { item: InventoryItem; say: Say; onClose: () => void; onSaved: () => Promise<void> }) {
  const [content, setContent] = useState(item.content);
  const [seats, setSeats] = useState(item.max_uses);
  const [expiresAt, setExpiresAt] = useState(
    item.expires_at ? new Date(new Date(item.expires_at).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''
  );
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const expiresIso = expiresAt ? new Date(expiresAt).toISOString() : undefined;
      await api.updateInventoryItem(item.id, content, seats, expiresIso);
      say('Saved.');
      await onSaved();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Edit item #${item.id}`}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={busy || !content.trim()}>
            Save
          </button>
        </>
      }
    >
      <p className="hint">
        {item.product_title}
        {item.uses ? ` · already with ${item.uses} customer${item.uses === 1 ? '' : 's'}, who keep what they received` : ''}
      </p>
      <label className="field">
        <span>Item</span>
        <textarea className="mono" rows={4} required value={content} onChange={(event) => setContent(event.target.value)} />
      </label>
      <label className="field">
        <span>Customers per item</span>
        <input type="number" min={Math.max(1, item.uses)} max={1000} step={1} value={seats} onChange={(event) => setSeats(parseInt(event.target.value, 10) || 1)} />
      </label>
      <ExpiryPicker value={expiresAt} onChange={setExpiresAt} />
    </Modal>
  );
}

function toLocalISOString(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function formatExpiryDisplay(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

function ExpiryPicker({ value, onChange }: { value: string; onChange: (val: string) => void }) {
  const [mode, setMode] = useState<'preset' | 'custom'>('preset');
  const [customAmount, setCustomAmount] = useState('12');
  const [unit, setUnit] = useState<'hours' | 'days'>('hours');
  const [activePreset, setActivePreset] = useState<number | null>(() => {
    if (!value) return null;
    const diffHours = Math.round((new Date(value).getTime() - Date.now()) / (3600 * 1000));
    if (Math.abs(diffHours - 24) <= 1) return 24;
    if (Math.abs(diffHours - 72) <= 2) return 72;
    if (Math.abs(diffHours - 168) <= 4) return 168;
    if (Math.abs(diffHours - 720) <= 8) return 720;
    return null;
  });

  const applyPreset = (presetHours: number) => {
    setMode('preset');
    setActivePreset(presetHours);
    const target = new Date(Date.now() + presetHours * 3600 * 1000);
    onChange(toLocalISOString(target));
  };

  const applyNone = () => {
    setMode('preset');
    setActivePreset(null);
    onChange('');
  };

  const applyCustom = (numStr: string, currentUnit: 'hours' | 'days') => {
    setMode('custom');
    setActivePreset(null);
    setCustomAmount(numStr);
    setUnit(currentUnit);
    const num = Number(numStr);
    if (!numStr.trim() || isNaN(num) || num <= 0) {
      onChange('');
      return;
    }
    const hours = currentUnit === 'hours' ? num : num * 24;
    const target = new Date(Date.now() + hours * 3600 * 1000);
    onChange(toLocalISOString(target));
  };

  const isNone = !value;

  return (
    <div className="field">
      <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
        Auto-Expiry <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
      </span>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* Preset quick pills */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          <button
            type="button"
            className={`expiry-preset-btn ${isNone ? 'active' : ''}`}
            onClick={applyNone}
          >
            Never (No Expiry)
          </button>
          <button
            type="button"
            className={`expiry-preset-btn ${mode === 'preset' && !isNone && activePreset === 24 ? 'active' : ''}`}
            onClick={() => applyPreset(24)}
          >
            24 Hours
          </button>
          <button
            type="button"
            className={`expiry-preset-btn ${mode === 'preset' && !isNone && activePreset === 72 ? 'active' : ''}`}
            onClick={() => applyPreset(72)}
          >
            3 Days
          </button>
          <button
            type="button"
            className={`expiry-preset-btn ${mode === 'preset' && !isNone && activePreset === 168 ? 'active' : ''}`}
            onClick={() => applyPreset(168)}
          >
            7 Days
          </button>
          <button
            type="button"
            className={`expiry-preset-btn ${mode === 'preset' && !isNone && activePreset === 720 ? 'active' : ''}`}
            onClick={() => applyPreset(720)}
          >
            30 Days
          </button>
          <button
            type="button"
            className={`expiry-preset-btn ${mode === 'custom' ? 'active' : ''}`}
            onClick={() => applyCustom(customAmount, unit)}
          >
            Custom...
          </button>
        </div>

        {/* Custom duration input (Only shown when mode === 'custom') */}
        {mode === 'custom' && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 10px',
              borderRadius: '8px',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              marginTop: '2px',
            }}
          >
            <span style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 500 }}>Expire in:</span>
            <input
              type="number"
              min="1"
              max="1000"
              value={customAmount}
              onChange={(e) => applyCustom(e.target.value, unit)}
              style={{
                width: '64px',
                height: '30px',
                padding: '0 6px',
                fontSize: '13px',
                fontWeight: 600,
                textAlign: 'center',
                border: '1px solid var(--border)',
                borderRadius: '5px',
                background: 'var(--surface)',
                color: 'var(--text)',
                outline: 'none',
              }}
            />
            {/* Hours / Days Segmented Switch */}
            <div
              style={{
                display: 'inline-flex',
                background: 'var(--surface)',
                padding: '2px',
                borderRadius: '6px',
                border: '1px solid var(--border)',
              }}
            >
              <button
                type="button"
                onClick={() => applyCustom(customAmount, 'hours')}
                style={{
                  border: 'none',
                  padding: '3px 8px',
                  fontSize: '11.5px',
                  fontWeight: unit === 'hours' ? 600 : 500,
                  borderRadius: '4px',
                  background: unit === 'hours' ? 'var(--accent)' : 'transparent',
                  color: unit === 'hours' ? '#fff' : 'var(--muted)',
                  cursor: 'pointer',
                  transition: 'all 120ms ease',
                }}
              >
                Hours
              </button>
              <button
                type="button"
                onClick={() => applyCustom(customAmount, 'days')}
                style={{
                  border: 'none',
                  padding: '3px 8px',
                  fontSize: '11.5px',
                  fontWeight: unit === 'days' ? 600 : 500,
                  borderRadius: '4px',
                  background: unit === 'days' ? 'var(--accent)' : 'transparent',
                  color: unit === 'days' ? '#fff' : 'var(--muted)',
                  cursor: 'pointer',
                  transition: 'all 120ms ease',
                }}
              >
                Days
              </button>
            </div>
          </div>
        )}

        {/* Live Status Badge - ONLY when an expiry date is set */}
        {value ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '7px 12px',
              borderRadius: '8px',
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              color: 'var(--text)',
              fontSize: '12.5px',
              marginTop: '3px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
              <Clock size={14} style={{ color: '#059669', flexShrink: 0 }} />
              <span>
                Will expire on: <strong style={{ color: '#059669' }}>{formatExpiryDisplay(value)}</strong>
              </span>
            </div>
            <button
              type="button"
              onClick={applyNone}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--danger)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '2px',
                padding: '2px 4px',
              }}
              title="Clear expiry date"
            >
              ✕ Clear
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
