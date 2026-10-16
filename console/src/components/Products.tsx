'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type Category, type Product } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';
import { EmojiPicker, splitLeadingEmoji } from './EmojiPicker';
import { ValidityPicker } from './ValidityPicker';
import { CustomSelect } from './CustomSelect';

function editableProductFields(title: string, icon: string, customEmojiId: string) {
  const leading = splitLeadingEmoji(title);
  return {
    title: leading.emoji ? leading.text : title,
    icon: customEmojiId ? '' : icon || leading.emoji,
  };
}

function separateProductLabels(name: string, selectedValidity: string, selectedWarranty: string) {
  const cleanName = name.trim();
  const validity = selectedValidity.trim();
  const warranty = selectedWarranty.trim();
  const warrantySuffix = /(?:[\s|·\-–—(]+)((?:full\s+warranty)|(?:\d+\s*[- ]?\s*(?:days?|weeks?)\s+warranty)|(?:fw|sww))\)?$/i;
  const nameWarranty = cleanName.match(warrantySuffix);
  let titleWithoutWarranty = cleanName;
  let warrantyLabel = warranty;
  if (warranty) {
    const selectedSuffix = new RegExp(
      `(?:[\\s|·\\-–—(]+)${warranty.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)?$`,
      'i'
    );
    titleWithoutWarranty = cleanName.replace(selectedSuffix, '').trim();
  }
  if (nameWarranty) {
    if (!warrantyLabel) warrantyLabel = nameWarranty[1].trim();
    titleWithoutWarranty = titleWithoutWarranty.replace(warrantySuffix, '').trim();
  }

  if (validity) {
    const suffix = new RegExp(
      `(?:[\\s|·\\-–—(]+)${validity.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)?$`,
      'i'
    );
    const withoutSelectedValidity = titleWithoutWarranty.replace(suffix, '').trim();
    if (withoutSelectedValidity !== titleWithoutWarranty) {
      return { title: withoutSelectedValidity, duration_label: validity, warranty_label: warrantyLabel };
    }
  }

  const match = titleWithoutWarranty.match(/(?:[\s|·\-–—(]+)(\d+\s*(?:days?|weeks?|months?|years?|hours?))(?:\s+validity)?\)?$/i);
  return match
    ? {
        title: titleWithoutWarranty.slice(0, match.index).trim(),
        duration_label: match[1].trim(),
        warranty_label: warrantyLabel,
      }
    : { title: titleWithoutWarranty, duration_label: validity, warranty_label: warrantyLabel };
}

type Draft = {
  id: number | null;
  category_id: number | null;
  title: string;
  description: string;
  icon: string;
  price: number;
  reseller_price?: number | null;
  duration_label: string;
  warranty_label: string;
  sort_order: number;
  is_pinned: boolean;
  is_active: boolean;
  delivery_type: 'stock' | 'manual';
  custom_emoji_id: string;
  upstream_product_id?: number | null;
  supplier_code?: string | null;
  upstream_devices?: number;
  upstream_share_hours?: number;
  requires_customer_input: boolean;
  customer_input_prompt: string;
};
type ProductFilter = 'all' | 'in_stock' | 'low_stock' | 'out_of_stock' | 'supplier' | 'hidden';
type SupplierFilter = 'all' | 'digital_mart' | 'safwan_tiger' | 'local' | 'manual';

const LOW_STOCK_MAX = 3;

export function Products({ say }: { say: Say }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<ProductFilter>('all');
  const [supplierFilter, setSupplierFilter] = useState<SupplierFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState<number | 'all'>('all');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkActing, setBulkActing] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(50);

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
      setSelectedIds((prev) => prev.filter((id) => id !== product.id));
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

  // Bulk actions on selected products
  async function handleBulkAction(action: 'activate' | 'hide' | 'delete') {
    if (!selectedIds.length) return;
    const label = action === 'activate' ? 'Activate' : action === 'hide' ? 'Hide' : 'Permanently Delete';
    if (
      !(await confirm(
        `${label} ${selectedIds.length} Products?`,
        `Are you sure you want to ${action} the selected ${selectedIds.length} product(s)?`,
        label,
        action === 'delete'
      ))
    ) {
      return;
    }
    setBulkActing(true);
    try {
      const res = await api.bulkProducts(action, selectedIds);
      say(res.message, 'good');
      setSelectedIds([]);
      await load();
    } catch (cause) {
      say(errorText(cause, `Failed to bulk ${action} products.`), 'bad');
    } finally {
      setBulkActing(false);
    }
  }

  const inStockCount = (products ?? []).filter((p) => p.delivery_type === 'manual' || (p.stock ?? 0) > 0 || Boolean(p.upstream_product_id)).length;
  const lowStockCount = (products ?? []).filter((p) => !p.upstream_product_id && p.delivery_type !== 'manual' && (p.stock ?? 0) > 0 && (p.stock ?? 0) <= LOW_STOCK_MAX).length;
  const outOfStockCount = (products ?? []).filter((p) => !p.upstream_product_id && p.delivery_type !== 'manual' && (p.stock ?? 0) === 0).length;
  const supplierCount = (products ?? []).filter((p) => Boolean(p.upstream_product_id)).length;
  const hiddenCount = (products ?? []).filter((p) => !p.is_active).length;
  const totalStockUnits = (products ?? []).reduce((sum, p) => sum + (p.stock ?? 0), 0);

  // Filtered products list
  const shown = (products ?? []).filter((product) => {
    // 1. Enhanced search
    if (search) {
      const q = search.toLowerCase().trim();
      const cat = categories.find((c) => c.id === product.category_id);
      const titleMatch = product.title.toLowerCase().includes(q);
      const durationMatch = (product.duration_label || '').toLowerCase().includes(q);
      const catMatch = (cat?.name || '').toLowerCase().includes(q);
      const idMatch = String(product.id) === q || String(product.upstream_product_id) === q || `#${product.upstream_product_id}` === q;
      const supplierMatch = (product.supplier_code || '').toLowerCase().includes(q);
      if (!titleMatch && !durationMatch && !catMatch && !idMatch && !supplierMatch) {
        return false;
      }
    }

    // 2. Tab Filter
    if (filter === 'in_stock') {
      if (!(product.delivery_type === 'manual' || (product.stock ?? 0) > 0 || Boolean(product.upstream_product_id))) return false;
    } else if (filter === 'low_stock') {
      if (!(!product.upstream_product_id && product.delivery_type !== 'manual' && (product.stock ?? 0) > 0 && (product.stock ?? 0) <= LOW_STOCK_MAX)) return false;
    } else if (filter === 'out_of_stock') {
      if (!(!product.upstream_product_id && product.delivery_type !== 'manual' && (product.stock ?? 0) === 0)) return false;
    } else if (filter === 'supplier') {
      if (!Boolean(product.upstream_product_id)) return false;
    } else if (filter === 'hidden') {
      if (Boolean(product.is_active)) return false;
    }

    // 3. Supplier Filter
    if (supplierFilter === 'digital_mart') {
      if (!product.upstream_product_id || (product.supplier_code && product.supplier_code !== 'digital_mart')) return false;
    } else if (supplierFilter === 'safwan_tiger') {
      if (!product.upstream_product_id || product.supplier_code !== 'safwan_tiger') return false;
    } else if (supplierFilter === 'local') {
      if (product.upstream_product_id || product.delivery_type === 'manual') return false;
    } else if (supplierFilter === 'manual') {
      if (product.delivery_type !== 'manual') return false;
    }

    // 4. Category Filter
    if (categoryFilter !== 'all') {
      if (product.category_id !== categoryFilter) return false;
    }

    return true;
  });

  // Pagination calculation
  const totalPages = Math.max(1, Math.ceil(shown.length / pageSize));
  const paginatedShown = shown.slice((page - 1) * pageSize, page * pageSize);

  const allVisibleSelected =
    paginatedShown.length > 0 && paginatedShown.every((p) => selectedIds.includes(p.id));

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      const pageIds = new Set(paginatedShown.map((p) => p.id));
      setSelectedIds(selectedIds.filter((id) => !pageIds.has(id)));
    } else {
      const newIds = new Set([...selectedIds, ...paginatedShown.map((p) => p.id)]);
      setSelectedIds(Array.from(newIds));
    }
  };

  return (
    <>
      {confirmDialog}

      {/* Filter Tabs */}
      <div className="segmented" role="group" aria-label="Filter products" style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          aria-pressed={filter === 'all'}
          className={filter === 'all' ? 'active' : ''}
          onClick={() => {
            setFilter('all');
            setPage(1);
          }}
        >
          All ({products?.length ?? 0})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'in_stock'}
          className={filter === 'in_stock' ? 'active' : ''}
          onClick={() => {
            setFilter('in_stock');
            setPage(1);
          }}
        >
          Available ({inStockCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'supplier'}
          className={filter === 'supplier' ? 'active' : ''}
          onClick={() => {
            setFilter('supplier');
            setPage(1);
          }}
        >
          Supplier ({supplierCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'low_stock'}
          className={filter === 'low_stock' ? 'active' : ''}
          onClick={() => {
            setFilter('low_stock');
            setPage(1);
          }}
        >
          Low Stock ({lowStockCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'out_of_stock'}
          className={filter === 'out_of_stock' ? 'active' : ''}
          onClick={() => {
            setFilter('out_of_stock');
            setPage(1);
          }}
        >
          Out of Stock ({outOfStockCount})
        </button>
        <button
          type="button"
          aria-pressed={filter === 'hidden'}
          className={filter === 'hidden' ? 'active' : ''}
          onClick={() => {
            setFilter('hidden');
            setPage(1);
          }}
        >
          Hidden ({hiddenCount})
        </button>
      </div>

      <section className="panel">
        <header className="product-toolbar" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 12 }}>
          {/* Top row: search & filters */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
            <div className="filters" style={{ flexWrap: 'wrap', gap: 10, flex: 1 }}>
              {/* Search input */}
              <div style={{ position: 'relative', minWidth: 220, flex: 1, maxWidth: 360 }}>
                <input
                  type="search"
                  aria-label="Search products"
                  placeholder="Search title, ID (#41), category..."
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setPage(1);
                  }}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>

              {/* Supplier dropdown filter */}
              <CustomSelect
                value={supplierFilter}
                onChange={(val) => {
                  setSupplierFilter(val as any);
                  setPage(1);
                }}
                options={[
                  { value: 'all', label: 'All Sources' },
                  { value: 'digital_mart', label: 'Digital Mart' },
                  { value: 'safwan_tiger', label: 'Safwan Tiger' },
                  { value: 'local', label: 'Local Stock' },
                  { value: 'manual', label: 'Manual Delivery' },
                ]}
                minWidth={135}
              />

              {/* Category dropdown filter */}
              <CustomSelect
                value={String(categoryFilter)}
                onChange={(val) => {
                  setCategoryFilter(val === 'all' ? 'all' : Number(val));
                  setPage(1);
                }}
                options={[
                  { value: 'all', label: 'All Categories' },
                  ...categories.map((c) => ({
                    value: String(c.id),
                    label: c.name,
                  })),
                ]}
                minWidth={145}
              />

              {/* Items per page */}
              <CustomSelect
                value={String(pageSize)}
                onChange={(val) => {
                  setPageSize(Number(val));
                  setPage(1);
                }}
                options={[
                  { value: '25', label: '25 / page' },
                  { value: '50', label: '50 / page' },
                  { value: '100', label: '100 / page' },
                  { value: '500', label: 'All / page' },
                ]}
                minWidth={110}
              />

              <span className="muted" style={{ fontSize: '12px', alignSelf: 'center' }}>
                {shown.length} of {products?.length ?? 0} shown ({totalStockUnits} local units)
              </span>
            </div>

            <button
              type="button"
              className="btn primary"
              onClick={() =>
                setDraft({
                  id: null,
                  category_id: null,
                  title: '',
                  description: '',
                  icon: '',
                  price: 1,
                  reseller_price: null,
                  duration_label: '1 Month',
                  warranty_label: '',
                  sort_order: 0,
                  is_pinned: false,
                  is_active: true,
                  delivery_type: 'stock',
                  custom_emoji_id: '',
                  upstream_product_id: null,
                  supplier_code: 'digital_mart',
                  upstream_devices: 1,
                  upstream_share_hours: 24,
                  requires_customer_input: false,
                  customer_input_prompt: '',
                })
              }
              style={{ fontWeight: 600 }}
            >
              + New product
            </button>
          </div>

          {/* Bulk actions bar if items are selected */}
          {selectedIds.length > 0 && (
            <div
              style={{
                padding: '8px 14px',
                background: 'rgba(14, 165, 233, 0.08)',
                borderRadius: '6px',
                border: '1px solid rgba(14, 165, 233, 0.25)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '13px', fontWeight: 600 }}>
                <span>{selectedIds.length} product(s) selected</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn small"
                  disabled={bulkActing}
                  onClick={() => handleBulkAction('activate')}
                  style={{ color: '#16a34a', borderColor: '#16a34a' }}
                >
                  Bulk Activate
                </button>
                <button
                  type="button"
                  className="btn small"
                  disabled={bulkActing}
                  onClick={() => handleBulkAction('hide')}
                >
                  Bulk Hide
                </button>
                <button
                  type="button"
                  className="btn small danger"
                  disabled={bulkActing}
                  onClick={() => handleBulkAction('delete')}
                >
                  Bulk Delete
                </button>
                <button
                  type="button"
                  className="btn small ghost"
                  onClick={() => setSelectedIds([])}
                >
                  Deselect
                </button>
              </div>
            </div>
          )}
        </header>

        <div className="scroll">
          <table className="mobile-records products-list">
            <thead>
              <tr>
                <th style={{ width: 36, textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    style={{ cursor: 'pointer' }}
                    title="Select all on this page"
                  />
                </th>
                <th>Product</th>
                <th>Price</th>
                <th>Stock / Source</th>
                <th style={{ width: '100px', textAlign: 'center' }}>Status</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {paginatedShown.map((product) => {
                const cat = categories.find((c) => c.id === product.category_id);
                const isSelected = selectedIds.includes(product.id);
                const isTiger = product.supplier_code === 'safwan_tiger';
                const isDM = Boolean(product.upstream_product_id) && !isTiger;
                return (
                  <tr key={product.id} style={{ background: isSelected ? 'rgba(14, 165, 233, 0.04)' : undefined }}>
                    <td style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedIds([...selectedIds, product.id]);
                          } else {
                            setSelectedIds(selectedIds.filter((id) => id !== product.id));
                          }
                        }}
                        style={{ cursor: 'pointer' }}
                      />
                    </td>
                    <td className="name">
                      {product.icon ? `${product.icon} ` : ''}
                      {product.title}
                      {product.is_pinned ? (
                        <span className="pill good mini" style={{ marginLeft: 6, fontSize: '10.5px', padding: '1px 5px' }}>
                          📌 Top
                        </span>
                      ) : null}
                      {product.requires_customer_input ? (
                        <span className="pill info mini" style={{ marginLeft: 6, fontSize: '10.5px', padding: '1px 5px' }} title={product.customer_input_prompt || 'Requires customer input'}>
                          📝 Input
                        </span>
                      ) : null}
                      <small style={{ display: 'block', color: 'var(--muted)', marginTop: 2 }}>
                        {[cat?.name, product.duration_label, product.warranty_label].filter(Boolean).join(' · ')}
                        {product.upstream_product_id ? ` · Upstream ID: #${product.upstream_product_id}` : ''}
                      </small>
                    </td>
                    <td className="money">
                      <div style={{ fontWeight: 700 }}>{money(product.price)}</div>
                      {product.reseller_price != null && product.reseller_price > 0 ? (
                        <small style={{ color: 'var(--accent)', fontSize: '11px', fontWeight: 600, display: 'block' }}>
                          Wholesale: {money(product.reseller_price)}
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
                              fontSize: '11px',
                              background: isTiger ? 'rgba(59, 130, 246, 0.1)' : 'rgba(34, 197, 94, 0.1)',
                              color: isTiger ? '#2563eb' : '#16a34a',
                              border: `1px solid ${isTiger ? 'rgba(59, 130, 246, 0.25)' : 'rgba(34, 197, 94, 0.25)'}`,
                            }}
                            title={`Fulfilled automatically by ${isTiger ? 'Safwan Tiger Shop' : 'Digital Mart'} (ID: #${product.upstream_product_id})`}
                          >
                            {isTiger ? 'Tiger Shop' : 'Digital Mart'}
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
                        <span className="pill info" style={{ fontWeight: 600, fontSize: '11.5px' }}>
                          Manual
                        </span>
                      ) : (
                        <span
                          className={`pill ${!product.stock ? 'bad' : product.stock <= LOW_STOCK_MAX ? 'warn' : 'good'}`}
                          title={product.stock && product.stock <= LOW_STOCK_MAX ? `Low stock (≤ ${LOW_STOCK_MAX} remaining)` : undefined}
                          style={{ fontSize: '11.5px' }}
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
                        <button
                          type="button"
                          className={`mini ${product.is_pinned ? 'btn' : 'ghost'}`}
                          onClick={async () => {
                            try {
                              await api.pinProduct(product.id);
                              say(product.is_pinned ? 'Product unpinned from top.' : 'Product pinned to top!');
                              await load();
                            } catch (e) {
                              say(errorText(e), 'bad');
                            }
                          }}
                          title={product.is_pinned ? 'Pinned to top (click to unpin)' : 'Pin to top of category'}
                        >
                          📌 {product.is_pinned ? 'Top' : 'Pin'}
                        </button>
                        <button type="button" className="mini" onClick={() => setPreviewProduct(product)}>
                          Post
                        </button>
                        <button
                          type="button"
                          className="mini"
                          onClick={() =>
                            {
                              const iconFields = editableProductFields(
                                product.title,
                                product.icon || '',
                                product.custom_emoji_id || ''
                              );
                              const separated = separateProductLabels(
                                iconFields.title,
                                product.duration_label,
                                product.warranty_label || ''
                              );
                              setDraft({
                                id: product.id,
                                category_id: product.category_id ?? null,
                                title: separated.title,
                                description: product.description,
                                icon: iconFields.icon,
                                price: product.price,
                                reseller_price: product.reseller_price ?? null,
                                duration_label: separated.duration_label,
                                warranty_label: separated.warranty_label,
                                sort_order: product.sort_order,
                                is_pinned: Boolean(product.is_pinned),
                                is_active: Boolean(product.is_active),
                                delivery_type: product.delivery_type || 'stock',
                                custom_emoji_id: product.custom_emoji_id || '',
                                upstream_product_id: product.upstream_product_id ?? null,
                                supplier_code: product.supplier_code || 'digital_mart',
                                upstream_devices: product.upstream_devices ?? 1,
                                upstream_share_hours: product.upstream_share_hours ?? 24,
                                requires_customer_input: Boolean(product.requires_customer_input),
                                customer_input_prompt: product.customer_input_prompt || '',
                              });
                            }
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
                <EmptyRow columns={6}>
                  {search
                    ? 'No products match your search.'
                    : filter === 'low_stock'
                    ? 'No low stock products right now.'
                    : 'No products found.'}
                </EmptyRow>
              ) : null}
              {!products ? <EmptyRow columns={6}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        {shown.length > 0 && (
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
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, shown.length)} of {shown.length} products
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                type="button"
                className="btn small"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Prev
              </button>
              <span style={{ padding: '0 6px', fontWeight: 600 }}>
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                className="btn small"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}
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
                  <span>{previewProduct.icon ? `${previewProduct.icon} ` : ''}{previewProduct.title}</span>
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

              <div style={{ display: 'flex', alignItems: 'center' }}>
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
  const [saveError, setSaveError] = useState('');
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
    if (busy) return;
    setSaveError('');
    setBusy(true);
    const enteredTitle = form.title.trim();
    const leading = splitLeadingEmoji(enteredTitle);
    const customEmojiId = form.custom_emoji_id.trim();
    const payload = {
      category_id: form.category_id ?? null,
      title: leading.emoji && leading.text ? leading.text : enteredTitle,
      description: (form.description || '').trim(),
      price: form.price,
      reseller_price: form.reseller_price != null && form.reseller_price > 0 ? form.reseller_price : null,
      icon: customEmojiId ? '' : form.icon.trim() || leading.emoji,
      duration_label: form.duration_label,
      warranty_label: form.warranty_label,
      sort_order: form.sort_order,
      is_pinned: form.is_pinned ? 1 : 0,
      is_active: form.is_active ? 1 : 0,
      delivery_type: form.delivery_type,
      custom_emoji_id: customEmojiId,
      upstream_product_id: form.upstream_product_id || null,
      supplier_code: form.upstream_product_id ? (form.supplier_code || 'digital_mart') : null,
      upstream_devices: form.upstream_devices ?? 1,
      upstream_share_hours: form.upstream_share_hours ?? 24,
      requires_customer_input: form.requires_customer_input ? 1 : 0,
      customer_input_prompt: form.customer_input_prompt ? form.customer_input_prompt.trim() : '',
    };
    try {
      if (form.id) await api.updateProduct(form.id, payload);
      else await api.createProduct(payload);
      say(form.id ? 'Saved.' : 'Product added.');
      await onSaved();
    } catch (cause) {
      setSaveError(errorText(cause));
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
            {busy ? 'Saving…' : form.id ? 'Save' : 'Add product'}
          </button>
        </>
      }
    >
      {saveError ? <p className="dialog-error bad-text" role="alert">{saveError}</p> : null}
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
                Automatic fulfillment. Your name, emoji, duration and prices are kept when syncing.
              </div>
            </div>
          </div>

          <div className="form-columns">
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Supplier Provider</span>
              <CustomSelect
                value={form.supplier_code || 'digital_mart'}
                onChange={(val) => set({ supplier_code: val })}
                options={[
                  { value: 'digital_mart', label: 'Digital Mart (BDT)' },
                  { value: 'safwan_tiger', label: 'Safwan Tiger Shop (USDT)' },
                ]}
                minWidth="100%"
              />
            </label>
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Supplier Product ID</span>
              <input
                type="number"
                min="1"
                required
                value={form.upstream_product_id ?? ''}
                onChange={(e) => set({ upstream_product_id: e.target.value === '' ? (null as any) : parseInt(e.target.value) || 1 })}
              />
            </label>
          </div>

          <div className="form-columns">
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontWeight: 600 }}>Devices per Account <small style={{ color: 'var(--muted)' }}>(Pool)</small></span>
              <input
                type="number"
                min="1"
                max="50"
                required
                value={form.upstream_devices ?? 1}
                onChange={(e) => set({ upstream_devices: e.target.value === '' ? ('' as any) : parseInt(e.target.value) || 1 })}
              />
              <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: '2px', display: 'block' }}>
                Seats per supplier account. Extra seats use the same purchase.
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
                onChange={(e) => set({ upstream_share_hours: e.target.value === '' ? ('' as any) : parseInt(e.target.value) || 24 })}
              />
              <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: '2px', display: 'block' }}>
                Unused seats expire after this time; the next order buys a new account.
              </small>
            </label>
          </div>
        </>
      ) : null}

      <label className="field">
        <span>Name <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(validity goes in the field below)</small></span>
        <input
          type="text"
          required
          maxLength={200}
          placeholder="e.g. NordVPN"
          value={form.title}
          onChange={(event) => set({ title: event.target.value })}
          onBlur={() => {
            const separated = separateProductLabels(form.title, form.duration_label, form.warranty_label);
            if (
              separated.title !== form.title ||
              separated.duration_label !== form.duration_label ||
              separated.warranty_label !== form.warranty_label
            ) {
              set(separated);
            }
          }}
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

      <div className="field">
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
          Category <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small>
        </span>
        <CustomSelect
          value={String(form.category_id ?? '')}
          onChange={(val) => set({ category_id: val ? Number(val) : null })}
          options={[
            { value: '', label: 'None (Others)' },
            ...categories.map((c) => ({
              value: String(c.id),
              label: c.name,
              badge: c.is_pinned ? 'Pinned' : undefined,
            })),
          ]}
          minWidth="100%"
        />
      </div>

      <div className="form-columns">
        <label className="field" style={{ margin: 0 }}>
          <span>Regular Price</span>
          <input type="number" step="any" min="0.0001" max="1000000000" required value={form.price} onChange={(event) => set({ price: parseFloat(event.target.value) || 0 })} />
        </label>
        <label className="field" style={{ margin: 0 }}>
          <span>Reseller Price <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
          <input
            type="number"
            step="any"
            min="0"
            max="1000000000"
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

      <label className="field">
        <span>Warranty <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Optional)</small></span>
        <input
          type="text"
          maxLength={64}
          placeholder="e.g. Full Warranty or 7 Days Warranty"
          value={form.warranty_label}
          onChange={(event) => set({ warranty_label: event.target.value })}
        />
      </label>

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
            <span>Automated Supplier Dropshipping (Zero Local Stock Required)</span>
          </div>
        ) : (
          <div className="delivery-method-grid">
            <button
              type="button"
              className={`delivery-method-card ${form.delivery_type === 'stock' ? 'active' : ''}`}
              onClick={() => set({ delivery_type: 'stock' })}
            >
              <span className="delivery-method-title">Instant Stock</span>
            </button>
            <button
              type="button"
              className={`delivery-method-card ${form.delivery_type === 'manual' ? 'active' : ''}`}
              onClick={() => set({ delivery_type: 'manual' })}
            >
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
        label={form.is_pinned ? '📌 Pinned to Top of Category' : 'Pin to Top of Category'}
        on={form.is_pinned}
        onChange={(on) => set({ is_pinned: on })}
      />
      <FlagRow
        label={form.requires_customer_input ? '📝 Require Customer Input (e.g. Gmail / ID)' : 'Require Customer Input (e.g. Gmail)'}
        on={form.requires_customer_input}
        onChange={(on) => set({ requires_customer_input: on })}
      />
      {form.requires_customer_input ? (
        <label className="field" style={{ marginTop: '8px', background: 'rgba(59, 130, 246, 0.05)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(59, 130, 246, 0.15)' }}>
          <span style={{ fontSize: '12px', fontWeight: 600 }}>Input Prompt <small style={{ color: 'var(--muted)', fontWeight: 'normal' }}>(Shown to customer before purchase)</small></span>
          <input
            type="text"
            placeholder="e.g. Enter your Gmail address for invite"
            value={form.customer_input_prompt || ''}
            onChange={(e) => set({ customer_input_prompt: e.target.value.slice(0, 200) })}
            style={{ marginTop: '4px' }}
          />
        </label>
      ) : null}
      <FlagRow
        label={form.is_active ? 'Active' : 'Hidden'}
        on={form.is_active}
        onChange={(on) => set({ is_active: on })}
      />
    </Modal>
  );
}
