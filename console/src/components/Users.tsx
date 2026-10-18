'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Ban,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  Eye,
  Power,
  RefreshCw,
  Send,
  UserCheck,
} from 'lucide-react';
import { api, type Order, type ResellerKeyInfo, type ResellerStats, type User, type UserSummary } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { MobileRecord } from './MobileRecord';
import { EmptyRow, Pager, errorText, tone, useConfirm, useDebounced, when, type Say } from './ui';

const PAGE = 50;

type UserFilter = 'all' | 'reseller' | 'has_balance' | 'banned';

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
  const [confirm, confirmDialog] = useConfirm();
  const [users, setUsers] = useState<User[] | null>(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [filter, setFilter] = useState<UserFilter>('all');
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(initialUserId);
  const [activeUser, setActiveUser] = useState<User | null>(null);
  const query = useDebounced(search);
  const money = useMoney();

  useEffect(() => {
    setSelectedId(initialUserId);
  }, [initialUserId]);

  const load = useCallback(async () => {
    setLoading(true);
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
    } finally {
      setLoading(false);
    }
  }, [query, offset, filter, say]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleToggleBan = async (user: User) => {
    if (
      !user.is_banned &&
      !(await confirm(
        `Ban ${nameOf(user)}?`,
        'They will lose access to the bot and web features until unbanned.',
        'Ban user'
      ))
    ) {
      return;
    }
    try {
      const res = await api.toggleBan(user.tg_user_id);
      say(res.is_banned ? 'User banned' : 'User unbanned', 'good');
      setUsers((prev) =>
        prev
          ? prev.map((u) => (u.tg_user_id === user.tg_user_id ? { ...u, is_banned: res.is_banned ? 1 : 0 } : u))
          : prev
      );
    } catch (err) {
      say(errorText(err, 'Could not toggle ban'), 'bad');
    }
  };

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
      <section className="panel queue-panel">
        <header>
          <div className="queue-tabs" aria-label="Customer filter">
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
            {summary?.reseller_count ? (
              <button
                type="button"
                className={filter === 'reseller' ? 'active' : ''}
                onClick={() => {
                  setFilter('reseller');
                  setOffset(0);
                }}
              >
                Resellers <span className="count">{summary.reseller_count}</span>
              </button>
            ) : null}
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

          <div className="filters">
            <input
              type="search"
              aria-label="Search users"
              placeholder="Search name, @username or ID…"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
            <button
              type="button"
              className="btn ghost small"
              onClick={() => void load()}
              disabled={loading}
              aria-label="Refresh users"
            >
              <RefreshCw size={14} className={loading ? 'refreshing' : ''} />
            </button>
          </div>
        </header>

        <div className="app-list-heading"><span>{total} {total === 1 ? 'customer' : 'customers'}</span><span>Wallet balance</span></div>
        <ul className="app-record-list customer-feed" aria-label="Customers" aria-busy={loading}>
          {(users ?? []).map(user => (
            <li key={user.id}>
              <MobileRecord
                title={nameOf(user)}
                subtitle={user.username ? `@${user.username}` : `ID ${user.tg_user_id}`}
                meta={`Joined ${when(user.created_at)}`}
                amount={money(user.balance)}
                status={user.is_banned ? 'Banned' : user.rank === 'Reseller' ? 'Reseller' : 'Active'}
                tone={user.is_banned ? 'bad' : 'good'}
                icon={<UserCheck size={20} />}
                label={`View customer ${nameOf(user)}`}
                onOpen={() => openProfile(user)}
              />
            </li>
          ))}
          {!users || !users.length ? <li className="app-list-empty">{loading ? 'Loading customers…' : 'No customers match your search.'}</li> : null}
        </ul>
        <div className="scroll desktop-record-scroll" tabIndex={0} role="region" aria-label="Users table">
          <table className="record-directory users-directory">
            <thead>
              <tr>
                <th>Customer</th>
                <th>User ID</th>
                <th>Wallet Balance</th>
                <th>Status</th>
                <th>Joined</th>
                <th className="right" aria-label="Actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(users ?? []).map((user) => (
                  <tr key={user.id}>
                    <td data-label="Customer">
                      <div className="overview-customer">
                        <button
                          type="button"
                          className="record-link"
                          onClick={() => openProfile(user)}
                          title={`View ${nameOf(user)}`}
                        >
                          {nameOf(user)}
                        </button>
                      </div>
                    </td>
                    <td data-label="User ID">
                      <code style={{ fontSize: '12px' }}>{user.tg_user_id}</code>
                    </td>
                    <td data-label="Wallet Balance">
                      <strong className="money">{money(user.balance)}</strong>
                    </td>
                    <td data-label="Status">
                      {user.is_banned ? (
                        <span className="pill bad">Banned</span>
                      ) : user.rank === 'Reseller' ? (
                        <span className="pill info">Reseller</span>
                      ) : (
                        <span className="pill good">Active</span>
                      )}
                    </td>
                    <td className="overview-delivery" data-label="Joined">
                      {when(user.created_at)}
                    </td>
                    <td className="right" data-label="Actions">
                      <div className="row-actions" style={{ justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="btn ghost small"
                          onClick={() => openProfile(user)}
                          title="View profile"
                        >
                          <Eye size={13} /> View profile
                        </button>
                        <button
                          type="button"
                          className={`btn ghost small ${user.is_banned ? '' : 'danger'}`}
                          onClick={() => void handleToggleBan(user)}
                          style={{ color: user.is_banned ? 'var(--positive)' : 'var(--danger)' }}
                          title={user.is_banned ? 'Unban user' : 'Ban user'}
                        >
                          <Ban size={13} /> {user.is_banned ? 'Unban' : 'Ban'}
                        </button>
                      </div>
                    </td>
                  </tr>
              ))}
              {users && users.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                    {loading ? 'Searching users…' : 'No customers match the criteria.'}
                  </td>
                </tr>
              ) : null}
              {!users ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                    Loading customers…
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
      </section>
      {confirmDialog}
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
  const [resellerKey, setResellerKey] = useState<ResellerKeyInfo | null>(null);
  const [resellerStats, setResellerStats] = useState<ResellerStats | null>(null);
  const [apiBusy, setApiBusy] = useState(false);
  const [newlyGeneratedKey, setNewlyGeneratedKey] = useState<string | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  // Load user data if not passed or when userId changes
  useEffect(() => {
    let mounted = true;
    if (!initialUser || initialUser.tg_user_id !== userId) {
      setLoading(true);
    }
    api
      .user(userId)
      .then((res) => {
        if (mounted && res.user) {
          setUser(res.user);
          setCurrentRank(res.user.rank || 'Standard');
          setResellerKey(res.reseller_key ?? null);
          setResellerStats(res.reseller_stats ?? null);
        }
      })
      .catch((err) => {
        if (mounted) say(errorText(err), 'bad');
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
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

  async function handleToggleResellerKey() {
    if (!user || !resellerKey) return;
    const willEnable = !resellerKey.is_active;
    const title = willEnable ? `Enable API access for ${nameOf(user)}?` : `Disable API access for ${nameOf(user)}?`;
    const message = willEnable
      ? 'The customer will immediately be able to make programmatic requests using their existing API key.'
      : 'Any automated requests made with their API key will be immediately rejected with an authorization error.';
    const confirmLabel = willEnable ? 'Enable API Key' : 'Disable API Key';

    const ok = await confirm(title, message, confirmLabel, !willEnable);
    if (!ok) return;

    setApiBusy(true);
    try {
      const res = await api.toggleResellerKey(user.tg_user_id);
      setResellerKey(res.reseller_key);
      say(`Reseller API key ${res.reseller_key.is_active ? 'enabled' : 'disabled'}.`);
      onUserUpdated({
        ...user,
        api_key_active: res.reseller_key.is_active,
        api_key_prefix: res.reseller_key.key_prefix,
      });
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setApiBusy(false);
    }
  }

  async function handleGenerateResellerKey() {
    if (!user) return;
    const isRotating = Boolean(resellerKey);
    const title = isRotating
      ? `Regenerate API Key for ${nameOf(user)}?`
      : `Generate Reseller API Key for ${nameOf(user)}?`;
    const message = isRotating
      ? 'Their current API key will be permanently invalidated and stopped immediately. Make sure to copy and provide them with the new key.'
      : `An API key will be generated for ${nameOf(user)}. If their account is not already a Reseller, it will be promoted to Reseller.`;
    const confirmLabel = isRotating ? 'Regenerate Key' : 'Generate Key';

    const ok = await confirm(title, message, confirmLabel, isRotating);
    if (!ok) return;

    setApiBusy(true);
    try {
      const res = await api.generateResellerKey(user.tg_user_id);
      setResellerKey(res.reseller_key);
      setNewlyGeneratedKey(res.raw_key);
      say('New Reseller API key generated successfully!');
      if (currentRank !== 'Reseller') {
        setCurrentRank('Reseller');
      }
      onUserUpdated({
        ...user,
        rank: 'Reseller',
        api_key_active: res.reseller_key.is_active,
        api_key_prefix: res.reseller_key.key_prefix,
      });
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setApiBusy(false);
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
          <div className="cust-hero-details">
            <div className="cust-hero-title-row">
              <h2 className="cust-hero-title">{nameOf(user)}</h2>
              <span className={`pill ${user.is_banned ? 'bad' : 'good'}`}>
                {user.is_banned ? 'Banned' : 'Active'}
              </span>
              {user.rank === 'Reseller' ? (
                <span className="pill cust-reseller-pill">Reseller</span>
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
            className={`btn small ghost ${user.is_banned ? '' : 'danger'} cust-hero-btn`}
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
          </div>
          <div className="cust-metric-val green">{money(user.balance)}</div>
        </div>

        <div className="cust-metric-card">
          <div className="cust-metric-top">
            <span className="cust-metric-label">Total Spent</span>
          </div>
          <div className="cust-metric-val">{money(user.total_spent)}</div>
        </div>

        <div className="cust-metric-card">
          <div className="cust-metric-top">
            <span className="cust-metric-label">Total Orders</span>
          </div>
          <div className="cust-metric-val">{orderTotal}</div>
        </div>

        <div className={`cust-metric-card cust-tier-card ${currentRank === 'Reseller' ? 'reseller-card' : ''}`}>
          <div className="cust-metric-top">
            <span className="cust-metric-label">Account Tier</span>
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

      {/* Reseller API Gateway & Usage Card */}
      {(currentRank === 'Reseller' || Boolean(resellerKey)) && (
        <div className="panel cust-reseller-panel">
          <header className="cust-panel-head">
            <div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <h3 style={{ margin: 0 }}>Reseller API & Usage</h3>
                  {resellerKey ? (
                    resellerKey.is_active ? (
                      <span className="pill good">API Active</span>
                    ) : (
                      <span className="pill bad">API Disabled</span>
                    )
                  ) : (
                    <span className="pill" style={{ opacity: 0.7 }}>No Key Generated</span>
                  )}
                </div>
                <p className="cust-panel-desc" style={{ margin: '4px 0 0 0' }}>
                  Programmatic wholesale purchasing and inventory integration via REST API.
                </p>
              </div>
            </div>

            <div className="cust-reseller-head-actions">
              <a
                href="/api/v1/reseller/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="btn small ghost"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                title="View interactive API Documentation"
              >
                <ExternalLink size={13} />
                <span>API Documentation</span>
              </a>

              {resellerKey ? (
                <button
                  type="button"
                  className={`btn small ${resellerKey.is_active ? 'danger' : 'cust-action-save-add'}`}
                  disabled={apiBusy}
                  onClick={() => void handleToggleResellerKey()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <Power size={13} />
                  <span>{resellerKey.is_active ? 'Disable API Access' : 'Enable API Access'}</span>
                </button>
              ) : null}

              <button
                type="button"
                className="btn small"
                disabled={apiBusy}
                onClick={() => void handleGenerateResellerKey()}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
              >
                <RefreshCw size={13} className={apiBusy ? 'spin' : ''} />
                <span>{resellerKey ? 'Regenerate Key' : 'Generate API Key'}</span>
              </button>
            </div>
          </header>

          <div className="cust-panel-body">
            {newlyGeneratedKey && (
              <div className="cust-new-key-alert">
                <div className="cust-new-key-header">
                  <strong>Newly Generated API Key (Copy Now)</strong>
                  <p>This full key will not be shown again. Share this securely with the reseller.</p>
                </div>
                <div className="cust-new-key-row">
                  <code>{newlyGeneratedKey}</code>
                  <button
                    type="button"
                    className="btn small"
                    onClick={() => {
                      void navigator.clipboard.writeText(newlyGeneratedKey);
                      say('Copied API Key to clipboard.');
                    }}
                  >
                    <Copy size={13} /> Copy Key
                  </button>
                </div>
              </div>
            )}

            <div className="cust-reseller-stats-grid">
              <div className="cust-reseller-stat-box">
                <span className="label">Key Identifier</span>
                <span className="val monospace">
                  {resellerKey ? resellerKey.key_prefix : '—'}
                </span>
                <span className="sub">
                  {resellerKey ? `Name: ${resellerKey.name}` : 'No key generated yet'}
                </span>
              </div>

              <div className="cust-reseller-stat-box">
                <span className="label">Last Activity (Usage)</span>
                <span className="val">
                  {resellerKey?.last_used_at ? when(resellerKey.last_used_at) : 'Never used'}
                </span>
                <span className="sub">
                  {resellerKey?.last_used_at
                    ? new Date(resellerKey.last_used_at).toLocaleString()
                    : 'Awaiting first API request'}
                </span>
              </div>

              <div className="cust-reseller-stat-box">
                <span className="label">API Orders</span>
                <span className="val">{resellerStats?.total_orders ?? 0}</span>
                <span className="sub">Completed via API / Bot</span>
              </div>

              <div className="cust-reseller-stat-box">
                <span className="label">API Volume</span>
                <span className="val green">{money(resellerStats?.total_spent ?? 0)}</span>
                <span className="sub">Total volume spent</span>
              </div>
            </div>

            <div className="cust-reseller-quick-guide">
              <div className="cust-guide-item">
                <span className="cust-guide-tag">Endpoint</span>
                <code>/api/v1/reseller</code>
              </div>
              <div className="cust-guide-item">
                <span className="cust-guide-tag">Header</span>
                <code>X-API-Key: {resellerKey?.key_prefix ?? 'rk_live_...'}</code>
              </div>
              <div className="cust-guide-item">
                <span className="cust-guide-tag">Rate Limits</span>
                <span>120 req/min (Read), 30 req/min (Purchase)</span>
              </div>
            </div>
          </div>
        </div>
      )}

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
                <p>No orders placed by this customer yet.</p>
              </div>
            ) : (
              <>
              <ul className="app-record-list customer-order-feed" aria-label="Customer orders">
                {orders.map(order => {
                  const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
                  return <li key={order.id}><MobileRecord title={order.product_title || `Order O${order.id}`} subtitle={`O${order.id} · ${when(order.created_at)}`} amount={money(order.price)} status={waiting ? 'To deliver' : order.status} tone={waiting ? 'warn' : tone(order.status) || 'neutral'} label={`Open order O${order.id}`} onOpen={() => { window.location.hash = `orders/${order.id}`; }} /></li>;
                })}
              </ul>
              <div className="cust-orders-scrollable desktop-customer-orders">
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
                            Order O{order.id} · {when(order.created_at)}
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
              </>
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
              <div className="tier-item-row"><strong>Normal</strong></div>
              <small>Standard customer pricing</small>
            </div>
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
              <div className="tier-item-row"><strong>Reseller</strong></div>
              <small>Discounted reseller prices in Bot</small>
            </div>
          </button>
        </div>
      ) : null}
    </div>
  );
}
