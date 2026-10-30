'use client';

import React, { useEffect, useState } from 'react';
import {
  Plus,
  Edit2,
  Trash2,
  Copy,
  Zap,
  Smartphone,
  RefreshCw,
  Eye,
  EyeOff,
  Check,
  ChevronRight,
  ArrowLeft,
} from 'lucide-react';
import { api, type DepositMethod, type PaymentsStatus } from '@/lib/api';
import { Modal, Switch, errorText, useConfirm, type Say } from '@/components/ui';
import { ZiniPayGateway } from './ZiniPayGateway';
import { CustomSelect } from './CustomSelect';

const METHOD_PRESETS = [
  {
    key: 'bkash',
    label: 'bKash',
    name: 'bKash',
    type: 'personal',
    badge: 'bK',
    brandClass: 'bkash',
    subtitle: 'Mobile Banking',
    placeholder: '01XXXXXXXXX',
    instructions: '',
    min_deposit: 50,
    sort_order: 1,
  },
  {
    key: 'nagad',
    label: 'Nagad',
    name: 'Nagad',
    type: 'personal',
    badge: 'NG',
    brandClass: 'nagad',
    subtitle: 'Mobile Banking',
    placeholder: '01XXXXXXXXX',
    instructions: '',
    min_deposit: 50,
    sort_order: 2,
  },
  {
    key: 'rocket',
    label: 'Rocket',
    name: 'Rocket',
    type: 'personal',
    badge: 'RK',
    brandClass: 'rocket',
    subtitle: 'Mobile Banking',
    placeholder: '01XXXXXXXXX',
    instructions: '',
    min_deposit: 50,
    sort_order: 3,
  },
  {
    key: 'binance',
    label: 'Binance',
    name: 'Binance',
    type: 'crypto',
    badge: 'BN',
    brandClass: 'binance',
    subtitle: 'Crypto / USDT',
    placeholder: '750176717',
    instructions: '',
    min_deposit: 1,
    sort_order: 4,
  },
];

const ACCOUNT_TYPE_OPTIONS = [
  { value: 'personal', label: 'Personal (Send Money)' },
  { value: 'agent', label: 'Agent (Cash Out)' },
  { value: 'merchant', label: 'Merchant (Payment)' },
];

const VERIFICATION_MODE_OPTIONS = [
  { value: 'none', label: 'Manual Review' },
  { value: 'zinipay', label: 'ZiniPay' },
];

export function PaymentMethods({
  say,
  symbol = '৳',
  zinipayActive = false,
  values,
  savedValues,
  setValues,
  setSaved,
  payStatus,
  setPayStatus,
  refreshGateways,
}: {
  say: Say;
  symbol?: string;
  zinipayActive?: boolean;
  values?: Record<string, string>;
  savedValues?: Record<string, string>;
  setValues?: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved?: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
  payStatus?: PaymentsStatus | null;
  setPayStatus?: (status: PaymentsStatus | null) => void;
  refreshGateways?: () => Promise<void>;
}) {
  const [confirm, confirmDialog] = useConfirm();
  const [methods, setMethods] = useState<DepositMethod[]>([]);
  const [methodsLoading, setMethodsLoading] = useState(false);
  const [editingMethod, setEditingMethod] = useState<DepositMethod | null>(null);
  const [isAddingMethod, setIsAddingMethod] = useState(false);
  const [isZinipayModalOpen, setIsZinipayModalOpen] = useState(false);
  const [selectedProviderKey, setSelectedProviderKey] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const [methodForm, setMethodForm] = useState<{
    name: string;
    account_info: string;
    account_type: string;
    min_deposit: number | string;
    rate_to_currency: number | string;
    sort_order: number | string;
    auto_verify: 'none' | 'zinipay';
    instructions: string;
    is_active: boolean;
    api_key: string;
    api_secret: string;
    custom_emoji_id: string;
  }>({
    name: '',
    account_info: '',
    account_type: 'personal',
    min_deposit: '10',
    rate_to_currency: '1.0',
    sort_order: '1',
    auto_verify: 'zinipay',
    instructions: '',
    is_active: true,
    api_key: '',
    api_secret: '',
    custom_emoji_id: '',
  });

  const [showSecret, setShowSecret] = useState(false);
  const [savingMethod, setSavingMethod] = useState(false);
  const [methodError, setMethodError] = useState('');
  const [clearCredentials, setClearCredentials] = useState(false);

  // Load payment methods
  const fetchMethods = async () => {
    setMethodsLoading(true);
    try {
      const res = await api.depositMethods();
      const list = Array.isArray(res) ? res : ((res as any)?.methods ?? []);
      setMethods(list);
    } catch (err) {
      say(errorText(err, 'Failed to load deposit methods'), 'bad');
    } finally {
      setMethodsLoading(false);
    }
  };

  useEffect(() => {
    void fetchMethods();
  }, []);

  // Toggle Deposit Method
  const handleToggleMethod = async (method: DepositMethod) => {
    const isCurrentlyActive = Boolean(method.is_active);
    const willActivate = !isCurrentlyActive;

    const confirmed = await confirm(
      willActivate ? 'Activate payment method?' : 'Deactivate payment method?',
      willActivate
        ? `Are you sure you want to activate "${method.name}"?`
        : `Are you sure you want to deactivate "${method.name}"?`,
      willActivate ? 'Activate' : 'Deactivate',
      !willActivate
    );
    if (!confirmed) return;

    try {
      const res = await api.toggleDepositMethod(method.id);
      const newActive = res.is_active === 1;
      setMethods((prev) =>
        prev.map((m) => (m.id === method.id ? { ...m, is_active: newActive ? 1 : 0 } : m))
      );
      say(`Method "${method.name}" ${newActive ? 'activated' : 'deactivated'}`, 'good');
    } catch (err) {
      say(errorText(err, 'Failed to toggle deposit method'), 'bad');
    }
  };

  // Delete Deposit Method
  const handleDeleteMethod = async (id: number, name: string) => {
    if (
      !(await confirm(
        'Delete payment method?',
        `Are you sure you want to delete "${name}"? Past deposits will remain in history.`,
        'Delete'
      ))
    )
      return;
    try {
      await api.deleteDepositMethod(id);
      setMethods((prev) => prev.filter((m) => m.id !== id));
      say(`Method "${name}" deleted`, 'good');
    } catch (err) {
      say(errorText(err, 'Failed to delete deposit method'), 'bad');
    }
  };

  const selectedPreset = METHOD_PRESETS.find((p) => p.key === selectedProviderKey);

  const isBinanceMethod =
    selectedProviderKey === 'binance' ||
    methodForm.name.trim().toLowerCase().includes('binance') ||
    methodForm.account_type === 'crypto';

  const limitSettings = savedValues ?? values;
  const globalMaximum = Number(limitSettings?.max_deposit_limit ?? 400);
  const exchangeRate = Number(limitSettings?.usd_rate ?? 125);
  const maximumPayment = globalMaximum * (isBinanceMethod ? 1 : exchangeRate);
  const paymentUnit = isBinanceMethod ? 'USDT' : 'BDT';
  const maximumLabel = `${maximumPayment.toLocaleString('en-US', { maximumFractionDigits: 4 })} ${paymentUnit}`;

  // Save Method (Create or Update)
  const handleSaveMethod = async (e: React.FormEvent) => {
    e.preventDefault();
    if (savingMethod) return;
    setMethodError('');
    const minimum = Number(methodForm.min_deposit);
    if (!Number.isFinite(minimum) || minimum <= 0 || minimum > maximumPayment) {
      setMethodError(`Minimum deposit must be greater than zero and no more than ${maximumLabel}.`);
      return;
    }
    setSavingMethod(true);
    try {
      const payload: any = {
        name: isBinanceMethod ? (methodForm.name.trim() || 'Binance') : methodForm.name.trim(),
        account_info: methodForm.account_info.trim(),
        account_type: isBinanceMethod ? 'crypto' : methodForm.account_type,
        min_deposit: minimum,
        rate_to_currency: parseFloat(String(methodForm.rate_to_currency)) || 1.0,
        sort_order: parseInt(String(methodForm.sort_order), 10) || 1,
        instructions: methodForm.instructions.trim(),
        is_active: methodForm.is_active ? 1 : 0,
        custom_emoji_id: methodForm.custom_emoji_id?.trim() || undefined,
      };

      if (isBinanceMethod) {
        if (Boolean(methodForm.api_key) !== Boolean(methodForm.api_secret)) {
          say('Both Binance API Key and Secret are required.', 'bad');
          return;
        }
        if (clearCredentials) {
          payload.clear_api_credentials = true;
        } else if (methodForm.api_key && methodForm.api_secret) {
          payload.api_key = methodForm.api_key.trim();
          payload.api_secret = methodForm.api_secret.trim();
        }
      } else {
        payload.auto_verify = methodForm.auto_verify || 'none';
      }

      if (editingMethod) {
        await api.updateDepositMethod(editingMethod.id, payload);
        say('Payment method updated', 'good');
        setEditingMethod(null);
        setSelectedProviderKey(null);
        setClearCredentials(false);
        await fetchMethods();
      } else {
        await api.createDepositMethod(payload);
        say('Payment method added', 'good');
        setIsAddingMethod(false);
        setSelectedProviderKey(null);
        setClearCredentials(false);
        await fetchMethods();
      }
    } catch (err) {
      setMethodError(errorText(err, 'Failed to save payment method'));
    } finally {
      setSavingMethod(false);
    }
  };

  const openAddModal = () => {
    setMethodError('');
    setEditingMethod(null);
    setSelectedProviderKey(null);
    setClearCredentials(false);
    setMethodForm({
      name: '',
      account_info: '',
      account_type: 'personal',
      min_deposit: '10',
      rate_to_currency: '1.0',
      sort_order: String(methods.length + 1),
      auto_verify: zinipayActive ? 'zinipay' : 'none',
      instructions: '',
      is_active: true,
      api_key: '',
      api_secret: '',
      custom_emoji_id: '',
    });
    setShowSecret(false);
    setIsAddingMethod(true);
  };

  const openEditModal = (method: DepositMethod) => {
    setMethodError('');
    setEditingMethod(method);
    setClearCredentials(false);
    const n = method.name.toLowerCase();
    const key = n.includes('bkash')
      ? 'bkash'
      : n.includes('nagad')
      ? 'nagad'
      : n.includes('rocket')
      ? 'rocket'
      : n.includes('binance') || method.account_type === 'crypto'
      ? 'binance'
      : null;
    setSelectedProviderKey(key);
    setMethodForm({
      name: method.name,
      account_info: method.account_info,
      account_type:
        key === 'binance' || method.account_type === 'crypto'
          ? 'crypto'
          : method.account_type || 'personal',
      min_deposit: String(method.min_deposit ?? 10),
      rate_to_currency: String(method.rate_to_currency ?? 1.0),
      sort_order: String(method.sort_order ?? 1),
      auto_verify: method.auto_verify === 'zinipay' ? 'zinipay' : 'none',
      instructions: method.instructions || '',
      is_active: Boolean(method.is_active),
      api_key: '',
      api_secret: '',
      custom_emoji_id: method.custom_emoji_id || '',
    });
    setShowSecret(false);
  };

  const applyPreset = (preset: (typeof METHOD_PRESETS)[0]) => {
    setMethodError('');
    setSelectedProviderKey(preset.key);
    setMethodForm((prev) => ({
      ...prev,
      name: preset.name,
      account_type: preset.type,
      min_deposit: String(preset.min_deposit),
      sort_order: String(preset.sort_order || methods.length + 1),
      instructions: preset.instructions,
      custom_emoji_id: '',
      auto_verify: preset.key !== 'binance' && zinipayActive ? 'zinipay' : 'none',
      api_key: preset.key === 'binance' ? prev.api_key : '',
      api_secret: preset.key === 'binance' ? prev.api_secret : '',
    }));
  };

  const copyToClipboard = (id: number, text: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      say('Copied to clipboard', 'good');
      setTimeout(() => {
        setCopiedId((prev) => (prev === id ? null : prev));
      }, 2000);
    }
  };

  // Sort methods strictly by sort_order ASC, then id ASC
  const sortedMethods = [...methods].sort(
    (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id
  );

  return (
    <div className="payment-methods-screen">
      <section className="panel payment-accounts-panel">
        <header>
          <div className="payment-section-copy">
            <h2>
              Payment accounts <span className="payment-account-count">{methods.length}</span>
            </h2>
          </div>
          <div className="filters payment-account-actions">
            {values && setValues && setSaved && refreshGateways && (
              <button
                type="button"
                className={`btn ghost small gateway-config-btn${zinipayActive ? ' is-configured' : ''}`}
                onClick={() => setIsZinipayModalOpen(true)}
                title="ZiniPay settings"
              >
                <Zap size={14} />
                <span>ZiniPay Gateway</span>
                <span className={`pill ${zinipayActive ? 'good' : 'muted'} gateway-status-pill`}>
                  {zinipayActive ? 'Configured' : 'Not set'}
                </span>
              </button>
            )}
            <button type="button" className="btn small" onClick={openAddModal}>
              <Plus size={14} /> Add Payment Method
            </button>
            <button
              type="button"
              className="btn ghost small"
              onClick={fetchMethods}
              disabled={methodsLoading}
              aria-label="Refresh payment accounts"
              title="Refresh payment accounts"
            >
              <RefreshCw size={14} className={methodsLoading ? 'refreshing' : ''} />
            </button>
          </div>
        </header>

        <div className="payment-account-list-wrap">
          {methodsLoading && methods.length === 0 ? (
            <p className="payment-list-message" role="status" aria-live="polite">
              Loading payment methods…
            </p>
          ) : methods.length === 0 ? (
            <div className="payment-empty-state">
              <span className="payment-empty-icon">
                <Smartphone size={22} />
              </span>
              <strong>No payment accounts yet</strong>
              <p>Add an account to accept deposits.</p>
              <button type="button" className="btn small" onClick={openAddModal}>
                <Plus size={14} /> Add first account
              </button>
            </div>
          ) : (
            <div className="payment-method-list">
              {sortedMethods.map((method) => {
                const isActive = Boolean(method.is_active);
                const nameLower = (method.name || '').toLowerCase();
                const isBkash = nameLower.includes('bkash');
                const isNagad = nameLower.includes('nagad');
                const isRocket = nameLower.includes('rocket');
                const isBinance = nameLower.includes('binance') || method.account_type === 'crypto';

                let brandClass = '';
                let brandBadge: React.ReactNode = <span>PM</span>;

                if (isBkash) {
                  brandClass = 'bkash';
                  brandBadge = <span>bK</span>;
                } else if (isNagad) {
                  brandClass = 'nagad';
                  brandBadge = <span>NG</span>;
                } else if (isRocket) {
                  brandClass = 'rocket';
                  brandBadge = <span>RK</span>;
                } else if (isBinance) {
                  brandClass = 'binance';
                  brandBadge = <Zap size={18} />;
                }

                const typeLabels: Record<string, string> = {
                  personal: 'Personal (Send Money)',
                  agent: 'Agent (Cash Out)',
                  merchant: 'Merchant (Payment)',
                  crypto: 'Crypto',
                };

                return (
                  <div
                    key={method.id}
                    className={`payment-method-item${isActive ? ' is-active' : ' is-disabled'}`}
                  >
                    <div className="payment-method-info">
                      <span className={`payment-method-icon ${brandClass}`}>{brandBadge}</span>
                      <div className="payment-method-copy">
                        <div className="payment-method-title">
                          <strong>{method.name || (isBinance ? 'Binance' : 'Deposit')}</strong>
                          {!isBinance && (
                            <span
                              className={`pill ${
                                method.account_type === 'agent'
                                  ? 'info'
                                  : method.account_type === 'merchant'
                                  ? 'warn'
                                  : 'good'
                              } payment-type-pill`}
                            >
                              {typeLabels[method.account_type || 'personal'] || 'Personal (Send Money)'}
                            </span>
                          )}

                          <span
                            className={`payment-availability${isActive ? ' available' : ' paused'}`}
                          >
                            {isActive ? 'Active' : 'Inactive'}
                          </span>

                          {/* Verification badge only when automated */}
                          {isBinance ? (
                            method.has_api_credentials ? (
                              <span className="pill good payment-type-pill">
                                API Connected
                              </span>
                            ) : null
                          ) : method.auto_verify === 'zinipay' ? (
                            <span className="pill good payment-type-pill">
                              Auto (ZiniPay)
                            </span>
                          ) : null}
                        </div>
                        <div className="payment-method-details">
                          <code>{method.account_info}</code>
                          <button
                            type="button"
                            onClick={() => copyToClipboard(method.id, method.account_info)}
                            className="payment-copy-button"
                            aria-label="Copy account details"
                            title="Copy"
                          >
                            {copiedId === method.id ? (
                              <Check size={13} style={{ color: 'var(--positive)' }} />
                            ) : (
                              <Copy size={13} />
                            )}
                          </button>
                          <span className="payment-minimum">
                            Minimum deposit {isBinance ? `${method.min_deposit} USDT` : `${symbol}${method.min_deposit} BDT`}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Action controls with ON/OFF switch */}
                    <div className="payment-method-actions">
                      <div className="payment-action-switch-wrap">
                        <Switch
                          on={isActive}
                          onChange={() => handleToggleMethod(method)}
                          label={`Toggle ${method.name}`}
                        />
                        <span
                          className={`payment-switch-status ${
                            isActive ? 'is-active' : 'is-paused'
                          }`}
                        >
                          {isActive ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                      <div className="payment-method-btns">
                        <button
                          type="button"
                          className="btn ghost small"
                          onClick={() => openEditModal(method)}
                          title={`Edit ${method.name}`}
                        >
                          <Edit2 size={13} /> Edit
                        </button>
                        <button
                          type="button"
                          className="btn ghost small danger"
                          onClick={() => handleDeleteMethod(method.id, method.name)}
                          aria-label={`Delete ${method.name}`}
                          title={`Delete ${method.name}`}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* Add / Edit Payment Method Modal */}
      {(isAddingMethod || editingMethod) && (
        <Modal
          title={
            editingMethod
              ? `Edit ${
                  editingMethod.name ||
                  (editingMethod.account_type === 'crypto' ? 'Binance' : 'Payment Method')
                }`
              : selectedPreset
              ? `Add ${selectedPreset.label}`
              : 'Add Payment Method'
          }
          wide
          className="pm-method-modal"
          onClose={() => {
            if (savingMethod) return;
            setIsAddingMethod(false);
            setEditingMethod(null);
            setSelectedProviderKey(null);
            setShowSecret(false);
          }}
          footer={
            isAddingMethod && !selectedProviderKey ? (
              <button
                type="button"
                className="btn ghost"
                onClick={() => {
                  setIsAddingMethod(false);
                  setSelectedProviderKey(null);
                }}
              >
                Cancel
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="btn ghost"
                  disabled={savingMethod}
                  onClick={() => {
                    if (isAddingMethod) {
                      setSelectedProviderKey(null);
                    } else {
                      setEditingMethod(null);
                    }
                    setShowSecret(false);
                  }}
                >
                  {isAddingMethod ? 'Back' : 'Cancel'}
                </button>
                <button type="submit" form="pm-method-form" className="btn" disabled={savingMethod}>
                  {savingMethod ? 'Saving…' : editingMethod ? 'Save Changes' : 'Create Method'}
                </button>
              </>
            )
          }
        >
          {isAddingMethod && !selectedProviderKey ? (
            /* Step 1: 4 Provider Selection Cards */
            <div className="pm-provider-selection">
              <div className="pm-provider-selection-head">
                <h3>Select Provider</h3>
              </div>
              <div className="pm-provider-cards-grid">
                {METHOD_PRESETS.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    className={`pm-provider-select-card ${preset.key}`}
                    onClick={() => applyPreset(preset)}
                  >
                    <div className={`pm-provider-select-badge ${preset.key}`}>
                      <span>{preset.badge}</span>
                    </div>
                    <div className="pm-provider-select-info">
                      <div className="pm-provider-select-title">
                        <strong>{preset.label}</strong>
                      </div>
                      <span className="pm-provider-select-sub">{preset.subtitle}</span>
                    </div>
                    <ChevronRight size={18} className="pm-provider-select-arrow" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Step 2: Form Configuration */
            <>
              {isAddingMethod && (
                <div className="pm-step2-header">
                  <button
                    type="button"
                    className="pm-back-btn"
                    onClick={() => setSelectedProviderKey(null)}
                  >
                    <ArrowLeft size={14} /> Providers
                  </button>
                  <div className="pm-presets-grid">
                    {METHOD_PRESETS.map((preset) => {
                      const isSelected = selectedProviderKey === preset.key;
                      return (
                        <button
                          key={preset.key}
                          type="button"
                          className={`pm-preset-card ${preset.key}${
                            isSelected ? ' is-selected' : ''
                          }`}
                          onClick={() => applyPreset(preset)}
                        >
                          {preset.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <form id="pm-method-form" onSubmit={handleSaveMethod} className="pm-form">
                <div className="pm-deposit-limit" id="pm-deposit-limit">
                  <div><span>Maximum per deposit</span><strong>{maximumLabel}</strong></div>
                  <p>Shared across payment methods. Change in Settings / General / Limits &amp; Rules.</p>
                </div>
                {methodError && <p className="dialog-error" role="alert">{methodError}</p>}
                {isBinanceMethod ? (
                  <>
                    <div className="pm-form-row">
                      <label className="field">
                        <span>Method name</span>
                        <input
                          type="text"
                          placeholder="Binance"
                          value={methodForm.name}
                          onChange={(e) => setMethodForm({ ...methodForm, name: e.target.value })}
                        />
                      </label>
                      <label className="field">
                        <span>Display Order</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          placeholder="1"
                          value={methodForm.sort_order}
                          onChange={(e) =>
                            setMethodForm({
                              ...methodForm,
                              sort_order: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>

                    <div className="pm-form-row is-binance">
                      <label className="field">
                        <span>Binance ID</span>
                        <input
                          type="text"
                          className="pm-input-mono"
                          placeholder="750176717"
                          value={methodForm.account_info}
                          onChange={(e) =>
                            setMethodForm({ ...methodForm, account_info: e.target.value })
                          }
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Minimum Deposit (USDT)</span>
                        <div className="pm-input-currency">
                          <input
                            type="number"
                            min="0.0001"
                            step="0.0001"
                            max={maximumPayment}
                            aria-describedby="pm-deposit-limit"
                            inputMode="decimal"
                            placeholder="1.00"
                            value={methodForm.min_deposit}
                            onChange={(e) =>
                              setMethodForm({
                                ...methodForm,
                                min_deposit: e.target.value,
                              })
                            }
                            required
                          />
                          <span className="pm-currency-tag">USDT</span>
                        </div>
                      </label>
                    </div>


                    <div className="pm-form-row">
                      <label className="field">
                        <span>API Key</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={methodForm.api_key}
                          placeholder={
                            editingMethod?.has_api_credentials
                              ? 'Configured (leave blank to keep)'
                              : 'Optional, for auto check'
                          }
                          onChange={(e) => setMethodForm({ ...methodForm, api_key: e.target.value })}
                        />
                      </label>
                      <label className="field">
                        <span>API Secret</span>
                        <div className="pm-password-input-wrap">
                          <input
                            type={showSecret ? 'text' : 'password'}
                            autoComplete="new-password"
                            value={methodForm.api_secret}
                            placeholder={
                              editingMethod?.has_api_credentials
                                ? 'Configured (leave blank to keep)'
                                : 'Optional'
                            }
                            onChange={(e) =>
                              setMethodForm({ ...methodForm, api_secret: e.target.value })
                            }
                          />
                          <button
                            type="button"
                            onClick={() => setShowSecret(!showSecret)}
                            className="pm-eye-button"
                            aria-label={showSecret ? 'Hide secret' : 'Show secret'}
                            title={showSecret ? 'Hide secret' : 'Show secret'}
                          >
                            {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        </div>
                      </label>
                    </div>

                    {editingMethod?.has_api_credentials && (
                      <div className="pm-credentials-status-bar" style={{ marginTop: '0.25rem' }}>
                        {clearCredentials ? (
                          <div
                            style={{
                              padding: '0.5rem 0.75rem',
                              background: 'rgba(239, 68, 68, 0.08)',
                              border: '1px solid rgba(239, 68, 68, 0.2)',
                              borderRadius: '6px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              fontSize: '0.8125rem',
                            }}
                          >
                            <span style={{ color: '#ef4444' }}>
                              API disconnected. Will switch to manual on save.
                            </span>
                            <button
                              type="button"
                              className="btn ghost tiny"
                              onClick={() => setClearCredentials(false)}
                            >
                              Undo
                            </button>
                          </div>
                        ) : (
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              fontSize: '0.8125rem',
                              padding: '0.25rem 0',
                            }}
                          >
                            <span
                              style={{
                                color: 'var(--positive, #10b981)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              <Check size={13} /> API connected
                            </span>
                            <button
                              type="button"
                              className="btn ghost tiny danger"
                              onClick={() => setClearCredentials(true)}
                              style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                            >
                              Disconnect
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="pm-form-row">
                      <label className="field">
                        <span>Method name</span>
                        <input
                          type="text"
                          placeholder="e.g. bKash"
                          value={methodForm.name}
                          onChange={(e) => setMethodForm({ ...methodForm, name: e.target.value })}
                          required
                        />
                      </label>

                      <label className="field">
                        <span>Account Type</span>
                        <CustomSelect
                          ariaLabel="Account Type"
                          width="100%"
                          minWidth={0}
                          value={methodForm.account_type}
                          onChange={(value) => setMethodForm({ ...methodForm, account_type: value })}
                          options={[
                            { value: 'personal', label: 'Personal (Send Money)' },
                            { value: 'agent', label: 'Agent (Cash Out)' },
                            { value: 'merchant', label: 'Merchant (Payment)' },
                          ]}
                        />
                      </label>
                    </div>

                    <div className="pm-form-row">
                      <label className="field">
                        <span>Account Number</span>
                        <input
                          type="text"
                          className="pm-input-mono"
                          placeholder={selectedPreset?.placeholder || '01XXXXXXXXX'}
                          value={methodForm.account_info}
                          onChange={(e) =>
                            setMethodForm({ ...methodForm, account_info: e.target.value })
                          }
                          required
                        />
                      </label>

                      <label className="field">
                        <span>Minimum Deposit (BDT)</span>
                        <input
                          type="number"
                          min="1"
                          step="0.01"
                          max={maximumPayment}
                          aria-describedby="pm-deposit-limit"
                          placeholder="50"
                          value={methodForm.min_deposit}
                          onChange={(e) =>
                            setMethodForm({
                              ...methodForm,
                              min_deposit: e.target.value,
                            })
                          }
                          required
                        />
                      </label>
                    </div>

                    <div className="pm-form-row">
                      <label className="field">
                        <span>Display Order</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          placeholder="1"
                          value={methodForm.sort_order}
                          onChange={(e) =>
                            setMethodForm({
                              ...methodForm,
                              sort_order: e.target.value,
                            })
                          }
                        />
                      </label>

                      <label className="field">
                        <span>Verification Mode</span>
                        <CustomSelect
                          ariaLabel="Verification Mode"
                          width="100%"
                          minWidth={0}
                          value={methodForm.auto_verify}
                          onChange={(value) => setMethodForm({ ...methodForm, auto_verify: value as 'none' | 'zinipay' })}
                          options={[
                            { value: 'none', label: 'Manual Review' },
                            { value: 'zinipay', label: 'ZiniPay', disabled: !zinipayActive },
                          ]}
                        />
                      </label>
                    </div>
                  </>
                )}

                <label className="field">
                  <span>Instructions</span>
                  <textarea
                    rows={2}
                    placeholder="Instructions shown to customers during deposit"
                    value={methodForm.instructions}
                    onChange={(e) => setMethodForm({ ...methodForm, instructions: e.target.value })}
                    className="pm-textarea"
                  />
                </label>

                {/* Clean Status Switch */}
                <div className="pm-status-switch-card">
                  <div className="pm-status-switch-info">
                    <div className="pm-switch-title-row">
                      <strong>Status</strong>
                      <span
                        className={`pm-status-text ${
                          methodForm.is_active ? 'is-active' : 'is-inactive'
                        }`}
                      >
                        {methodForm.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </div>
                  <div className="pm-status-switch-ctrl">
                    <Switch
                      on={methodForm.is_active}
                      onChange={(val) => setMethodForm({ ...methodForm, is_active: val })}
                      label="Status"
                    />
                  </div>
                </div>
              </form>
            </>
          )}
        </Modal>
      )}

      {/* ZiniPay Gateway Modal */}
      {isZinipayModalOpen && values && setValues && setSaved && refreshGateways && (
        <Modal
          title="ZiniPay Gateway Settings"
          className="zinipay-gateway-modal"
          onClose={() => setIsZinipayModalOpen(false)}
          footer={
            <button
              type="button"
              className="btn"
              onClick={() => setIsZinipayModalOpen(false)}
            >
              Done
            </button>
          }
        >
          <ZiniPayGateway
            say={say}
            values={values}
            setValues={setValues}
            setSaved={setSaved}
            payStatus={payStatus ?? null}
            setPayStatus={setPayStatus ?? (() => {})}
            refreshGateways={refreshGateways}
            symbol={symbol}
            isModal
          />
        </Modal>
      )}
      {confirmDialog}
    </div>
  );
}
