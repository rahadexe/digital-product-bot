'use client';

import { useCallback, useEffect, useState } from 'react';
import { Calendar, CheckCircle2, Clock, Wallet } from 'lucide-react';
import { api, type Deposit, type DepositSummary, type PaymentInvoice } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, FlagRow, Modal, Pager, errorText, tone, when, who, type Say } from './ui';

const PAGE = 50;

type Review = { deposit: Deposit; approve: boolean };

type Tab = 'waiting' | 'all' | 'instant';

const TABS: { key: Tab; label: string }[] = [
  { key: 'waiting', label: 'Waiting' },
  { key: 'all', label: 'All' },
  { key: 'instant', label: 'Instant' },
];

export function Deposits({ say, initialMode = 'deposits', onPendingChange }: { say: Say; initialMode?: 'deposits' | 'instant'; onPendingChange?: (count: number) => void }) {
  const [tab, setTab] = useState<Tab>(initialMode === 'instant' ? 'instant' : 'waiting');

  const choose = (next: Tab) => {
    setTab(next);
    // A reload lands on the same tab.
    window.history.replaceState(null, '', next === 'instant' ? '#deposits/instant' : '#deposits');
  };

  return (
    <>
      <div className="segmented" role="tablist" aria-label="Deposits">
        {TABS.map((item) => (
          <button key={item.key} type="button" role="tab" aria-selected={tab === item.key} className={tab === item.key ? 'active' : ''} onClick={() => choose(item.key)}>
            {item.label}
          </button>
        ))}
      </div>
      {tab === 'instant' ? <Instant say={say} /> : <TopUps key={tab} say={say} waiting={tab === 'waiting'} onPendingChange={onPendingChange} />}
    </>
  );
}

function TopUps({ say, waiting, onPendingChange }: { say: Say; waiting: boolean; onPendingChange?: (count: number) => void }) {
  const [summary, setSummary] = useState<DepositSummary | null>(null);
  const [rows, setRows] = useState<Deposit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState<number | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const money = useMoney();

  const load = useCallback(async () => {
    try {
      const result = await api.deposits(waiting ? 'pending' : undefined, PAGE, offset);
      setRows(result.deposits);
      setTotal(result.total);
      if (result.summary) setSummary(result.summary);
      if (waiting) onPendingChange?.(result.total);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [waiting, offset, onPendingChange, say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function checkOnBinance(deposit: Deposit) {
    setBusy(deposit.id);
    try {
      const result = await api.checkDepositOnBinance(deposit.id);
      say(result.detail || 'Checked.', result.credited ? 'good' : undefined);
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {/* Analytics Metric Summary Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Completed</span>
            <CheckCircle2 className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{money(summary?.total_completed_amount ?? 0)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Pending Review</span>
            <Clock className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.pending_count ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Pending Amount</span>
            <Wallet className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{money(summary?.pending_amount ?? 0)}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Today Completed</span>
            <Calendar className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{money(summary?.today_amount ?? 0)}</div>
        </div>
      </div>

      <section className="panel">
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Customer</th>
                <th>Amount</th>
                <th>Transaction ID</th>
                <th>Status</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((deposit) => {
                const checkable = deposit.auto_verify === 'binance' || deposit.auto_verify === 'binance_pay';
                // "Needs a look: …" is written by the automatic check when something did not match.
                const flagged = deposit.status === 'pending' && Boolean(deposit.admin_note?.startsWith('Needs a look'));
                return (
                  <tr key={deposit.id}>
                    <td className="name">
                      {who(deposit)}
                      <small>
                        {deposit.method_name} · {when(deposit.created_at)}
                      </small>
                    </td>
                    <td className="money">
                      {money(deposit.amount)}
                      {deposit.pay_amount != null && deposit.rate_to_currency != null && deposit.rate_to_currency !== 1 ? (
                        <small>pays {deposit.pay_amount.toFixed(2)}</small>
                      ) : null}
                    </td>
                    <td>
                      <code className="key" title={deposit.transaction_id}>
                        {deposit.transaction_id}
                      </code>
                    </td>
                    <td>
                      <span className={`pill ${flagged ? 'bad' : tone(deposit.status)}`}>{flagged ? 'check it' : deposit.status}</span>
                      {deposit.admin_note ? (
                        <small className={flagged ? 'bad-text' : undefined} title={deposit.admin_note}>
                          {deposit.admin_note}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      {deposit.status === 'pending' ? (
                        <div className="row-actions">
                          {checkable ? (
                            <button type="button" className="mini" disabled={busy === deposit.id} title="Look it up in your Binance account" onClick={() => checkOnBinance(deposit)}>
                              {busy === deposit.id ? 'Checking…' : 'Check'}
                            </button>
                          ) : null}
                          <button type="button" className="mini primary" disabled={busy === deposit.id} onClick={() => setReview({ deposit, approve: true })}>
                            Approve
                          </button>
                          <button type="button" className="mini danger" disabled={busy === deposit.id} onClick={() => setReview({ deposit, approve: false })}>
                            Reject
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
              {rows && rows.length === 0 ? <EmptyRow columns={5}>{waiting ? 'Nothing waiting. All caught up.' : 'No deposits yet.'}</EmptyRow> : null}
              {!rows ? <EmptyRow columns={5}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
      </section>

      {review ? (
        <ReviewDialog
          review={review}
          amount={money(review.deposit.amount)}
          onClose={() => setReview(null)}
          onDone={async (message) => {
            setReview(null);
            say(message);
            await load();
          }}
          say={say}
        />
      ) : null}
    </>
  );
}

function ReviewDialog({ review, amount, onClose, onDone, say }: { review: Review; amount: string; onClose: () => void; onDone: (message: string) => Promise<void>; say: Say }) {
  const { deposit, approve } = review;
  const [note, setNote] = useState(approve ? '' : 'Payment not received');
  const [ban, setBan] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      if (approve) {
        await api.approveDeposit(deposit.id, note);
        await onDone(`${amount} added to ${who(deposit)}.`);
      } else {
        await api.rejectDeposit(deposit.id, note);
        if (ban) await api.setBan(deposit.tg_user_id, true);
        await onDone(ban ? 'Rejected and banned.' : 'Rejected.');
      }
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={approve ? `Approve ${amount}?` : `Reject ${amount}?`}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className={`btn${approve ? '' : ' danger'}`} disabled={busy}>
            {approve ? 'Approve' : 'Reject'}
          </button>
        </>
      }
    >
      <p className="hint">
        {who(deposit)} · {deposit.method_name} · <code>{deposit.transaction_id}</code>
      </p>
      <label className="field">
        <span>{approve ? 'Note (optional)' : 'Reason, sent to the customer'}</span>
        <input type="text" value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      {approve ? null : <FlagRow label="Also ban this customer" on={ban} onChange={setBan} danger />}
    </Modal>
  );
}

function Instant({ say }: { say: Say }) {
  const [rows, setRows] = useState<PaymentInvoice[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState('');
  const money = useMoney();

  const load = useCallback(async () => {
    try {
      const result = await api.payments(undefined, PAGE, offset);
      setRows(result.invoices);
      setTotal(result.total);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [offset, say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function check(payment: PaymentInvoice) {
    setBusy(payment.reference);
    try {
      const result = await api.checkPayment(payment.reference);
      say(result.status === 'completed' ? 'Paid and credited.' : result.status === 'pending' ? 'Not paid yet.' : `ZiniPay says ${result.status}.`, result.status === 'completed' ? 'good' : undefined);
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy('');
    }
  }

  return (
    <section className="panel">
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Credit</th>
              <th>Paid with</th>
              <th>Status</th>
              <th className="right" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((payment) => (
              <tr key={payment.id}>
                <td className="name">
                  {who(payment)}
                  <small>{when(payment.created_at)}</small>
                </td>
                <td className="money">
                  {money(payment.credit_amount)}
                  <small>৳{payment.pay_amount.toFixed(2)}</small>
                </td>
                <td>
                  {payment.payment_method || '—'}
                  {payment.provider_transaction_id ? <small>{payment.provider_transaction_id}</small> : null}
                </td>
                <td>
                  <span className={`pill ${tone(payment.status)}`}>{payment.status === 'pending' || payment.status === 'created' ? 'unpaid' : payment.status}</span>
                  {payment.last_error ? <small className="bad-text">{payment.last_error}</small> : null}
                </td>
                <td>
                  <div className="row-actions">
                    {payment.status === 'pending' ? (
                      <button type="button" className="mini" disabled={busy === payment.reference} onClick={() => check(payment)}>
                        {busy === payment.reference ? 'Checking…' : 'Check'}
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
            {rows && rows.length === 0 ? <EmptyRow columns={5}>No instant deposits yet.</EmptyRow> : null}
            {!rows ? <EmptyRow columns={5}>Loading…</EmptyRow> : null}
          </tbody>
        </table>
      </div>
      <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
    </section>
  );
}
