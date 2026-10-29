'use client';

import { Fragment, useEffect, useState } from 'react';
import { api, type BinanceStatus, type PaymentsStatus } from '@/lib/api';
import { resetCurrencySymbol } from '@/lib/currency';
import { AdminNotifications } from './AdminNotifications';
import { BotAdmins } from './BotAdmins';
import { GateChannels } from './GateChannels';
import { PaymentMethods } from './PaymentMethods';
import { UpdateChannels } from './UpdateChannels';
import { PageLoading, Switch, errorText, useConfirm, type Say } from './ui';

export type SettingsTab = 'economics' | 'gate' | 'payments' | 'notifications';

const TABS: {
  key: SettingsTab;
  label: string;
  icon: 'sliders' | 'shield' | 'card' | 'bell';
}[] = [
  { key: 'economics', label: 'General', icon: 'sliders' },
  { key: 'gate', label: 'Channels', icon: 'shield' },
  { key: 'payments', label: 'Payments', icon: 'card' },
  { key: 'notifications', label: 'Alerts', icon: 'bell' },
];

const MOVED: Record<string, SettingsTab> = {
  general: 'economics',
  store: 'economics',
  channels: 'gate',
  access: 'gate',
  admins: 'economics',
};

function TabIcon({ icon }: { icon: 'sliders' | 'shield' | 'card' | 'bell' }) {
  if (icon === 'sliders') {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
        <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
        <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
        <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
      </svg>
    );
  }
  if (icon === 'shield') {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    );
  }
  if (icon === 'card') {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect width="20" height="14" x="2" y="5" rx="2" />
        <line x1="2" x2="22" y1="10" y2="10" />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

export function Settings({
  say,
  initialTab,
  onTabChange,
}: {
  say: Say;
  initialTab?: SettingsTab;
  onTabChange?: (tab: SettingsTab) => void;
}) {
  const resolve = (wanted?: string): SettingsTab =>
    TABS.some((item) => item.key === wanted)
      ? (wanted as SettingsTab)
      : MOVED[wanted ?? ''] ?? 'economics';

  const [tab, setTab] = useState<SettingsTab>(resolve(initialTab));
  const [loadError, setLoadError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [saved, setSaved] = useState<Record<string, string> | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [payStatus, setPayStatus] = useState<PaymentsStatus | null>(null);
  const [binance, setBinance] = useState<BinanceStatus | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  useEffect(() => {
    setTab(resolve(initialTab));
  }, [initialTab]);

  useEffect(() => {
    let active = true;
    setLoadError('');
    api
      .settings()
      .then((settings) => {
        if (!active) return;
        setSaved(settings);
        setValues(settings);
      })
      .catch((cause) => {
        if (active) setLoadError(errorText(cause, 'Could not load settings.'));
      });
    void refreshGateways();
    return () => {
      active = false;
    };
  }, [loadAttempt]);

  async function refreshGateways() {
    const [payments, checker] = await Promise.all([
      api.paymentsStatus().catch(() => null),
      api.binanceStatus().catch(() => null),
    ]);
    setPayStatus(payments);
    setBinance(checker);
  }

  const symbol = '৳';

  const isStoreActive = values.store_paused !== '1';
  const isDepositsActive = values.zinipay_enabled === '1' || values.binance_enabled === '1';
  const isReferralActive = values.referral_enabled !== '0';
  const isForceJoinActive = values.force_join_enabled === '1';

  const isLimitsDirty = Boolean(
    saved &&
      ((values.store_name ?? '') !== (saved.store_name ?? '') ||
        (values.max_deposit_limit ?? '') !== (saved.max_deposit_limit ?? '') ||
        (values.referral_reward_amount ?? '') !== (saved.referral_reward_amount ?? '') ||
        (values.usd_rate ?? '') !== (saved.usd_rate ?? '') ||
        (values.maintenance_message ?? '') !== (saved.maintenance_message ?? ''))
  );

  const isSupportDirty = Boolean(
    saved &&
      ((values.support_username ?? '') !== (saved.support_username ?? '') ||
        (values.announcement_channel ?? '') !== (saved.announcement_channel ?? ''))
  );

  const [savingLimits, setSavingLimits] = useState(false);
  const [savingSupport, setSavingSupport] = useState(false);

  const hasUnsaved = isLimitsDirty || isSupportDirty;

  useEffect(() => {
    if (!hasUnsaved) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    const leave = (event: Event) => {
      if (!window.confirm('Discard unsaved settings changes?')) event.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    window.addEventListener('console-leave-settings', leave);
    return () => {
      window.removeEventListener('beforeunload', warn);
      window.removeEventListener('console-leave-settings', leave);
    };
  }, [hasUnsaved]);

  async function flipToggle(key: string, next: boolean, label?: string) {
    const value = next ? '1' : '0';
    const before = values[key];
    setValues((cur) => ({ ...cur, [key]: value }));

    try {
      await api.updateSettings({ [key]: value });
      setSaved((cur) => ({ ...(cur ?? {}), [key]: value }));
      if (label) {
        say(`${label} ${next ? 'activated' : 'deactivated'}.`);
      }
      if (key === 'zinipay_enabled' || key === 'binance_enabled') {
        void refreshGateways();
      }
    } catch (cause) {
      setValues((cur) => ({ ...cur, [key]: before }));
      say(errorText(cause, `Could not change ${label || key}.`), 'bad');
    }
  }

  async function toggleStoreActive(nextActive: boolean) {
    const title = nextActive ? 'Reopen Store?' : 'Pause Store?';
    const message = nextActive
      ? 'Customers will be able to browse and place new orders normally.'
      : 'Customers will be blocked from placing new orders while store is paused.';
    const confirmLabel = nextActive ? 'Reopen Store' : 'Pause Store';
    const ok = await confirm(title, message, confirmLabel, !nextActive);
    if (!ok) return;

    await flipToggle('store_paused', !nextActive, 'Store');
  }

  async function toggleDepositsActive(next: boolean) {
    const title = next ? 'Enable Deposits?' : 'Pause Deposits?';
    const message = next
      ? 'Customers will be able to submit deposit requests.'
      : 'Customers will be prevented from submitting new deposits.';
    const confirmLabel = next ? 'Enable Deposits' : 'Pause Deposits';
    const ok = await confirm(title, message, confirmLabel, !next);
    if (!ok) return;

    await flipToggle('zinipay_enabled', next, 'Deposit requests');
  }

  async function toggleReferralActive(next: boolean) {
    const title = next ? 'Enable Refer & Earn?' : 'Pause Refer & Earn?';
    const message = next
      ? 'Customers will earn bonus rewards for qualifying referrals.'
      : 'Referral rewards distribution will be temporarily paused.';
    const confirmLabel = next ? 'Enable' : 'Pause';
    const ok = await confirm(title, message, confirmLabel, !next);
    if (!ok) return;

    await flipToggle('referral_enabled', next, 'Refer & Earn');
  }

  async function toggleForceJoinActive(next: boolean) {
    const title = next ? 'Activate Force Join Gate?' : 'Deactivate Force Join Gate?';
    const message = next
      ? 'Customers will be required to join all channels before using the bot.'
      : 'Anyone will be able to access the bot without joining channels.';
    const confirmLabel = next ? 'Activate Gate' : 'Deactivate Gate';
    const ok = await confirm(title, message, confirmLabel, !next);
    if (!ok) return;

    await flipToggle('force_join_enabled', next, 'Force Join Gate');
  }

  async function saveLimits() {
    if (!saved || !isLimitsDirty) return;
    setSavingLimits(true);
    try {
      const depositLimitNum = Math.max(1, parseFloat(values.max_deposit_limit || '500') || 500);
      const referralNum = Math.max(0, parseFloat(values.referral_reward_amount || '0.024') || 0);
      const usdRateNum = Math.max(0.0001, parseFloat(values.usd_rate || '125') || 125);
      const payload: Record<string, string> = {
        store_name: values.store_name?.trim() || 'Premium Haven',
        max_deposit_limit: String(depositLimitNum),
        referral_reward_amount: String(referralNum),
        usd_rate: String(usdRateNum),
        maintenance_message: values.maintenance_message?.trim() || '',
      };
      await api.updateSettings(payload);
      setSaved((cur) => ({ ...(cur ?? {}), ...payload }));
      setValues((cur) => ({ ...cur, ...payload }));
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('store-name-updated', { detail: payload.store_name }));
      }
      say('Limits & rules saved.');
    } catch (cause) {
      say(errorText(cause, 'Could not save limits and rules.'), 'bad');
    } finally {
      setSavingLimits(false);
    }
  }

  async function saveSupport() {
    if (!saved || !isSupportDirty) return;
    setSavingSupport(true);
    try {
      const payload: Record<string, string> = {
        support_username: values.support_username?.trim() || '',
        announcement_channel: values.announcement_channel?.trim() || '',
      };
      await api.updateSettings(payload);
      setSaved((cur) => ({ ...(cur ?? {}), ...payload }));
      setValues((cur) => ({ ...cur, ...payload }));
      say('Support & channels saved.');
    } catch (cause) {
      say(errorText(cause, 'Could not save support and channels.'), 'bad');
    } finally {
      setSavingSupport(false);
    }
  }

  if (!saved) {
    return loadError ? (
      <section className="panel">
        <div className="panel-body" role="alert">
          <p>{loadError}</p>
          <button className="btn" onClick={() => setLoadAttempt((n) => n + 1)}>
            Retry
          </button>
        </div>
      </section>
    ) : (
      <PageLoading label="Loading…" />
    );
  }

  return (
    <>
      <div className="settings-tabs-modern" role="tablist" aria-label="Settings navigation">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            className={`settings-tab-btn ${tab === item.key ? 'active' : ''}`}
            onClick={() => {
              setTab(item.key);
              onTabChange?.(item.key);
            }}
          >
            <TabIcon icon={item.icon} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>

      {tab === 'economics' && (
        <div className="settings-sections">
          {/* User Service Controls Card */}
          <section className="panel settings-card">
            <header>
              <div>
                <h2>Services</h2>
              </div>
            </header>
            <div className="service-control-list">
              <div className="service-control-item">
                <div className="service-control-text">
                  <strong>Purchases</strong>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Switch
                    label="Store purchases"
                    on={isStoreActive}
                    onChange={(next) => void toggleStoreActive(next)}
                  />
                </div>
              </div>

              {!isStoreActive && (
                <div style={{ padding: '12px 20px', background: 'var(--surface-2, #F9FAFB)' }}>
                  <label className="field wide" style={{ margin: 0 }}>
                    <span>Message while paused</span>
                    <textarea
                      rows={2}
                      placeholder="Store maintenance is in progress..."
                      value={values.maintenance_message ?? ''}
                      onChange={(e) =>
                        setValues((cur) => ({ ...cur, maintenance_message: e.target.value }))
                      }
                    />
                  </label>
                  {(values.maintenance_message ?? '') !== (saved.maintenance_message ?? '') ? (
                    <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        className="btn primary"
                        disabled={savingLimits}
                        onClick={() => void saveLimits()}
                      >
                        {savingLimits ? 'Saving...' : 'Save message'}
                      </button>
                    </div>
                  ) : null}
                </div>
              )}

              <div className="service-control-item">
                <div className="service-control-text">
                  <strong>Accept deposits</strong>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Switch
                    label="Accept deposits"
                    on={isDepositsActive}
                    onChange={(next) => void toggleDepositsActive(next)}
                  />
                </div>
              </div>

              <div className="service-control-item">
                <div className="service-control-text">
                  <strong>Refer & Earn</strong>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Switch
                    label="Refer & Earn"
                    on={isReferralActive}
                    onChange={(next) => void toggleReferralActive(next)}
                  />
                </div>
              </div>
            </div>
          </section>

          {/* 2-Column Limits & Administrators Grid */}
          <div className="settings-grid-2col">
            <section className="panel settings-card">
              <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h2>Limits & Rules</h2>
                  {isLimitsDirty && (
                    <span className="unsaved-dot-indicator" title="Unsaved changes">
                      ●
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className={`btn-card-save ${isLimitsDirty ? 'active' : 'dhundhla'}`}
                  disabled={!isLimitsDirty || savingLimits}
                  onClick={() => void saveLimits()}
                >
                  {savingLimits ? 'Saving…' : 'Save'}
                </button>
              </header>
              <div className="field-grid" style={{ padding: '16px 20px' }}>
                <label className="field wide">
                  <span>Store name</span>
                  <input
                    type="text"
                    placeholder="Premium Haven"
                    value={values.store_name ?? ''}
                    onChange={(e) => setValues((cur) => ({ ...cur, store_name: e.target.value }))}
                  />
                </label>

                <label className="field wide">
                  <span>Maximum single wallet credit (USD)</span>
                  <input
                    type="number"
                    min="1"
                    placeholder="400"
                    value={values.max_deposit_limit ?? '400'}
                    onChange={(e) =>
                      setValues((cur) => ({ ...cur, max_deposit_limit: e.target.value }))
                    }
                  />
                </label>

                <label className="field wide">
                  <span>Bonus per Referral (USD)</span>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="0.024"
                    value={values.referral_reward_amount ?? '0.024'}
                    onChange={(e) =>
                      setValues((cur) => ({ ...cur, referral_reward_amount: e.target.value }))
                    }
                  />
                </label>

                <label className="field wide">
                  <span>Exchange Rate (1 USD/USDT in BDT)</span>
                  <input
                    type="number"
                    step="any"
                    min="0.0001"
                    placeholder="125"
                    value={values.usd_rate ?? '125'}
                    onChange={(e) => setValues((cur) => ({ ...cur, usd_rate: e.target.value }))}
                  />
                </label>
              </div>
            </section>

            <section className="panel settings-card">
              <header>
                <div>
                  <h2>Bot Administrators</h2>
                </div>
              </header>
              <div style={{ padding: '0 20px 20px' }}>
                <BotAdmins
                  say={say}
                  values={values}
                  setValues={setValues}
                  setSaved={setSaved}
                />
              </div>
            </section>
          </div>
        </div>
      )}

      {tab === 'gate' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="settings-grid-2col">
            {/* Left Column: Force Join Gate */}
            <section className="panel settings-card">
              <header>
                <div>
                  <h2>Force Join Gate</h2>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {isForceJoinActive && <span className="badge-active-pill">Active</span>}
                  <Switch
                    label="Force Join Gate"
                    on={isForceJoinActive}
                    onChange={(next) => void toggleForceJoinActive(next)}
                  />
                </div>
              </header>

              <div style={{ padding: '16px 20px 20px' }}>
                <GateChannels say={say} isGateEnabled={isForceJoinActive} />
              </div>
            </section>

            {/* Right Column: Support & Channels */}
            <section className="panel settings-card">
              <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h2>Support & Channels</h2>
                  {isSupportDirty && (
                    <span className="unsaved-dot-indicator" title="Unsaved changes">
                      ●
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className={`btn-card-save ${isSupportDirty ? 'active' : 'dhundhla'}`}
                  disabled={!isSupportDirty || savingSupport}
                  onClick={() => void saveSupport()}
                >
                  {savingSupport ? 'Saving…' : 'Save'}
                </button>
              </header>
              <div className="field-grid" style={{ padding: '16px 20px' }}>
                <label className="field wide">
                  <span>Support username</span>
                  <input
                    type="text"
                    placeholder="@username"
                    value={values.support_username ?? ''}
                    onChange={(e) =>
                      setValues((cur) => ({ ...cur, support_username: e.target.value }))
                    }
                  />
                </label>

                <label className="field wide">
                  <span>Announcement Channel or Group</span>
                  <input
                    type="text"
                    placeholder="@channel or -100..."
                    value={values.announcement_channel ?? ''}
                    onChange={(e) =>
                      setValues((cur) => ({ ...cur, announcement_channel: e.target.value }))
                    }
                  />
                </label>
              </div>
            </section>
          </div>

          {/* Dedicated Separate Box: Help & Support Links */}
          <section className="panel settings-card">
            <UpdateChannels say={say} />
          </section>
        </div>
      )}

      {tab === 'payments' && (
        <div className="payments-screen-layout">
          <PaymentMethods
            say={say}
            symbol={symbol}
            zinipayActive={Boolean((values.zinipay_api_key || '').trim())}
            values={values}
            setValues={setValues}
            setSaved={setSaved}
            payStatus={payStatus}
            setPayStatus={setPayStatus}
            refreshGateways={refreshGateways}
          />
        </div>
      )}

      {tab === 'notifications' && (
        <section className="panel settings-card">
          <div className="settings-alerts-body">
            <AdminNotifications
              say={say}
              values={values}
              setValues={setValues}
              setSaved={setSaved}
              flip={flipToggle}
              confirm={confirm}
            />
          </div>
        </section>
      )}

      {confirmDialog}
    </>
  );
}
