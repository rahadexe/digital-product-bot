'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Zap,
  Globe,
  Wallet,
  ShieldCheck,
  Save,
  Package,
  Layers,
  ArrowRight,
  Eye,
  EyeOff,
  ExternalLink,
} from 'lucide-react';
import { api, type SupplierStatus, type Product, type Category } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { PageLoading, errorText, type Say } from './ui';

export function Suppliers({ say, onOpen }: { say: Say; onOpen?: (screen: string) => void }) {
  const [status, setStatus] = useState<SupplierStatus | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeProvider, setActiveProvider] = useState<'digital_mart' | 'safwan_tiger'>('digital_mart');

  // Form fields
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [markupPercent, setMarkupPercent] = useState<number>(15);
  const [autoSync, setAutoSync] = useState<boolean>(true);
  const [lowBalanceAlert, setLowBalanceAlert] = useState<number>(50);

  const money = useMoney();

  const loadData = useCallback(async () => {
    try {
      const [supStatus, prods, cats] = await Promise.all([
        api.supplierStatus(),
        api.products(),
        api.categories(),
      ]);
      setStatus(supStatus);
      setProducts(prods.filter((p) => p.upstream_product_id != null));
      setCategories(cats);

      const prov = supStatus.providers?.find((p) => p.code === activeProvider);
      if (prov) {
        setBaseUrl(prov.base_url);
        setMarkupPercent(prov.markup_percent ?? 15);
        setAutoSync(Boolean(prov.auto_sync ?? 1));
        setLowBalanceAlert(prov.low_balance_alert ?? (prov.currency === 'USDT' ? 5 : 50));
      } else {
        setBaseUrl(supStatus.base_url || 'https://dmb.bmdigital.bd/api/v1/reseller');
        setMarkupPercent(supStatus.markup_percent ?? 15);
        setAutoSync(Boolean(supStatus.auto_sync ?? 1));
        setLowBalanceAlert(supStatus.low_balance_alert ?? 50);
      }
    } catch (err) {
      say(errorText(err, 'Failed to load supplier status.'), 'bad');
    } finally {
      setLoading(false);
    }
  }, [say, activeProvider]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const switchProvider = (code: 'digital_mart' | 'safwan_tiger') => {
    setActiveProvider(code);
    setApiKey('');
    const prov = status?.providers?.find((p) => p.code === code);
    if (prov) {
      setBaseUrl(prov.base_url);
      setMarkupPercent(prov.markup_percent ?? 15);
      setAutoSync(Boolean(prov.auto_sync ?? 1));
      setLowBalanceAlert(prov.low_balance_alert ?? (prov.currency === 'USDT' ? 5 : 50));
    } else if (code === 'safwan_tiger') {
      setBaseUrl('https://safwantigershopbot-production.up.railway.app/api');
      setMarkupPercent(15);
      setAutoSync(false);
      setLowBalanceAlert(5);
    } else {
      setBaseUrl('https://dmb.bmdigital.bd/api/v1/reseller');
      setMarkupPercent(15);
      setAutoSync(true);
      setLowBalanceAlert(50);
    }
  };

  const handleSync = async (supplierTarget: string = 'all') => {
    setSyncing(supplierTarget);
    try {
      const res = await api.supplierSync(supplierTarget);
      say(
        res.message || `✅ Synced ${res.products_synced} products & ${res.categories_synced} categories!`,
        'good'
      );
      await loadData();
    } catch (err) {
      say(errorText(err, 'Failed to sync catalog from supplier.'), 'bad');
    } finally {
      setSyncing(null);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.supplierSaveConfig({
        supplier_code: activeProvider,
        base_url: baseUrl,
        api_key: apiKey || 'keep_existing',
        markup_percent: markupPercent,
        auto_sync: autoSync ? 1 : 0,
        low_balance_alert: lowBalanceAlert,
      });
      say(res.message, res.connected ? 'good' : 'bad');
      setApiKey('');
      await loadData();
    } catch (err) {
      say(errorText(err, 'Failed to save supplier configuration.'), 'bad');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <PageLoading />;
  }

  const dmProvider = status?.providers?.find((p) => p.code === 'digital_mart');
  const stProvider = status?.providers?.find((p) => p.code === 'safwan_tiger');

  return (
    <div className="suppliers-container" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Top Banner Header */}
      <section className="panel" style={{ margin: 0 }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
          <div>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '18px', fontWeight: 700 }}>
              <Globe size={20} style={{ color: 'var(--accent)' }} />
              Multi-Supplier Wholesale Hub
            </h2>
            <p style={{ marginTop: 4, color: 'var(--muted)', fontSize: '13px' }}>
              Connect multiple upstream wholesale providers (Digital Mart & Safwan Tiger Shop) with automated catalog syncing and resilient fallback fulfillment.
            </p>
          </div>
          <div className="actions" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn small"
              onClick={() => handleSync('safwan_tiger')}
              disabled={Boolean(syncing)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <RefreshCw size={13} className={syncing === 'safwan_tiger' ? 'spin' : ''} />
              Sync Tiger Shop
            </button>
            <button
              type="button"
              className="btn small"
              onClick={() => handleSync('digital_mart')}
              disabled={Boolean(syncing)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <RefreshCw size={13} className={syncing === 'digital_mart' ? 'spin' : ''} />
              Sync Digital Mart
            </button>
            <button
              type="button"
              className="btn primary small"
              onClick={() => handleSync('all')}
              disabled={Boolean(syncing)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
            >
              <RefreshCw size={13} className={syncing === 'all' ? 'spin' : ''} />
              {syncing === 'all' ? 'Syncing All...' : '⚡ Sync All Suppliers'}
            </button>
          </div>
        </header>
      </section>

      {/* KPI Cards Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
        {/* Digital Mart Wallet */}
        <div className="panel" style={{ margin: 0, padding: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Digital Mart Balance (BDT)
            </span>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(34, 197, 94, 0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Wallet size={17} style={{ color: '#22c55e' }} />
            </div>
          </div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: dmProvider?.connected ? 'var(--positive)' : 'var(--text)' }}>
            ৳{(dmProvider?.balance ?? 0).toFixed(2)} <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--muted)' }}>BDT</span>
          </div>
          <div style={{ marginTop: 6, fontSize: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: dmProvider?.connected ? 'var(--positive)' : 'var(--muted)' }}>
              {dmProvider?.connected ? '🟢 Connected' : dmProvider?.is_configured ? '🔴 Auth Error' : '⚪ Not configured'}
            </span>
            <span style={{ color: 'var(--muted)' }}>{dmProvider?.products_count ?? 0} products synced</span>
          </div>
        </div>

        {/* Safwan Tiger Shop Wallet */}
        <div className="panel" style={{ margin: 0, padding: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Safwan Tiger Balance (USDT)
            </span>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(59, 130, 246, 0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Wallet size={17} style={{ color: '#3b82f6' }} />
            </div>
          </div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: stProvider?.connected ? 'var(--positive)' : 'var(--text)' }}>
            ${(stProvider?.balance ?? 0).toFixed(2)} <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--muted)' }}>USDT</span>
          </div>
          <div style={{ marginTop: 6, fontSize: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: stProvider?.connected ? 'var(--positive)' : 'var(--muted)' }}>
              {stProvider?.connected ? '🟢 Connected' : stProvider?.is_configured ? '🔴 Auth Error' : '⚪ Not configured'}
            </span>
            <span style={{ color: 'var(--muted)' }}>{stProvider?.products_count ?? 0} products synced</span>
          </div>
        </div>

        {/* Catalog Coverage */}
        <div className="panel" style={{ margin: 0, padding: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Total Supplier Products
            </span>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(234, 88, 12, 0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Zap size={17} style={{ color: '#ea580c' }} />
            </div>
          </div>
          <div style={{ fontSize: '26px', fontWeight: 800 }}>
            {status?.upstream_products_count ?? 0}{' '}
            <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--muted)' }}>
              / {status?.total_products ?? 0} in store
            </span>
          </div>
          <div style={{ marginTop: 6, fontSize: '12px', color: 'var(--muted)' }}>
            Instant wholesale dropship coverage
          </div>
        </div>
      </div>

      {/* Configuration & Details Section */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
        {/* Settings Card */}
        <section className="panel" style={{ margin: 0 }}>
          <header>
            <div style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                <h2>Supplier API Credentials</h2>
                {/* Provider switcher tabs */}
                <div className="segmented" role="tablist">
                  <button
                    type="button"
                    className={activeProvider === 'digital_mart' ? 'active' : ''}
                    onClick={() => switchProvider('digital_mart')}
                  >
                    Digital Mart (BDT)
                  </button>
                  <button
                    type="button"
                    className={activeProvider === 'safwan_tiger' ? 'active' : ''}
                    onClick={() => switchProvider('safwan_tiger')}
                  >
                    Safwan Tiger (USDT)
                  </button>
                </div>
              </div>
              <p style={{ marginTop: 4 }}>
                Configure wholesale endpoint and API credentials for <strong>{activeProvider === 'safwan_tiger' ? 'Safwan Tiger Shop' : 'Digital Mart'}</strong>.
              </p>
            </div>
          </header>
          <div className="panel-body">
            <form onSubmit={handleSaveConfig} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                  Provider API Base URL
                </label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={activeProvider === 'safwan_tiger' ? 'https://safwantigershopbot-production.up.railway.app/api' : 'https://dmb.bmdigital.bd/api/v1/reseller'}
                  required
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
                <small style={{ display: 'block', marginTop: 4, color: 'var(--muted)', fontSize: '11.5px' }}>
                  {activeProvider === 'safwan_tiger' ? 'Serves /balance, /products, and /order.' : 'Serves /me, /products, and /orders.'}
                </small>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                  API Key ({activeProvider === 'safwan_tiger' ? 'Safwan Tiger' : 'Digital Mart'})
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={
                      (activeProvider === 'safwan_tiger' ? stProvider?.api_key_masked : dmProvider?.api_key_masked)
                        ? `Configured: ${activeProvider === 'safwan_tiger' ? stProvider?.api_key_masked : dmProvider?.api_key_masked}`
                        : 'Enter secret API key...'
                    }
                    style={{ width: '100%', paddingRight: 40, boxSizing: 'border-box' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    style={{
                      position: 'absolute',
                      right: 8,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none',
                      border: 'none',
                      color: 'var(--muted)',
                      cursor: 'pointer',
                    }}
                  >
                    {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <small style={{ display: 'block', marginTop: 4, color: 'var(--muted)', fontSize: '11.5px' }}>
                  Leave blank to keep existing configured key.
                </small>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                    Profit Margin Markup (%)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="200"
                    step="1"
                    value={markupPercent}
                    onChange={(e) => setMarkupPercent(Number(e.target.value))}
                    required
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                  <small style={{ display: 'block', marginTop: 4, color: 'var(--muted)', fontSize: '11.5px' }}>
                    Auto-added on wholesale rate (e.g. 15% margin).
                  </small>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                    Low Balance Alert Threshold ({activeProvider === 'safwan_tiger' ? 'USDT' : '৳'})
                  </label>
                  <input
                    type="number"
                    min="0"
                    step={activeProvider === 'safwan_tiger' ? '1' : '5'}
                    value={lowBalanceAlert}
                    onChange={(e) => setLowBalanceAlert(Number(e.target.value))}
                    required
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                  <small style={{ display: 'block', marginTop: 4, color: 'var(--muted)', fontSize: '11.5px' }}>
                    Telegram alert sent to admins if balance drops below this.
                  </small>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                <input
                  type="checkbox"
                  id="auto_sync"
                  checked={autoSync}
                  onChange={(e) => setAutoSync(e.target.checked)}
                  style={{ width: 16, height: 16, cursor: 'pointer' }}
                />
                <label htmlFor="auto_sync" style={{ fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}>
                  Enable Periodic Background Catalog Sync for {activeProvider === 'safwan_tiger' ? 'Safwan Tiger' : 'Digital Mart'}
                </label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                <button
                  type="submit"
                  className="btn primary"
                  disabled={saving}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
                >
                  <Save size={15} />
                  {saving ? 'Saving...' : `Save & Test ${activeProvider === 'safwan_tiger' ? 'Tiger Shop' : 'Digital Mart'}`}
                </button>
              </div>
            </form>
          </div>
        </section>

        {/* How It Works Guide */}
        <section className="panel" style={{ margin: 0 }}>
          <header>
            <div>
              <h2>How Dropshipping Works</h2>
              <p>Automated fulfillment flow without holding stock locally.</p>
            </div>
          </header>
          <div className="panel-body" style={{ fontSize: '13px', lineHeight: '1.6', color: 'var(--muted)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontWeight: 700, fontSize: '12px' }}>
                  1
                </div>
                <div>
                  <strong style={{ color: 'var(--text)', display: 'block' }}>One-Click Catalog Sync</strong>
                  Sync categories, titles, durations, and reseller wholesale rates directly from the provider into your store.
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontWeight: 700, fontSize: '12px' }}>
                  2
                </div>
                <div>
                  <strong style={{ color: 'var(--text)', display: 'block' }}>Instant Customer Delivery</strong>
                  When a customer purchases a supplier product, the bot charges their wallet and instantly places an order with the supplier API.
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontWeight: 700, fontSize: '12px' }}>
                  3
                </div>
                <div>
                  <strong style={{ color: 'var(--text)', display: 'block' }}>Zero Inventory Maintenance</strong>
                  Credentials and license keys returned by the supplier are directly forwarded to the customer in Telegram. No manual stock uploads needed!
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Supplier Products List */}
      <section className="panel" style={{ margin: 0 }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <h2>Synced Supplier Products ({products.length})</h2>
            <p>Products fulfilled automatically through Digital Mart Reseller API.</p>
          </div>
          {onOpen && (
            <button
              type="button"
              className="btn small ghost"
              onClick={() => onOpen('products')}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              View in Products <ArrowRight size={14} />
            </button>
          )}
        </header>

        {products.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--muted)' }}>
            <Layers size={36} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
            <p style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text)' }}>No products synced from supplier yet</p>
            <p style={{ fontSize: '12.5px', marginTop: 4 }}>
              Click &quot;Sync Catalog Now&quot; above to import live products from your upstream supplier.
            </p>
          </div>
        ) : (
          <div className="scroll">
            <table className="mobile-records">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Category</th>
                  <th>Duration</th>
                  <th>Retail Price</th>
                  <th>Wholesale Rate</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  const cat = categories.find((c) => c.id === p.category_id);
                  return (
                    <tr key={p.id}>
                      <td className="name" style={{ fontWeight: 600 }}>
                        <span style={{ marginRight: 6 }}>{p.icon || '📦'}</span>
                        {p.title}
                        <small style={{ display: 'block', color: 'var(--muted)', fontSize: '11px' }}>
                          Supplier ID: #{p.upstream_product_id} • {p.supplier_code === 'safwan_tiger' ? 'Safwan Tiger (USDT)' : 'Digital Mart (BDT)'}
                        </small>
                      </td>
                      <td>{cat?.name || 'General'}</td>
                      <td>{p.duration_label || '—'}</td>
                      <td style={{ fontWeight: 700 }}>{money(p.price)}</td>
                      <td style={{ color: 'var(--accent)', fontWeight: 600 }}>
                        {p.reseller_price != null ? money(p.reseller_price) : '—'}
                      </td>
                      <td>
                        <span className={`pill ${p.is_active ? 'good' : 'bad'}`}>
                          {p.is_active ? 'Active' : 'Hidden'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
