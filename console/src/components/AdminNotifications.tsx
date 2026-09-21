'use client';

import { Bell, HelpCircle, Lock } from 'lucide-react';
import { FlagRow, Switch, type Say } from './ui';

interface AdminNotificationsProps {
  say: Say;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
  flip: (key: string, on: boolean) => Promise<void>;
}

export function AdminNotifications({ say, values, setValues, setSaved, flip }: AdminNotificationsProps) {
  const isOn = (key: string, def = '1') => (values[key] ?? def) === '1';

  return (
    <>
      {/* SUB-SECTION: Operational Alerts & Notification Rules */}
      <div className="panel-subhead">
        <div>
          <h3>
            <Bell size={15} style={{ color: 'var(--positive)', flexShrink: 0 }} />
            <span>Notification preferences</span>
          </h3>
        </div>
      </div>

      <div className="rows">
        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Manual Delivery Orders</strong>
              <span className="mandatory-badge warn">ALWAYS ON</span>
            </div>
          </div>
          <div className="mandatory-switch" title="Always active. Cannot be disabled.">
            <Switch label="Manual Delivery Orders" on={true} disabled={true} onChange={() => {}} />
          </div>
        </div>

        <div className="mandatory-row">
          <div className="mandatory-info">
            <div className="mandatory-title-row">
              <strong>Payment &amp; gateway errors</strong>
              <span className="mandatory-badge danger">ALWAYS ON</span>
            </div>
          </div>
          <div className="mandatory-switch" title="Always active. Cannot be disabled.">
            <Switch label="Payment Errors" on={true} disabled={true} onChange={() => {}} />
          </div>
        </div>

        <FlagRow
          label="Instant Stock Purchases"
          on={isOn('notify_admin_orders', '1')}
          onChange={(next) => void flip('notify_admin_orders', next)}
        />

        <FlagRow
          label="Manual Deposit Requests"
          on={isOn('notify_admin_deposits', '1')}
          onChange={(next) => void flip('notify_admin_deposits', next)}
        />

        <FlagRow
          label="Automatic Gateway Deposits"
          on={isOn('notify_admin_payments', '1')}
          onChange={(next) => void flip('notify_admin_payments', next)}
        />

        <FlagRow
          label="Stock updates"
          on={isOn('notify_admin_restock', '1')}
          onChange={(next) => void flip('notify_admin_restock', next)}
        />

        <FlagRow
          label="Price Change Alerts (Drop & Up)"
          on={isOn('notify_admin_price_change', '1')}
          onChange={(next) => void flip('notify_admin_price_change', next)}
        />

        <FlagRow
          label="New customers"
          on={isOn('notify_admin_new_user', '0')}
          onChange={(next) => void flip('notify_admin_new_user', next)}
        />
      </div>
    </>
  );
}
