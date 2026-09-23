'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Check,
  Clock,
  Copy,
  PackageCheck,
  ShoppingBag,
  Wallet,
  X,
} from 'lucide-react';
import { api, type Order, type OrderDetail, type OrderSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, Modal, Pager, errorText, tone, useConfirm, useDebounced, when, who, type Say } from './ui';

const PAGE = 50;

type Timeframe = 'all' | 'today' | '7d' | '30d' | 'custom';

function formatOrderDateTime(iso?: string | null): string {
  if (!iso) return '—';
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
      {/* Timeframe Filter Bar */}
      <div className="orders-toolbar">
        <div className="segmented" role="tablist">
          <button
            type="button"
            className={timeframe === 'all' ? 'active' : ''}
            onClick={() => { setTimeframe('all'); setOffset(0); }}
          >
            All Time
          </button>
          <button
            type="button"
            className={timeframe === 'today' ? 'active' : ''}
            onClick={() => { setTimeframe('today'); setOffset(0); }}
          >
            Today
          </button>
          <button
            type="button"
            className={timeframe === '7d' ? 'active' : ''}
            onClick={() => { setTimeframe('7d'); setOffset(0); }}
          >
            Last 7 Days
          </button>
          <button
            type="button"
            className={timeframe === '30d' ? 'active' : ''}
            onClick={() => { setTimeframe('30d'); setOffset(0); }}
          >
            Last 30 Days
          </button>
          <button
            type="button"
            className={timeframe === 'custom' ? 'active' : ''}
            onClick={() => { setTimeframe('custom'); setOffset(0); }}
          >
            Custom Range
          </button>
        </div>

        {timeframe === 'custom' ? (
          <div className="custom-date-inputs">
            <div className="date-box">
              <span className="date-label">From</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setOffset(0); }}
              />
            </div>
            <span className="date-arrow">→</span>
            <div className="date-box">
              <span className="date-label">To</span>
              <input
                type="date"
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

      {/* Analytics Metric Summary Cards */}
      <div className="stat-cards-grid compact-metrics">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Orders</span>
            <ShoppingBag className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary ? summary.total_orders : total}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Sales</span>
            <Wallet className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{money(summary?.total_revenue ?? 0)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Delivered</span>
            <PackageCheck className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.delivered_orders ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Waiting to Send</span>
            <Clock className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.waiting_orders ?? waitingCount}</div>
        </div>
      </div>

      <div className="segmented" role="tablist">
        <button type="button" role="tab" aria-selected={!waitingOnly} className={waitingOnly ? '' : 'active'} onClick={() => show(false)}>
          All Orders
        </button>
        <button type="button" role="tab" aria-selected={waitingOnly} className={waitingOnly ? 'active' : ''} onClick={() => show(true)}>
          Waiting to send
          {waitingCount ? <span className="count">{waitingCount}</span> : null}
        </button>
      </div>

      <section className="panel">
        <header>
          <h2>{total === 1 ? '1 order' : `${total} orders`}</h2>
          <div className="filters">
            <input
              type="search"
              aria-label="Search orders" placeholder="Search buyer, product or #id"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
          </div>
        </header>
        <div className="scroll">
          <table className="mobile-records orders-list">
            <thead>
              <tr>
                <th>Order</th>
                <th>Buyer</th>
                <th>Status</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {(orders ?? []).map((order) => {
                const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
                return (
                  <tr
                    key={order.id}
                    className="order-table-row"
                    onClick={() => openOrder(order.id)}
                  >
                    <td className="name">
                      {order.product_title}
                      <small>
                        #{order.id} · {money(order.price)} · {when(order.created_at)}
                      </small>
                    </td>
                    <td data-label="Customer">
                      {who(order)}
                      <small>{order.tg_user_id}</small>
                    </td>
                    <td>
                      {waiting ? (
                        <span className="pill warn">waiting</span>
                      ) : (
                        <span className={`pill ${tone(order.status)}`}>{order.status}</span>
                      )}
                      {!waiting && order.status === 'completed' && order.delivery_status === 'failed' ? (
                        <span className="pill bad">message failed</span>
                      ) : null}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className={`mini${waiting ? ' primary' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            openOrder(order.id);
                          }}
                        >
                          {waiting ? 'Send' : 'Details'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {orders && orders.length === 0 ? (
                <EmptyRow columns={4}>{waitingOnly ? 'Every paid order has been sent.' : query ? 'Nothing matches.' : 'No orders yet.'}</EmptyRow>
              ) : null}
              {!orders ? <EmptyRow columns={4}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
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
  const [copiedField, setCopiedField] = useState<'id' | 'credentials' | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoadError('');
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

  const copyText = (text: string, field: 'id' | 'credentials') => {
    if (!text) return;
    void navigator.clipboard.writeText(text);
    setCopiedField(field);
    say(field === 'id' ? 'Copied Order ID.' : 'Copied credentials.');
    setTimeout(() => {
      setCopiedField((cur) => (cur === field ? null : cur));
    }, 2000);
  };

  if (loadError) {
    return (
      <Modal title={`Order #${orderId}`} onClose={onClose} wide>
        <div className="dialog-error" role="alert">
          <strong>Order details unavailable</strong>
          <p>{loadError}</p>
        </div>
      </Modal>
    );
  }

  if (!detail) {
    return (
      <Modal title={`Order #${orderId}`} onClose={onClose} wide>
        <p className="hint" style={{ padding: '24px 0', textAlign: 'center' }}>Loading…</p>
      </Modal>
    );
  }

  const { order } = detail;
  const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
  const customerName = getCustomerDisplayName(order);
  const variation = getVariationLabel(order);
  const orderCode = order.request_id || `#${order.id}`;

  return (
    <Modal
      title={`Order #${order.id}`}
      onClose={onClose}
      wide
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
                    `Refund order #${order.id}?`,
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
        </div>
      </div>

      {/* Card 2: Delivered Credentials (Exact match with target image) */}
      <div className="order-modal-cred-card">
        <div className="order-modal-cred-header">
          <div className="order-modal-cred-title">
            <span className="order-modal-key-icon">🔑</span>
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
          <div className="order-modal-cred-box" style={{ textAlign: 'center', color: 'var(--muted)' }}>
            {waiting ? 'Order has not been delivered yet.' : 'No credentials recorded.'}
          </div>
        )}
      </div>

      {/* Manual Fulfill Input (Only if waiting) */}
      {waiting ? (
        <div className="order-modal-cred-card" style={{ marginTop: '14px', borderColor: 'rgba(234, 88, 12, 0.3)' }}>
          <div className="order-modal-cred-header">
            <strong style={{ fontSize: '14px', color: '#ea580c' }}>⚡ Fulfill & Send to Customer</strong>
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
