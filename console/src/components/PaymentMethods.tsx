'use client';

// Adding a way to pay starts with what kind it is, because a bKash number and a USDT address need
// different answers. Picking the kind fills in everything that follows from it - the rate, who checks
// the payment, the network - so the only questions left are the ones only the shop owner can answer.

import { useCallback, useEffect, useState } from 'react';
import { Smartphone, type LucideIcon } from 'lucide-react';
import { api, type DepositMethod } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

type KindId = 'bkash' | 'nagad' | 'rocket';

type Kind = {
  id: KindId;
  title: string;
  blurb: string;
  icon: LucideIcon;
  defaults: { name: string; rate: number; auto_verify: 'none'; network: string; instructions?: string };
  account: { label: string; placeholder: string; hint?: string };
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
    },
    account: { label: 'bKash Number', placeholder: '01700000000', hint: 'Your bKash account number.' },
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
    },
    account: { label: 'Nagad Number', placeholder: '01800000000', hint: 'Your Nagad account number.' },
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
    },
    account: { label: 'Rocket Number', placeholder: '01900000000', hint: 'Your Rocket account number.' },
  },
];

function kindOf(method: DepositMethod): Kind {
  const name = (method.name || '').toLowerCase();
  if (name.includes('bkash') || name.includes('b-kash')) return KINDS[0];
  if (name.includes('nagad')) return KINDS[1];
  return KINDS[2];
}

type Draft = { kind: Kind; method: DepositMethod | null };

export function PaymentMethods({ say, symbol }: { say: Say; symbol: string }) {
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
            <h2>Custom Payment Methods (Manual)</h2>
          </div>
          <button type="button" className="btn small" onClick={() => setChoosing(true)}>
            Add method
          </button>
        </header>
        {!methods ? <p className="note">Loading…</p> : null}
        {methods && manualMethods.length === 0 ? <p className="note">No manual methods added. Only automated gateways (ZiniPay / Binance) will appear in the bot.</p> : null}
        <div className="rows">
          {manualMethods.map((method) => (
            <div key={method.id} className={`row${method.is_active ? '' : ' off'}`}>
              <div className="text">
                <strong>
                  {method.name}
                  {method.is_active ? '' : ' · off'}
                </strong>
                <small>
                  You approve · from {money(method.min_deposit)}
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
        <Modal title="Choose payment method to add" onClose={() => setChoosing(false)}>
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
  });
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      account_info: form.account_info.trim(),
      instructions: form.instructions.trim(),
      min_deposit: form.min_deposit,
      rate_to_currency: 1,
      sort_order: method?.sort_order ?? order,
      is_active: form.active ? 1 : 0,
      auto_verify: 'none' as const,
      auto_verify_network: '',
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
        {kind.account.hint ? <small>{kind.account.hint}</small> : null}
      </label>
      <label className="field">
        <span>Name customers see in bot</span>
        <input type="text" required placeholder={kind.defaults.name || 'Payment method name'} value={form.name} onChange={(event) => set({ name: event.target.value })} />
      </label>
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
        <FlagRow label="Offer to customers in bot" on={form.active} onChange={(on) => set({ active: on })} />
      </div>
    </Modal>
  );
}
