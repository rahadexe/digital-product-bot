'use client';

import { Bell, Lock, Megaphone, ShieldAlert, Users } from 'lucide-react';
import { api } from '@/lib/api';
import { errorText, FlagRow, type Say } from './ui';

interface AdminNotificationsProps {
  say: Say;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
  flip: (key: string, on: boolean) => Promise<void>;
}

export function AdminNotifications({ say, values, setValues, setSaved, flip }: AdminNotificationsProps) {
  const isOn = (key: string, def = '1') => (values[key] ?? def) === '1';
  const channel = values.announcement_channel?.trim();

  return (
    <>
      {/* ── 1. Public Channel Auto-Posts (TOP) ─────────────────── */}
      <div className="panel-subhead" style={{ borderTop: 0 }}>
        <div>
          <h3>
            <Megaphone size={15} style={{ color: '#0ea5e9', flexShrink: 0 }} />
            <span>Public channel announcements</span>
          </h3>
          <p>
            Automated marketing posts dispatched to your Telegram announcement channels ({channel ? <code style={{ wordBreak: 'break-all' }}>{channel}</code> : 'configured in Channels tab'}).
          </p>
        </div>
      </div>

      <div className="rows">
        <FlagRow
          label="Auto-post on Restock"
          hint="Automatically posts an announcement with a 1-click Buy button to your channels whenever stock is added"
          on={isOn('auto_restock_alerts', '1')}
          onChange={(next) => void flip('auto_restock_alerts', next)}
        />

        <FlagRow
          label="Auto-post on Price Drop"
          hint="Automatically posts discount announcements to your channels when a product price is reduced"
          on={isOn('auto_price_drop_alerts', '1')}
          onChange={(next) => void flip('auto_price_drop_alerts', next)}
        />
      </div>

      {/* ── 2. Admin Operational & Security Alerts ─────────────── */}
      <div className="panel-subhead notif-section-head">
        <div>
          <h3>
            <Bell size={15} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            <span>Admin alert preferences</span>
          </h3>
          <p>
            Notifications dispatched directly to the Telegram accounts configured under &ldquo;Who runs this shop&rdquo;.
          </p>
        </div>
      </div>

      <div className="rows">
        {/* TOGGLABLE (ON/OFF) FIRST */}
        <div className="notif-divider">
          <span>Configurable Alerts (Toggle on/off)</span>
        </div>

        <FlagRow
          label="Instant Stock Purchases"
          hint="Alert when an order is automatically delivered from inventory stock"
          on={isOn('notify_admin_orders', '0')}
          onChange={(next) => void flip('notify_admin_orders', next)}
        />

        <FlagRow
          label="Automatic Gateway Deposits"
          hint="Alert when an automated deposit is verified and credited via Binance Pay or ZiniPay"
          on={isOn('notify_admin_payments', '0')}
          onChange={(next) => void flip('notify_admin_payments', next)}
        />

        <FlagRow
          label="Stock Restock Alerts"
          hint="Alert when new items or accounts are added to inventory stock"
          on={isOn('notify_admin_restock', '1')}
          onChange={(next) => void flip('notify_admin_restock', next)}
        />

        <FlagRow
          label="Low Stock &amp; Out of Stock Alerts"
          hint={`Immediate Telegram alert when stock falls to ${values.low_stock_threshold || '3'} items or fewer, or becomes completely sold out`}
          on={isOn('notify_admin_low_stock', '1')}
          onChange={(next) => void flip('notify_admin_low_stock', next)}
        />
        {isOn('notify_admin_low_stock', '1') && (
          <div style={{ padding: '8px 16px 14px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
              Alert threshold:
            </span>
            <div style={{ display: 'inline-flex', gap: '6px' }}>
              {['1', '2', '3', '5', '10'].map((num) => {
                const active = (values.low_stock_threshold || '3') === num;
                return (
                  <button
                    key={num}
                    type="button"
                    className={`button compact ${active ? 'primary' : 'ghost'}`}
                    style={{
                      padding: '2px 10px',
                      fontSize: '12px',
                      minHeight: '26px',
                      borderRadius: '6px',
                      border: active ? '1px solid var(--accent)' : '1px solid var(--border)',
                      background: active ? 'var(--accent)' : 'transparent',
                      color: active ? '#fff' : 'inherit',
                      fontWeight: active ? 600 : 400,
                      cursor: 'pointer',
                    }}
                    onClick={async () => {
                      setValues((c) => ({ ...c, low_stock_threshold: num }));
                      try {
                        await api.updateSettings({ low_stock_threshold: num });
                        setSaved((c) => ({ ...(c ?? {}), low_stock_threshold: num }));
                        say(`Low stock threshold set to ${num}.`);
                      } catch (err) {
                        say(errorText(err, 'Failed to update threshold'), 'bad');
                      }
                    }}
                  >
                    {num} {num === '3' ? '(Default)' : ''}
                  </button>
                );
              })}
            </div>
            <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
              items remaining
            </span>
          </div>
        )}

        <FlagRow
          label="Price Change Alerts (Drop &amp; Up)"
          hint="Alert when catalog prices are modified"
          on={isOn('notify_admin_price_change', '1')}
          onChange={(next) => void flip('notify_admin_price_change', next)}
        />

        <FlagRow
          label="New customers"
          hint="Alert when a new Telegram user starts the bot and creates an account"
          on={isOn('notify_admin_new_user', '0')}
          onChange={(next) => void flip('notify_admin_new_user', next)}
        />

        {/* REQUIRED / ALWAYS ON SYSTEM ALERTS */}
        <div className="notif-divider required" style={{ marginTop: '10px' }}>
          <span>Required System &amp; Security Alerts</span>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Delivery Orders</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Immediate alert when a customer orders a manual-delivery product requiring admin fulfillment.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Deposit Requests</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Immediate alert with Approve &amp; Reject buttons when a customer submits a manual bKash / Nagad / Rocket transaction receipt for admin verification.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Payment &amp; gateway errors</strong>
              <span className="mandatory-badge danger" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · CRITICAL
              </span>
            </div>
            <p className="mandatory-desc">
              Critical alerts when payment verification gateways (Binance Pay, ZiniPay) fail or timeout.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Security: Group Invites Auto-Blocked</strong>
              <span className="mandatory-badge neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <ShieldAlert size={10} /> ALWAYS OFF · AUTO-LEAVE
              </span>
            </div>
            <p className="mandatory-desc">
              When added to a Telegram group, the bot silently leaves immediately to prevent data leakage without sending spam alerts to admin inboxes.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Security: Unauthorized Channels Auto-Blocked</strong>
              <span className="mandatory-badge neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <ShieldAlert size={10} /> ALWAYS OFF · AUTO-LEAVE
              </span>
            </div>
            <p className="mandatory-desc">
              When added to an unconfigured channel, the bot silently leaves immediately to protect broadcasting without sending spam alerts to admin inboxes.
            </p>
          </div>
        </div>
      </div>

      {/* ── 3. Customer Notifications ──────────────────────────── */}
      <div className="panel-subhead notif-section-head">
        <div>
          <h3>
            <Users size={15} style={{ color: 'var(--positive)', flexShrink: 0 }} />
            <span>Customer notifications</span>
          </h3>
          <p>
            Direct Telegram messages sent to customers for orders, wallet updates, and referral bonuses.
          </p>
        </div>
      </div>

      <div className="rows">
        {/* TOGGLABLE (ON/OFF) FIRST */}
        <div className="notif-divider">
          <span>Configurable Customer Alerts</span>
        </div>

        <FlagRow
          label="Referral Bonus Alerts"
          hint="Notify referrer when an invited friend joins and a referral bonus is credited"
          on={isOn('notify_user_referral', '1')}
          onChange={(next) => void flip('notify_user_referral', next)}
        />

        {/* ALWAYS ON (MANDATORY) BELOW - NO BUTTON */}
        <div className="notif-divider required" style={{ marginTop: '10px' }}>
          <span>Required Customer Deliveries &amp; Receipts</span>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Order Delivery &amp; Credentials</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Sends product credentials, license keys, or accounts immediately upon order completion.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Order Acknowledgment</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Sends an immediate confirmation that payment was received and manual order is in queue.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Deposit Approved &amp; Balance Credited</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Sends wallet credit confirmation and updated balance when a deposit succeeds.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Deposit Rejected Notification</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Sends an explanation notice if an invalid TrxID or unverified deposit is rejected.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Balance Adjustments</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Receipt sent to customer when admin adjusts their balance directly from the Customers tab.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Order Refund Notification</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> REQUIRED · ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Instant notification and wallet refund receipt sent to customer when an order is refunded.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
