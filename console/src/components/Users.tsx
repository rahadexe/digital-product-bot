'use client';

import { useCallback, useEffect, useState } from 'react';
import { Ban, CreditCard, Users as UsersIcon, Wallet } from 'lucide-react';
import { api, type Order, type User, type UserSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, Modal, Pager, errorText, tone, useConfirm, useDebounced, when, type Say } from './ui';

const PAGE = 50;

type UserFilter = 'all' | 'has_balance' | 'banned';

const nameOf = (user: User) => [user.first_name, user.last_name].filter(Boolean).join(' ') || (user.username ? `@${user.username}` : `User ${user.tg_user_id}`);

export function Users({ say }: { say: Say }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [filter, setFilter] = useState<UserFilter>('all');
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<User | null>(null);
  const query = useDebounced(search);
  const money = useMoney();

  const load = useCallback(async () => {
    try {
      const filterParam = filter === 'all' ? undefined : filter;
      const result = await api.users(query, PAGE, offset, filterParam);
      setUsers(result.users);
      setTotal(result.total);
      setSummary(result.summary ?? null);
      return result.users;
    } catch (cause) {
      say(errorText(cause), 'bad');
      return null;
    }
  }, [query, offset, filter, say]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      {/* 4 Customer Metric Summary Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Customers</span>
            <UsersIcon className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary ? summary.total_users : total}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Wallet Balance</span>
            <Wallet className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{money(summary?.total_balance ?? 0)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Active Wallets</span>
            <CreditCard className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.with_balance_count ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Banned Customers</span>
            <Ban className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.banned_count ?? 0}</div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="segmented" role="tablist">
        <button
          type="button"
          className={filter === 'all' ? 'active' : ''}
          onClick={() => { setFilter('all'); setOffset(0); }}
        >
          All Customers
        </button>
        <button
          type="button"
          className={filter === 'has_balance' ? 'active' : ''}
          onClick={() => { setFilter('has_balance'); setOffset(0); }}
        >
          With Balance
          {summary?.with_balance_count ? <span className="count">{summary.with_balance_count}</span> : null}
        </button>
        <button
          type="button"
          className={filter === 'banned' ? 'active' : ''}
          onClick={() => { setFilter('banned'); setOffset(0); }}
        >
          Banned
          {summary?.banned_count ? <span className="count">{summary.banned_count}</span> : null}
        </button>
      </div>

      <section className="panel">
        <header>
          <h2>{total} customers</h2>
          <div className="filters">
            <input
              type="search"
              placeholder="Search name, @username or ID"
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
                <th>Customer</th>
                <th>Balance</th>
                <th>Spent</th>
                <th>Status</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {(users ?? []).map((user) => (
                <tr key={user.id}>
                  <td className="name">
                    {nameOf(user)}
                    <small>
                      {user.username ? `@${user.username} · ` : ''}
                      {user.tg_user_id} · joined {when(user.created_at)}
                    </small>
                  </td>
                  <td className="money">{money(user.balance)}</td>
                  <td className="money">{money(user.total_spent)}</td>
                  <td>{user.is_banned ? <span className="pill bad">banned</span> : <span className="pill good">active</span>}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="mini" onClick={() => setOpen(user)}>
                        Open
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {users && users.length === 0 ? <EmptyRow columns={5}>{query ? 'Nothing matches.' : 'No customers yet.'}</EmptyRow> : null}
              {!users ? <EmptyRow columns={5}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
      </section>

      {open ? (
        <CustomerDialog
          user={open}
          say={say}
          onClose={() => setOpen(null)}
          onChanged={async () => {
            const fresh = await load();
            const updated = fresh?.find((row) => row.tg_user_id === open.tg_user_id);
            if (updated) setOpen(updated);
          }}
        />
      ) : null}
    </>
  );
}

/** Everything about one customer in one place: their wallet, their orders, and whether they may use the store. */
function CustomerDialog({ user, say, onClose, onChanged }: { user: User; say: Say; onClose: () => void; onChanged: () => Promise<void> }) {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [orderTotal, setOrderTotal] = useState(0);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();
  const value = Number(amount);
  const valid = Number.isFinite(value) && value > 0 && Boolean(reason.trim());

  useEffect(() => {
    api
      .orders('', 50, 0, false, user.tg_user_id)
      .then((result) => {
        setOrders(result.orders);
        setOrderTotal(result.total);
      })
      .catch((cause) => say(errorText(cause), 'bad'));
  }, [user.tg_user_id, say]);

  async function adjust(sign: 1 | -1) {
    if (!valid) return;
    setBusy(true);
    try {
      await api.adjustBalance(user.tg_user_id, sign * value, reason.trim());
      say(`${sign > 0 ? 'Added' : 'Took'} ${money(value)}.`);
      setAmount('');
      setReason('');
      await onChanged();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(false);
    }
  }

  async function toggleBan() {
    if (!user.is_banned && !(await confirm(`Ban ${nameOf(user)}?`, 'They will not be able to use the bot or the Mini App until unbanned.', 'Ban customer'))) return;
    try {
      const result = await api.toggleBan(user.tg_user_id);
      say(result.is_banned ? 'Banned.' : 'Unbanned.');
      await onChanged();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  return (
    <Modal
      title={nameOf(user)}
      wide
      onClose={onClose}
      footer={
        <>
          <button type="button" className={`btn small${user.is_banned ? ' ghost' : ' danger'}`} onClick={() => void toggleBan()}>
            {user.is_banned ? 'Unban' : 'Ban'}
          </button>
          <button type="button" className="btn ghost small" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      <dl className="facts-grid">
        <div>
          <dt>Balance</dt>
          <dd>{money(user.balance)}</dd>
        </div>
        <div>
          <dt>Spent</dt>
          <dd>{money(user.total_spent)}</dd>
        </div>
        <div>
          <dt>Telegram</dt>
          <dd>
            {user.username ? `@${user.username}` : '—'} <span className="hint">{user.tg_user_id}</span>
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{user.is_banned ? <span className="pill bad">banned</span> : <span className="pill good">active</span>}</dd>
        </div>
      </dl>

      <div className="field">
        <span>Change balance</span>
        <div className="field-row">
          <input type="number" step="any" min="0" placeholder="Amount" aria-label="Amount" value={amount} onChange={(event) => setAmount(event.target.value)} />
          <input type="text" placeholder="Reason: bonus, refund, correction" aria-label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
        <div className="filters">
          <button type="button" className="btn small" disabled={busy || !valid} onClick={() => void adjust(1)}>
            Add {value > 0 ? money(value) : ''}
          </button>
          <button type="button" className="btn ghost small" disabled={busy || !valid || value > user.balance} onClick={() => void adjust(-1)}>
            Take {value > 0 ? money(value) : ''}
          </button>
        </div>
      </div>

      <div className="field">
        <span>Orders{orderTotal > 50 ? ` (latest 50 of ${orderTotal})` : ''}</span>
        {!orders ? <p className="hint">Loading…</p> : null}
        {orders && orders.length === 0 ? <p className="hint">No orders yet.</p> : null}
        {orders && orders.length ? (
          <ul className="messages">
            {orders.map((order) => (
              <li key={order.id}>
                <span className={`pill ${order.status === 'completed' && order.fulfillment === 'waiting' ? 'warn' : tone(order.status)}`}>
                  {order.status === 'completed' && order.fulfillment === 'waiting' ? 'waiting' : order.status}
                </span>{' '}
                <strong>{order.product_title}</strong> <span className="hint">
                  #{order.id} · {money(order.price)} · {when(order.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      {confirmDialog}
    </Modal>
  );
}
