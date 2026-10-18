'use client';

import { api } from '@/lib/api';
import { errorText, FlagRow, type Say } from './ui';

interface AdminNotificationsProps {
  say: Say;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
  flip: (key: string, on: boolean, label?: string) => Promise<void>;
  confirm?: (title: string, message: string, confirmLabel?: string, isDanger?: boolean) => Promise<boolean>;
}

export function AdminNotifications({ say, values, setValues, setSaved, flip, confirm }: AdminNotificationsProps) {
  const isOn = (key: string, def = '1') => (values[key] ?? def) === '1';
  const channel = values.announcement_channel?.trim();

  async function confirmAndFlip(key: string, next: boolean, label: string) {
    if (confirm) {
      const action = next ? 'Enable' : 'Disable';
      const ok = await confirm(
        `${action} ${label}?`,
        next ? `You will now receive alerts for ${label}.` : `Alerts for ${label} will be turned off.`,
        action,
        !next
      );
      if (!ok) return;
    }
    await flip(key, next, label);
  }

  return (
    <>
      {/* ── 1. Public Channel Auto-Posts (TOP) ─────────────────── */}
      <div className="panel-subhead" style={{ borderTop: 0 }}>
        <div>
          <h3>
            <span>Channel posts</span>
          </h3>
          <p>
            {channel ? <code style={{ wordBreak: 'break-all' }}>{channel}</code> : <a href="#settings/channels">Set channel</a>}
          </p>
        </div>
      </div>

      <div className="rows">
        <FlagRow
          label="Restocks"
          on={isOn('auto_restock_alerts', '1')}
          onChange={(next) => void confirmAndFlip('auto_restock_alerts', next, 'Restock posts')}
        />

        <FlagRow
          label="Price drops"
          on={isOn('auto_price_drop_alerts', '1')}
          onChange={(next) => void confirmAndFlip('auto_price_drop_alerts', next, 'Price drop posts')}
        />
      </div>

      {/* ── 2. Admin Operational & Security Alerts ─────────────── */}
      <div className="panel-subhead notif-section-head">
        <div>
          <h3>
            <span>Admin alerts</span>
          </h3>
        </div>
      </div>

      <div className="rows">
        {/* TOGGLABLE (ON/OFF) FIRST */}

        <FlagRow
          label="Automatic deliveries"
          on={isOn('notify_admin_orders', '0')}
          onChange={(next) => void confirmAndFlip('notify_admin_orders', next, 'Automatic deliveries')}
        />

        <FlagRow
          label="Auto deposits"
          on={isOn('notify_admin_payments', '0')}
          onChange={(next) => void confirmAndFlip('notify_admin_payments', next, 'Automatic Gateway Deposits')}
        />

        <FlagRow
          label="Restocks"
          on={isOn('notify_admin_restock', '1')}
          onChange={(next) => void confirmAndFlip('notify_admin_restock', next, 'Stock Restock Alerts')}
        />

        <FlagRow
          label="Low stock"
          hint="Includes out of stock."
          on={isOn('notify_admin_low_stock', '1')}
          onChange={(next) => void confirmAndFlip('notify_admin_low_stock', next, 'Low Stock Alerts')}
        />
        {isOn('notify_admin_low_stock', '1') && (
          <div className="low-stock-threshold">
            <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
              Threshold (items)
            </span>
            <div role="group" aria-label="Low stock threshold">
              {['1', '2', '3', '5', '10'].map((num) => {
                const active = (values.low_stock_threshold || '3') === num;
                return (
                  <button
                    key={num}
                    type="button"
                    className={`button compact ${active ? 'primary' : 'ghost'}`}
                    aria-pressed={active}
                    style={{
                      padding: '2px 10px',
                      fontSize: '12px',
                      minHeight: '44px',
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
                    {num}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <FlagRow
          label="Price changes"
          on={isOn('notify_admin_price_change', '1')}
          onChange={(next) => void confirmAndFlip('notify_admin_price_change', next, 'Price Change Alerts')}
        />

        <FlagRow
          label="New customers"
          on={isOn('notify_admin_new_user', '0')}
          onChange={(next) => void confirmAndFlip('notify_admin_new_user', next, 'New Customers Alert')}
        />

        <details className="notification-details">
          <summary>System &amp; security</summary>
        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Delivery Orders</strong>
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge danger">Always on</span>
            </div>
            <p className="mandatory-desc">
              Critical alerts when payment verification gateways (Binance Pay, ZiniPay) fail or timeout.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Group invites</strong>
              <span className="mandatory-badge neutral">Auto leave</span>
            </div>
            <p className="mandatory-desc">
              When added to a Telegram group, the bot silently leaves immediately to prevent data leakage without sending spam alerts to admin inboxes.
            </p>
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Unapproved channels</strong>
              <span className="mandatory-badge neutral">Auto leave</span>
            </div>
            <p className="mandatory-desc">
              When added to an unconfigured channel, the bot silently leaves immediately to protect broadcasting without sending spam alerts to admin inboxes.
            </p>
          </div>
        </div>
        </details>
      </div>

      {/* ── 3. Customer Notifications ──────────────────────────── */}
      <div className="panel-subhead notif-section-head">
        <div>
          <h3>
            <span>Customer notifications</span>
          </h3>
        </div>
      </div>

      <div className="rows">
        {/* TOGGLABLE (ON/OFF) FIRST */}

        <FlagRow
          label="Referral rewards"
          on={isOn('notify_user_referral', '1')}
          onChange={(next) => void flip('notify_user_referral', next, 'Referral Bonus Alerts')}
        />

        <details className="notification-details">
          <summary>Customer receipts <span>Always on</span></summary>
        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Order Delivery &amp; Credentials</strong>
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge warn">Always on</span>
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
              <span className="mandatory-badge warn">Always on</span>
            </div>
            <p className="mandatory-desc">
              Instant notification and wallet refund receipt sent to customer when an order is refunded.
            </p>
          </div>
        </div>
        </details>
      </div>
    </>
  );
}
