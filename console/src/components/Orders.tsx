'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  ExternalLink,
  KeyRound,
  PackageCheck,
  RotateCw,
  Send,
  ShoppingBag,
  Undo2,
  Wallet,
  X,
} from 'lucide-react';
import { api, type Order, type OrderDetail, type OrderSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, Pager, errorText, tone, useConfirm, useDebounced, when, who, type Say } from './ui';

const PAGE = 50;

type Timeframe = 'all' | 'today' | '7d' | '30d' | 'custom';

const SOURCE: Record<Order['source'], string> = {
  stock: 'From your stock',
  supplier: 'From the supplier',
  manual: 'Typed by you',
  legacy: 'Older order',
};

const MESSAGE_STATE: Record<string, string> = {
  sent: 'sent',
  pending: 'queued',
  sending: 'sending',
  failed: 'not delivered',
  cancelled: 'cancelled',
};

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
  onNavigate,
}: {
  say: Say;
  initialWaiting?: boolean;
  initialOrderId?: number | null;
  onWaitingChange?: (count: number) => void;
  onNavigate?: (orderId: number | null) => void;
}) {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [total, setTotal] = useState(0);
  const [waitingCount, setWaitingCount] = useState(0);
  const [waitingOnly, setWaitingOnly] = useState(initialWaiting);
  const [timeframe, setTimeframe] = useState<Timeframe>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(initialOrderId);
  const query = useDebounced(search);
  const money = useMoney();

  useEffect(() => {
    setSelectedOrderId(initialOrderId);
  }, [initialOrderId]);

  const load = useCallback(async () => {
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
      setOrders(result.orders);
      setTotal(result.total);
      setWaitingCount(result.waiting);
      setSummary(result.summary ?? null);
      onWaitingChange?.(result.waiting);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [query, offset, waitingOnly, timeframe, dateFrom, dateTo, onWaitingChange, say]);

  useEffect(() => {
    void load();
  }, [load]);

  const show = (onlyWaiting: boolean) => {
    setWaitingOnly(onlyWaiting);
    setOffset(0);
    setOrders(null);
    window.history.replaceState(null, '', onlyWaiting ? '#orders/waiting' : '#orders');
  };

  const openOrder = (id: number) => {
    setSelectedOrderId(id);
    onNavigate?.(id);
  };

  const closeOrder = () => {
    setSelectedOrderId(null);
    onNavigate?.(null);
  };

  // Dedicated full-page view for order detail
  if (selectedOrderId) {
    return (
      <OrderDetailPage
        orderId={selectedOrderId}
        say={say}
        onBack={closeOrder}
        onChanged={() => void load()}
      />
    );
  }

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
      <div className="stat-cards-grid">
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
              placeholder="Search buyer, product or #id"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
          </div>
        </header>
        <div className="scroll">
          <table>
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
                    <td>
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
    </>
  );
}

/**
 * Dedicated, executive-grade Order Detail View matching the target clean reference design.
 * Features:
 * - Top metadata key-value grid (Order ID, Customer, Product, Variation, Amount, Payment, Created, Delivered)
 * - Distinct Delivered Credentials card with orange key icon and copy all button
 * - Clean manual fulfill card (when order is waiting)
 * - Collapsible Telegram notification logs
 * - Full confirmation dialog on refunds
 */
function OrderDetailPage({
  orderId,
  say,
  onBack,
  onChanged,
}: {
  orderId: number;
  say: Say;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loadError, setLoadError] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState('');
  const [copiedField, setCopiedField] = useState<'id' | 'credentials' | null>(null);
  const [showMessages, setShowMessages] = useState(false);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  const load = useCallback(async () => {
    setLoadError('');
    try {
      setDetail(await api.orderDetail(orderId));
    } catch (cause) {
      setLoadError(errorText(cause, 'Could not load this order.'));
    }
  }, [orderId]);

  useEffect(() => {
    void load();
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
    say(field === 'id' ? 'Copied Order ID to clipboard.' : 'Copied credentials to clipboard.');
    setTimeout(() => {
      setCopiedField((cur) => (cur === field ? null : cur));
    }, 2000);
  };

  if (loadError) {
    return (
      <div className="order-page">
        <div className="order-page-header">
          <button type="button" className="order-back-btn" onClick={onBack}>
            <ArrowLeft size={16} />
            <span>Back to Orders</span>
          </button>
        </div>
        <div className="panel" style={{ padding: '32px', textAlign: 'center' }}>
          <p className="bad-text" style={{ fontWeight: 600, fontSize: '15px' }}>{loadError}</p>
          <div style={{ marginTop: '16px' }}>
            <button type="button" className="btn" onClick={() => void load()}>
              <RotateCw size={14} />
              <span>Try Again</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="order-page">
        <div className="order-page-header">
          <button type="button" className="order-back-btn" onClick={onBack}>
            <ArrowLeft size={16} />
            <span>Back to Orders</span>
          </button>
        </div>
        <div className="panel" style={{ padding: '32px', textAlign: 'center', color: 'var(--muted)' }}>
          <p>Loading order details…</p>
        </div>
      </div>
    );
  }

  const { order, stock_item: item, messages } = detail;
  const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
  const customerName = getCustomerDisplayName(order);
  const variation = getVariationLabel(order);
  const orderCode = order.request_id || `#${order.id}`;

  return (
    <div className="order-page">
      {confirmDialog}

      {/* Top Navigation Bar & Action Buttons */}
      <div className="order-page-header">
        <div className="order-header-left">
          <button type="button" className="order-back-btn" onClick={onBack}>
            <ArrowLeft size={16} />
            <span>Back to Orders</span>
          </button>
          <nav className="order-breadcrumbs" aria-label="Breadcrumbs">
            <button type="button" className="order-crumb-link" onClick={onBack}>
              Orders
            </button>
            <span className="order-crumb-sep">/</span>
            <span className="order-crumb-active">Order #{order.id}</span>
          </nav>
        </div>

        <div className="order-header-actions">
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
              <RotateCw size={13} className={busy === 'retry' ? 'spin' : ''} />
              <span>Resend Message</span>
            </button>
          ) : null}

          {order.status === 'completed' ? (
            <button
              type="button"
              className="btn danger small"
              disabled={Boolean(busy)}
              onClick={async () => {
                const confirmed = await confirm(
                  `Refund order #${order.id}?`,
                  `${money(order.price)} will be returned directly to ${customerName}'s wallet balance.`,
                  'Refund Order',
                  true
                );
                if (!confirmed) return;
                void run('refund', async () => (await api.refundOrder(order.id)).message || 'Refunded successfully.');
              }}
            >
              <Undo2 size={13} />
              <span>Refund {money(order.price)}</span>
            </button>
          ) : null}
        </div>
      </div>

      {/* Card 1: Order Metadata Key-Value List (Matches Reference Image) */}
      <div className="panel order-detail-card">
        <div className="order-meta-grid">
          <div className="order-meta-row">
            <span className="order-meta-label">Order ID</span>
            <div className="order-meta-value">
              <span className="order-id-badge">{orderCode}</span>
              <button
                type="button"
                className="order-copy-chip"
                title="Copy Order ID"
                onClick={() => copyText(orderCode, 'id')}
              >
                {copiedField === 'id' ? <Check size={12} className="good-text" /> : <Copy size={12} />}
                <span>{copiedField === 'id' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Customer</span>
            <div className="order-meta-value">
              <span className="order-customer-name">{customerName}</span>
              <span className="order-customer-sub">
                {order.username ? (
                  <a
                    href={`https://t.me/${order.username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="order-tg-link"
                    title="Open in Telegram"
                  >
                    @{order.username}
                  </a>
                ) : null}
                <a
                  href={`#users/${order.tg_user_id}`}
                  className="order-user-chip"
                  title="View customer profile"
                >
                  <span>ID: {order.tg_user_id}</span>
                  <ExternalLink size={11} />
                </a>
              </span>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Product</span>
            <div className="order-meta-value">
              <span className="order-product-title">
                {order.product_icon ? <span className="order-product-icon">{order.product_icon}</span> : null}
                {order.product_title}
              </span>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Variation</span>
            <div className="order-meta-value">
              <span className="order-variation-text">{variation}</span>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Amount</span>
            <div className="order-meta-value">
              <span className="order-amount-text">{money(order.price)}</span>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Payment</span>
            <div className="order-meta-value">
              <span className="order-payment-text">
                {order.source === 'manual' ? 'Manual' : 'Wallet'} /{' '}
                {order.status === 'completed' ? (
                  waiting ? 'waiting fulfillment' : 'paid'
                ) : order.status === 'refunded' ? (
                  'refunded'
                ) : (
                  order.status
                )}
              </span>
              <span className={`pill ${order.status === 'completed' && !waiting ? 'good' : waiting ? 'warn' : 'bad'}`}>
                {order.status === 'completed' ? (waiting ? 'waiting' : 'completed') : order.status}
              </span>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Created</span>
            <div className="order-meta-value">
              <span className="order-time-text">{formatOrderDateTime(order.created_at)}</span>
            </div>
          </div>

          <div className="order-meta-row">
            <span className="order-meta-label">Delivered</span>
            <div className="order-meta-value">
              <span className="order-time-text">
                {waiting
                  ? 'Pending fulfillment'
                  : formatOrderDateTime(order.fulfilled_at || (order.status === 'completed' ? order.created_at : null))}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Card 2: Delivered Credentials (Matches Reference Image) */}
      <div className="panel order-credentials-card">
        <div className="order-credentials-header">
          <div className="order-credentials-title-group">
            <KeyRound size={18} className="order-key-icon" />
            <h3 className="order-credentials-title">Delivered Credentials</h3>
            {item && item.max_uses > 1 ? (
              <span className="pill info" style={{ fontSize: '11px' }}>
                Shared stock ({item.uses} of {item.max_uses} used)
              </span>
            ) : order.source ? (
              <span className="order-source-badge">
                {SOURCE[order.source] || order.source}
              </span>
            ) : null}
          </div>

          {order.delivered_item ? (
            <button
              type="button"
              className="order-copy-chip large"
              onClick={() => copyText(order.delivered_item, 'credentials')}
            >
              {copiedField === 'credentials' ? <Check size={13} className="good-text" /> : <Copy size={13} />}
              <span>{copiedField === 'credentials' ? 'Copied All' : 'Copy All'}</span>
            </button>
          ) : null}
        </div>

        {order.delivered_item ? (
          <div className="order-credentials-box">
            <pre>{order.delivered_item}</pre>
          </div>
        ) : (
          <div className="order-credentials-empty">
            <p>{waiting ? 'Credentials have not been sent yet.' : 'No credentials recorded for this order.'}</p>
          </div>
        )}
      </div>

      {/* Card 3: Manual Fulfillment (Only if waiting) */}
      {waiting ? (
        <div className="panel order-fulfill-card">
          <div className="order-fulfill-header">
            <div className="order-fulfill-title-group">
              <PackageCheck size={18} style={{ color: '#059669' }} />
              <h3>Fulfill & Deliver to Customer</h3>
            </div>
            <span className="pill warn">Action Required</span>
          </div>
          <p className="order-fulfill-desc">
            The customer has completed payment and is waiting. Enter the credentials or activation details below. Once submitted, it will be instantly delivered to the customer via Telegram.
          </p>
          <div className="field">
            <textarea
              className="mono order-fulfill-textarea"
              rows={5}
              placeholder={'Account / Credentials:\nEmail: customer@example.com\nPassword: password123\n\nInstructions:\nPlease login only on 1 device.'}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </div>
          <div className="order-fulfill-actions">
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
              <Send size={14} />
              <span>{busy === 'deliver' ? 'Sending to Customer…' : 'Send to Customer'}</span>
            </button>
          </div>
        </div>
      ) : null}

      {/* Card 4: Collapsible Telegram Outbox / Notification Log */}
      {messages && messages.length > 0 ? (
        <div className="panel order-messages-panel">
          <button
            type="button"
            className="order-messages-toggle"
            onClick={() => setShowMessages(!showMessages)}
          >
            <div className="order-messages-toggle-title">
              <Send size={15} style={{ color: 'var(--accent)' }} />
              <span>Telegram Messages & Notifications ({messages.length})</span>
            </div>
            <div className="order-messages-toggle-status">
              <span className={`pill ${messages.some((m) => m.status === 'failed') ? 'bad' : 'good'}`}>
                {messages.some((m) => m.status === 'failed') ? 'Delivery issue' : 'Delivered'}
              </span>
              {showMessages ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
          </button>

          {showMessages ? (
            <div className="order-messages-content">
              <ul className="order-messages-list">
                {messages.map((message) => (
                  <li key={message.id} className="order-message-item">
                    <div className="order-message-top">
                      <span className={`pill ${message.status === 'sent' ? 'good' : message.status === 'failed' ? 'bad' : 'warn'}`}>
                        {message.is_receipt ? 'Receipt' : 'Notification'} · {MESSAGE_STATE[message.status] ?? message.status}
                      </span>
                      {message.error ? <span className="bad-text" style={{ fontSize: '12px' }}>{message.error}</span> : null}
                    </div>
                    <div className="order-message-text">
                      {message.text.replace(/<[^>]+>/g, '')}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
