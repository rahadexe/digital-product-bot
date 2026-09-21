'use client';

// Settings as a list of panels. Each panel owns its fields and saves them itself; a switch saves the moment
// it flips. To add a control, add a field to a section below.

import { Fragment, useEffect, useState } from 'react';
import { api, type BinanceStatus, type PaymentsStatus } from '@/lib/api';
import { resetCurrencySymbol } from '@/lib/currency';
import { AdminNotifications } from './AdminNotifications';
import { BotAdmins } from './BotAdmins';
import { CustomSelect } from './CustomSelect';
import { GateChannels } from './GateChannels';
import { PaymentMethods } from './PaymentMethods';
import { UpdateChannels } from './UpdateChannels';
import { PageLoading, FlagRow, Switch, errorText, type Say } from './ui';
import { Check, Eye, EyeOff, RotateCcw, Save } from 'lucide-react';

export type SettingsTab = 'general' | 'payments' | 'notifications' | 'channels';

const TABS: { key: SettingsTab; label: string }[] = [
  { key: 'general', label: 'Store' },
  { key: 'payments', label: 'Payments' },
  { key: 'notifications', label: 'Notifications' },
  { key: 'channels', label: 'Channels' },
];

/** Where a tab that no longer exists should land, so old links still work. */
const MOVED: Record<string, SettingsTab> = { access: 'channels' };

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
  /** The switch the whole panel hangs from, with what it means in each position. */
  master?: { key: string; on?: string; off?: string };
  fields: Field[];
  extra?: 'zinipay' | 'binance';
};

const SECTIONS: Section[] = [
  // ── Store ────────────────────────────────────────────────
  {
    id: 'store',
    tab: 'general',
    title: 'Store profile',
    fields: [
      { key: 'store_name', label: 'Store name', placeholder: 'Store name' },
      { key: 'support_username', label: 'Support username', placeholder: '@username' },
      {
        key: 'welcome_text',
        label: 'Welcome message',
        hint: 'The first thing a customer sees. Leave blank for the default.',
        type: 'textarea',
        rows: 3,
        placeholder: 'Custom welcome message (optional)',
      },
    ],
  },
  {
    id: 'admins',
    tab: 'general',
    title: 'Who runs this shop',
    fields: [],
  },
  {
    id: 'availability',
    tab: 'general',
    title: 'Store availability',
    fields: [
      { key: 'store_paused', label: 'Pause the store', hint: 'Blocks new orders and deposits.', type: 'toggle' },
      {
        key: 'maintenance_message',
        label: 'Message while paused',
        type: 'textarea',
        rows: 2,
        placeholder: 'Store maintenance is in progress...',
      },
    ],
  },
  {
    id: 'pricing_display',
    tab: 'general',
    title: 'Price display',
    fields: [
      { key: 'show_usd_price', label: 'Show USD price on products (৳ & $)', type: 'toggle' },
      { key: 'usd_rate', label: 'Exchange Rate: 1 USD', type: 'number', fallback: '125', money: true },
    ],
  },
  {
    id: 'referral',
    tab: 'general',
    title: 'Refer & Earn',
    master: { key: 'referral_enabled' },
    fields: [
      {
        key: 'referral_reward_amount',
        label: 'Bonus per Referral',
        type: 'number',
        fallback: '3',
        money: true,
      },
    ],
  },
  // ── Payments ─────────────────────────────────────────────
  {
    id: 'deposit_limits',
    tab: 'payments',
    title: 'Deposit limits',
    fields: [
      {
        key: 'max_deposit_limit',
        label: 'Most a customer may add at once',
        hint: 'Applies to every method below.',
        type: 'number',
        fallback: '500',
        money: true,
      },
    ],
  },
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
    title: 'ZiniPay checkout',
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
      { key: 'binance_pay_name', label: 'Account name customers see', placeholder: 'Leave blank to show only the UID' },
      { key: 'binance_api_key', label: 'API Key (Read-only)', type: 'password', secret: 'binance_api_key' },
      { key: 'binance_api_secret', label: 'API Secret', type: 'password', secret: 'binance_api_secret' },
      { key: 'binance_pay_rate', label: 'Rate per 1 USDT (৳)', type: 'number', fallback: '125' },
      { key: 'binance_pay_min', label: 'Smallest deposit ($)', type: 'number', fallback: '1' },
      { key: 'binance_pay_instructions', label: 'Custom instructions (optional)', type: 'textarea', rows: 2, placeholder: 'Leave blank for default instructions' },
    ],
    extra: 'binance',
  },
  // ── Notifications ────────────────────────────────────────
  { id: 'notifications', tab: 'notifications', title: 'Notifications', fields: [] },
  // ── Channels ─────────────────────────────────────────────
  // Everything to do with a channel lives here. The force-join switch used to
  // sit on another tab from the channels it requires, so turning it on meant
  // going somewhere else to say which channels it meant.
  {
    id: 'force_join',
    tab: 'channels',
    title: 'Force join',
    master: { key: 'force_join_enabled' },
    fields: [],
  },
  {
    id: 'announcements',
    tab: 'channels',
    title: 'Announcement channel',
    fields: [
      {
        key: 'announcement_channel',
        label: 'Announcement channel',
        hint: 'The Telegram channel where the bot posts restock and price drop alerts.',
        placeholder: '@YourChannel or -100…',
      },
    ],
  },
  {
    id: 'update_channels',
    tab: 'channels',
    title: 'Customer channel buttons',
    fields: [],
  },
];


export function Settings({ say, initialTab, onTabChange }: { say: Say; initialTab?: SettingsTab; onTabChange?: (tab: SettingsTab) => void }) {
  const resolve = (wanted?: string): SettingsTab =>
    TABS.some((item) => item.key === wanted) ? (wanted as SettingsTab) : MOVED[wanted ?? ''] ?? 'general';
  const [tab, setTab] = useState<SettingsTab>(resolve(initialTab));
  const [saved, setSaved] = useState<Record<string, string> | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({});
  const [savingSection, setSavingSection] = useState('');
  const [payStatus, setPayStatus] = useState<PaymentsStatus | null>(null);
  const [binance, setBinance] = useState<BinanceStatus | null>(null);

  // Following a link to another tab (#settings/payments) while Settings is already open.
  useEffect(() => {
    // #settings with no tab means the first tab. Leaving the previous one showing
    // would put the address and the screen at odds.
    setTab(resolve(initialTab));
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
  const symbol = values.currency_symbol || '৳';

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
      const fresh = await api.settings().catch(() => null);
      if (fresh) {
        setSaved(fresh);
        setValues(fresh);
      } else {
        setSaved((current) => ({ ...(current ?? {}), ...Object.fromEntries(changed.filter((field) => !field.secret).map((field) => [field.key, payload[field.key]])) }));
      }
      setSecrets((current) => {
        const next = { ...current };
        for (const field of changed) if (field.secret) delete next[field.key];
        return next;
      });
      setVisibleSecrets((current) => {
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
    setVisibleSecrets((current) => {
      const next = { ...current };
      for (const field of section.fields) delete next[field.key];
      return next;
    });
  }

  if (!saved) return <PageLoading label="Loading…" />;

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
      // CustomSelect, not a native <select>: the browser draws its own list,
      // which does not follow the console's type, spacing or dark mode.
      return (
        <label key={field.key} className="field">
          <span>{label}</span>
          <CustomSelect
            value={valueOf(field)}
            options={field.options}
            onChange={(next) => setValues((current) => ({ ...current, [field.key]: next }))}
          />
          {field.hint ? <small>{field.hint}</small> : null}
        </label>
      );
    }
    if (field.secret) {
      const maskedVal = values[field.key] || '';
      const isVisible = Boolean(visibleSecrets[field.key]);
      const isEntering = Boolean(secrets[field.key]);

      return (
        <label key={field.key} className="field">
          <span>{label}</span>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center', width: '100%' }}>
            <input
              type={isVisible ? 'text' : 'password'}
              maxLength={field.maxLength}
              autoComplete="off"
              style={{
                width: '100%',
                paddingRight: isEntering ? '36px' : '12px',
                fontFamily: isEntering ? 'inherit' : 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              }}
              placeholder={maskedVal ? maskedVal : 'Enter key...'}
              value={secrets[field.key] ?? ''}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  const targetSection = SECTIONS.find((s) => s.fields.some((f) => f.key === field.key));
                  if (targetSection) void save(targetSection);
                }
              }}
              onChange={(event) =>
                setSecrets((current) => ({ ...current, [field.key]: event.target.value }))
              }
            />
            {isEntering && (
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setVisibleSecrets((cur) => ({ ...cur, [field.key]: !cur[field.key] }))}
                style={{
                  position: 'absolute',
                  right: '8px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--muted)',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '4px',
                }}
                title={isVisible ? 'Hide key' : 'Show key'}
              >
                {isVisible ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            )}
          </div>
          {field.hint ? <small>{field.hint}</small> : null}
        </label>
      );
    }

    return (
      <label key={field.key} className="field">
        <span>{label}</span>
        <input
          type={field.type === 'number' ? 'number' : 'text'}
          step={field.type === 'number' ? 'any' : undefined}
          min={field.type === 'number' ? '0' : undefined}
          maxLength={field.maxLength}
          autoComplete="off"
          placeholder={field.placeholder}
          value={valueOf(field)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              const targetSection = SECTIONS.find((s) => s.fields.some((f) => f.key === field.key));
              if (targetSection) void save(targetSection);
            }
          }}
          onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
        />
        {field.hint ? <small>{field.hint}</small> : null}
      </label>
    );
  }

  function renderSaveActions(section: Section, changed: boolean) {
    const isSaving = savingSection === section.id;
    return (
      <div className="panel-save-actions">
        {changed ? (
          <span className="unsaved-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '12px', fontWeight: 600, color: 'var(--warning)', marginRight: '6px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--warning)', display: 'inline-block' }} />
            Unsaved changes
          </span>
        ) : (
          <span className="saved-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: 'var(--muted)', marginRight: '6px' }}>
            <Check size={13} style={{ color: 'var(--positive)' }} />
            Saved
          </span>
        )}
        {changed ? (
          <button
            type="button"
            className="btn ghost small"
            disabled={isSaving}
            onClick={() => discard(section)}
            title="Discard unsaved changes"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <RotateCcw size={13} />
            <span>Undo</span>
          </button>
        ) : null}
        <button
          type="button"
          className="btn small"
          disabled={!changed || isSaving}
          onClick={() => void save(section)}
          title={changed ? 'Save changes' : 'All changes saved'}
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
      <div className="segmented settings-tabs" role="tablist" aria-label="Settings">
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

      <div className={`settings-sections settings-sections-${tab}`}>
      {SECTIONS.filter((section) => section.tab === tab).map((section) => {
        const on = section.master ? isOn(section.master.key) : true;
        const changed = changedIn(section).length > 0;
        const inputs = section.fields.filter((field) => field.type !== 'toggle');
        const toggles = section.fields.filter((field) => field.type === 'toggle');
        return (
          <Fragment key={section.id}>
            <section className={`panel settings-card settings-card-${section.id}${on ? '' : ' off'}`}>
              <header>
                <div>
                  <h2>{section.title}</h2>
                  {section.master && (on ? section.master.on : section.master.off) ? <p>{on ? section.master.on : section.master.off}</p> : null}
                </div>
                <div className="actions">
                  {section.master ? <Switch label={section.title} on={on} onChange={(next) => void flip(section.master!.key, next)} /> : null}
                </div>
              </header>

              {inputs.length ? <div className="field-grid">{inputs.map(renderInput)}</div> : null}
              {toggles.map((field) => (
                <FlagRow key={field.key} label={field.label} hint={field.hint} on={isOn(field.key)} onChange={(next) => void flip(field.key, next)} />
              ))}
              {section.extra === 'zinipay' ? (
                <ZiniPayExtra
                  status={payStatus}
                  setStatus={setPayStatus}
                  say={say}
                  saveActions={renderSaveActions(section, changed)}
                />
              ) : null}
              {section.extra === 'binance' ? (
                <BinanceExtra
                  status={binance}
                  say={say}
                  saveActions={renderSaveActions(section, changed)}
                />
              ) : null}
              {!section.extra && inputs.length ? (
                <div className="panel-actions panel-actions-save-only">
                  {renderSaveActions(section, changed)}
                </div>
              ) : null}

              {/* Embedded Sub-components inside the unified card */}
              {section.id === 'admins' ? (
                <BotAdmins say={say} values={values} setValues={setValues} setSaved={setSaved} />
              ) : null}
              {section.id === 'notifications' ? (
                <AdminNotifications
                  say={say}
                  values={values}
                  setValues={setValues}
                  setSaved={setSaved}
                  flip={flip}
                />
              ) : null}
              {section.id === 'update_channels' ? <UpdateChannels say={say} /> : null}
              {section.id === 'force_join' ? <GateChannels say={say} /> : null}
            </section>

            {section.id === 'zinipay_autoverify' ? <PaymentMethods say={say} symbol={symbol} zinipayActive={isOn('zinipay_enabled')} /> : null}
          </Fragment>
        );
      })}
      </div>
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



