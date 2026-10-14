'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  RefreshCw,
  Wallet,
  X,
  Zap,
} from 'lucide-react';
import { RecordDetails } from './RecordDetails';
import { api, type Deposit, type DepositSummary, type PaymentInvoice } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { EmptyRow, FlagRow, Modal, Pager, errorText, tone, useDebounced, when, who, type Say } from './ui';

const PAGE = 50;

type Review = { deposit: Deposit; approve: boolean };

type Tab = 'waiting' | 'all' | 'instant';

export function Deposits({
  say,
  initialMode = 'deposits',
  onPendingChange,
}: {
  say: Say;
  initialMode?: 'deposits' | 'instant';
  onPendingChange?: (count: number) => void;
}) {
  const [tab, setTab] = useState<Tab>(initialMode === 'instant' ? 'instant' : 'all');
  const [pendingCount, setPendingCount] = useState(0);
  const pendingCountLoaded = useRef(false);

  const choose = (next: Tab) => {
    setTab(next);
    window.history.replaceState(null, '', next === 'instant' ? '#deposits/instant' : '#deposits');
  };

  const handlePendingCount = useCallback((count: number) => {
    pendingCountLoaded.current = true;
    setPendingCount(count);
    onPendingChange?.(count);
  }, [onPendingChange]);

  useEffect(() => {
    if (tab !== 'instant' || pendingCountLoaded.current) return;
    let cancelled = false;
    api.deposits('pending', 1, 0)
      .then((result) => {
        if (!cancelled) handlePendingCount(result.summary?.pending_count ?? result.total);
      })
      .catch((cause) => {
        if (!cancelled) say(errorText(cause), 'bad');
      });
    return () => { cancelled = true; };
  }, [tab, handlePendingCount, say]);

  return (
    <>
      {tab === 'instant' ? (
        <Instant
          say={say}
          tab={tab}
          onSelectTab={choose}
          pendingCount={pendingCount}
        />
      ) : (
        <TopUps
          key={tab}
          say={say}
          tab={tab}
          waiting={tab === 'waiting'}
          onSelectTab={choose}
          onPendingChange={handlePendingCount}
        />
      )}
    </>
  );
}

function TopUps({
  say,
  tab,
  waiting,
  onSelectTab,
  onPendingChange,
}: {
  say: Say;
  tab: Tab;
  waiting: boolean;
  onSelectTab: (t: Tab) => void;
  onPendingChange?: (count: number) => void;
}) {
  const [summary, setSummary] = useState<DepositSummary | null>(null);
  const [rows, setRows] = useState<Deposit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const settledSearch = useDebounced(search);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const requestVersion = useRef(0);
  const [busy, setBusy] = useState<number | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const money = useMoney();

  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoadError('');
    setLoading(true);
    try {
      const result = await api.deposits(waiting ? 'pending' : undefined, PAGE, offset, settledSearch);
      if (version !== requestVersion.current) return;
      setRows(result.deposits);
      setTotal(result.total);
      if (result.summary) {
        setSummary(result.summary);
        onPendingChange?.(result.summary.pending_count);
      } else if (waiting) {
        onPendingChange?.(result.total);
      }
    } catch (cause) {
      if (version === requestVersion.current) setLoadError(errorText(cause));
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [waiting, offset, settledSearch, onPendingChange, say]);

  useEffect(() => {
    void load();
    return () => { requestVersion.current++; };
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

  const pCount = summary?.pending_count ?? (waiting ? total : 0);

  return (
    <>
      <section className="panel queue-panel">
        <header>
          <div className="queue-tabs" aria-label="Status filter">
            <button
              type="button"
              className={tab === 'all' ? 'active' : ''} aria-pressed={tab === 'all'}
              onClick={() => {
                onSelectTab('all');
                setOffset(0);
              }}
            >
              All
            </button>
            <button
              type="button"
              className={tab === 'waiting' ? 'active' : ''} aria-pressed={tab === 'waiting'}
              onClick={() => {
                onSelectTab('waiting');
                setOffset(0);
              }}
            >
              Pending <span className="count">({pCount})</span>
            </button>
            <button
              type="button"
              className={tab === 'instant' ? 'active' : ''} aria-pressed={tab === 'instant'}
              onClick={() => {
                onSelectTab('instant');
                setOffset(0);
              }}
            >
              ZiniPay
            </button>
          </div>

          <div className="filters">
            <input
              type="search"
              aria-label="Search deposits"
              placeholder="Search ID, user, or TrxID…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
            <button
              type="button"
              className="btn ghost small"
              onClick={() => void load()}
              disabled={loading}
              aria-label="Refresh deposits"
            >
              <RefreshCw size={14} /> <span>{loading ? 'Refreshing…' : 'Refresh'}</span>
            </button>
          </div>
        </header>

        <div className="scroll" tabIndex={0} role="region" aria-label="Deposits table" aria-busy={loading}>
          <table className="record-directory deposit-directory">
            <thead>
              <tr>
                <th scope="col">Customer</th>
                <th scope="col" className="right">Amount</th>
                <th scope="col">Method</th>
                <th scope="col">Transaction ID</th>
                <th scope="col">Status</th>
                <th scope="col" className="right" aria-label="Actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadError ? <EmptyRow columns={6}><div role="alert">{loadError} <button type="button" className="btn ghost small" onClick={() => void load()}>Retry deposits</button></div></EmptyRow> : null}
              {!loadError && rows && rows.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                    {loading ? 'Loading deposits…' : settledSearch ? 'No deposits match your search. Try another ID or customer.' : waiting ? 'Nothing waiting. All caught up.' : 'No deposits found.'}
                  </td>
                </tr>
              ) : null}
              {!loadError && !rows ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                    Loading deposits…
                  </td>
                </tr>
              ) : null}
              {(rows ?? []).map((deposit) => {
                const checkable = deposit.auto_verify === 'binance' || deposit.auto_verify === 'binance_pay';
                const flagged = deposit.status === 'pending' && Boolean(deposit.admin_note?.startsWith('Needs a look'));
                const isBinance = deposit.method_name?.toLowerCase().includes('binance');
                return (
                  <tr key={deposit.id}>
                    <td data-label="Customer">
                      <div className="overview-customer">
                        <RecordDetails
                          label={who(deposit)}
                          title={`Deposit D${deposit.id}`}
                          fields={[
                            ['Deposit ID', `D${deposit.id}`],
                            ['Customer', who(deposit)],
                            ['Amount', money(deposit.amount)],
                            ['Method', deposit.method_name || '—'],
                            ['Transaction ID', deposit.transaction_id || '—'],
                            ['Created', when(deposit.created_at)],
                            ['Status', deposit.status],
                            ['Admin note', deposit.admin_note || '—'],
                          ]}
                        />
                      </div>
                    </td>
                    <td className="right" data-label="Amount">
                      <strong className="money">{money(deposit.amount)}</strong>
                      {deposit.pay_amount != null && deposit.rate_to_currency != null && deposit.rate_to_currency !== 1 ? (
                        <small style={{ display: 'block', color: 'var(--muted)', fontSize: '11px' }}>
                          pays {deposit.pay_amount.toFixed(2)}
                        </small>
                      ) : null}
                    </td>
                    <td data-label="Method">
                      <span
                        className={`pill ${isBinance ? 'good' : ''}`}
                        style={{ textTransform: 'uppercase' }}
                      >
                        {deposit.method_name || '—'}
                      </span>
                    </td>
                    <td data-label="Transaction ID">
                      <code
                        style={{
                          fontSize: '12px',
                          background: 'var(--surface-2)',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          display: 'block',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={deposit.transaction_id}
                      >
                        {deposit.transaction_id || 'N/A'}
                      </code>
                    </td>
                    <td data-label="Status">
                      <span className={`pill ${flagged ? 'bad' : tone(deposit.status)}`}>
                        {flagged ? 'needs review' : deposit.status}
                      </span>
                      {deposit.admin_note && !flagged ? (
                        <small
                          style={{
                            display: 'block',
                            color: 'var(--muted)',
                            fontSize: '11px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                          title={deposit.admin_note}
                        >
                          {deposit.admin_note}
                        </small>
                      ) : null}
                    </td>
                    <td className="right" data-label="Actions">
                      {deposit.status === 'pending' ? (
                        <div className="row-actions" style={{ justifyContent: 'flex-end', gap: '6px' }}>
                          {checkable ? (
                            <button
                              type="button"
                              className="btn small"
                              disabled={busy === deposit.id}
                              onClick={() => void checkOnBinance(deposit)}
                              style={{
                                background: 'linear-gradient(135deg, #f3ba2f, #f0b90b)',
                                color: '#000',
                                fontWeight: 600,
                                border: 0,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                              title="Check Binance transaction and credit deposit"
                              aria-label={`Check Binance deposit D${deposit.id}`}
                            >
                              <Zap size={13} className={busy === deposit.id ? 'refreshing' : ''} />
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="btn small"
                            disabled={busy === deposit.id}
                            onClick={() => setReview({ deposit, approve: true })}
                            style={{ background: 'var(--positive)', color: '#fff', border: 0 }}
                          >
                            <Check size={13} /> Verify
                          </button>
                          <button
                            type="button"
                            className="btn ghost small danger icon-action"
                            disabled={busy === deposit.id}
                            onClick={() => setReview({ deposit, approve: false })}
                            style={{ color: 'var(--danger)' }}
                            title="Reject"
                            aria-label={`Reject deposit D${deposit.id}`}
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <span className="muted" style={{ fontSize: '11px', color: 'var(--muted)' }}>
                          {when(deposit.created_at)}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
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

function ReviewDialog({
  review,
  amount,
  onClose,
  onDone,
  say,
}: {
  review: Review;
  amount: string;
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
  say: Say;
}) {
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
      title={approve ? `Verify deposit D${deposit.id}?` : `Reject deposit D${deposit.id}?`}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className={`btn${approve ? '' : ' danger'}`} disabled={busy}>
            {approve ? 'Verify deposit' : 'Reject deposit'}
          </button>
        </>
      }
    >
      <p className="hint">
        {who(deposit)} · {deposit.method_name} · <code>{deposit.transaction_id}</code>
      </p>
      <label className="field">
        <span>{approve ? 'Admin note (optional)' : 'Reason sent to customer'}</span>
        <input type="text" value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      {approve ? null : <FlagRow label="Also ban this customer" on={ban} onChange={setBan} danger />}
    </Modal>
  );
}

function Instant({
  say,
  tab,
  onSelectTab,
  pendingCount,
}: {
  say: Say;
  tab: Tab;
  onSelectTab: (t: Tab) => void;
  pendingCount: number;
}) {
  const [rows, setRows] = useState<PaymentInvoice[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(false);
  const money = useMoney();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.payments(undefined, PAGE, offset);
      setRows(result.invoices);
      setTotal(result.total);
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setLoading(false);
    }
  }, [offset, say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function check(payment: PaymentInvoice) {
    setBusy(payment.reference);
    try {
      const result = await api.checkPayment(payment.reference);
      say(
        result.status === 'completed'
          ? 'Paid and credited.'
          : result.status === 'pending'
          ? 'Not paid yet.'
          : `ZiniPay says ${result.status}.`,
        result.status === 'completed' ? 'good' : undefined
      );
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy('');
    }
  }

  return (
    <section className="panel queue-panel">
      <header>
        <div className="queue-tabs" aria-label="Status filter">
          <button
            type="button"
            className={tab === 'all' ? 'active' : ''} aria-pressed={tab === 'all'}
            onClick={() => onSelectTab('all')}
          >
            All
          </button>
          <button
            type="button"
            className={tab === 'waiting' ? 'active' : ''} aria-pressed={tab === 'waiting'}
            onClick={() => onSelectTab('waiting')}
          >
            Pending <span className="count">({pendingCount})</span>
          </button>
          <button
            type="button"
            className={tab === 'instant' ? 'active' : ''} aria-pressed={tab === 'instant'}
            onClick={() => onSelectTab('instant')}
          >
            ZiniPay
          </button>
        </div>

        <div className="filters">
          <button
            type="button"
            className="btn ghost small"
            onClick={() => void load()}
            disabled={loading}
            aria-label="Refresh instant deposits"
          >
            <RefreshCw size={14} className={loading ? 'refreshing' : ''} />
          </button>
        </div>
      </header>

      <div className="scroll" tabIndex={0} role="region" aria-label="Instant deposits table">
        <table className="record-directory deposit-directory">
          <thead>
            <tr>
              <th scope="col">Customer</th>
              <th scope="col">Credit</th>
              <th scope="col">Paid with</th>
              <th scope="col">Transaction ID</th>
              <th scope="col">Status</th>
              <th scope="col" className="right" aria-label="Actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((payment) => (
                <tr key={payment.id}>
                  <td data-label="Customer">
                    <div className="overview-customer">
                      <RecordDetails
                        label={who(payment)}
                        title={`Invoice #${payment.id}`}
                        fields={[
                          ['Invoice ID', `#${payment.id}`],
                          ['Customer', who(payment)],
                          ['Credit amount', money(payment.credit_amount)],
                          ['Payable amount', `৳${payment.pay_amount.toFixed(2)}`],
                          ['Method', payment.payment_method || 'ZiniPay'],
                          ['Reference', payment.reference],
                          ['Provider TrxID', payment.provider_transaction_id || '—'],
                          ['Status', payment.status],
                          ['Created', when(payment.created_at)],
                        ]}
                      />
                    </div>
                  </td>
                  <td data-label="Credit">
                    <strong className="money">{money(payment.credit_amount)}</strong>
                    <small style={{ display: 'block', color: 'var(--muted)', fontSize: '11px' }}>
                      ৳{payment.pay_amount.toFixed(2)}
                    </small>
                  </td>
                  <td data-label="Paid with">
                    <span className="pill">{payment.payment_method || 'ZiniPay'}</span>
                  </td>
                  <td data-label="Transaction ID">
                    <code
                      style={{
                        fontSize: '12px',
                        background: 'var(--surface-2)',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        display: 'block',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={payment.provider_transaction_id || payment.reference}
                    >
                      {payment.provider_transaction_id || payment.reference}
                    </code>
                  </td>
                  <td data-label="Status">
                    <span className={`pill ${tone(payment.status)}`}>
                      {payment.status === 'pending' || payment.status === 'created' ? 'unpaid' : payment.status}
                    </span>
                    {payment.last_error ? (
                      <small style={{ display: 'block', color: 'var(--danger)', fontSize: '11px' }}>
                        {payment.last_error}
                      </small>
                    ) : null}
                  </td>
                  <td className="right" data-label="Actions">
                    <div className="row-actions" style={{ justifyContent: 'flex-end' }}>
                      {payment.status === 'pending' ? (
                        <button
                          type="button"
                          className="btn small"
                          disabled={busy === payment.reference}
                          onClick={() => void check(payment)}
                        >
                          {busy === payment.reference ? 'Checking…' : 'Check'}
                        </button>
                      ) : (
                        <span className="muted" style={{ fontSize: '11px', color: 'var(--muted)' }}>
                          {when(payment.created_at)}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
            ))}
            {rows && rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                  No instant deposits yet.
                </td>
              </tr>
            ) : null}
            {!rows ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--muted)' }}>
                  Loading…
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
    </section>
  );
}
