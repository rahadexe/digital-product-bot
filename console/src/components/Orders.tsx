'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Check,
  Clock,
  Copy,
  Eye,
  PackageCheck,
  RefreshCw,
  ShoppingBag,
  SlidersHorizontal,
  Wallet,
  X,
} from 'lucide-react';
import { api, type Order, type OrderDetail, type OrderSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { CustomSelect } from './CustomSelect';
import { MobileRecord } from './MobileRecord';
import { EmptyRow, Modal, Pager, errorText, tone, useConfirm, useDebounced, when, who, type Say } from './ui';

const PAGE = 50;

type Timeframe = 'all' | 'today' | '7d' | '30d' | 'custom';

function formatOrderDateTime(iso?: string | null): string {
  if (!iso) return 'Unknown';
  try {
    const d = new Date(iso.includes('T') || iso.includes('Z') ? iso : `${iso.replace(' ', 'T')}Z`);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString('en-US', {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return iso;
  }
}

function getVariationLabel(order: Order): string {
  if (order.duration_label && order.duration_label.trim()) {
    return order.duration_label.trim();
  }
  const title = order.product_title || '';
  const match = title.match(/(\d+\s*(?:day|days|month|months|year|years|hour|hours|week|weeks|device|devices|gb|tb))(?:\s*\(x\d+\))?/i);
  if (match) {
    return match[0];
  }
  const qtyMatch = title.match(/\(x\d+\)/i);
  if (qtyMatch) {
    return qtyMatch[0];
  }
  return 'Standard';
}

function getCustomerDisplayName(order: Order): string {
  const parts = [order.first_name, order.last_name].filter(Boolean);
  if (parts.length > 0) return parts.join(' ');
  if (order.username) return `@${order.username}`;
  return `User ${order.tg_user_id}`;
}

export function Orders({
  say,
  initialWaiting = false,
  initialOrderId = null,
  onWaitingChange,
}: {
  say: Say;
  initialWaiting?: boolean;
  initialOrderId?: number | null;
  onWaitingChange?: (count: number) => void;
}) {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [total, setTotal] = useState(0);
  const [waitingCount, setWaitingCount] = useState(0);
  const [waitingOnly, setWaitingOnly] = useState(initialWaiting);
  const [timeframe, setTimeframe] = useState<Timeframe>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [openOrderId, setOpenOrderId] = useState<number | null>(initialOrderId);
  const query = useDebounced(search);
  const money = useMoney();

  useEffect(() => {
    setOpenOrderId(initialOrderId);
  }, [initialOrderId]);

  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoadError('');
    setLoading(true);
    try {
      let days: number | undefined = undefined;
      let df: string | undefined = undefined;
      let dt: string | undefined = undefined;
      if (timeframe === 'today') days = 1;
      else if (timeframe === '7d') days = 7;
      else if (timeframe === '30d') days = 30;
      else if (timeframe === 'custom') {
        if (dateFrom) df = dateFrom;
        if (dateTo) dt = dateTo;
      }

      const result = await api.orders(query, PAGE, offset, waitingOnly, undefined, days, df, dt);
      if (version !== requestVersion.current) return;
      setOrders(result.orders);
      setTotal(result.total);
      setWaitingCount(result.waiting);
      setSummary(result.summary ?? null);
      onWaitingChange?.(result.waiting);
    } catch (cause) {
      if (version === requestVersion.current) setLoadError(errorText(cause));
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [query, offset, waitingOnly, timeframe, dateFrom, dateTo, onWaitingChange, say]);

  useEffect(() => {
    void load();
    return () => {requestVersion.current++;};
  }, [load]);

  const show = (onlyWaiting: boolean) => {
    setWaitingOnly(onlyWaiting);
    setOffset(0);
    setOrders(null);
    window.history.replaceState(null, '', onlyWaiting ? '#orders/waiting' : '#orders');
  };

  const openOrder = (id: number) => {
    setOpenOrderId(id);
    window.history.replaceState(null, '', `#orders/${id}`);
  };

  const closeOrder = () => {
    setOpenOrderId(null);
    window.history.replaceState(null, '', waitingOnly ? '#orders/waiting' : '#orders');
  };

  if (loadError) return <section className="panel"><div className="panel-body" role="alert"><p>{loadError}</p><button className="btn" onClick={() => void load()}>Retry orders</button></div></section>;
  return (
    <>
      <section className="panel queue-panel">
        <header>
          <div className="queue-tabs" aria-label="Order status filter">
            <button
              type="button"
              className={!waitingOnly ? 'active' : ''} aria-pressed={!waitingOnly}
              onClick={() => show(false)}
            >
              All orders
            </button>
            <button
              type="button"
              className={waitingOnly ? 'active' : ''} aria-pressed={waitingOnly}
              onClick={() => show(true)}
            >
              Waiting to send
              {waitingCount ? <span className="count">{waitingCount}</span> : null}
            </button>
          </div>

          <div className={`filters${mobileFiltersOpen ? ' mobile-filters-open' : ''}`}>
            <div id="order-date-filter" className="order-date-filter">
            <CustomSelect ariaLabel="Order date range" value={timeframe} width={150} minWidth={0}
              onChange={(value) => { setTimeframe(value as Timeframe); setOffset(0); }}
              options={[{ value: 'all', label: 'All time' }, { value: 'today', label: 'Today' }, { value: '7d', label: 'Last 7 days' }, { value: '30d', label: 'Last 30 days' }, { value: 'custom', label: 'Custom dates' }]} />
            </div>
            <input
              type="search"
              aria-label="Search orders"
              placeholder="Search buyer, product or #id…"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
            <button type="button" className={`btn ghost small mobile-filter-toggle${timeframe !== 'all' ? ' active' : ''}`} aria-label="Order filters" aria-expanded={mobileFiltersOpen} aria-controls="order-date-filter" onClick={() => setMobileFiltersOpen(open => !open)}>
              <SlidersHorizontal size={18} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="btn ghost small"
              onClick={() => void load()}
              disabled={loading}
              aria-label="Refresh orders"
            >
              <RefreshCw size={14} /> <span>{loading ? 'Refreshing…' : 'Refresh'}</span>
            </button>
          </div>
        </header>

      <div className="orders-custom-dates">
        {timeframe === 'custom' ? (
          <div className="custom-date-inputs">
            <div className="date-box">
              <span className="date-label">From</span>
              <input
                type="date"
                aria-label="From date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setOffset(0); }}
              />
            </div>
            <div className="date-box">
              <span className="date-label">To</span>
              <input
                type="date"
                aria-label="To date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setOffset(0); }}
              />
            </div>
            {dateFrom || dateTo ? (
              <button
                type="button"
                className="date-clear-btn"
                title="Clear date filter"
                onClick={() => { setDateFrom(''); setDateTo(''); setOffset(0); }}
              >
                <X size={12} />
                Clear
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

        <div className="app-list-heading"><span>{total} {total === 1 ? 'order' : 'orders'}</span></div>
        <ul className="app-record-list order-feed" aria-label="Orders" aria-busy={loading}>
          {(orders ?? []).map(order => {
            const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
            const deliveryFailed = !waiting && order.status === 'completed' && order.delivery_status === 'failed';
            return (
              <li key={order.id}>
                <MobileRecord
                  title={order.product_title}
                  subtitle={`#${order.id}, ${getCustomerDisplayName(order)}`}
                  amount={money(order.price)}
                  status={waiting ? 'To deliver' : deliveryFailed ? 'Delivery failed' : order.status}
                  tone={waiting ? 'warn' : deliveryFailed || order.status === 'failed' ? 'bad' : order.status === 'completed' ? 'good' : 'neutral'}
                  label={`Open order ${order.id}: ${order.product_title}`}
                  onOpen={() => openOrder(order.id)}
                />
              </li>
            );
          })}
          {!orders ? <li className="app-list-empty" role="status">Loading orders…</li> : orders.length === 0 ? <li className="app-list-empty">{query ? 'No matching orders.' : waitingOnly ? 'All paid orders have been sent.' : 'No orders yet.'}</li> : null}
        </ul>
        <div className="scroll desktop-record-scroll" tabIndex={0} role="region" aria-label="Orders table" aria-busy={loading}>
          <table className="record-directory orders-directory">
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Product</th>
                <th scope="col">Buyer</th>
                <th scope="col" className="right">Price</th>
                <th scope="col">Status</th>
                <th scope="col" className="right" aria-label="Actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(orders ?? []).map((order) => {
                const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
                return (
                  <tr key={order.id} className="order-list-item">
                    <td data-label="Order">
                      <code style={{ fontSize: '12px' }}>O{order.id}</code>
                    </td>
                    <td data-label="Product">
                      <button
                        type="button"
                        className="record-link"
                        onClick={() => openOrder(order.id)}
                        title={order.product_title}
                      >
                        {order.product_title}
                      </button>
                      <small style={{ display: 'block', color: 'var(--muted)', fontSize: '11px' }}>
                        {when(order.created_at)}
                      </small>
                      {order.customer_input ? (
                        <div className="order-customer-input">
                          <span className="order-input-label">Customer details</span>
                          <span className="order-input-value" title={`Customer info: ${order.customer_input}`}>
                            {order.customer_input}
                          </span>
                        </div>
                      ) : null}
                    </td>
                    <td data-label="Buyer">
                      <div className="overview-customer">
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', minWidth: 0, overflow: 'hidden' }}>
                          <span style={{ fontWeight: 550, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {getCustomerDisplayName(order)}
                          </span>
                          <small style={{ color: 'var(--muted)', fontSize: '11px' }}>
                            {order.tg_user_id}
                          </small>
                        </div>
                      </div>
                    </td>
                    <td className="right" data-label="Price">
                      <strong className="money">{money(order.price)}</strong>
                    </td>
                    <td data-label="Status">
                      {waiting ? (
                        <span className="pill warn">waiting</span>
                      ) : (
                        <span className={`pill ${tone(order.status)}`}>{order.status}</span>
                      )}
                      {!waiting && order.status === 'completed' && order.delivery_status === 'failed' ? (
                        <span className="pill bad" style={{ display: 'block', marginTop: '2px' }}>message failed</span>
                      ) : null}
                    </td>
                    <td className="right" data-label="Actions">
                      <div className="row-actions" style={{ justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className={`btn ghost small${waiting ? ' primary' : ''}`}
                          onClick={() => openOrder(order.id)}
                        >
                          <Eye size={13} /> {waiting ? 'Send item' : 'Details'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {orders && orders.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                    {query ? 'No orders match your search. Try another name or order ID.' : waitingOnly ? 'Every paid order has been sent.' : 'No orders in this date range.'}
                  </td>
                </tr>
              ) : null}
              {!orders ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                    Loading orders…
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className={`order-pagination${total <= PAGE && offset === 0 ? ' single-page' : ''}`}>
          <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
        </div>
      </section>

      {/* Exact replica of the target clean modal design */}
      {openOrderId ? (
        <OrderDetailModal
          orderId={openOrderId}
          say={say}
          onClose={closeOrder}
          onChanged={() => void load()}
        />
      ) : null}
    </>
  );
}

/**
 * Clean, compact Order Details Modal matching the target reference design (media_1789824618164.png).
 */
function OrderDetailModal({
  orderId,
  say,
  onClose,
  onChanged,
}: {
  orderId: number;
  say: Say;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loadError, setLoadError] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState('');
  const [copiedField, setCopiedField] = useState<'id' | 'credentials' | 'customer_input' | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoadError('');
    try {
      setDetail(await api.orderDetail(orderId));
    } catch (cause) {
      setLoadError(errorText(cause, 'Could not load this order.'));
    }
  }, [orderId]);

  useEffect(() => {
    void load();
    return () => {requestVersion.current++;};
  }, [load]);

  async function run(name: string, action: () => Promise<string>) {
    setBusy(name);
    try {
      say(await action());
      await load();
      onChanged();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy('');
    }
  }

  const copyText = (text: string, field: 'id' | 'credentials' | 'customer_input') => {
    if (!text) return;
    void navigator.clipboard.writeText(text);
    setCopiedField(field);
    say(field === 'id' ? 'Copied Order ID.' : field === 'customer_input' ? 'Copied Customer Info.' : 'Copied credentials.');
    setTimeout(() => {
      setCopiedField((cur) => (cur === field ? null : cur));
    }, 2000);
  };

  if (loadError) {
    return (
      <Modal title={`Order O${orderId}`} onClose={onClose} wide className="record-drawer">
        <div className="dialog-error" role="alert">
          <strong>Order details unavailable</strong>
          <p>{loadError}</p>
        </div>
      </Modal>
    );
  }

  if (!detail) {
    return (
      <Modal title={`Order O${orderId}`} onClose={onClose} wide className="record-drawer">
        <p className="hint" style={{ padding: '24px 0', textAlign: 'center' }}>Loading…</p>
      </Modal>
    );
  }

  const { order } = detail;
  const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
  const supplierNeedsReview = Boolean(order.supplier_order_id || order.supplier_error?.startsWith('[RECONCILE]'));
  const customerName = getCustomerDisplayName(order);
  const variation = getVariationLabel(order);
  const orderCode = `O${order.id}`;

  return (
    <Modal
      title={`Order O${order.id}`}
      onClose={onClose}
      wide
      className="record-drawer"
      footer={
        <div className="order-modal-footer">
          <div>
            {order.status === 'completed' ? (
              <button
                type="button"
                className="btn danger small"
                disabled={Boolean(busy)}
                onClick={async () => {
                  const confirmed = await confirm(
                    `Refund order O${order.id}?`,
                    `${money(order.price)} will go back to ${customerName}'s balance.`,
                    'Refund Order',
                    true
                  );
                  if (!confirmed) return;
                  void run('refund', async () => (await api.refundOrder(order.id)).message || 'Refunded.');
                }}
              >
                Refund {money(order.price)}
              </button>
            ) : null}

            {waiting && (order.supplier_code || order.supplier_error || order.source === 'supplier_pending' || order.source === 'upstream_reseller') ? (
              <button
                type="button"
                className="btn primary small"
                disabled={Boolean(busy) || supplierNeedsReview}
                title={supplierNeedsReview ? 'Confirm the existing order with the supplier before taking another action.' : undefined}
                onClick={() =>
                  run('retry_supplier', async () => (await api.retrySupplierOrder(order.id)).message || 'Supplier fulfillment successful!')
                }
              >
                {supplierNeedsReview ? 'Supplier review needed' : busy === 'retry_supplier' ? 'Retrying...' : 'Retry Supplier'}
              </button>
            ) : null}

            {!waiting && order.status === 'completed' && order.delivery_status === 'failed' ? (
              <button
                type="button"
                className="btn ghost small"
                disabled={Boolean(busy)}
                onClick={() =>
                  run('retry', async () => {
                    await api.retryDelivery(order.id);
                    return 'Sending the message again.';
                  })
                }
              >
                Resend Message
              </button>
            ) : null}
          </div>

          <button type="button" className="btn ghost small" onClick={onClose}>
            Close
          </button>
        </div>
      }
    >
      {confirmDialog}

      {/* Card 1: Order Metadata Table (Exact match with target image) */}
      <div className="order-modal-card">
        <div className="order-modal-meta-grid">
          <div className="order-modal-row">
            <span className="order-modal-label">Order ID</span>
            <div className="order-modal-val">
              <span
                className="order-modal-id-pill"
                onClick={() => copyText(orderCode, 'id')}
                title="Click to copy ID"
              >
                <span>{orderCode}</span>
                {copiedField === 'id' ? <Check size={11} className="good-text" /> : <Copy size={11} />}
              </span>
            </div>
          </div>

          <div className="order-modal-row">
            <span className="order-modal-label">Customer</span>
            <div className="order-modal-val strong">
              <span>{customerName}</span>
              {order.username ? (
                <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({order.username})</span>
              ) : null}
            </div>
          </div>

          <div className="order-modal-row">
            <span className="order-modal-label">Product</span>
            <div className="order-modal-val strong">
              <span>{order.product_title}</span>
            </div>
          </div>

          {order.customer_input ? (
            <div className="order-detail-customer">
              <span className="order-modal-label">Customer info</span>
                <button
                  type="button"
                  className="order-customer-copy"
                  onClick={() => copyText(order.customer_input || '', 'customer_input')}
                  aria-label="Copy customer info"
                >
                  <span>{order.customer_input}</span>
                  {copiedField === 'customer_input' ? <Check size={16} className="good-text" /> : <Copy size={16} />}
                </button>
            </div>
          ) : null}

          <div className="order-modal-row">
            <span className="order-modal-label">Variation</span>
            <div className="order-modal-val strong">
              <span>{variation}</span>
            </div>
          </div>

          <div className="order-modal-row">
            <span className="order-modal-label">Amount</span>
            <div className="order-modal-val strong">
              <span>{money(order.price)}</span>
            </div>
          </div>

          <div className="order-modal-row">
            <span className="order-modal-label">Payment</span>
            <div className="order-modal-val">
              <span>{order.source === 'manual' ? 'Manual' : 'Wallet'} / {order.status}</span>
            </div>
          </div>

          <div className="order-modal-row">
            <span className="order-modal-label">Created</span>
            <div className="order-modal-val">
              <span>{formatOrderDateTime(order.created_at)}</span>
            </div>
          </div>

          <div className="order-modal-row">
            <span className="order-modal-label">Delivered</span>
            <div className="order-modal-val">
              <span>
                {waiting
                  ? 'Pending fulfillment'
                  : formatOrderDateTime(order.fulfilled_at || (order.status === 'completed' ? order.created_at : null))}
              </span>
            </div>
          </div>

          {order.supplier_code && (
            <div className="order-modal-row">
              <span className="order-modal-label">Supplier</span>
              <div className="order-modal-val">
                <span className="pill primary">
                  {order.supplier_code === 'safwan_tiger' ? 'Safwan Tiger Shop' : 'Digital Mart'}
                </span>
                {order.supplier_order_id && (
                  <span style={{ marginLeft: 6, fontSize: '11px', color: 'var(--muted)' }}>
                    #{order.supplier_order_id}
                  </span>
                )}
              </div>
            </div>
          )}

          {order.supplier_error && (
            <div className="order-modal-row">
              <span className="order-modal-label">Supplier Issue</span>
              <div className="order-modal-val" style={{ color: 'var(--negative)', fontSize: '12px' }}>
                <span>{order.supplier_error.replace(/^\[RECONCILE\]\s*/, '')}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Card 2: Delivered Credentials (Exact match with target image) */}
      <div className="order-modal-cred-card">
        <div className="order-modal-cred-header">
          <div className="order-modal-cred-title">
            <span>Delivered Credentials</span>
          </div>

          {order.delivered_item ? (
            <button
              type="button"
              className="order-modal-copy-btn"
              onClick={() => copyText(order.delivered_item, 'credentials')}
            >
              {copiedField === 'credentials' ? <Check size={11} className="good-text" /> : <Copy size={11} />}
              <span>{copiedField === 'credentials' ? 'Copied' : 'Copy'}</span>
            </button>
          ) : null}
        </div>

        {order.delivered_item ? (
          <div className="order-modal-cred-box">
            {order.delivered_item}
          </div>
        ) : (
          <p className="order-not-delivered">{waiting ? 'Not delivered yet.' : 'No credentials recorded.'}</p>
        )}
      </div>

      {/* Manual Fulfill Input (Only if waiting) */}
      {waiting ? (
        <div className="order-modal-cred-card" style={{ marginTop: '14px', borderColor: 'rgba(234, 88, 12, 0.3)' }}>
          <div className="order-modal-cred-header">
            <strong style={{ fontSize: '14px', color: '#ea580c' }}>Fulfill & Send to Customer</strong>
          </div>
          <p style={{ margin: '6px 0 10px', fontSize: '12px', color: 'var(--muted)' }}>
            Enter the credentials to deliver directly to the customer in Telegram.
          </p>
          <textarea
            className="order-modal-cred-box"
            style={{ width: '100%', border: '1px solid var(--border)', resize: 'vertical' }}
            rows={4}
            placeholder={'Email: ...\nPassword: ...'}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn primary"
              disabled={Boolean(busy) || !content.trim()}
              onClick={() =>
                run('deliver', async () => {
                  await api.deliverOrder(order.id, content);
                  setContent('');
                  return 'Sent to the customer.';
                })
              }
            >
              {busy === 'deliver' ? 'Sending…' : 'Send to customer'}
            </button>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
