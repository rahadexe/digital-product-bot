'use client';

// Adding a way to pay starts with what kind it is, because a bKash number and a USDT address need
// different answers. Picking the kind fills in everything that follows from it - the rate, who checks
// the payment, the network - so the only questions left are the ones only the shop owner can answer.

import { useCallback, useEffect, useState } from 'react';
import { Smartphone, type LucideIcon } from 'lucide-react';
import { api, type DepositMethod } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { FlagRow, Modal, errorText, useConfirm, type Say } from './ui';
import { EmojiPicker } from './EmojiPicker';

type KindId = 'bkash' | 'nagad' | 'rocket';

type Kind = {
  id: KindId;
  title: string;
  blurb: string;
  icon: LucideIcon;
  defaults: { name: string; rate: number; auto_verify: 'none'; network: string; instructions?: string; custom_emoji_id?: string };
  account: { label: string; placeholder: string };
};

const KINDS: Kind[] = [
  {
    id: 'bkash',
    title: 'bKash',
    blurb: 'Personal, Agent or Merchant number.',
    icon: Smartphone,
    defaults: {
      name: 'bKash',
      rate: 1,
      auto_verify: 'none',
      network: '',
      instructions: '',
      custom_emoji_id: '6217678000977089090',
    },
    account: { label: 'bKash Number', placeholder: '01700000000' },
  },
  {
    id: 'nagad',
    title: 'Nagad',
    blurb: 'Personal or Merchant number.',
    icon: Smartphone,
    defaults: {
      name: 'Nagad',
      rate: 1,
      auto_verify: 'none',
      network: '',
      instructions: '',
      custom_emoji_id: '6217625168584380551',
    },
    account: { label: 'Nagad Number', placeholder: '01800000000' },
  },
  {
    id: 'rocket',
    title: 'Rocket',
    blurb: 'Personal or Merchant number.',
    icon: Smartphone,
    defaults: {
      name: 'Rocket',
      rate: 1,
      auto_verify: 'none',
      network: '',
      instructions: '',
      custom_emoji_id: '4911601033496494993',
    },
    account: { label: 'Rocket Number', placeholder: '01900000000' },
  },
];

function kindOf(method: DepositMethod): Kind {
  const name = (method.name || '').toLowerCase();
  if (name.includes('bkash') || name.includes('b-kash')) return KINDS[0];
  if (name.includes('nagad')) return KINDS[1];
  return KINDS[2];
}

type Draft = { kind: Kind; method: DepositMethod | null };

export function PaymentMethods({ say, symbol, zinipayActive }: { say: Say; symbol: string; zinipayActive?: boolean }) {
  const [methods, setMethods] = useState<DepositMethod[] | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const money = useMoney();

  const load = useCallback(() => api.depositMethods().then(setMethods).catch((cause) => say(errorText(cause), 'bad')), [say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(method: DepositMethod) {
    if (!(await confirm(`Delete ${method.name}?`, 'Past deposits made with it will stay in the history.', 'Delete method'))) return;
    try {
      await api.deleteDepositMethod(method.id);
      say('Deleted.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  const manualMethods = (methods ?? []).filter((m) => (m.auto_verify ?? 'none') === 'none');

  return (
    <>
      {confirmDialog}
      <section className="panel">
        <header>
          <div>
            <h2>Local Payment Accounts</h2>
          </div>
          <button type="button" className="btn small" onClick={() => setChoosing(true)}>
            Add account
          </button>
        </header>
        {!methods ? <p className="note">Loading…</p> : null}
        {methods && manualMethods.length === 0 ? (
          <p className="note">No payment accounts added yet.</p>
        ) : null}
        <div className="rows">
          {manualMethods.map((method) => (
            <div key={method.id} className={`row${method.is_active ? '' : ' off'}`}>
              <div className="text">
                <strong>
                  {method.name}
                  {method.is_active ? '' : ' · off'}
                </strong>
                <small>
                  from {money(method.min_deposit)} ·{' '}
                  <span className={`pill ${method.account_type === 'agent' ? 'info' : method.account_type === 'merchant' ? 'warn' : 'good'}`} style={{ textTransform: 'capitalize' }}>
                    {method.account_type || 'personal'} ({method.account_type === 'agent' ? 'Cash Out' : method.account_type === 'merchant' ? 'Payment' : 'Send Money'})
                  </span>
                </small>
                <code className="key" title={method.account_info}>
                  {method.account_info}
                </code>
              </div>
              <div className="row-actions">
                <button type="button" className="mini" onClick={() => setDraft({ kind: kindOf(method), method })}>
                  Edit
                </button>
                <button type="button" className="mini danger" onClick={() => remove(method)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {choosing ? (
        <Modal title="Add payment account" onClose={() => setChoosing(false)}>
          <div className="kinds">
            {KINDS.map((kind) => {
              const Icon = kind.icon;
              return (
                <button
                  type="button"
                  key={kind.id}
                  className="kind"
                  onClick={() => {
                    setChoosing(false);
                    setDraft({ kind, method: null });
                  }}
                >
                  <span className="icon">
                    <Icon />
                  </span>
                  <span>
                    <strong>{kind.title}</strong>
                    <small>{kind.blurb}</small>
                  </span>
                </button>
              );
            })}
          </div>
        </Modal>
      ) : null}

      {draft ? (
        <MethodForm
          draft={draft}
          symbol={symbol}
          order={methods?.length ?? 0}
          say={say}
          onBack={
            draft.method
              ? undefined
              : () => {
                  setDraft(null);
                  setChoosing(true);
                }
          }
          onClose={() => setDraft(null)}
          onSaved={async () => {
            setDraft(null);
            await load();
          }}
        />
      ) : null}
    </>
  );
}

function MethodForm({
  draft,
  symbol,
  order,
  say,
  onBack,
  onClose,
  onSaved,
}: {
  draft: Draft;
  symbol: string;
  order: number;
  say: Say;
  onBack?: () => void;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { kind, method } = draft;
  const [form, setForm] = useState({
    account_info: method?.account_info ?? '',
    name: method?.name ?? kind.defaults.name,
    min_deposit: method?.min_deposit ?? 50,
    instructions: method?.instructions ?? kind.defaults.instructions ?? '',
    active: method ? method.is_active === 1 : true,
    custom_emoji_id: method?.custom_emoji_id ?? kind.defaults.custom_emoji_id ?? '',
    account_type: ((method as any)?.account_type ?? 'personal') as 'personal' | 'agent' | 'merchant',
  });
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      account_info: form.account_info.trim(),
      account_type: form.account_type,
      instructions: form.instructions.trim(),
      min_deposit: form.min_deposit,
      rate_to_currency: 1,
      sort_order: method?.sort_order ?? order,
      is_active: form.active ? 1 : 0,
      auto_verify: 'none' as const,
      auto_verify_network: '',
      custom_emoji_id: form.custom_emoji_id.trim() || null,
    };
    try {
      if (method) await api.updateDepositMethod(method.id, payload);
      else await api.createDepositMethod(payload);
      say(method ? 'Saved.' : `${payload.name} added.`);
      await onSaved();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={method ? `Edit ${method.name}` : `Add ${kind.title}`}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          {onBack ? (
            <button type="button" className="btn ghost" onClick={onBack}>
              Back
            </button>
          ) : null}
          <button type="submit" className="btn" disabled={busy}>
            {method ? 'Save' : 'Add method'}
          </button>
        </>
      }
    >
      <label className="field">
        <span>{kind.account.label}</span>
        <input type="text" required placeholder={kind.account.placeholder} value={form.account_info} onChange={(event) => set({ account_info: event.target.value })} />
      </label>
      <div className="field">
        <span>Account Type & Action</span>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginTop: '4px' }}>
          {[
            { id: 'personal', title: 'Personal', action: 'Send Money', icon: '👤' },
            { id: 'agent', title: 'Agent', action: 'Cash Out', icon: '🏪' },
            { id: 'merchant', title: 'Merchant', action: 'Payment', icon: '💳' },
          ].map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => set({ account_type: item.id as any })}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '10px 8px',
                borderRadius: '8px',
                border: form.account_type === item.id ? '2px solid var(--accent, #0284c7)' : '1px solid var(--border)',
                background: form.account_type === item.id ? 'rgba(2, 132, 199, 0.08)' : 'var(--surface-2)',
                cursor: 'pointer',
                textAlign: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              <span style={{ fontSize: '1.2rem', marginBottom: '2px' }}>{item.icon}</span>
              <strong style={{ fontSize: '0.85rem', color: form.account_type === item.id ? 'var(--accent, #0284c7)' : 'var(--text)' }}>
                {item.title}
              </strong>
              <small style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '2px' }}>
                {item.action}
              </small>
            </button>
          ))}
        </div>
      </div>
      <label className="field">
        <span>Name customers see in bot</span>
        <input type="text" required placeholder={kind.defaults.name || 'Payment method name'} value={form.name} onChange={(event) => set({ name: event.target.value })} />
      </label>
      <div className="field">
        <EmojiPicker
          value={form.custom_emoji_id}
          onChange={(id) => set({ custom_emoji_id: id })}
        />
      </div>
      <label className="field">
        <span>Smallest deposit ({symbol})</span>
        <input type="number" step="any" min="1" required value={form.min_deposit} onChange={(event) => set({ min_deposit: parseFloat(event.target.value) || 1 })} />
      </label>
      <label className="field">
        <span>Payment instructions</span>
        <textarea
          rows={3}
          placeholder="Optional: Enter instructions for customers during payment (leave blank if none)"
          value={form.instructions}
          onChange={(event) => set({ instructions: event.target.value })}
        />
      </label>
      <div>
        <FlagRow label={form.active ? 'Active' : 'Inactive'} on={form.active} onChange={(on) => set({ active: on })} />
      </div>
    </Modal>
  );
}
