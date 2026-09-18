'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Ban,
  Check,
  Copy,
  CreditCard,
  ExternalLink,
  PackageCheck,
  ShoppingBag,
  UserCheck,
  Users as UsersIcon,
  Wallet,
} from 'lucide-react';
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
                <th>Status / Rank</th>
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
                  <td>
                    {user.is_banned ? (
                      <span className="pill bad">banned</span>
                    ) : (
                      <span className={`pill ${user.rank === 'Affiliate' ? 'warn' : user.rank === 'Reseller' ? 'info' : user.rank === 'VIP' ? 'vip' : 'good'}`}>
                        {user.rank === 'Affiliate' ? 'Affiliate 🤝' : user.rank === 'Reseller' ? 'Reseller 💼' : user.rank === 'VIP' ? 'VIP 💎' : 'Active 👤'}
                      </span>
                    )}
                  </td>
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
  const [adjustType, setAdjustType] = useState<'add' | 'take'>('add');
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, confirmDialog] = useConfirm();
  const [currentRank, setCurrentRank] = useState(user.rank || 'Standard');
  const [rankBusy, setRankBusy] = useState(false);
  const money = useMoney();
  const value = Number(amount);
  const valid = Number.isFinite(value) && value > 0 && Boolean(reason.trim());

  useEffect(() => {
    setCurrentRank(user.rank || 'Standard');
  }, [user.rank]);

  async function handleRankChange(newRank: string) {
    setCurrentRank(newRank);
    setRankBusy(true);
    try {
      await api.setUserRank(user.tg_user_id, newRank);
      say(`Account type updated to ${newRank}.`);
      await onChanged();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setCurrentRank(user.rank || 'Standard');
    } finally {
      setRankBusy(false);
    }
  }

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
      say(`${sign > 0 ? 'Added' : 'Deducted'} ${money(value)}.`);
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

  const initials = nameOf(user).replace(/[^a-zA-Z0-9]/g, '').slice(0, 2).toUpperCase() || 'U';

  return (
    <Modal
      title="Customer Profile"
      wide
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className={`btn small ${user.is_banned ? 'ghost' : 'danger'}`}
            onClick={() => void toggleBan()}
          >
            {user.is_banned ? (
              <>
                <UserCheck size={14} /> Unban Customer
              </>
            ) : (
              <>
                <Ban size={14} /> Ban Customer
              </>
            )}
          </button>
          <button type="button" className="btn ghost small" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      <div className="cust-dialog-content">
        {/* 1. Identity Hero Header Card */}
        <div className="cust-hero-card">
          <div className="cust-hero-left">
            <div className="cust-avatar">{initials}</div>
            <div className="cust-hero-info">
              <div className="cust-hero-name-row">
                <h3 className="cust-hero-name">{nameOf(user)}</h3>
                <span className={`pill ${user.is_banned ? 'bad' : 'good'}`}>
                  {user.is_banned ? 'Banned' : 'Active'}
                </span>
              </div>
              <div className="cust-hero-sub">
                {user.username ? (
                  <a
                    href={`https://t.me/${user.username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="cust-tg-link"
                    title="Open Telegram Chat"
                  >
                    <span>@{user.username}</span>
                    <ExternalLink size={12} />
                  </a>
                ) : (
                  <span>No username</span>
                )}
                <span className="cust-dot">·</span>
                <button
                  type="button"
                  className="cust-copy-id-btn"
                  onClick={() => {
                    void navigator.clipboard.writeText(String(user.tg_user_id));
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  title="Click to copy Telegram ID"
                >
                  <span>ID: {user.tg_user_id}</span>
                  {copied ? <Check size={11} style={{ color: '#059669' }} /> : <Copy size={11} />}
                </button>
                {user.created_at ? (
                  <>
                    <span className="cust-dot">·</span>
                    <span>Joined {when(user.created_at)}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {/* 2. Balanced 4-Metric Grid */}
        <div className="cust-stats-grid">
          <div className="cust-stat-card">
            <div className="cust-stat-top">
              <span className="cust-stat-label">Balance</span>
              <Wallet size={15} style={{ color: '#059669' }} />
            </div>
            <div className="cust-stat-value green">{money(user.balance)}</div>
          </div>

          <div className="cust-stat-card">
            <div className="cust-stat-top">
              <span className="cust-stat-label">Total Spent</span>
              <ShoppingBag size={15} style={{ color: '#0284c7' }} />
            </div>
            <div className="cust-stat-value">{money(user.total_spent)}</div>
          </div>

          <div className="cust-stat-card">
            <div className="cust-stat-top">
              <span className="cust-stat-label">Orders</span>
              <PackageCheck size={15} style={{ color: '#8b5cf6' }} />
            </div>
            <div className="cust-stat-value">{orderTotal}</div>
          </div>

          <div className="cust-stat-card">
            <div className="cust-stat-top">
              <span className="cust-stat-label">Account Type</span>
              <UserCheck size={15} style={{ color: '#d97706' }} />
            </div>
            <div className="cust-stat-value" style={{ marginTop: 4 }}>
              <select
                className="cust-rank-select"
                value={currentRank}
                disabled={rankBusy}
                onChange={(e) => void handleRankChange(e.target.value)}
                title="Change customer account type"
              >
                <option value="Standard">Normal User 👤</option>
                <option value="Affiliate">Affiliate Partner 🤝</option>
                <option value="Reseller">Reseller Partner 💼</option>
                <option value="VIP">VIP Member 💎</option>
              </select>
            </div>
          </div>
        </div>

        {/* 3. Wallet Adjustment Panel */}
        <div className="cust-balance-section">
          <div className="cust-section-header">
            <span className="cust-section-title">
              <Wallet size={14} /> Adjust Balance
            </span>
            <div className="cust-adjust-type-toggle">
              <button
                type="button"
                className={`cust-adjust-tab ${adjustType === 'add' ? 'active add' : ''}`}
                onClick={() => setAdjustType('add')}
              >
                + Add Balance
              </button>
              <button
                type="button"
                className={`cust-adjust-tab ${adjustType === 'take' ? 'active take' : ''}`}
                onClick={() => setAdjustType('take')}
              >
                - Deduct Balance
              </button>
            </div>
          </div>

          <div className="cust-adjust-box">
            {/* Quick Presets */}
            {adjustType === 'add' ? (
              <div className="cust-quick-amounts">
                <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>Quick:</span>
                {[50, 100, 200, 500, 1000].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    className="cust-quick-amt-btn"
                    onClick={() => setAmount(String(preset))}
                  >
                    +{preset}
                  </button>
                ))}
              </div>
            ) : null}

            <div className="cust-adjust-inputs">
              <div className="cust-input-group">
                <label>Amount</label>
                <input
                  type="number"
                  step="any"
                  min="0"
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </div>

              <div className="cust-input-group">
                <label>Reason / Note</label>
                <input
                  type="text"
                  placeholder="e.g. Deposit bonus, refund, correction"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>

              <button
                type="button"
                className={`btn small ${adjustType === 'add' ? 'cust-btn-add' : 'danger'}`}
                style={{ minHeight: 38 }}
                disabled={busy || !valid || (adjustType === 'take' && value > user.balance)}
                onClick={() => void adjust(adjustType === 'add' ? 1 : -1)}
              >
                {busy
                  ? 'Saving…'
                  : adjustType === 'add'
                  ? `Add ${value > 0 ? money(value) : ''}`
                  : `Deduct ${value > 0 ? money(value) : ''}`}
              </button>
            </div>
          </div>
        </div>

        {/* 4. Order History */}
        <div className="cust-orders-section">
          <div className="cust-section-header">
            <span className="cust-section-title">
              <ShoppingBag size={14} /> Recent Orders {orderTotal > 0 ? `(${orderTotal})` : ''}
            </span>
          </div>

          {!orders ? (
            <div className="cust-orders-loading">Loading order history…</div>
          ) : orders.length === 0 ? (
            <div className="cust-orders-empty">
              <PackageCheck size={28} style={{ opacity: 0.35, margin: '0 auto 6px', display: 'block' }} />
              <p style={{ margin: 0 }}>No orders placed by this customer yet.</p>
            </div>
          ) : (
            <div className="cust-orders-list">
              {orders.map((order) => {
                const isWaiting = order.status === 'completed' && order.fulfillment === 'waiting';
                return (
                  <div key={order.id} className="cust-order-row">
                    <div className="cust-order-left">
                      <span className={`pill ${isWaiting ? 'warn' : tone(order.status)}`}>
                        {isWaiting ? 'waiting' : order.status}
                      </span>
                      <div className="cust-order-info">
                        <span className="cust-order-title">{order.product_title}</span>
                        <span className="cust-order-meta">
                          Order #{order.id} · {when(order.created_at)}
                        </span>
                      </div>
                    </div>
                    <div className="cust-order-right">
                      <span className="cust-order-price">{money(order.price)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      {confirmDialog}
    </Modal>
  );
}
