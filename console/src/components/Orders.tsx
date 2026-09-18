'use client';

import { useCallback, useEffect, useState } from 'react';
import { Clock, PackageCheck, ShoppingBag, Wallet, X } from 'lucide-react';
import { api, type Order, type OrderDetail, type OrderSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, Modal, Pager, errorText, tone, useConfirm, useDebounced, when, who, type Say } from './ui';

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
  const [total, setTotal] = useState(0);
  const [waitingCount, setWaitingCount] = useState(0);
  const [waitingOnly, setWaitingOnly] = useState(initialWaiting);
  const [timeframe, setTimeframe] = useState<Timeframe>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<number | null>(initialOrderId);
  const query = useDebounced(search);
  const money = useMoney();

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
                  <tr key={order.id}>
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
                        <button type="button" className={`mini${waiting ? ' primary' : ''}`} onClick={() => setOpen(order.id)}>
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

      {open ? (
        <OrderDialog
          orderId={open}
          say={say}
          onClose={() => setOpen(null)}
          onChanged={() => void load()}
        />
      ) : null}
    </>
  );
}

function OrderDialog({ orderId, say, onClose, onChanged }: { orderId: number; say: Say; onClose: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loadError, setLoadError] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState('');
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
    // Loaded once per opened order.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

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

  if (loadError) {
    return (
      <Modal
        title={`Order #${orderId}`}
        onClose={onClose}
        footer={
          <>
            <button type="button" className="btn ghost" onClick={onClose}>Close</button>
            <button type="button" className="btn" onClick={() => void load()}>Try again</button>
          </>
        }
      >
        <div className="dialog-error" role="alert">
          <strong>Order details unavailable</strong>
          <p>{loadError}</p>
        </div>
      </Modal>
    );
  }

  if (!detail) {
    return (
      <Modal title={`Order #${orderId}`} onClose={onClose}>
        <p className="hint">Loading…</p>
      </Modal>
    );
  }

  const { order, stock_item: item, messages } = detail;
  const waiting = order.status === 'completed' && order.fulfillment === 'waiting';

  return (
    <Modal title={`Order #${order.id}`} wide onClose={onClose}>
      {confirmDialog}
      <dl className="facts-grid">
        <div>
          <dt>Product</dt>
          <dd>{order.product_title}</dd>
        </div>
        <div>
          <dt>Buyer</dt>
          <dd>
            {who(order)} <span className="hint">{order.tg_user_id}</span>
          </dd>
        </div>
        <div>
          <dt>Paid</dt>
          <dd>
            {money(order.price)} <span className="hint">{when(order.created_at)}</span>
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            {waiting ? <span className="pill warn">waiting to send</span> : <span className={`pill ${tone(order.status)}`}>{order.status}</span>}
          </dd>
        </div>
      </dl>

      {waiting ? (
        <div className="stack">
          <p className="warn-text">
            The customer has paid and was told it is being prepared. Nothing has been sent yet.
          </p>
          <label className="field">
            <span>What the customer gets</span>
            <textarea className="mono" rows={4} placeholder={'Email: …\nPassword: …'} value={content} onChange={(event) => setContent(event.target.value)} />
          </label>
          <div className="filters">
            <button
              type="button"
              className="btn"
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
      ) : (
        <div className="stack">
          <div className="field">
            <span>
              Delivered · {SOURCE[order.source]}
              {item && item.max_uses > 1 ? ` (shared account, ${item.uses} of ${item.max_uses} used)` : ''}
            </span>
            <pre className="delivered">{order.delivered_item || '—'}</pre>
          </div>
        </div>
      )}

      <div className="field">
        <span>Messages to the customer</span>
        {messages.length ? (
          <ul className="messages">
            {messages.map((message) => (
              <li key={message.id}>
                <span className={`pill ${message.status === 'sent' ? 'good' : message.status === 'failed' ? 'bad' : 'warn'}`}>
                  {message.is_receipt ? 'receipt' : 'notice'} · {MESSAGE_STATE[message.status] ?? message.status}
                </span>
                {message.error ? <small className="bad-text"> {message.error}</small> : null}
                <p>{message.text.replace(/<[^>]+>/g, '')}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">None. Orders from before messages were recorded show nothing here.</p>
        )}
      </div>


      <div className="filters">
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
            Send the message again
          </button>
        ) : null}
        {order.status === 'completed' ? (
          <button
            type="button"
            className="btn danger small"
            disabled={Boolean(busy)}
            onClick={async () => {
              if (!(await confirm(`Refund order #${order.id}?`, `${money(order.price)} will go back to the customer's balance.`, 'Refund order'))) return;
              void run('refund', async () => (await api.refundOrder(order.id)).message || 'Refunded.');
            }}
          >
            Refund {money(order.price)}
          </button>
        ) : null}
      </div>
    </Modal>
  );
}
