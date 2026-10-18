'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api,
  forgetAnswers,
  type SupplierStatus,
  type Product,
  type Category,
  type RemoteSupplierProduct,
  type RemoteSupplierCatalogResponse,
} from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { Modal, PageLoading, errorText, useConfirm, type Say } from './ui';
import { CustomSelect } from './CustomSelect';
import { MobileRecordDetails } from './MobileRecordDetails';

export function Suppliers({ say, onOpen }: { say: Say; onOpen?: (screen: string) => void }) {
  const [status, setStatus] = useState<SupplierStatus | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeProvider, setActiveProvider] = useState<'digital_mart' | 'safwan_tiger'>('digital_mart');
  const [confirm, confirmDialog] = useConfirm();
  const [apiSettingsOpen, setApiSettingsOpen] = useState(false);
  const formInitialized = useRef(false);

  // Form fields
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [markupPercent, setMarkupPercent] = useState<number>(15);
  const [autoSync, setAutoSync] = useState<boolean>(true);
  const [lowBalanceAlert, setLowBalanceAlert] = useState<number>(50);

  // Tab View Mode: 'synced' | 'explore'
  const [viewMode, setViewMode] = useState<'synced' | 'explore'>('synced');

  // Filter & Search state for Synced Products
  const [syncedSearch, setSyncedSearch] = useState('');
  const [syncedSupplierFilter, setSyncedSupplierFilter] = useState<'all' | 'digital_mart' | 'safwan_tiger'>('all');
  const [syncedCategoryFilter, setSyncedCategoryFilter] = useState<string>('all');
  const [syncedStatusFilter, setSyncedStatusFilter] = useState<'all' | 'active' | 'hidden'>('all');
  const [selectedSyncedIds, setSelectedSyncedIds] = useState<number[]>([]);
  const [syncedPage, setSyncedPage] = useState(1);
  const [syncedPageSize, setSyncedPageSize] = useState<number>(25);
  const [bulkActing, setBulkActing] = useState(false);

  // State for Live Remote Supplier Catalog Explorer
  const [exploreSupplier, setExploreSupplier] = useState<'digital_mart' | 'safwan_tiger'>('digital_mart');
  const [remoteSearch, setRemoteSearch] = useState('');
  const [remoteCategoryFilter, setRemoteCategoryFilter] = useState('all');
  const [remoteCatalog, setRemoteCatalog] = useState<RemoteSupplierCatalogResponse | null>(null);
  const [remoteLoading, setRemoteLoading] = useState(false);
  const [remoteError, setRemoteError] = useState('');
  const remoteRequest = useRef(0);
  const statusRequest = useRef(0);
  const [selectedRemoteIds, setSelectedRemoteIds] = useState<number[]>([]);
  const [remoteImporting, setRemoteImporting] = useState(false);
  const [importActivateImmediately, setImportActivateImmediately] = useState(false);
  const [importTargetCategoryId, setImportTargetCategoryId] = useState<string>('auto');

  const money = useMoney();

  const loadData = useCallback(async () => {
    const request = ++statusRequest.current;
    try {
      const [supStatus, prods, cats] = await Promise.all([
        api.supplierStatus(),
        api.products(),
        api.categories(),
      ]);
      if (request !== statusRequest.current) return;
      setStatus(supStatus);
      setProducts(prods.filter((p) => p.upstream_product_id != null));
      setCategories(cats);

      const prov = supStatus.providers?.find((p) => p.code === 'digital_mart');
      if (!formInitialized.current && prov) {
        setBaseUrl(prov.base_url);
        setMarkupPercent(prov.markup_percent ?? 15);
        setAutoSync(Boolean(prov.auto_sync ?? 1));
        setLowBalanceAlert(prov.low_balance_alert ?? (prov.currency === 'USDT' ? 5 : 50));
      } else if (!formInitialized.current) {
        setBaseUrl(supStatus.base_url || 'https://dmb.bmdigital.bd/api/v1/reseller');
        setMarkupPercent(supStatus.markup_percent ?? 15);
        setAutoSync(Boolean(supStatus.auto_sync ?? 1));
        setLowBalanceAlert(supStatus.low_balance_alert ?? 50);
      }
      formInitialized.current = true;
    } catch (err) {
      if (request === statusRequest.current) say(errorText(err, 'Could not load suppliers.'), 'bad');
    } finally {
      if (request === statusRequest.current) setLoading(false);
    }
  }, [say]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const loadRemoteCatalog = useCallback(async (supplierCode = exploreSupplier, refresh = false) => {
    if (refresh) forgetAnswers();
    const request = ++remoteRequest.current;
    setRemoteLoading(true);
    setRemoteError('');
    setRemoteCatalog(null);
    setSelectedRemoteIds([]);
    try {
      const res = await api.supplierRemoteProducts(supplierCode);
      if (request !== remoteRequest.current) return;
      setRemoteCatalog(res);
    } catch (err) {
      if (request === remoteRequest.current) {
        setRemoteError(errorText(err, 'Could not load catalog. Check the supplier settings.'));
      }
    } finally {
      if (request === remoteRequest.current) setRemoteLoading(false);
    }
  }, [exploreSupplier]);

  useEffect(() => {
    if (viewMode === 'explore') {
      void loadRemoteCatalog(exploreSupplier);
    }
    return () => { remoteRequest.current += 1; };
  }, [viewMode, exploreSupplier, loadRemoteCatalog]);

  const switchProvider = (code: 'digital_mart' | 'safwan_tiger') => {
    setActiveProvider(code);
    setApiKey('');
    setShowApiKey(false);
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

  const switchCatalog = (code: 'digital_mart' | 'safwan_tiger') => {
    if (code === exploreSupplier) return;
    remoteRequest.current += 1;
    setRemoteCatalog(null);
    setSelectedRemoteIds([]);
    setRemoteCategoryFilter('all');
    setRemoteSearch('');
    setRemoteError('');
    setExploreSupplier(code);
  };

  const handleSync = async (supplierTarget: string = 'all') => {
    setSyncing(supplierTarget);
    try {
      const res = await api.supplierSync(supplierTarget);
      say(
        res.message || `Synced ${res.products_synced} products & ${res.categories_synced} categories.`,
        'good'
      );
      await loadData();
      if (viewMode === 'explore') {
        void loadRemoteCatalog();
      }
    } catch (err) {
      say(errorText(err, 'Failed to sync catalog from supplier.'), 'bad');
    } finally {
      setSyncing(null);
    }
  };

  const openApiSettings = (code: 'digital_mart' | 'safwan_tiger') => {
    switchProvider(code);
    setApiSettingsOpen(true);
  };

  const closeApiSettings = () => {
    if (saving) return;
    setApiSettingsOpen(false);
    setApiKey('');
    setShowApiKey(false);
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

  // Toggle active/hidden for a synced product
  const toggleProductActive = async (p: Product) => {
    try {
      await api.updateProduct(p.id, { is_active: p.is_active ? 0 : 1 });
      say(`${p.title} is now ${p.is_active ? 'Hidden' : 'Active'}.`, 'good');
      await loadData();
      if (viewMode === 'explore') {
        void loadRemoteCatalog();
      }
    } catch (err) {
      say(errorText(err, 'Failed to update product status.'), 'bad');
    }
  };

  // Bulk actions for synced products
  const handleBulkSyncedAction = async (action: 'activate' | 'hide' | 'delete') => {
    if (!selectedSyncedIds.length) return;
    const actionLabel = action === 'activate' ? 'Activate' : action === 'hide' ? 'Hide' : 'Permanently Delete';
    if (
      !(await confirm(
        `${actionLabel} ${selectedSyncedIds.length} Products?`,
        `Are you sure you want to ${action} the selected ${selectedSyncedIds.length} supplier products?`,
        actionLabel,
        action === 'delete'
      ))
    ) {
      return;
    }
    setBulkActing(true);
    try {
      const res = await api.bulkProducts(action, selectedSyncedIds);
      say(res.message, 'good');
      setSelectedSyncedIds([]);
      await loadData();
      if (viewMode === 'explore') {
        void loadRemoteCatalog();
      }
    } catch (err) {
      say(errorText(err, `Failed to bulk ${action} products.`), 'bad');
    } finally {
      setBulkActing(false);
    }
  };

  // Import single remote product
  const handleImportRemoteProduct = async (remoteProd: RemoteSupplierProduct) => {
    if (remoteLoading || remoteCatalog?.supplier !== exploreSupplier || remoteImporting) return;
    setRemoteImporting(true);
    const targetCat = importTargetCategoryId !== 'auto' ? Number(importTargetCategoryId) : null;
    try {
      const res = await api.supplierImportProducts({
        supplier_code: exploreSupplier,
        product_ids: [remoteProd.id],
        activate: importActivateImmediately,
        target_category_id: targetCat,
      });
      say(res.message, 'good');
      await loadData();
      void loadRemoteCatalog();
    } catch (err) {
      say(errorText(err, 'Failed to import product.'), 'bad');
    } finally {
      setRemoteImporting(false);
    }
  };

  // Bulk import selected remote products
  const handleBulkImportRemote = async () => {
    if (!selectedRemoteIds.length || remoteLoading || remoteCatalog?.supplier !== exploreSupplier || remoteImporting) return;
    setRemoteImporting(true);
    const targetCat = importTargetCategoryId !== 'auto' ? Number(importTargetCategoryId) : null;
    try {
      const res = await api.supplierImportProducts({
        supplier_code: exploreSupplier,
        product_ids: selectedRemoteIds,
        activate: importActivateImmediately,
        target_category_id: targetCat,
      });
      say(res.message, 'good');
      setSelectedRemoteIds([]);
      await loadData();
      void loadRemoteCatalog();
    } catch (err) {
      say(errorText(err, 'Failed to import selected products.'), 'bad');
    } finally {
      setRemoteImporting(false);
    }
  };

  if (loading) {
    return <PageLoading />;
  }

  const dmProvider = status?.providers?.find((p) => p.code === 'digital_mart');
  const stProvider = status?.providers?.find((p) => p.code === 'safwan_tiger');

  // Filter synced products
  const filteredSynced = products.filter((p) => {
    // Search filter
    if (syncedSearch) {
      const q = syncedSearch.toLowerCase();
      const matchTitle = p.title.toLowerCase().includes(q);
      const matchId = String(p.upstream_product_id).includes(q) || String(p.id).includes(q);
      const cat = categories.find((c) => c.id === p.category_id);
      const matchCat = cat?.name?.toLowerCase().includes(q);
      if (!matchTitle && !matchId && !matchCat) return false;
    }
    // Supplier filter
    if (syncedSupplierFilter === 'digital_mart') {
      if (p.supplier_code && p.supplier_code !== 'digital_mart') return false;
    } else if (syncedSupplierFilter === 'safwan_tiger') {
      if (p.supplier_code !== 'safwan_tiger') return false;
    }
    // Category filter
    if (syncedCategoryFilter !== 'all') {
      if (String(p.category_id) !== syncedCategoryFilter) return false;
    }
    // Status filter
    if (syncedStatusFilter === 'active' && !p.is_active) return false;
    if (syncedStatusFilter === 'hidden' && p.is_active) return false;

    return true;
  });

  // Synced pagination
  const totalSyncedPages = Math.max(1, Math.ceil(filteredSynced.length / syncedPageSize));
  const paginatedSynced = filteredSynced.slice(
    (syncedPage - 1) * syncedPageSize,
    syncedPage * syncedPageSize
  );

  const allVisibleSyncedSelected =
    paginatedSynced.length > 0 && paginatedSynced.every((p) => selectedSyncedIds.includes(p.id));

  const toggleSelectAllVisibleSynced = () => {
    if (allVisibleSyncedSelected) {
      const pageIds = new Set(paginatedSynced.map((p) => p.id));
      setSelectedSyncedIds(selectedSyncedIds.filter((id) => !pageIds.has(id)));
    } else {
      const newIds = new Set([...selectedSyncedIds, ...paginatedSynced.map((p) => p.id)]);
      setSelectedSyncedIds(Array.from(newIds));
    }
  };

  // Remote products filter
  const filteredRemote = (remoteCatalog?.products ?? []).filter((rp) => {
    const query = remoteSearch.trim().toLowerCase();
    if (query && !`${rp.title} ${rp.category_name} ${rp.id}`.toLowerCase().includes(query)) return false;
    if (remoteCategoryFilter !== 'all' && rp.category_name !== remoteCategoryFilter) {
      return false;
    }
    return true;
  });

  const allVisibleRemoteSelected =
    filteredRemote.length > 0 && filteredRemote.every((rp) => selectedRemoteIds.includes(rp.id));

  const toggleSelectAllRemote = () => {
    if (allVisibleRemoteSelected) {
      setSelectedRemoteIds([]);
    } else {
      setSelectedRemoteIds(filteredRemote.map((rp) => rp.id));
    }
  };

  return (
    <div className="suppliers-container" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {confirmDialog}

      <section className="panel supplier-directory">
        <header><button type="button" className="btn ghost small" disabled={Boolean(syncing) || !status?.providers?.some(provider => provider.is_configured)} onClick={() => handleSync('all')}>{syncing ? 'Syncing…' : 'Sync all'}</button></header>
        <div className="scroll" role="region" aria-label="Suppliers table" tabIndex={0}>
          <table><thead><tr><th scope="col">Supplier</th><th scope="col">Status</th><th scope="col" className="right">Balance</th><th scope="col" className="right">Products</th><th scope="col" className="right">Actions</th></tr></thead>
          <tbody>{[{ code: 'digital_mart', name: 'Digital Mart', provider: dmProvider, currency: 'BDT' }, { code: 'safwan_tiger', name: 'Safwan Tiger', provider: stProvider, currency: 'USDT' }].map(({ code, name, provider, currency }) => <tr key={code}>
            <td><strong>{name}</strong></td>
            <td><span className={`pill ${provider?.connected ? 'good' : provider?.is_configured ? 'bad' : ''}`}>{provider?.connected ? 'Connected' : provider?.is_configured ? 'Connection error' : 'Not configured'}</span></td>
              <td className="right money">{provider?.connected && provider.balance != null ? `${provider.balance.toFixed(2)} ${currency}` : ''}</td>
            <td className="right">{provider?.products_count ?? 0}</td>
            <td className="right"><div className="supplier-actions">
              <button type="button" className="btn primary small" disabled={saving} aria-label={`${provider?.is_configured ? 'Edit' : 'Add'} API for ${name}`} onClick={() => openApiSettings(code as 'digital_mart' | 'safwan_tiger')}>{provider?.is_configured ? 'Edit API' : 'Add API'}</button>
              <button type="button" className="btn ghost small" disabled={Boolean(syncing) || !provider?.is_configured} onClick={() => handleSync(code)}>Sync</button>
            </div></td>
          </tr>)}</tbody></table>
        </div>
      </section>

      {apiSettingsOpen ? <Modal title={`${activeProvider === 'digital_mart' ? 'Digital Mart' : 'Safwan Tiger'} API`} onClose={closeApiSettings} className="supplier-api-dialog">
            <form onSubmit={handleSaveConfig} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                  API URL
                </label>
                <input
                  type="url"
                  aria-label="Supplier API URL"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={activeProvider === 'safwan_tiger' ? 'https://safwantigershopbot-production.up.railway.app/api' : 'https://dmb.bmdigital.bd/api/v1/reseller'}
                  required
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                  API key
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    aria-label="Supplier API key"
                    autoComplete="new-password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={
                      (activeProvider === 'safwan_tiger' ? stProvider?.api_key_masked : dmProvider?.api_key_masked)
                        ? 'Key configured'
                        : 'Enter API key'
                    }
                    style={{ width: '100%', paddingRight: 40, boxSizing: 'border-box' }}
                  />
                  <button
                    type="button"
                    aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
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
                    {showApiKey ? 'Hide' : 'Show'}
                  </button>
                </div>
                <small style={{ display: 'block', marginTop: 4, color: 'var(--muted)', fontSize: '11.5px' }}>
                  Leave blank to keep the saved key.
                </small>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                    Markup (%)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="500"
                    step="0.01"
                    value={markupPercent}
                    onChange={(e) => setMarkupPercent(Number(e.target.value))}
                    required
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                  <small style={{ display: 'block', marginTop: 4, color: 'var(--muted)', fontSize: '11.5px' }}>
                    Markup on wholesale price.
                  </small>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
                    Balance alert ({activeProvider === 'safwan_tiger' ? 'USDT' : '৳'})
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={lowBalanceAlert}
                    onChange={(e) => setLowBalanceAlert(Number(e.target.value))}
                    required
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
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
                  Auto sync
                </label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                <button
                  type="submit"
                  className="btn primary"
                  disabled={saving}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
                >
                  {saving ? 'Connecting...' : 'Save & connect'}
                </button>
              </div>
            </form>
      </Modal> : null}

      {/* Main Catalog View Section: Mode Switcher (Synced Products vs Live Supplier Explorer) */}
      <section className="panel" style={{ margin: 0 }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* View switcher tabs */}
            <div className="segmented" role="tablist">
              <button
                type="button"
                className={viewMode === 'synced' ? 'active' : ''}
                onClick={() => setViewMode('synced')}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
              >
                Imported ({filteredSynced.length})
              </button>
              <button
                type="button"
                className={viewMode === 'explore' ? 'active' : ''}
                onClick={() => setViewMode('explore')}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
              >
                Browse catalog {remoteCatalog ? `(${remoteCatalog.total})` : ''}
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {onOpen && (
              <button
                type="button"
                className="btn small ghost"
                onClick={() => onOpen('products')}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                Open Full Catalog
              </button>
            )}
          </div>
        </header>
        <p style={{ margin: '0 18px 12px', color: 'var(--muted)' }}>Store retail and wholesale prices and customer balances use BDT. Remote supplier prices show the supplier's source currency; imported USD/USDT wholesale costs are converted to BDT using the Settings exchange rate.</p>

        {/* TAB 1: SYNCED STORE PRODUCTS */}
        {viewMode === 'synced' && (
          <div className="panel-body" style={{ padding: 0 }}>
            {/* Filter & Search Bar */}
            <div
              className="supplier-catalog-filters"
              style={{
                padding: '14px 18px',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                background: 'var(--bg-subtle, rgba(0,0,0,0.02))',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', flex: 1 }}>
                {/* Search Input */}
                <div style={{ position: 'relative', minWidth: 220, flex: 1, maxWidth: 360 }}>
                  <input
                    type="search"
                    placeholder="Search supplier products or ID..."
                    value={syncedSearch}
                    onChange={(e) => {
                      setSyncedSearch(e.target.value);
                      setSyncedPage(1);
                    }}
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>

                {/* Supplier Filter */}
                <CustomSelect
                  value={syncedSupplierFilter}
                  onChange={(val) => {
                    setSyncedSupplierFilter(val as any);
                    setSyncedPage(1);
                  }}
                  options={[
                    { value: 'all', label: `All Suppliers (${products.length})` },
                    {
                      value: 'digital_mart',
                      label: `Digital Mart (${products.filter((p) => !p.supplier_code || p.supplier_code === 'digital_mart').length})`,
                    },
                    {
                      value: 'safwan_tiger',
                      label: `Safwan Tiger (${products.filter((p) => p.supplier_code === 'safwan_tiger').length})`,
                    },
                  ]}
                  minWidth={160}
                />

                {/* Category Filter */}
                <CustomSelect
                  value={syncedCategoryFilter}
                  onChange={(val) => {
                    setSyncedCategoryFilter(val);
                    setSyncedPage(1);
                  }}
                  options={[
                    { value: 'all', label: 'All Categories' },
                    ...categories.map((c) => ({
                      value: String(c.id),
                      label: c.name,
                    })),
                  ]}
                  minWidth={150}
                />

                {/* Status Filter */}
                <CustomSelect
                  value={syncedStatusFilter}
                  onChange={(val) => {
                    setSyncedStatusFilter(val as any);
                    setSyncedPage(1);
                  }}
                  options={[
                    { value: 'all', label: 'All Status' },
                    { value: 'active', label: `Active (${products.filter((p) => p.is_active).length})` },
                    { value: 'hidden', label: `Hidden (${products.filter((p) => !p.is_active).length})` },
                  ]}
                  minWidth={130}
                />
              </div>

              {/* Items per page */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '12px', color: 'var(--muted)' }}>
                <span>Show:</span>
                <CustomSelect
                  value={String(syncedPageSize)}
                  onChange={(val) => {
                    setSyncedPageSize(Number(val));
                    setSyncedPage(1);
                  }}
                  options={[
                    { value: '20', label: '20' },
                    { value: '50', label: '50' },
                    { value: '100', label: '100' },
                    { value: '500', label: 'All' },
                  ]}
                  minWidth={85}
                />
              </div>
            </div>

            {/* Bulk Actions Bar when items selected */}
            {selectedSyncedIds.length > 0 && (
              <div
                style={{
                  padding: '10px 18px',
                  background: 'rgba(14, 165, 233, 0.08)',
                  borderBottom: '1px solid rgba(14, 165, 233, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '13px', fontWeight: 600 }}>
                  <span>{selectedSyncedIds.length} product(s) selected</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn small"
                    disabled={bulkActing}
                    onClick={() => handleBulkSyncedAction('activate')}
                    style={{ color: '#16a34a', borderColor: '#16a34a' }}
                  >
                    Activate Selected
                  </button>
                  <button
                    type="button"
                    className="btn small"
                    disabled={bulkActing}
                    onClick={() => handleBulkSyncedAction('hide')}
                  >
                    Hide Selected
                  </button>
                  <button
                    type="button"
                    className="btn small danger"
                    disabled={bulkActing}
                    onClick={() => handleBulkSyncedAction('delete')}
                  >
                    Delete Selected
                  </button>
                  <button
                    type="button"
                    className="btn small ghost"
                    onClick={() => setSelectedSyncedIds([])}
                  >
                    Clear Selection
                  </button>
                </div>
              </div>
            )}

            {/* Table of Synced Products */}
            {filteredSynced.length === 0 ? (
              <p className="supplier-empty">No products found.</p>
            ) : (
              <>
              <label className="app-select-all"><input type="checkbox" checked={allVisibleSyncedSelected} onChange={toggleSelectAllVisibleSynced} /> Select page</label>
              <ul className="app-record-list supplier-product-feed" aria-label="Synced supplier products">
                {paginatedSynced.map(product => <li key={product.id}>
                  <label className="app-record-select"><input type="checkbox" aria-label={`Select supplier product ${product.id}`} checked={selectedSyncedIds.includes(product.id)} onChange={event => setSelectedSyncedIds(ids => event.target.checked ? [...ids, product.id] : ids.filter(id => id !== product.id))} /></label>
                  <MobileRecordDetails title={product.title} subtitle={product.supplier_code === 'safwan_tiger' ? 'Safwan Tiger' : 'Digital Mart'} meta={product.duration_label || undefined} amount={money(product.price)} status={product.is_active ? 'Active' : 'Hidden'} tone={product.is_active ? 'good' : 'neutral'} icon={product.icon || undefined} label={`View supplier product ${product.id}`} fields={[
                    ['Product', product.title], ['Supplier ID', product.upstream_product_id], ['Category', categories.find(category => category.id === product.category_id)?.name || 'General'],
                    ['Retail price (BDT)', `${money(product.price)} BDT`], ['Wholesale rate (BDT)', product.reseller_price != null ? `${money(product.reseller_price)} BDT` : 'Not set'], ['Duration', product.duration_label || 'Default'],
                  ]}>
                    <button type="button" className="btn" onClick={() => void toggleProductActive(product)}>{product.is_active ? 'Hide product' : 'Activate product'}</button>
                  </MobileRecordDetails>
                </li>)}
              </ul>
              <div className="scroll desktop-record-scroll">
                <table className="mobile-records">
                  <thead>
                    <tr>
                      <th style={{ width: 36, textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={allVisibleSyncedSelected}
                          onChange={toggleSelectAllVisibleSynced}
                          style={{ cursor: 'pointer' }}
                          title="Select all on this page"
                        />
                      </th>
                      <th>Product</th>
                      <th>Supplier</th>
                      <th>Category</th>
                      <th>Retail Price (BDT)</th>
                      <th>Wholesale Rate (BDT)</th>
                      <th style={{ textAlign: 'center' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedSynced.map((p) => {
                      const cat = categories.find((c) => c.id === p.category_id);
                      const isSelected = selectedSyncedIds.includes(p.id);
                      const isTiger = p.supplier_code === 'safwan_tiger';
                      return (
                        <tr key={p.id} style={{ background: isSelected ? 'rgba(14, 165, 233, 0.04)' : undefined }}>
                          <td style={{ textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedSyncedIds([...selectedSyncedIds, p.id]);
                                } else {
                                  setSelectedSyncedIds(selectedSyncedIds.filter((id) => id !== p.id));
                                }
                              }}
                              style={{ cursor: 'pointer' }}
                            />
                          </td>
                          <td className="name" style={{ fontWeight: 600 }}>
                            {p.icon ? <span style={{ marginRight: 6 }}>{p.icon}</span> : null}
                            {p.title}
                            <small style={{ display: 'block', color: 'var(--muted)', fontSize: '11px', marginTop: 2 }}>
                              #{p.upstream_product_id}, {p.duration_label || 'Default'}
                            </small>
                          </td>
                          <td>
                            <span
                              className="pill"
                              style={{
                                fontSize: '11px',
                                fontWeight: 600,
                                background: isTiger ? 'rgba(59, 130, 246, 0.1)' : 'rgba(34, 197, 94, 0.1)',
                                color: isTiger ? '#2563eb' : '#16a34a',
                                border: `1px solid ${isTiger ? 'rgba(59, 130, 246, 0.25)' : 'rgba(34, 197, 94, 0.25)'}`,
                              }}
                            >
                              {isTiger ? 'Safwan Tiger' : 'Digital Mart'}
                            </span>
                          </td>
                          <td>{cat?.name || 'General'}</td>
                          <td style={{ fontWeight: 700 }}>{money(p.price)}</td>
                          <td style={{ color: 'var(--accent)', fontWeight: 600 }}>
                            {p.reseller_price != null ? money(p.reseller_price) : 'Not set'}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button
                              type="button"
                              onClick={() => toggleProductActive(p)}
                              className={`pill ${p.is_active ? 'good' : 'bad'}`}
                              style={{ cursor: 'pointer', border: 'none', fontWeight: 600, padding: '3px 8px' }}
                              title="Click to toggle Active / Hidden"
                            >
                              {p.is_active ? 'Active' : 'Hidden'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              </>
            )}

            {/* Synced Pagination footer */}
            {filteredSynced.length > 0 && (
              <div
                style={{
                  padding: '12px 18px',
                  borderTop: '1px solid var(--border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 10,
                  fontSize: '13px',
                }}
              >
                <div style={{ color: 'var(--muted)' }}>
                  Showing {(syncedPage - 1) * syncedPageSize + 1} to{' '}
                  {Math.min(syncedPage * syncedPageSize, filteredSynced.length)} of {filteredSynced.length} products
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <button
                    type="button"
                    className="btn small"
                    disabled={syncedPage <= 1}
                    onClick={() => setSyncedPage(syncedPage - 1)}
                  >
                    Prev
                  </button>
                  <span style={{ padding: '0 6px', fontWeight: 600 }}>
                    Page {syncedPage} of {totalSyncedPages}
                  </span>
                  <button
                    type="button"
                    className="btn small"
                    disabled={syncedPage >= totalSyncedPages}
                    onClick={() => setSyncedPage(syncedPage + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: LIVE REMOTE SUPPLIER CATALOG EXPLORER */}
        {viewMode === 'explore' && (
          <div className="panel-body" style={{ padding: 0 }}>
            {/* Explorer Controls Bar */}
            <div
              className="supplier-catalog-filters"
              style={{
                padding: '14px 18px',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                background: 'var(--bg-subtle, rgba(0,0,0,0.02))',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', flex: 1 }}>
                {/* Provider switcher */}
                <div className="segmented" role="tablist">
                  <button
                    type="button"
                    className={exploreSupplier === 'digital_mart' ? 'active' : ''}
                    disabled={remoteImporting}
                    onClick={() => switchCatalog('digital_mart')}
                  >
                    Digital Mart API
                  </button>
                  <button
                    type="button"
                    className={exploreSupplier === 'safwan_tiger' ? 'active' : ''}
                    disabled={remoteImporting}
                    onClick={() => switchCatalog('safwan_tiger')}
                  >
                    Safwan Tiger API
                  </button>
                </div>

                {/* Live Search */}
                <div style={{ position: 'relative', minWidth: 200, flex: 1, maxWidth: 320 }}>
                  <input
                    type="search"
                    placeholder="Search live supplier catalog..."
                    value={remoteSearch}
                    onChange={(e) => setRemoteSearch(e.target.value)}
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>

                {/* Category filter */}
                {remoteCatalog?.categories && (
                  <CustomSelect
                    value={remoteCategoryFilter}
                    onChange={(val) => setRemoteCategoryFilter(val)}
                    options={[
                      { value: 'all', label: `All Remote Categories (${remoteCatalog.categories.length})` },
                      ...remoteCatalog.categories.map((c) => ({
                        value: c,
                        label: c,
                      })),
                    ]}
                    minWidth={180}
                  />
                )}

                <button
                  type="button"
                  className="btn small"
                  onClick={() => loadRemoteCatalog(exploreSupplier, true)}
                  disabled={remoteLoading || remoteImporting}
                >
                  Refresh API
                </button>
              </div>

            {/* Options */}
              <div className="supplier-import-options" style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)' }}>Store Category:</span>
                  <CustomSelect
                    value={importTargetCategoryId}
                    onChange={(val) => setImportTargetCategoryId(val)}
                    options={[
                      { value: 'auto', label: 'Auto (Use Remote Category)' },
                      ...categories.map((c) => ({
                        value: String(c.id),
                        label: `${c.icon ? c.icon + ' ' : ''}${c.name}`,
                      })),
                    ]}
                    minWidth={170}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input
                    type="checkbox"
                    id="import_activate"
                    checked={importActivateImmediately}
                    onChange={(e) => setImportActivateImmediately(e.target.checked)}
                    style={{ width: 15, height: 15, cursor: 'pointer' }}
                  />
                  <label htmlFor="import_activate" style={{ fontSize: '12.5px', fontWeight: 600, cursor: 'pointer' }}>
                    Make Active Immediately
                  </label>
                </div>
              </div>
            </div>

            {/* Bulk Import Bar */}
            {selectedRemoteIds.length > 0 && (
              <div
                className="supplier-import-selection"
                style={{
                  padding: '10px 18px',
                  background: 'rgba(34, 197, 94, 0.08)',
                  borderBottom: '1px solid rgba(34, 197, 94, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '13px', fontWeight: 600 }}>
                  <span>{selectedRemoteIds.length} selected</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    type="button"
                    className="btn primary small"
                    disabled={remoteImporting}
                    onClick={handleBulkImportRemote}
                    style={{ display: 'inline-flex', alignItems: 'center', fontWeight: 600 }}
                  >
                    {remoteImporting ? 'Importing…' : `Import selected (${selectedRemoteIds.length})`}
                  </button>
                  <button
                    type="button"
                    className="btn small ghost"
                    onClick={() => setSelectedRemoteIds([])}
                  >
                    Clear
                  </button>
                </div>
              </div>
            )}

            {/* Remote Explorer Body */}
            {remoteLoading ? (
              <div style={{ padding: '60px 20px', textAlign: 'center' }}>
                <p style={{ fontWeight: 600, color: 'var(--muted)' }}>
                  Fetching live products from {exploreSupplier === 'safwan_tiger' ? 'Safwan Tiger' : 'Digital Mart'} API...
                </p>
              </div>
            ) : remoteError ? (
              <div role="alert" style={{ padding: '24px 18px' }}>
                <p>{remoteError}</p>
                <button type="button" className="btn" onClick={() => loadRemoteCatalog()}>Retry</button>
              </div>
            ) : filteredRemote.length === 0 ? (
              <p className="supplier-empty">No products found.</p>
            ) : (
              <>
              <label className="app-select-all"><input type="checkbox" checked={allVisibleRemoteSelected} onChange={toggleSelectAllRemote} /> Select results</label>
              <ul className="app-record-list supplier-product-feed" aria-label="Remote supplier products">
                {filteredRemote.map(product => <li key={product.id}>
                  <label className="app-record-select"><input type="checkbox" aria-label={`Select remote product ${product.id}`} checked={selectedRemoteIds.includes(product.id)} onChange={event => setSelectedRemoteIds(ids => event.target.checked ? [...ids, product.id] : ids.filter(id => id !== product.id))} /></label>
                  <MobileRecordDetails title={product.title} subtitle={product.category_name} meta={product.duration || undefined} amount={`${product.currency_symbol}${product.reseller_price.toFixed(2)} ${product.currency}`} status={product.in_store ? product.local_is_active ? 'Active' : 'Hidden' : 'Not imported'} tone={product.in_store && product.local_is_active ? 'good' : 'neutral'} icon={product.icon || undefined} label={`View remote product ${product.id}`} fields={[
                    ['Product', product.title], ['Supplier ID', product.id], ['Category', product.category_name],
                    ['Source wholesale rate', `${product.currency_symbol}${product.reseller_price.toFixed(2)} ${product.currency}`], ['Duration', product.duration || ''],
                    ['Warranty', product.warranty || ''], ['Description', product.description || ''],
                  ]}>
                    <button type="button" className="btn" disabled={remoteImporting} onClick={() => void handleImportRemoteProduct(product)}>{product.in_store ? 'Re-sync' : 'Import to Store'}</button>
                  </MobileRecordDetails>
                </li>)}
              </ul>
              <div className="scroll desktop-record-scroll">
                <table className="mobile-records">
                  <thead>
                    <tr>
                      <th style={{ width: 36, textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={allVisibleRemoteSelected}
                          onChange={toggleSelectAllRemote}
                          style={{ cursor: 'pointer' }}
                          title="Select all"
                        />
                      </th>
                      <th>Product Title</th>
                      <th>Category</th>
                      <th>Source Wholesale Rate</th>
                      <th>Store Status</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRemote.map((rp) => {
                      const isSelected = selectedRemoteIds.includes(rp.id);
                      return (
                        <tr key={rp.id} style={{ background: isSelected ? 'rgba(34, 197, 94, 0.04)' : undefined }}>
                          <td style={{ textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedRemoteIds([...selectedRemoteIds, rp.id]);
                                } else {
                                  setSelectedRemoteIds(selectedRemoteIds.filter((id) => id !== rp.id));
                                }
                              }}
                              style={{ cursor: 'pointer' }}
                            />
                          </td>
                          <td className="name" style={{ fontWeight: 600 }}>
                            {rp.icon ? <span style={{ marginRight: 6 }}>{rp.icon}</span> : null}
                            {rp.title}
                            <small style={{ display: 'block', color: 'var(--muted)', fontSize: '11px', marginTop: 2 }}>
                              #{rp.id}{rp.duration ? `, ${rp.duration}` : ''}
                              {rp.warranty ? `, warranty ${rp.warranty}` : ''}
                            </small>
                          </td>
                          <td>{rp.category_name}</td>
                          <td style={{ fontWeight: 700, color: 'var(--accent)' }}>
                            {rp.currency_symbol}
                            {rp.reseller_price.toFixed(2)} {rp.currency}
                          </td>
                          <td>
                            {rp.in_store ? (
                              <span
                                className={`pill ${rp.local_is_active ? 'good' : 'warn'}`}
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                              >
                                {rp.local_is_active ? 'In Store (Active)' : 'In Store (Hidden)'}
                              </span>
                            ) : (
                              <span className="pill" style={{ opacity: 0.7 }}>
                                Not in Store
                              </span>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button
                              type="button"
                              className={`btn small ${rp.in_store ? 'ghost' : 'primary'}`}
                              disabled={remoteImporting}
                              onClick={() => handleImportRemoteProduct(rp)}
                              style={{ display: 'inline-flex', alignItems: 'center', fontSize: '12px' }}
                            >
                              {rp.in_store ? 'Re-sync' : 'Import to Store'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
