'use client';

// Settings as a list of panels. Each panel owns its fields and saves them itself; a switch saves the moment
// it flips. To add a control, add a field to a section below.

import { Fragment, useEffect, useState } from 'react';
import { api, type BinanceStatus, type PaymentsStatus } from '@/lib/api';
import { resetCurrencySymbol } from '@/lib/currency';
import { AdminNotifications } from './AdminNotifications';
import { GateChannels } from './GateChannels';
import { PaymentMethods } from './PaymentMethods';
import { UpdateChannels } from './UpdateChannels';
import { FlagRow, Switch, errorText, type Say } from './ui';
import { RotateCcw, Save } from 'lucide-react';

export type SettingsTab = 'general' | 'payments';

const TABS: { key: SettingsTab; label: string }[] = [
  { key: 'general', label: 'General' },
  { key: 'payments', label: 'Payments' },
];

type Secret = 'zinipay_api_key' | 'binance_api_key' | 'binance_api_secret';

type Field = {
  key: string;
  label: string;
  hint?: string;
  type?: 'text' | 'number' | 'password' | 'toggle' | 'textarea' | 'select';
  options?: { value: string; label: string }[];
  placeholder?: string;
  rows?: number;
  maxLength?: number;
  fallback?: string;
  /** Password fields are write-only: kept apart and sent only when typed. */
  secret?: Secret;
  /** Shown with the store's currency symbol. */
  money?: boolean;
};

type Section = {
  id: string;
  tab: SettingsTab;
  title: string;
  description?: string;
  subhead?: string;
  /** The switch the whole panel hangs from, with what it means in each position. */
  master?: { key: string; on?: string; off?: string };
  fields: Field[];
  extra?: 'zinipay' | 'binance';
};

const SECTIONS: Section[] = [
  // ── General Tab ──────────────────────────────────────────
  {
    id: 'store',
    tab: 'general',
    title: 'Bot Profile & Admin Settings',
    description: 'Core bot identity, support contact, store currency, and admin notification recipients.',
    subhead: 'Bot & Store Identity',
    fields: [
      { key: 'store_name', label: 'Bot / Store Name', placeholder: 'PremiumOne' },
      { key: 'support_username', label: 'Telegram Support Username', placeholder: '@username' },
      { key: 'currency_symbol', label: 'Currency Symbol', placeholder: '৳' },
      { key: 'currency', label: 'Currency Code', placeholder: 'BDT' },
    ],
  },
  {
    id: 'channels',
    tab: 'general',
    title: 'Welcome & Channels',
    description: 'Customer greeting message, automated stock restock broadcasts, and bot channel buttons.',
    subhead: 'Welcome Greeting & Channel Posts',
    fields: [
      {
        key: 'welcome_text',
        label: 'Welcome Message (Optional)',
        type: 'textarea',
        rows: 3,
        placeholder: 'Enter custom welcome message, or leave blank for default...',
        hint: 'If left blank, default welcome text will be sent to the customer.',
      },
      { key: 'announcement_channel', label: 'Announcement Channel', placeholder: '@YourChannel or -100…' },
      { key: 'auto_restock_alerts', label: 'Post when stock is added', type: 'toggle' },
      { key: 'auto_price_drop_alerts', label: 'Post when a price drops', type: 'toggle' },
    ],
  },
  {
    id: 'access',
    tab: 'general',
    title: 'Store Access & Force-Join Gate',
    description: 'Maintenance mode controls, single deposit limits, and required channel memberships.',
    subhead: 'Operations & Limits',
    fields: [
      { key: 'maintenance_message', label: 'Maintenance message', placeholder: 'Store maintenance is in progress. Please try again soon.' },
      { key: 'max_deposit_limit', label: 'Largest single deposit', type: 'number', fallback: '500', money: true },
      { key: 'store_paused', label: 'Pause new purchases and deposits', type: 'toggle' },
      { key: 'force_join_enabled', label: 'Customers must join the channels below', type: 'toggle' },
    ],
  },
  {
    id: 'referral',
    tab: 'general',
    title: 'Refer & Earn Program',
    description: 'Cash bonus rewards credited to customer wallets when invited friends join and verify channel membership.',
    subhead: 'Referral Rewards',
    master: { key: 'referral_enabled' },
    fields: [
      {
        key: 'referral_reward_amount',
        label: 'Bonus per Referral (Flat Cash)',
        type: 'number',
        fallback: '3',
        money: true,
        hint: 'Cash bonus credited to referrer wallet when invited friend joins bot and verifies channel membership (Max limit: 100 ৳).',
      },
    ],
  },
  // ── Payments Tab ─────────────────────────────────────────
  {
    id: 'zinipay_autoverify',
    tab: 'payments',
    title: 'ZiniPay Auto-Verification',
    master: {
      key: 'zinipay_enabled',
    },
    fields: [
      {
        key: 'zinipay_api_key',
        label: 'ZiniPay API Key',
        type: 'password',
        secret: 'zinipay_api_key',
      },
    ],
  },
  {
    id: 'zinipay_web',
    tab: 'payments',
    title: 'Web Checkout (ZiniPay Hosted)',
    master: {
      key: 'zinipay_web_gateway_enabled',
    },
    fields: [
      { key: 'zinipay_brand_url', label: 'Brand website URL', placeholder: 'https://myshop.com' },
      { key: 'zinipay_label', label: 'Name customers see', maxLength: 40, placeholder: 'Instant Web Checkout' },
      { key: 'zinipay_min_deposit', label: 'Smallest deposit', type: 'number', fallback: '10', money: true },
    ],
    extra: 'zinipay',
  },
  {
    id: 'binance',
    tab: 'payments',
    title: 'Binance',
    master: {
      key: 'binance_enabled',
    },
    fields: [
      { key: 'binance_pay_id', label: 'Binance UID', placeholder: '750176717' },
      { key: 'binance_api_key', label: 'API Key (Read-only)', type: 'password', secret: 'binance_api_key' },
      { key: 'binance_api_secret', label: 'API Secret', type: 'password', secret: 'binance_api_secret' },
      {
        key: 'binance_coin',
        label: 'Coin',
        type: 'select',
        fallback: 'USDT',
        options: [
          { value: 'USDT', label: 'USDT' },
        ],
      },
      { key: 'binance_pay_rate', label: 'Rate per 1 USDT (৳)', type: 'number', fallback: '125' },
      { key: 'binance_pay_min', label: 'Smallest deposit ($)', type: 'number', fallback: '1' },
      { key: 'binance_pay_instructions', label: 'Custom instructions (optional)', type: 'textarea', rows: 2, placeholder: 'Leave blank for default instructions' },
    ],
    extra: 'binance',
  },
];

export function Settings({ say, initialTab, onTabChange }: { say: Say; initialTab?: SettingsTab; onTabChange?: (tab: SettingsTab) => void }) {
  const [tab, setTab] = useState<SettingsTab>(TABS.some((item) => item.key === initialTab) ? (initialTab as SettingsTab) : 'general');
  const [saved, setSaved] = useState<Record<string, string> | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [savingSection, setSavingSection] = useState('');
  const [payStatus, setPayStatus] = useState<PaymentsStatus | null>(null);
  const [binance, setBinance] = useState<BinanceStatus | null>(null);

  // Following a link to another tab (#settings/payments) while Settings is already open.
  useEffect(() => {
    if (initialTab && TABS.some((item) => item.key === initialTab)) setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setSaved(settings);
        setValues(settings);
      })
      .catch((cause) => say(errorText(cause, 'Could not load settings.'), 'bad'));
    void refreshGateways();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshGateways() {
    const [payments, checker] = await Promise.all([api.paymentsStatus().catch(() => null), api.binanceStatus().catch(() => null)]);
    setPayStatus(payments);
    setBinance(checker);
  }

  const valueOf = (field: Field) => values[field.key] ?? field.fallback ?? '';
  const isOn = (key: string) => (values[key] ?? (key.endsWith('_enabled') && key !== 'force_join_enabled' ? '0' : '1')) === '1';
  const changedIn = (section: Section) =>
    section.fields.filter((field) => field.type !== 'toggle' && (field.secret ? Boolean(secrets[field.key]?.trim()) : (values[field.key] ?? '') !== (saved?.[field.key] ?? '')));
  const unsaved = SECTIONS.some((section) => changedIn(section).length > 0);
  const symbol = values.currency_symbol || '$';

  // Leaving or reloading with typed but unsaved values asks first.
  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [unsaved]);

  async function flip(key: string, on: boolean) {
    const value = on ? '1' : '0';
    const before = values[key];
    setValues((current) => ({ ...current, [key]: value }));
    try {
      await api.updateSettings({ [key]: value });
      setSaved((current) => ({ ...(current ?? {}), [key]: value }));
      say(on ? 'On.' : 'Off.');
      if (key === 'zinipay_enabled' || key === 'zinipay_web_gateway_enabled' || key === 'binance_enabled') void refreshGateways();
    } catch (cause) {
      setValues((current) => ({ ...current, [key]: before }));
      say(errorText(cause, 'Could not change that.'), 'bad');
    }
  }

  async function save(section: Section) {
    const changed = changedIn(section);
    if (!changed.length) return;
    const payload: Record<string, string> = {};
    for (const field of changed) payload[field.key] = field.secret ? secrets[field.key].trim() : values[field.key] ?? '';
    setSavingSection(section.id);
    try {
      await api.updateSettings(payload);
      setSaved((current) => ({ ...(current ?? {}), ...Object.fromEntries(changed.filter((field) => !field.secret).map((field) => [field.key, payload[field.key]])) }));
      setSecrets((current) => {
        const next = { ...current };
        for (const field of changed) if (field.secret) delete next[field.key];
        return next;
      });
      resetCurrencySymbol();
      if (section.extra === 'zinipay' || section.extra === 'binance') void refreshGateways();
      say('Saved.');
    } catch (cause) {
      say(errorText(cause, 'Could not save.'), 'bad');
    } finally {
      setSavingSection('');
    }
  }

  function discard(section: Section) {
    setValues((current) => ({ ...current, ...Object.fromEntries(section.fields.map((field) => [field.key, saved?.[field.key] ?? ''])) }));
    setSecrets((current) => {
      const next = { ...current };
      for (const field of section.fields) delete next[field.key];
      return next;
    });
  }

  if (!saved) return <p className="loading">Loading…</p>;

  function renderInput(field: Field) {
    const coinName = values['binance_coin'] || 'USDT';
    const label =
      field.key === 'binance_pay_rate'
        ? `Rate per 1 ${coinName} (${symbol})`
        : field.money
        ? `${field.label} (${symbol})`
        : field.label;

    if (field.type === 'textarea') {
      return (
        <label key={field.key} className="field wide">
          <span>{label}</span>
          <textarea rows={field.rows ?? 3} placeholder={field.placeholder} value={valueOf(field)} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))} />
        </label>
      );
    }

    if (field.type === 'select' && field.options) {
      return (
        <label key={field.key} className="field">
          <span>{label}</span>
          <select
            value={valueOf(field)}
            onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
          >
            {field.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {field.hint ? <small>{field.hint}</small> : null}
        </label>
      );
    }
    const stored = field.secret === 'zinipay_api_key' ? payStatus?.has_api_key : field.secret ? binance?.has_credentials : false;
    return (
      <label key={field.key} className="field">
        <span>{label}</span>
        <input
          type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
          step={field.type === 'number' ? 'any' : undefined}
          min={field.type === 'number' ? '0' : undefined}
          maxLength={field.maxLength}
          autoComplete="off"
          placeholder={field.secret ? (stored ? 'Saved · type to replace' : 'Not set') : field.placeholder}
          value={field.secret ? secrets[field.key] ?? '' : valueOf(field)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              const targetSection = SECTIONS.find((s) => s.fields.some((f) => f.key === field.key));
              if (targetSection) void save(targetSection);
            }
          }}
          onChange={(event) =>
            field.secret
              ? setSecrets((current) => ({ ...current, [field.key]: event.target.value }))
              : setValues((current) => ({ ...current, [field.key]: event.target.value }))
          }
        />
        {field.hint ? <small>{field.hint}</small> : null}
      </label>
    );
  }

  function renderSaveActions(section: Section) {
    const isSaving = savingSection === section.id;
    return (
      <div className="panel-save-actions">
        <button
          type="button"
          className="btn ghost small"
          onClick={() => discard(section)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <RotateCcw size={13} />
          <span>Undo</span>
        </button>
        <button
          type="button"
          className="btn small"
          disabled={isSaving}
          onClick={() => void save(section)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <Save size={14} />
          <span>{isSaving ? 'Saving…' : 'Save'}</span>
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="segmented" role="tablist" aria-label="Settings">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            className={tab === item.key ? 'active' : ''}
            onClick={() => {
              setTab(item.key);
              onTabChange?.(item.key);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      {SECTIONS.filter((section) => section.tab === tab).map((section) => {
        const on = section.master ? isOn(section.master.key) : true;
        const changed = changedIn(section).length > 0;
        const inputs = section.fields.filter((field) => field.type !== 'toggle');
        const toggles = section.fields.filter((field) => field.type === 'toggle');
        return (
          <Fragment key={section.id}>
            <section className={`panel${on ? '' : ' off'}`}>
              <header>
                <div>
                  <h2>{section.title}</h2>
                  {section.description ? <p>{section.description}</p> : null}
                  {section.master && (on ? section.master.on : section.master.off) ? <p>{on ? section.master.on : section.master.off}</p> : null}
                </div>
                <div className="actions">
                  {section.master ? <Switch label={section.title} on={on} onChange={(next) => void flip(section.master!.key, next)} /> : null}
                </div>
              </header>

              {/* Subhead for section parameters if defined */}
              {section.subhead ? (
                <div className="panel-subhead">
                  <div>
                    <h3>{section.subhead}</h3>
                    <p>
                      {section.id === 'store'
                        ? 'Basic store branding, support contact, and currency settings.'
                        : section.id === 'channels'
                        ? 'Customer onboarding greeting and automated inventory alerts.'
                        : section.id === 'access'
                        ? 'Store availability toggles and financial ceilings.'
                        : 'Referral cash reward amounts.'}
                    </p>
                  </div>
                </div>
              ) : null}

              {inputs.length ? <div className="field-grid">{inputs.map(renderInput)}</div> : null}
              {toggles.map((field) => (
                <FlagRow key={field.key} label={field.label} hint={field.hint} on={isOn(field.key)} onChange={(next) => void flip(field.key, next)} />
              ))}
              {section.extra === 'zinipay' ? (
                <ZiniPayExtra
                  status={payStatus}
                  setStatus={setPayStatus}
                  say={say}
                  saveActions={changed ? renderSaveActions(section) : null}
                />
              ) : null}
              {section.extra === 'binance' ? (
                <BinanceExtra
                  status={binance}
                  say={say}
                  saveActions={changed ? renderSaveActions(section) : null}
                />
              ) : null}
              {!section.extra && changed ? (
                <div className="panel-actions panel-actions-save-only">
                  {renderSaveActions(section)}
                </div>
              ) : null}

              {/* Embedded Sub-components inside the unified card */}
              {section.id === 'store' ? (
                <AdminNotifications
                  say={say}
                  values={values}
                  setValues={setValues}
                  setSaved={setSaved}
                  flip={flip}
                />
              ) : null}
              {section.id === 'channels' ? <UpdateChannels say={say} /> : null}
              {section.id === 'access' ? <GateChannels say={say} /> : null}
            </section>

            {section.id === 'zinipay_autoverify' ? <PaymentMethods say={say} symbol={symbol} zinipayActive={isOn('zinipay_enabled')} /> : null}
          </Fragment>
        );
      })}
    </>
  );
}

function useRunner(say: Say) {
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<string>) {
    setBusy(true);
    try {
      say(await action());
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}

function ZiniPayExtra({
  status,
  setStatus,
  say,
  saveActions,
}: {
  status: PaymentsStatus | null;
  setStatus: (status: PaymentsStatus | null) => void;
  say: Say;
  saveActions?: React.ReactNode;
}) {
  const { busy, run } = useRunner(say);
  const ready = Boolean(status?.has_api_key);
  return (
    <>
      {status?.public_url ? (
        <div className="facts">
          <span>
            Website in ZiniPay: <code>{status.public_url.replace('https://', '')}</code>
          </span>
          <span>
            {status.counts.completed ?? 0} paid · {status.counts.pending ?? 0} unpaid · {status.counts.failed ?? 0} failed
          </span>
          {status.last_error ? <span className="bad-text">Last refusal: {status.last_error}</span> : null}
        </div>
      ) : null}
      <div className="panel-actions">
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button type="button" className="mini" disabled={busy || !ready} onClick={() => run(async () => (await api.testPayments()).message)}>
            Test connection
          </button>
          <button
            type="button"
            className="mini"
            disabled={busy || !ready}
            onClick={() =>
              run(async () => {
                const result = await api.testPaymentPage();
                if (!result.ok) throw new Error(result.message);
                if (result.payment_url) window.open(result.payment_url, '_blank', 'noopener');
                return result.message;
              })
            }
          >
            Open a test payment
          </button>
          <button
            type="button"
            className="mini"
            disabled={busy || !ready}
            onClick={() =>
              run(async () => {
                const result = await api.checkPendingPayments();
                setStatus(await api.paymentsStatus().catch(() => null));
                return result.checked ? `Checked ${result.checked}.` : 'Nothing unpaid.';
              })
            }
          >
            Check unpaid
          </button>
        </div>
        {saveActions}
      </div>
    </>
  );
}

function BinanceExtra({
  status,
  say,
  saveActions,
}: {
  status: BinanceStatus | null;
  say: Say;
  saveActions?: React.ReactNode;
}) {
  const { busy, run } = useRunner(say);
  const ready = Boolean(status?.has_credentials);
  return (
    <div className="panel-actions">
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <button type="button" className="mini" disabled={busy || !ready} onClick={() => run(async () => (await api.testBinance()).message)}>
          Test connection
        </button>
        <button
          type="button"
          className="mini"
          disabled={busy || !ready}
          onClick={() =>
            run(async () => {
              const result = await api.recheckBinanceDeposits();
              return result.checked ? `Checked ${result.checked}.` : 'Nothing waiting.';
            })
          }
        >
          Check waiting
        </button>
      </div>
      {saveActions}
    </div>
  );
}



