'use client';

import { Bell, Lock, Megaphone, Users } from 'lucide-react';
import { FlagRow, type Say } from './ui';

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
      <div className="panel-subhead">
        <div>
          <h3>
            <Megaphone size={15} style={{ color: '#0ea5e9', flexShrink: 0 }} />
            <span>Public channel announcements</span>
          </h3>
          <p>
            Automated marketing posts dispatched to your Telegram announcement channel ({channel ? <code>{channel}</code> : 'configured in Channels tab'}).
          </p>
        </div>
      </div>

      <div className="rows">
        <FlagRow
          label="Auto-post on Restock"
          hint="Automatically posts an announcement with a 1-click Buy button to your channel whenever stock is added"
          on={isOn('auto_restock_alerts', '1')}
          onChange={(next) => void flip('auto_restock_alerts', next)}
        />

        <FlagRow
          label="Auto-post on Price Drop"
          hint="Automatically posts discount announcements to your channel when a product price is reduced"
          on={isOn('auto_price_drop_alerts', '1')}
          onChange={(next) => void flip('auto_price_drop_alerts', next)}
        />
      </div>

      {/* ── 2. Admin Operational Alerts ────────────────────────── */}
      <div className="panel-subhead" style={{ marginTop: '28px' }}>
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
        <FlagRow
          label="Instant Stock Purchases"
          hint="Alert when an order is automatically delivered from inventory stock"
          on={isOn('notify_admin_orders', '1')}
          onChange={(next) => void flip('notify_admin_orders', next)}
        />

        <FlagRow
          label="Manual Deposit Requests"
          hint="Alert when a customer submits a bKash / Nagad / Rocket transaction receipt"
          on={isOn('notify_admin_deposits', '1')}
          onChange={(next) => void flip('notify_admin_deposits', next)}
        />

        <FlagRow
          label="Automatic Gateway Deposits"
          hint="Alert when an automated deposit is verified and credited via Binance Pay or ZiniPay"
          on={isOn('notify_admin_payments', '1')}
          onChange={(next) => void flip('notify_admin_payments', next)}
        />

        <FlagRow
          label="Stock updates &amp; alerts"
          hint="Alert when items are added to stock, or when a product runs out of stock"
          on={isOn('notify_admin_restock', '1')}
          onChange={(next) => void flip('notify_admin_restock', next)}
        />

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

        {/* ALWAYS ON (MANDATORY) BELOW - NO BUTTON */}
        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Delivery Orders</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> ALWAYS ON
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
              <strong>Payment &amp; gateway errors</strong>
              <span className="mandatory-badge danger" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> ALWAYS ON
              </span>
            </div>
            <p className="mandatory-desc">
              Critical alerts when payment verification gateways (Binance Pay, ZiniPay) fail or timeout.
            </p>
          </div>
        </div>
      </div>

      {/* ── 3. Customer Notifications ──────────────────────────── */}
      <div className="panel-subhead" style={{ marginTop: '28px' }}>
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
        <FlagRow
          label="Referral Bonus Alerts"
          hint="Notify referrer when an invited friend joins and a referral bonus is credited"
          on={isOn('notify_user_referral', '1')}
          onChange={(next) => void flip('notify_user_referral', next)}
        />

        {/* ALWAYS ON (MANDATORY) BELOW - NO BUTTON */}
        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Order Delivery &amp; Credentials</strong>
              <span className="mandatory-badge warn" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <Lock size={10} /> ALWAYS ON
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
                <Lock size={10} /> ALWAYS ON
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
                <Lock size={10} /> ALWAYS ON
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
                <Lock size={10} /> ALWAYS ON
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
                <Lock size={10} /> ALWAYS ON
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
                <Lock size={10} /> ALWAYS ON
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
