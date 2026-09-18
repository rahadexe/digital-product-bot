'use client';

// Settings as a list of panels. Each panel owns its fields and saves them itself; a switch saves the moment
// it flips. To add a control, add a field to a section below.

import { Fragment, useEffect, useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import { api, type BinanceStatus, type PaymentsStatus } from '@/lib/api';
import { resetCurrencySymbol } from '@/lib/currency';
import { AdminNotifications } from './AdminNotifications';
import { GateChannels } from './GateChannels';
import { PaymentMethods } from './PaymentMethods';
import { UpdateChannels } from './UpdateChannels';
import { FlagRow, Modal, Switch, errorText, useConfirm, type Say } from './ui';

export type SettingsTab = 'store' | 'notifications' | 'notices' | 'access' | 'payments';

const TABS: { key: SettingsTab; label: string }[] = [
  { key: 'store', label: 'Store' },
  { key: 'notifications', label: 'Admin & Alerts' },
  { key: 'notices', label: 'Channels & Notices' },
  { key: 'access', label: 'Access' },
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
  /** The switch the whole panel hangs from, with what it means in each position. */
  master?: { key: string; on?: string; off?: string };
  fields: Field[];
  extra?: 'zinipay' | 'binance';
};

const SECTIONS: Section[] = [
  {
    id: 'store',
    tab: 'store',
    title: 'Bot & Store Profile',
    fields: [
      { key: 'store_name', label: 'Bot / Store Name', placeholder: 'PremiumOne' },
      { key: 'support_username', label: 'Telegram Support Username', placeholder: '@username' },
      { key: 'admin_tg_id', label: 'Primary Admin Telegram ID', placeholder: '123456789', hint: 'Manage all admin accounts & alert rules in the Admin & Alerts tab.' },
      { key: 'currency_symbol', label: 'Currency Symbol', placeholder: '৳' },
      { key: 'currency', label: 'Currency Code', placeholder: 'BDT' },
    ],
  },
  {
    id: 'referral',
    tab: 'store',
    title: 'Refer & Earn Program',
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
  {
    id: 'notice',
    tab: 'notices',
    title: 'Bot Welcome',
    fields: [
      {
        key: 'welcome_text',
        label: 'Welcome Message (Optional)',
        type: 'textarea',
        rows: 4,
        placeholder: 'Enter custom welcome message, or leave blank to only show banner and buttons...',
        hint: 'If left blank, no extra welcome text will be sent to the customer.',
      },
    ],
  },
  {
    id: 'channel',
    tab: 'notices',
    title: 'Channel posts',
    fields: [
      { key: 'announcement_channel', label: 'Channel', placeholder: '@YourChannel or -100…' },
      { key: 'auto_restock_alerts', label: 'Post when stock is added', type: 'toggle' },
      { key: 'auto_price_drop_alerts', label: 'Post when a price drops', type: 'toggle' },
    ],
  },
  {
    id: 'access',
    tab: 'access',
    title: 'Limits',
    fields: [
      { key: 'store_paused', label: 'Pause new purchases and deposits', type: 'toggle' },
      { key: 'maintenance_message', label: 'Maintenance message', placeholder: 'Store maintenance is in progress. Please try again soon.' },
      { key: 'max_deposit_limit', label: 'Largest single deposit', type: 'number', fallback: '500', money: true },
      { key: 'force_join_enabled', label: 'Customers must join the channels below', type: 'toggle' },
    ],
  },
  {
    id: 'zinipay',
    tab: 'payments',
    title: 'ZiniPay',
    master: { key: 'zinipay_enabled' },
    fields: [
      { key: 'zinipay_api_key', label: 'API key', type: 'password', secret: 'zinipay_api_key' },
      { key: 'zinipay_brand_url', label: 'Brand website URL', placeholder: 'https://myshop.com' },
      { key: 'zinipay_label', label: 'Name customers see', maxLength: 40, placeholder: 'bKash / Nagad · Instant' },
      { key: 'zinipay_min_deposit', label: 'Smallest deposit', type: 'number', fallback: '1', money: true },
    ],
    extra: 'zinipay',
  },
  {
    id: 'binance',
    tab: 'payments',
    title: 'Binance',
    master: { key: 'binance_enabled' },
    fields: [
      { key: 'binance_api_key', label: 'API key (Read-only)', type: 'password', secret: 'binance_api_key' },
      { key: 'binance_api_secret', label: 'API secret', type: 'password', secret: 'binance_api_secret' },
      { key: 'binance_pay_id', label: 'Our Binance UID', placeholder: '12345678' },
      {
        key: 'binance_coin',
        label: 'Coin',
        type: 'select',
        fallback: 'USDT',
        options: [
          { value: 'USDT', label: 'USDT' },
        ],
      },
      { key: 'binance_pay_rate', label: 'Rate per coin', type: 'number', fallback: '125' },
      { key: 'binance_pay_min', label: 'Smallest deposit', type: 'number', fallback: '100', money: true },
      { key: 'binance_pay_instructions', label: 'Custom instructions (optional)', type: 'textarea', rows: 2, placeholder: 'Send USDT to our Binance UID.' },
    ],
    extra: 'binance',
  },
];

export function Settings({ say, initialTab, onTabChange }: { say: Say; initialTab?: SettingsTab; onTabChange?: (tab: SettingsTab) => void }) {
  const [tab, setTab] = useState<SettingsTab>(TABS.some((item) => item.key === initialTab) ? (initialTab as SettingsTab) : 'store');
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
      if (key === 'zinipay_enabled' || key === 'binance_enabled') void refreshGateways();
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
        const changed = changedIn(section).length;
        const inputs = section.fields.filter((field) => field.type !== 'toggle');
        const toggles = section.fields.filter((field) => field.type === 'toggle');
        return (
          <Fragment key={section.id}>
            <form
              className={`panel${on ? '' : ' off'}`}
              onSubmit={(event) => {
                event.preventDefault();
                void save(section);
              }}
            >
              <header>
                <div>
                  <h2>{section.title}</h2>
                  {section.master && (on ? section.master.on : section.master.off) ? <p>{on ? section.master.on : section.master.off}</p> : null}
                </div>
                <div className="actions">
                  {changed ? (
                    <>
                      <span className="unsaved">Unsaved</span>
                      <button type="button" className="btn ghost small" onClick={() => discard(section)}>
                        Undo
                      </button>
                      <button type="submit" className="btn small" disabled={savingSection === section.id}>
                        {savingSection === section.id ? 'Saving…' : 'Save'}
                      </button>
                    </>
                  ) : null}
                  {section.master ? <Switch label={section.title} on={on} onChange={(next) => void flip(section.master!.key, next)} /> : null}
                </div>
              </header>
              {section.id === 'notice' ? (
                <WelcomeBannerField
                  bannerUrl={values.notice_banner || ''}
                  onBannerChange={(newUrl) => {
                    setValues((current) => ({ ...current, notice_banner: newUrl }));
                    setSaved((current) => ({ ...(current ?? {}), notice_banner: newUrl }));
                  }}
                  say={say}
                />
              ) : null}
              {inputs.length ? <div className="field-grid">{inputs.map(renderInput)}</div> : null}
              {toggles.map((field) => (
                <FlagRow key={field.key} label={field.label} hint={field.hint} on={isOn(field.key)} onChange={(next) => void flip(field.key, next)} />
              ))}
              {section.extra === 'zinipay' ? <ZiniPayExtra status={payStatus} setStatus={setPayStatus} say={say} /> : null}
              {section.extra === 'binance' ? <BinanceExtra status={binance} say={say} /> : null}
            </form>
            {section.id === 'binance' ? <PaymentMethods say={say} symbol={symbol} /> : null}
          </Fragment>
        );
      })}

      {tab === 'notifications' ? (
        <AdminNotifications
          say={say}
          values={values}
          setValues={setValues}
          setSaved={setSaved}
          flip={flip}
        />
      ) : null}
      {tab === 'notices' ? <UpdateChannels say={say} /> : null}
      {tab === 'access' ? <GateChannels say={say} /> : null}
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

function ZiniPayExtra({ status, setStatus, say }: { status: PaymentsStatus | null; setStatus: (status: PaymentsStatus | null) => void; say: Say }) {
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
    </>
  );
}

function BinanceExtra({ status, say }: { status: BinanceStatus | null; say: Say }) {
  const { busy, run } = useRunner(say);
  const ready = Boolean(status?.has_credentials);
  return (
    <>
      <div className="panel-actions">
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
    </>
  );
}

function WelcomeBannerField({
  bannerUrl,
  onBannerChange,
  say,
}: {
  bannerUrl: string;
  onBannerChange: (url: string) => void;
  say: Say;
}) {
  const [loading, setLoading] = useState(false);
  const [meta, setMeta] = useState<{
    has_banner: boolean;
    url?: string | null;
    width?: number | null;
    height?: number | null;
    size?: number | null;
    content_type?: string | null;
  } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [confirm, confirmModal] = useConfirm();

  useEffect(() => {
    api
      .getWelcomeBanner()
      .then((data) => {
        if (data && data.has_banner) {
          setMeta(data);
        } else {
          setMeta(null);
        }
      })
      .catch(() => setMeta(null));
  }, [bannerUrl]);

  async function handleUpload(file: File) {
    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      say('Please upload a valid JPG, PNG, or WebP image.', 'bad');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      say('File exceeds 5 MB limit. Please choose a smaller image.', 'bad');
      return;
    }

    setLoading(true);
    try {
      const res = await api.uploadWelcomeBanner(file);
      onBannerChange(res.banner.url);
      setMeta({
        has_banner: true,
        url: res.banner.url,
        width: res.banner.width,
        height: res.banner.height,
        size: res.banner.size,
        content_type: res.banner.content_type,
      });
      say('Welcome banner uploaded successfully.');
    } catch (cause) {
      say(errorText(cause, 'Could not upload banner.'), 'bad');
    } finally {
      setLoading(false);
    }
  }

  async function handleRemove() {
    const confirmed = await confirm('Remove Welcome Banner', 'Are you sure you want to remove the bot welcome banner?', 'Remove');
    if (!confirmed) return;
    setLoading(true);
    try {
      await api.deleteWelcomeBanner();
      onBannerChange('');
      setMeta(null);
      say('Welcome banner removed.');
    } catch (cause) {
      say(errorText(cause, 'Could not remove banner.'), 'bad');
    } finally {
      setLoading(false);
    }
  }

  const activeUrl = meta?.url || bannerUrl;
  const hasActiveBanner = Boolean(activeUrl);


  return (
    <div className="welcome-banner-wrapper">
      <div className="welcome-banner-header">
        <label className="field-title">Bot Welcome Banner</label>
        <div className="banner-specs-pill">
          <span>Recommended: 1280 × 720 px (16:9) or 1200 × 600 px · Max 5 MB</span>
        </div>
      </div>

      {hasActiveBanner ? (
        <div className="banner-preview-card">
          <div className="banner-image-box">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={activeUrl} alt="Welcome Banner Preview" />
          </div>
          <div className="banner-card-meta">
            <div className="banner-status-info">
              <span className="badge-active">● Active Banner</span>
              {meta?.width && meta?.height ? (
                <span className="banner-dim-info">
                  {meta.width} × {meta.height} px
                  {meta.size ? ` · ${(meta.size / 1024).toFixed(0)} KB` : ''}
                  {meta.content_type ? ` · ${meta.content_type.replace('image/', '').toUpperCase()}` : ''}
                </span>
              ) : (
                <span className="banner-dim-info">External Image / Telegram File</span>
              )}
            </div>
            <div className="banner-card-actions">
              <button
                type="button"
                className="btn small"
                disabled={loading}
                onClick={() => fileInputRef.current?.click()}
              >
                {loading ? 'Uploading…' : 'Change Image'}
              </button>
              <button
                type="button"
                className="btn danger small ghost"
                disabled={loading}
                onClick={handleRemove}
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div
          className={`banner-dropzone ${dragOver ? 'drag-over' : ''} ${loading ? 'busy' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files?.[0];
            if (file) void handleUpload(file);
          }}
          onClick={() => {
            if (!loading) fileInputRef.current?.click();
          }}
        >
          <div className="dropzone-icon">
            <UploadCloud size={32} />
          </div>
          <div className="dropzone-text">
            <strong>{loading ? 'Uploading banner…' : 'Click to upload welcome banner or drag & drop'}</strong>
            <p>JPG, PNG, or WebP up to 5 MB</p>
          </div>
          <button type="button" className="btn small" disabled={loading}>
            Browse Image
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleUpload(file);
          e.target.value = '';
        }}
      />

      {confirmModal}
    </div>
  );
}


