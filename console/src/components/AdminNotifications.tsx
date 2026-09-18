'use client';

import { useState } from 'react';
import { Bell, CheckCircle, HelpCircle, Lock, Plus, Send, ShieldAlert, Trash2, UserCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { FlagRow, Switch, errorText, type Say } from './ui';

interface AdminNotificationsProps {
  say: Say;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
  flip: (key: string, on: boolean) => Promise<void>;
}

export function AdminNotifications({ say, values, setValues, setSaved, flip }: AdminNotificationsProps) {
  const [newAdminId, setNewAdminId] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    delivered_count: number;
    total_admins: number;
    message?: string;
    results: { chat_id: number; delivered: boolean; error?: string | null }[];
  } | null>(null);

  // Parse admin IDs from admin_tg_ids, falling back to admin_tg_id
  const rawAdminIds = values.admin_tg_ids || values.admin_tg_id || '';
  const adminIds = Array.from(
    new Set(
      rawAdminIds
        .split(/[\s,;]+/)
        .map((s) => s.trim())
        .filter((s) => /^\d{5,20}$/.test(s))
    )
  );

  async function updateAdminIds(nextIds: string[]) {
    const formatted = nextIds.join(', ');
    const primaryId = nextIds[0] || '0';
    setValues((prev) => ({
      ...prev,
      admin_tg_ids: formatted,
      admin_tg_id: primaryId,
    }));
    try {
      await api.updateSettings({
        admin_tg_ids: formatted,
        admin_tg_id: primaryId,
      });
      setSaved((prev) => ({
        ...(prev ?? {}),
        admin_tg_ids: formatted,
        admin_tg_id: primaryId,
      }));
      say('Admin recipients updated.');
    } catch (cause) {
      say(errorText(cause, 'Could not save admin IDs.'), 'bad');
    }
  }

  function handleAddAdmin(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const cleaned = newAdminId.trim();
    if (!cleaned) return;

    // Support entering one ID or comma-separated IDs
    const parts = cleaned.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    const validParts = parts.filter((s) => /^\d{5,20}$/.test(s));

    if (validParts.length === 0) {
      say('Please enter a valid numeric Telegram ID (usually 8-12 digits).', 'bad');
      return;
    }

    const next = Array.from(new Set([...adminIds, ...validParts]));
    void updateAdminIds(next);
    setNewAdminId('');
    setIsAdding(false);
  }

  function handleRemoveAdmin(idToRemove: string) {
    if (adminIds.length <= 1) {
      if (!confirm('This is the only configured admin ID. If you remove it, no one will receive alerts. Remove anyway?')) {
        return;
      }
    }
    const next = adminIds.filter((id) => id !== idToRemove);
    void updateAdminIds(next);
  }

  async function handleSendTestAlert() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testAdminNotification();
      setTestResult(res);
      if (res.success) {
        say(`Test alert sent! Delivered to ${res.delivered_count} of ${res.total_admins} admin(s).`);
      } else {
        say(res.message || 'Could not deliver test notification.', 'bad');
      }
    } catch (cause) {
      say(errorText(cause, 'Failed to send test alert.'), 'bad');
    } finally {
      setTesting(false);
    }
  }

  const isOn = (key: string, def = '1') => (values[key] ?? def) === '1';

  return (
    <div className="admin-notifications-container">
      {/* PANEL 1: Admin Recipients */}
      <section className="panel">
        <header>
          <div>
            <h2>Admin Telegram Recipients</h2>
            <p>Every operational alert will be broadcast concurrently to all configured admin Telegram accounts.</p>
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn small ghost"
              disabled={testing || adminIds.length === 0}
              onClick={handleSendTestAlert}
              title="Sends a test ping to all admins to verify delivery"
            >
              <Send size={14} style={{ marginRight: 6 }} />
              {testing ? 'Sending…' : 'Send Test Alert'}
            </button>
          </div>
        </header>

        <div className="panel-body">
          {testResult && (
            <div className={`admin-test-result ${testResult.success ? 'success' : 'error'}`}>
              <div className="admin-test-result-header">
                {testResult.success ? <CheckCircle size={16} /> : <ShieldAlert size={16} />}
                <span>
                  {testResult.success
                    ? `Delivered to ${testResult.delivered_count} of ${testResult.total_admins} admin Telegram accounts!`
                    : testResult.message || 'Delivery failed for all admins.'}
                </span>
              </div>
              {testResult.results.some((r) => !r.delivered) && (
                <ul style={{ marginTop: 8, paddingLeft: 20, color: 'var(--muted)', fontSize: '0.8rem' }}>
                  {testResult.results
                    .filter((r) => !r.delivered)
                    .map((r) => (
                      <li key={r.chat_id}>
                        UID <code>{r.chat_id}</code>: {r.error || 'Failed to deliver message'}
                      </li>
                    ))}
                </ul>
              )}
            </div>
          )}

          <div className="admin-ids-list" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {adminIds.length === 0 ? (
              <div className="empty-state" style={{ padding: '20px 0', textAlign: 'center', color: 'var(--muted)' }}>
                No admin Telegram IDs configured. Click &quot;Add Admin ID&quot; below to add your ID.
              </div>
            ) : (
              <div className="admin-chips-wrap">
                {adminIds.map((id, index) => (
                  <div key={id} className="admin-chip">
                    <UserCheck size={16} style={{ color: index === 0 ? 'var(--positive)' : 'var(--muted)', flexShrink: 0 }} />
                    <span className="admin-chip-id">{id}</span>
                    <span className={`admin-chip-badge ${index === 0 ? 'primary' : 'coadmin'}`}>
                      {index === 0 ? 'Primary' : 'Co-Admin'}
                    </span>
                    <button
                      type="button"
                      className="admin-chip-remove"
                      onClick={() => handleRemoveAdmin(id)}
                      title="Remove admin recipient"
                      aria-label={`Remove admin ${id}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {isAdding ? (
              <form onSubmit={handleAddAdmin} className="admin-add-form">
                <input
                  type="text"
                  autoFocus
                  placeholder="Enter Telegram User ID (e.g. 6775546602)"
                  value={newAdminId}
                  onChange={(e) => setNewAdminId(e.target.value)}
                />
                <div className="admin-add-form-actions">
                  <button type="submit" className="btn small">
                    Add
                  </button>
                  <button
                    type="button"
                    className="btn small ghost"
                    onClick={() => {
                      setIsAdding(false);
                      setNewAdminId('');
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div style={{ marginTop: 8 }}>
                <button
                  type="button"
                  className="btn small ghost"
                  onClick={() => setIsAdding(true)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <Plus size={14} />
                  Add Admin ID
                </button>
              </div>
            )}
          </div>

          <div className="admin-help-box">
            <HelpCircle size={16} />
            <div>
              <b>How to find your Telegram ID?</b> Open Telegram, message{' '}
              <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer">
                @userinfobot
              </a>{' '}
              or{' '}
              <a href="https://t.me/raw_data_bot" target="_blank" rel="noreferrer">
                @raw_data_bot
              </a>
              , and send <code>/start</code>. Copy the numeric <b>Id</b>.
              <br />
              <i>Note: The admin must have clicked &quot;Start&quot; on your store bot at least once so Telegram permits the bot to send messages.</i>
            </div>
          </div>
        </div>
      </section>

      {/* PANEL 2: Mandatory Notifications (Locked ON) */}
      <section className="panel">
        <header>
          <div>
            <h2 className="admin-header-title">
              <Lock size={16} style={{ color: '#d97706', flexShrink: 0 }} />
              <span>Mandatory Operational Alerts (Always Active)</span>
            </h2>
            <p>These critical notifications cannot be turned off. They ensure customers never get stuck without fulfillment or financial safety.</p>
          </div>
        </header>

        <div className="rows">
          <div className="mandatory-row">
            <div className="mandatory-info">
              <div className="mandatory-title-row">
                <strong>⏳ Manual Delivery Orders (Waiting Fulfillment)</strong>
                <span className="mandatory-badge warn">MANDATORY · LOCKED ON 🔒</span>
              </div>
              <p className="mandatory-desc">
                Sent instantly when a customer pays for a product marked as &quot;Manual Delivery&quot; or when an order requires manual credentials/fulfillment.
              </p>
            </div>
            <div className="mandatory-switch" title="Always active. Cannot be disabled.">
              <Switch label="Manual Delivery Orders" on={true} disabled={true} onChange={() => {}} />
            </div>
          </div>

          <div className="mandatory-row">
            <div className="mandatory-info">
              <div className="mandatory-title-row">
                <strong>⚠️ Critical Payment &amp; Gateway Errors</strong>
                <span className="mandatory-badge danger">CRITICAL · LOCKED ON 🔒</span>
              </div>
              <p className="mandatory-desc">
                Sent when a payment gateway (ZiniPay/Binance) rejects an invoice, detects an amount mismatch, or experiences a verification failure.
              </p>
            </div>
            <div className="mandatory-switch" title="Always active. Cannot be disabled.">
              <Switch label="Payment Errors" on={true} disabled={true} onChange={() => {}} />
            </div>
          </div>
        </div>
      </section>

      {/* PANEL 3: Configurable Notification Toggles */}
      <section className="panel">
        <header>
          <div>
            <h2 className="admin-header-title">
              <Bell size={16} style={{ color: 'var(--positive)', flexShrink: 0 }} />
              <span>Configurable Notifications</span>
            </h2>
            <p>Toggle optional operational receipts and alerts on or off according to your preference.</p>
          </div>
        </header>

        <div className="rows">
          <FlagRow
            label="🛒 Instant Stock Purchases"
            hint="Alert when a customer successfully buys an automated instant stock item from the catalog."
            on={isOn('notify_admin_orders', '1')}
            onChange={(next) => void flip('notify_admin_orders', next)}
          />

          <FlagRow
            label="🔔 Manual Deposit Requests"
            hint="Alert when a customer submits a manual deposit (TrxID) for review & wallet approval."
            on={isOn('notify_admin_deposits', '1')}
            onChange={(next) => void flip('notify_admin_deposits', next)}
          />

          <FlagRow
            label="💳 Automatic Gateway Deposits"
            hint="Alert when an online gateway (ZiniPay / Binance) successfully auto-credits a customer's wallet."
            on={isOn('notify_admin_payments', '1')}
            onChange={(next) => void flip('notify_admin_payments', next)}
          />

          <FlagRow
            label="📦 Stock Added / Restock"
            hint="Alert when stock units or accounts are added or restocked for a product."
            on={isOn('notify_admin_restock', '1')}
            onChange={(next) => void flip('notify_admin_restock', next)}
          />

          <FlagRow
            label="👤 New Customer Registration"
            hint="Alert when a brand new user starts the Telegram bot for the first time."
            on={isOn('notify_admin_new_user', '0')}
            onChange={(next) => void flip('notify_admin_new_user', next)}
          />
        </div>
      </section>
    </div>
  );
}
