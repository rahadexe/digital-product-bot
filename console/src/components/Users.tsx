'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Ban,
  Briefcase,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  CreditCard,
  ExternalLink,
  PackageCheck,
  Send,
  ShoppingBag,
  User as UserIcon,
  UserCheck,
  Users as UsersIcon,
  Wallet,
} from 'lucide-react';
import { api, type Order, type User, type UserSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, Pager, errorText, tone, useConfirm, useDebounced, when, type Say } from './ui';

const PAGE = 50;

type UserFilter = 'all' | 'has_balance' | 'banned';

const nameOf = (user: User) =>
  [user.first_name, user.last_name].filter(Boolean).join(' ') ||
  (user.username ? `@${user.username}` : `User ${user.tg_user_id}`);

export function Users({
  say,
  initialUserId = null,
  onNavigate,
}: {
  say: Say;
  initialUserId?: number | null;
  onNavigate?: (userId: number | null) => void;
}) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [filter, setFilter] = useState<UserFilter>('all');
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(initialUserId);
  const [activeUser, setActiveUser] = useState<User | null>(null);
  const query = useDebounced(search);
  const money = useMoney();

  useEffect(() => {
    setSelectedId(initialUserId);
  }, [initialUserId]);

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

  const openProfile = (user: User) => {
    setActiveUser(user);
    setSelectedId(user.tg_user_id);
    onNavigate?.(user.tg_user_id);
  };

  const closeProfile = () => {
    setSelectedId(null);
    setActiveUser(null);
    onNavigate?.(null);
  };

  // If a customer is opened, render the dedicated full-page profile view
  if (selectedId) {
    return (
      <CustomerProfilePage
        userId={selectedId}
        initialUser={activeUser}
        say={say}
        onBack={closeProfile}
        onUserUpdated={(updated) => {
          setActiveUser(updated);
          void load();
        }}
      />
    );
  }

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
          onClick={() => {
            setFilter('all');
            setOffset(0);
          }}
        >
          All Customers
        </button>
        <button
          type="button"
          className={filter === 'has_balance' ? 'active' : ''}
          onClick={() => {
            setFilter('has_balance');
            setOffset(0);
          }}
        >
          With Balance
          {summary?.with_balance_count ? <span className="count">{summary.with_balance_count}</span> : null}
        </button>
        <button
          type="button"
          className={filter === 'banned' ? 'active' : ''}
          onClick={() => {
            setFilter('banned');
            setOffset(0);
          }}
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
          <table className="cust-table-responsive">
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
              {(users ?? []).map((user) => {
                const initials =
                  nameOf(user)
                    .replace(/[^a-zA-Z0-9]/g, '')
                    .slice(0, 2)
                    .toUpperCase() || 'U';
                return (
                  <tr
                    key={user.id}
                    onClick={() => openProfile(user)}
                    className="cust-table-row"
                    title="Click to view customer profile"
                  >
                    <td className="name" data-label="Customer">
                      <div className="cust-table-user-cell">
                        <div className="cust-table-avatar">{initials}</div>
                        <div className="cust-table-user-meta">
                          <span className="cust-table-name">{nameOf(user)}</span>
                          <small>
                            {user.username ? `@${user.username} · ` : ''}
                            {user.tg_user_id} · joined {when(user.created_at)}
                          </small>
                        </div>
                      </div>
                    </td>
                    <td className="money" data-label="Balance">
                      <span className="cust-money-badge">{money(user.balance)}</span>
                    </td>
                    <td className="money" data-label="Spent">
                      {money(user.total_spent)}
                    </td>
                    <td data-label="Status / Rank">
                      <div className="cust-status-stack">
                        {user.is_banned ? (
                          <span className="pill bad">banned</span>
                        ) : user.rank === 'Reseller' ? (
                          <span className="pill info">Reseller</span>
                        ) : (
                          <span className="pill good">Normal</span>
                        )}
                      </div>
                    </td>
                    <td className="right" data-label="Action">
                      <div className="row-actions">
                        <button
                          type="button"
                          className="mini cust-view-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            openProfile(user);
                          }}
                        >
                          <span>Open</span>
                          <ChevronRight size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {users && users.length === 0 ? (
                <EmptyRow columns={5}>{query ? 'Nothing matches.' : 'No customers yet.'}</EmptyRow>
              ) : null}
              {!users ? <EmptyRow columns={5}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
      </section>
    </>
  );
}

/** Dedicated, executive-grade, fully responsive customer profile page */
function CustomerProfilePage({
  userId,
  initialUser,
  say,
  onBack,
  onUserUpdated,
}: {
  userId: number;
  initialUser?: User | null;
  say: Say;
  onBack: () => void;
  onUserUpdated: (user: User) => void;
}) {
  const [user, setUser] = useState<User | null>(initialUser ?? null);
  const [loading, setLoading] = useState<boolean>(!initialUser);
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [orderTotal, setOrderTotal] = useState(0);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [adjustType, setAdjustType] = useState<'add' | 'take'>('add');
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [currentRank, setCurrentRank] = useState(initialUser?.rank || 'Standard');
  const [rankBusy, setRankBusy] = useState(false);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  // Load user data if not passed or when userId changes
  useEffect(() => {
    let mounted = true;
    if (!initialUser || initialUser.tg_user_id !== userId) {
      setLoading(true);
      api
        .user(userId)
        .then((res) => {
          if (mounted && res.user) {
            setUser(res.user);
            setCurrentRank(res.user.rank || 'Standard');
          }
        })
        .catch((err) => {
          if (mounted) say(errorText(err), 'bad');
        })
        .finally(() => {
          if (mounted) setLoading(false);
        });
    } else {
      setUser(initialUser);
      setCurrentRank(initialUser.rank || 'Standard');
      setLoading(false);
    }
    return () => {
      mounted = false;
    };
  }, [userId, initialUser, say]);

  // Load customer orders
  useEffect(() => {
    let mounted = true;
    api
      .orders('', 50, 0, false, userId)
      .then((result) => {
        if (mounted) {
          setOrders(result.orders);
          setOrderTotal(result.total);
        }
      })
      .catch((cause) => {
        if (mounted) say(errorText(cause), 'bad');
      });
    return () => {
      mounted = false;
    };
  }, [userId, say]);

  const value = Number(amount);
  const valid = Number.isFinite(value) && value > 0 && Boolean(reason.trim());

  async function handleRankChange(newRank: string) {
    if (!user || newRank === (user.rank || 'Standard')) return;
    const isReseller = newRank === 'Reseller';
    const title = isReseller
      ? `Make ${nameOf(user)} a Reseller?`
      : `Change ${nameOf(user)} to Normal?`;
    const message = isReseller
      ? `Are you sure you want to change this customer to Reseller? They will automatically receive reseller pricing in the Telegram bot.`
      : `Are you sure you want to change this customer back to Normal?`;
    const confirmLabel = isReseller ? 'Make Reseller' : 'Change to Normal';

    const ok = await confirm(title, message, confirmLabel, false);
    if (!ok) {
      setCurrentRank(user.rank || 'Standard');
      return;
    }

    setCurrentRank(newRank);
    setRankBusy(true);
    try {
      await api.setUserRank(user.tg_user_id, newRank);
      say(`Account type updated to ${isReseller ? 'Reseller' : 'Normal'}.`);
      const updated = { ...user, rank: newRank };
      setUser(updated);
      onUserUpdated(updated);
    } catch (cause) {
      say(errorText(cause), 'bad');
      setCurrentRank(user.rank || 'Standard');
    } finally {
      setRankBusy(false);
    }
  }

  async function adjust(sign: 1 | -1) {
    if (!user || !valid) return;
    const actionWord = sign > 0 ? 'Add' : 'Deduct';
    const confirmed = await confirm(
      `${actionWord} ${money(value)}?`,
      `Are you sure you want to ${actionWord.toLowerCase()} ${money(value)} ${sign > 0 ? 'to' : 'from'} ${nameOf(user)}'s wallet? Note: "${reason.trim()}".`,
      `${actionWord} Balance`,
      sign < 0
    );
    if (!confirmed) return;

    setBusy(true);
    try {
      const res = await api.adjustBalance(user.tg_user_id, sign * value, reason.trim());
      say(`${sign > 0 ? 'Added' : 'Deducted'} ${money(value)}.`);
      setAmount('');
      setReason('');
      if (res.user) {
        setUser(res.user);
        onUserUpdated(res.user);
      }
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(false);
    }
  }

  async function toggleBan() {
    if (!user) return;
    if (
      !user.is_banned &&
      !(await confirm(
        `Ban ${nameOf(user)}?`,
        'They will not be able to use the bot or the Mini App until unbanned.',
        'Ban customer'
      ))
    ) {
      return;
    }
    try {
      const result = await api.toggleBan(user.tg_user_id);
      say(result.is_banned ? 'Customer banned.' : 'Customer unbanned.');
      const updated = { ...user, is_banned: result.is_banned ? 1 : 0 };
      setUser(updated);
      onUserUpdated(updated);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  const copyId = () => {
    if (!user) return;
    void navigator.clipboard.writeText(String(user.tg_user_id));
    setCopied(true);
    say('Copied Telegram ID to clipboard.');
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading && !user) {
    return (
      <div className="cust-profile-page">
        <div className="cust-page-header">
          <button type="button" className="cust-back-btn" onClick={onBack}>
            <ArrowLeft size={16} />
            <span>Back to Customers</span>
          </button>
        </div>
        <div className="panel cust-loading-card">
          <p>Loading customer profile…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="cust-profile-page">
        <div className="cust-page-header">
          <button type="button" className="cust-back-btn" onClick={onBack}>
            <ArrowLeft size={16} />
            <span>Back to Customers</span>
          </button>
        </div>
        <div className="panel cust-loading-card">
          <p>Customer not found or failed to load.</p>
        </div>
      </div>
    );
  }

  const initials =
    nameOf(user)
      .replace(/[^a-zA-Z0-9]/g, '')
      .slice(0, 2)
      .toUpperCase() || 'U';

  return (
    <div className="cust-profile-page">
      {confirmDialog}
      {/* 1. Header Navigation Bar */}
      <div className="cust-page-header">
        <button type="button" className="cust-back-btn" onClick={onBack}>
          <ArrowLeft size={16} />
          <span>Back to Customers</span>
        </button>
        <nav className="cust-breadcrumbs" aria-label="Breadcrumbs">
          <button type="button" className="cust-crumb-link" onClick={onBack}>
            Customers
          </button>
          <span className="cust-crumb-sep">/</span>
          <span className="cust-crumb-active">{nameOf(user)}</span>
        </nav>
      </div>

      {/* 2. Hero Profile Banner Card */}
      <div className="cust-profile-hero">
        <div className="cust-hero-main">
          <div className="cust-avatar-large">{initials}</div>
          <div className="cust-hero-details">
            <div className="cust-hero-title-row">
              <h2 className="cust-hero-title">{nameOf(user)}</h2>
              <span className={`pill ${user.is_banned ? 'bad' : 'good'}`}>
                {user.is_banned ? 'Banned' : 'Active'}
              </span>
              {user.rank === 'Reseller' ? (
                <span className="pill cust-reseller-pill">
                  <Briefcase size={12} /> Reseller
                </span>
              ) : null}
            </div>

            <div className="cust-hero-meta-row">
              {user.username ? (
                <a
                  href={`https://t.me/${user.username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="cust-tg-chip"
                  title="Open Telegram Chat"
                >
                  <Send size={12} />
                  <span>@{user.username}</span>
                  <ExternalLink size={11} style={{ opacity: 0.7 }} />
                </a>
              ) : (
                <span className="cust-meta-text">No username</span>
              )}

              <span className="cust-meta-sep">·</span>

              <button
                type="button"
                className="cust-copy-chip"
                onClick={copyId}
                title="Click to copy Telegram ID"
              >
                <span>ID: {user.tg_user_id}</span>
                {copied ? <Check size={12} style={{ color: '#059669' }} /> : <Copy size={12} />}
              </button>

              {user.created_at ? (
                <>
                  <span className="cust-meta-sep">·</span>
                  <span className="cust-meta-text">Joined {when(user.created_at)}</span>
                </>
              ) : null}
            </div>
          </div>
        </div>

        {/* Hero Actions on the right */}
        <div className="cust-hero-actions">
          {user.username ? (
            <a
              href={`https://t.me/${user.username}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn small ghost cust-hero-btn"
            >
              <Send size={14} />
              <span>Telegram Chat</span>
            </a>
          ) : null}

          <button
            type="button"
            className={`btn small ${user.is_banned ? 'ghost' : 'danger'} cust-hero-btn`}
            onClick={() => void toggleBan()}
          >
            {user.is_banned ? (
              <>
                <UserCheck size={14} />
                <span>Unban Customer</span>
              </>
            ) : (
              <>
                <Ban size={14} />
                <span>Ban Customer</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 3. 4-Metric Highlight Grid */}
      <div className="cust-metrics-grid">
        <div className="cust-metric-card">
          <div className="cust-metric-top">
            <span className="cust-metric-label">Available Balance</span>
            <div
              className="cust-metric-icon-wrap"
              style={{ background: 'rgba(16, 185, 129, 0.12)', color: '#059669' }}
            >
              <Wallet size={16} />
            </div>
          </div>
          <div className="cust-metric-val green">{money(user.balance)}</div>
        </div>

        <div className="cust-metric-card">
          <div className="cust-metric-top">
            <span className="cust-metric-label">Total Spent</span>
            <div
              className="cust-metric-icon-wrap"
              style={{ background: 'rgba(2, 132, 199, 0.12)', color: '#0284c7' }}
            >
              <ShoppingBag size={16} />
            </div>
          </div>
          <div className="cust-metric-val">{money(user.total_spent)}</div>
        </div>

        <div className="cust-metric-card">
          <div className="cust-metric-top">
            <span className="cust-metric-label">Total Orders</span>
            <div
              className="cust-metric-icon-wrap"
              style={{ background: 'rgba(139, 92, 246, 0.12)', color: '#8b5cf6' }}
            >
              <PackageCheck size={16} />
            </div>
          </div>
          <div className="cust-metric-val">{orderTotal}</div>
        </div>

        <div className={`cust-metric-card cust-tier-card ${currentRank === 'Reseller' ? 'reseller-card' : ''}`}>
          <div className="cust-metric-top">
            <span className="cust-metric-label">Account Tier</span>
            <div
              className="cust-metric-icon-wrap"
              style={
                currentRank === 'Reseller'
                  ? { background: 'rgba(2, 132, 199, 0.16)', color: '#0284c7' }
                  : { background: 'rgba(217, 119, 6, 0.12)', color: '#d97706' }
              }
            >
              {currentRank === 'Reseller' ? <Briefcase size={16} /> : <UserCheck size={16} />}
            </div>
          </div>
          <div className="cust-tier-select-wrap">
            <TierDropdown
              value={currentRank}
              disabled={rankBusy}
              onChange={(newRank) => void handleRankChange(newRank)}
            />
          </div>
        </div>
      </div>

      {/* 4. Two-Column Workspace Grid */}
      <div className="cust-workspace-grid">
        {/* Left Column: Wallet Management Card */}
        <div className="panel cust-workspace-panel">
          <header className="cust-panel-head">
            <div>
              <h3>Adjust Wallet Balance</h3>
              <p className="cust-panel-desc">Add or deduct wallet funds.</p>
            </div>
          </header>

          <div className="cust-panel-body">
            {/* Toggle add/take */}
            <div className="cust-adjust-switch">
              <button
                type="button"
                className={`cust-switch-tab ${adjustType === 'add' ? 'active-add' : ''}`}
                onClick={() => setAdjustType('add')}
              >
                + Add Balance
              </button>
              <button
                type="button"
                className={`cust-switch-tab ${adjustType === 'take' ? 'active-take' : ''}`}
                onClick={() => setAdjustType('take')}
              >
                - Deduct Balance
              </button>
            </div>

            {/* Form Inputs */}
            <div className="cust-form-grid">
              <div className="field">
                <label htmlFor="adjust-amount">Amount (৳)</label>
                <input
                  id="adjust-amount"
                  type="number"
                  step="any"
                  min="0"
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </div>

              <div className="field">
                <label htmlFor="adjust-reason">Reason</label>
                <input
                  id="adjust-reason"
                  type="text"
                  placeholder="e.g. Bonus, refund"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            </div>

            <button
              type="button"
              className={`btn ${adjustType === 'add' ? 'cust-action-save-add' : 'danger'} cust-full-action-btn`}
              disabled={busy || !valid || (adjustType === 'take' && value > user.balance)}
              onClick={() => void adjust(adjustType === 'add' ? 1 : -1)}
            >
              {busy
                ? 'Processing…'
                : adjustType === 'add'
                ? `+ Add ${value > 0 ? money(value) : ''} to Balance`
                : `- Deduct ${value > 0 ? money(value) : ''} from Balance`}
            </button>
          </div>
        </div>

        {/* Right Column: Order History Card */}
        <div className="panel cust-workspace-panel">
          <header className="cust-panel-head">
            <div>
              <h3>Recent Orders</h3>
              <p className="cust-panel-desc">Order history for this customer.</p>
            </div>
            {orderTotal > 0 ? <span className="pill">{orderTotal}</span> : null}
          </header>

          <div className="cust-panel-body">
            {!orders ? (
              <div className="cust-state-box">Loading order history…</div>
            ) : orders.length === 0 ? (
              <div className="cust-state-box empty">
                <PackageCheck size={32} className="cust-empty-icon" />
                <p>No orders placed by this customer yet.</p>
              </div>
            ) : (
              <div className="cust-orders-scrollable">
                {orders.map((order) => {
                  const isWaiting = order.status === 'completed' && order.fulfillment === 'waiting';
                  return (
                    <div key={order.id} className="cust-order-item">
                      <div className="cust-order-item-left">
                        <span className={`pill ${isWaiting ? 'warn' : tone(order.status)}`}>
                          {isWaiting ? 'waiting' : order.status}
                        </span>
                        <div className="cust-order-meta">
                          <strong className="cust-order-product">{order.product_title}</strong>
                          <span className="cust-order-sub">
                            Order #{order.id} · {when(order.created_at)}
                          </span>
                        </div>
                      </div>
                      <div className="cust-order-item-right">
                        <span className="cust-order-amount">{money(order.price)}</span>
                        <a
                          href={`#orders/${order.id}`}
                          className="cust-order-link"
                          title="View order in Orders screen"
                        >
                          <span>View</span>
                          <ChevronRight size={13} />
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {confirmDialog}
    </div>
  );
}

/** Custom, modern Account Tier dropdown with rich options and icons */
function TierDropdown({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (newRank: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const isReseller = value === 'Reseller';

  useEffect(() => {
    if (!open) return;
    const clickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', clickOutside);
    return () => document.removeEventListener('mousedown', clickOutside);
  }, [open]);

  return (
    <div className={`tier-dropdown-container ${open ? 'is-open' : ''}`} ref={containerRef}>
      <button
        type="button"
        className={`tier-dropdown-trigger ${isReseller ? 'reseller-trigger' : ''}`}
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <div className="tier-trigger-left">
          {isReseller ? (
            <Briefcase size={15} className="tier-icon-reseller" />
          ) : (
            <UserIcon size={15} className="tier-icon-normal" />
          )}
          <span className="tier-trigger-label">
            {isReseller ? 'Reseller' : 'Normal'}
          </span>
        </div>
        <ChevronDown size={14} className={`tier-chevron ${open ? 'rotated' : ''}`} />
      </button>

      {open ? (
        <div className="tier-dropdown-menu">
          <button
            type="button"
            className={`tier-menu-item ${!isReseller ? 'active' : ''}`}
            onClick={() => {
              setOpen(false);
              onChange('Standard');
            }}
          >
            <div className="tier-item-info">
              <div className="tier-item-row">
                <UserIcon size={14} />
                <strong>Normal</strong>
              </div>
              <small>Standard customer pricing</small>
            </div>
            {!isReseller ? <Check size={14} className="tier-check" /> : null}
          </button>

          <button
            type="button"
            className={`tier-menu-item reseller-item ${isReseller ? 'active' : ''}`}
            onClick={() => {
              setOpen(false);
              onChange('Reseller');
            }}
          >
            <div className="tier-item-info">
              <div className="tier-item-row">
                <Briefcase size={14} />
                <strong>Reseller</strong>
              </div>
              <small>Discounted reseller prices in Bot</small>
            </div>
            {isReseller ? <Check size={14} className="tier-check" /> : null}
          </button>
        </div>
      ) : null}
    </div>
  );
}
