'use client';

import React, { useState } from 'react';
import { Eye, EyeOff, Check, Key, Globe, ExternalLink, RefreshCw, AlertCircle } from 'lucide-react';
import { api, type PaymentsStatus } from '@/lib/api';
import { Switch, errorText, type Say } from './ui';

interface ZiniPayGatewayProps {
  say: Say;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
  payStatus: PaymentsStatus | null;
  setPayStatus: (status: PaymentsStatus | null) => void;
  refreshGateways: () => Promise<void>;
  symbol?: string;
  isModal?: boolean;
}

export function ZiniPayGateway({
  say,
  values,
  setValues,
  setSaved,
  payStatus,
  setPayStatus,
  refreshGateways,
  symbol = '৳',
  isModal = false,
}: ZiniPayGatewayProps) {
  const [showSecret, setShowSecret] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [isEditingKey, setIsEditingKey] = useState(false);
  const [busy, setBusy] = useState(false);

  // Checkout form state
  const currentKey = (values.zinipay_api_key || '').trim();
  const isConfigured = Boolean(currentKey || payStatus?.has_api_key);
  const webEnabled = values.zinipay_web_gateway_enabled === '1';

  // Checkout fields
  const [webForm, setWebForm] = useState({
    brand_url: values.zinipay_brand_url || '',
    label: values.zinipay_label || 'Instant Deposit',
    min_deposit: values.zinipay_min_deposit || '10',
  });
  const [webFormDirty, setWebFormDirty] = useState(false);

  // Save new API Key
  const handleSaveKey = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanKey = newKey.trim();
    if (!cleanKey) return;

    setBusy(true);
    try {
      await api.updateSettings({
        zinipay_api_key: cleanKey,
        zinipay_enabled: '1',
      });
      setValues((prev) => ({
        ...prev,
        zinipay_api_key: cleanKey,
        zinipay_enabled: '1',
      }));
      setSaved((prev) => ({
        ...(prev ?? {}),
        zinipay_api_key: cleanKey,
        zinipay_enabled: '1',
      }));
      setNewKey('');
      setIsEditingKey(false);
      await refreshGateways();
      say('ZiniPay API key saved.', 'good');
    } catch (err) {
      say(errorText(err, 'Failed to save ZiniPay API key.'), 'bad');
    } finally {
      setBusy(false);
    }
  };

  // Remove API Key
  const handleRemoveKey = async () => {
    setBusy(true);
    try {
      await api.updateSettings({
        zinipay_api_key: '',
        zinipay_enabled: '0',
        zinipay_web_gateway_enabled: '0',
      });
      setValues((prev) => ({
        ...prev,
        zinipay_api_key: '',
        zinipay_enabled: '0',
        zinipay_web_gateway_enabled: '0',
      }));
      setSaved((prev) => ({
        ...(prev ?? {}),
        zinipay_api_key: '',
        zinipay_enabled: '0',
        zinipay_web_gateway_enabled: '0',
      }));
      setNewKey('');
      setIsEditingKey(false);
      await refreshGateways();
      say('ZiniPay API key removed.', 'good');
    } catch (err) {
      say(errorText(err, 'Failed to remove API key.'), 'bad');
    } finally {
      setBusy(false);
    }
  };

  // Toggle Web Checkout
  const handleToggleWebCheckout = async (on: boolean) => {
    const val = on ? '1' : '0';
    setValues((prev) => ({ ...prev, zinipay_web_gateway_enabled: val }));
    try {
      await api.updateSettings({ zinipay_web_gateway_enabled: val });
      setSaved((prev) => ({ ...(prev ?? {}), zinipay_web_gateway_enabled: val }));
      await refreshGateways();
      say(on ? 'Hosted web checkout enabled.' : 'Hosted web checkout disabled.');
    } catch (err) {
      setValues((prev) => ({ ...prev, zinipay_web_gateway_enabled: on ? '0' : '1' }));
      say(errorText(err, 'Failed to update checkout status.'), 'bad');
    }
  };

  // Save Web Checkout Fields
  const handleSaveWebForm = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.updateSettings({
        zinipay_brand_url: webForm.brand_url.trim(),
        zinipay_label: webForm.label.trim(),
        zinipay_min_deposit: webForm.min_deposit.trim(),
      });
      setValues((prev) => ({
        ...prev,
        zinipay_brand_url: webForm.brand_url.trim(),
        zinipay_label: webForm.label.trim(),
        zinipay_min_deposit: webForm.min_deposit.trim(),
      }));
      setSaved((prev) => ({
        ...(prev ?? {}),
        zinipay_brand_url: webForm.brand_url.trim(),
        zinipay_label: webForm.label.trim(),
        zinipay_min_deposit: webForm.min_deposit.trim(),
      }));
      setWebFormDirty(false);
      await refreshGateways();
      say('Checkout settings saved.', 'good');
    } catch (err) {
      say(errorText(err, 'Failed to save checkout settings.'), 'bad');
    } finally {
      setBusy(false);
    }
  };

  // Gateway test actions
  const handleTestConnection = async () => {
    setBusy(true);
    try {
      const res = await api.testPayments();
      say(res.message || 'Connection successful.', 'good');
    } catch (err) {
      say(errorText(err, 'Connection test failed.'), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const handleTestInvoice = async () => {
    setBusy(true);
    try {
      const res = await api.testPaymentPage();
      if (!res.ok) throw new Error(res.message);
      if (res.payment_url) {
        window.open(res.payment_url, '_blank', 'noopener');
      }
      say(res.message || 'Test invoice opened.', 'good');
    } catch (err) {
      say(errorText(err, 'Failed to generate test invoice.'), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const handleCheckUnpaid = async () => {
    setBusy(true);
    try {
      const res = await api.checkPendingPayments();
      const updated = await api.paymentsStatus().catch(() => null);
      if (updated) setPayStatus(updated);
      say(res.checked ? `Checked ${res.checked} unpaid payments.` : 'Nothing unpaid.', 'good');
    } catch (err) {
      say(errorText(err, 'Failed to check unpaid payments.'), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const bodyContent = (
    <div style={{ display: 'grid', gap: 12 }}>
      {isModal && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            background: 'var(--surface-2)',
            borderRadius: '8px',
            border: '1px solid var(--border)',
          }}
        >
          <strong style={{ fontSize: '13.5px', color: 'var(--text)' }}>
            Auto Verification Gateway
          </strong>
          <span className={`pill ${isConfigured ? 'good' : ''}`}>
            {isConfigured ? 'Configured' : 'Not configured'}
          </span>
        </div>
      )}

      {/* Section 1: API Key */}
      <div className="zinipay-api-block" style={{ display: 'grid', gap: 8 }}>
          <label className="field" style={{ margin: 0 }}>
            <span style={{ fontWeight: 600, fontSize: '13px' }}>API Key</span>
            {isConfigured && !isEditingKey ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '9px 12px',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  background: 'var(--surface-2)',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Check size={14} style={{ color: 'var(--positive)' }} />
                  <span style={{ fontFamily: 'monospace' }}>
                    {showSecret ? currentKey : '••••••••••••••••••••••••••••••••'}
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    style={{
                      background: 'none',
                      border: 0,
                      cursor: 'pointer',
                      color: 'var(--muted)',
                      padding: 2,
                      display: 'grid',
                      placeItems: 'center',
                    }}
                    title={showSecret ? 'Hide key' : 'Show key'}
                  >
                    {showSecret ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    className="btn ghost tiny"
                    onClick={() => setIsEditingKey(true)}
                  >
                    Change
                  </button>
                  <button
                    type="button"
                    className="btn ghost tiny danger"
                    onClick={handleRemoveKey}
                    disabled={busy}
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="password"
                  placeholder="Enter ZiniPay API key..."
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  autoComplete="new-password"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="btn small"
                  disabled={busy || !newKey.trim()}
                  onClick={() => void handleSaveKey()}
                >
                  Save Key
                </button>
                {isConfigured && (
                  <button
                    type="button"
                    className="btn ghost small"
                    onClick={() => {
                      setIsEditingKey(false);
                      setNewKey('');
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            )}
          </label>
        </div>

        {/* Section 2: Hosted Web Checkout (Shown only when API key is configured) */}
        {isConfigured && (
          <div
            className="zinipay-web-block"
            style={{
              borderTop: '1px solid var(--line)',
              paddingTop: 12,
              display: 'grid',
              gap: 10,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
              }}
            >
              <strong style={{ fontSize: '13.5px', color: 'var(--text)' }}>
                Hosted Web Checkout
              </strong>
              <Switch
                on={webEnabled}
                onChange={handleToggleWebCheckout}
                label="Hosted Web Checkout"
              />
            </div>

            {webEnabled && (
              <form onSubmit={handleSaveWebForm} style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <label className="field" style={{ margin: 0 }}>
                    <span style={{ fontSize: '12.5px', fontWeight: 500 }}>Checkout button label</span>
                    <input
                      type="text"
                      maxLength={40}
                      placeholder="Instant Deposit"
                      value={webForm.label}
                      onChange={(e) => {
                        setWebForm({ ...webForm, label: e.target.value });
                        setWebFormDirty(true);
                      }}
                    />
                  </label>

                  <label className="field" style={{ margin: 0 }}>
                    <span style={{ fontSize: '12.5px', fontWeight: 500 }}>Smallest deposit (BDT)</span>
                    <input
                      type="number"
                      min="1"
                      placeholder="50"
                      value={webForm.min_deposit}
                      onChange={(e) => {
                        setWebForm({ ...webForm, min_deposit: e.target.value });
                        setWebFormDirty(true);
                      }}
                    />
                  </label>
                </div>

                <label className="field" style={{ margin: 0 }}>
                  <span style={{ fontSize: '12.5px', fontWeight: 500 }}>Brand website URL</span>
                  <input
                    type="url"
                    placeholder={typeof window !== 'undefined' ? `${window.location.origin} (Auto-detected if empty)` : 'Auto-detected if empty'}
                    value={webForm.brand_url}
                    onChange={(e) => {
                      setWebForm({ ...webForm, brand_url: e.target.value });
                      setWebFormDirty(true);
                    }}
                  />
                </label>

                {payStatus && (
                  <div className="zinipay-stats-card">
                    <div className="zinipay-metrics-row">
                      <span className="zinipay-metric-pill completed">
                        <span className="zinipay-metric-dot good" />
                        <strong>{payStatus.counts.completed ?? 0}</strong> Paid
                      </span>
                      <span className="zinipay-metric-pill pending">
                        <span className="zinipay-metric-dot warn" />
                        <strong>{payStatus.counts.pending ?? 0}</strong> Unpaid
                      </span>
                      <span className="zinipay-metric-pill failed">
                        <span className="zinipay-metric-dot bad" />
                        <strong>{payStatus.counts.failed ?? 0}</strong> Failed
                      </span>
                      {payStatus.public_url && (
                        <span className="zinipay-site-tag">
                          <code>{payStatus.public_url.replace(/^https?:\/\//, '')}</code>
                        </span>
                      )}
                    </div>

                    {payStatus.last_error && (
                      <div className="zinipay-error-banner">
                        <AlertCircle size={15} className="zinipay-error-icon" />
                        <div className="zinipay-error-text">
                          <strong>Gateway Error:</strong> {payStatus.last_error}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <div className="zinipay-actions-toolbar">
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn ghost tiny"
                      disabled={busy}
                      onClick={() => void handleTestConnection()}
                    >
                      Test Connection
                    </button>
                    <button
                      type="button"
                      className="btn ghost tiny"
                      disabled={busy}
                      onClick={() => void handleTestInvoice()}
                    >
                      Test Payment
                    </button>
                    <button
                      type="button"
                      className="btn ghost tiny"
                      disabled={busy}
                      onClick={() => void handleCheckUnpaid()}
                    >
                      Check Unpaid
                    </button>
                  </div>

                  {webFormDirty && (
                    <button type="submit" className="btn small" disabled={busy}>
                      Save Changes
                    </button>
                  )}
                </div>
              </form>
            )}
          </div>
        )}
      </div>
  );

  if (isModal) {
    return <div className="zinipay-gateway-modal-inner">{bodyContent}</div>;
  }

  return (
    <section className="panel settings-card zinipay-gateway-card">
      <header>
        <div>
          <h2>ZiniPay Gateway</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`pill ${isConfigured ? 'good' : ''}`}>
            {isConfigured ? 'Configured' : 'Not configured'}
          </span>
        </div>
      </header>
      {bodyContent}
    </section>
  );
}
