'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api, forgetAnswers, type OverviewStats, type SupplierStatus } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { errorText, tone, when, type Say } from './ui';

const metricLabels = ['Revenue', 'Orders', 'Customers', 'Stock'];
const shortcuts = [{ label: 'Products', screen: 'products' }, { label: 'Broadcast', screen: 'broadcast' }, { label: 'Store settings', screen: 'settings' }];

function DashboardLoading() {
  return (
    <section className="home-overview home-loading" role="status" aria-label="Loading dashboard" aria-busy="true">
      <header className="home-toolbar" aria-hidden="true">
        <div><h1>Home</h1><h2><span className="home-skeleton home-loading-status" /></h2></div>
        <span className="home-refresh"><RefreshCw size={15} />Refresh</span>
      </header>
      <div className="home-queue" aria-hidden="true"><span className="home-loading-queue"><span className="home-skeleton home-loading-status" /></span></div>
      <div className="home-metrics" aria-hidden="true">
        {metricLabels.map(label => (
          <div className="home-metric" key={label}>
            <span>{label}</span><strong><span className="home-skeleton home-loading-value" /></strong>
          </div>
        ))}
      </div>
      <section className="home-recent" aria-hidden="true">
        <header><h2>Recent orders</h2><span className="home-view-all">View all</span></header>
        <ul className="home-order-feed"><li><div className="home-order">
          <span className="home-order-left"><span className="home-skeleton home-loading-reference" /><span className="home-skeleton home-loading-customer" /></span>
          <span className="home-order-right"><span className="home-skeleton home-loading-amount" /><span className="home-skeleton home-loading-status" /></span>
        </div></li></ul>
      </section>
      <div className="home-revenue" aria-hidden="true">
        <div className="home-loading-summary"><strong>Revenue</strong><span className="home-skeleton home-loading-amount" /></div>
      </div>
      <div className="home-shortcuts" aria-hidden="true">
        {shortcuts.map(({ label }) => <span className="home-loading-shortcut" key={label}>{label}</span>)}
      </div>
    </section>
  );
}

export function Overview({ say, onOpen }: { say: Say; onOpen: (screen: string) => void }) {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [supplier, setSupplier] = useState<SupplierStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState<number | null>(null);
  const money = useMoney();

  const load = useCallback(async (refresh = false) => {
    if (refresh) forgetAnswers();
    setRefreshing(true);
    setFailed(false);
    void api.supplierStatus().then(setSupplier).catch(() => undefined);
    try {
      setStats(await api.overview());
      setSelectedPoint(null);
    } catch (cause) {
      setFailed(true);
      say(errorText(cause, 'Could not load the dashboard.'), 'bad');
    } finally {
      setRefreshing(false);
    }
  }, [say]);

  useEffect(() => {
    void load();
  }, [load]);

  const chart = useMemo(() => {
    const rows = stats?.chart_data ?? [];
    const max = Math.max(...rows.map((row) => row.revenue), 1);
    const points = rows.map((row, index) => ({ ...row, x: 12 + (index / Math.max(rows.length - 1, 1)) * 676, y: 178 - (row.revenue / max) * 150 }));
    const line = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
    const area = points.length > 1 ? `${line} L ${points[points.length - 1].x} 178 L ${points[0].x} 178 Z` : '';
    return { points, line, area, total: rows.reduce((sum, row) => sum + row.revenue, 0), orders: rows.reduce((sum, row) => sum + row.orders, 0) };
  }, [stats]);

  if (!stats && !failed) return <DashboardLoading />;
  if (!stats) return <section className="panel dashboard-error" role="alert"><p>Could not load the dashboard.</p><button type="button" className="btn ghost" onClick={() => void load()}>Try again</button></section>;

  const metrics = [
    { label: 'Revenue', value: money(stats.total_revenue), screen: 'orders' },
    { label: 'Orders', value: stats.total_orders.toLocaleString(), screen: 'orders' },
    { label: 'Customers', value: stats.total_users.toLocaleString(), screen: 'users' },
    { label: 'Stock', value: stats.available_stock.toLocaleString(), screen: 'inventory' },
  ];
  const point = selectedPoint === null ? null : chart.points[selectedPoint];
  const pending = stats.waiting_orders + stats.pending_deposits;

  return (
    <div className="home-overview">
      <header className="home-toolbar">
        <div><h1>Home</h1><h2>{pending ? `${pending} pending` : 'All clear'}</h2></div>
        <button type="button" className="home-refresh" disabled={refreshing} onClick={() => void load(true)}><RefreshCw size={15} className={refreshing ? 'studio-spin' : ''} aria-hidden="true" />{refreshing ? 'Refreshing' : 'Refresh'}</button>
      </header>
      {failed ? <p className="note bad" role="alert">Refresh failed. Showing the last loaded figures.</p> : null}
      {pending ? <nav className="home-queue" aria-label="Pending work">
        {stats.waiting_orders ? <button type="button" onClick={() => onOpen('orders/waiting')}>To deliver <strong>{stats.waiting_orders}</strong></button> : null}
        {stats.pending_deposits ? <button type="button" onClick={() => onOpen('deposits')}>Deposits <strong>{stats.pending_deposits}</strong></button> : null}
      </nav> : null}
      <div className="home-metrics">
        {metrics.map(({ label, value, screen }) => (
          <button type="button" key={label} className="home-metric" onClick={() => onOpen(screen)}>
            <span>{label}</span><strong>{value}</strong>
          </button>
        ))}
      </div>
      <section className="home-recent" aria-labelledby="home-recent-title">
        <header><h2 id="home-recent-title">Recent orders</h2><button type="button" className="home-view-all" onClick={() => onOpen('orders')}>View all</button></header>
        {stats.recent_orders.length ? <ul className="home-order-feed">{stats.recent_orders.map(order => {
          const customer = [order.first_name, order.last_name].filter(Boolean).join(' ') || order.username || `User ${order.tg_user_id}`;
          const waiting = order.status === 'completed' && order.fulfillment === 'waiting';
          return <li key={order.id}><button type="button" className="home-order" aria-label={`Open order O${order.id}`} onClick={() => onOpen(`orders/${order.id}`)}>
            <span className="home-order-left"><span className="home-order-reference"><strong>O{order.id}</strong><small>{when(order.created_at)}</small></span><span className="home-customer">{customer}</span></span>
            <span className="home-order-right"><strong>{money(order.price)}</strong><span className={`pill ${waiting ? 'warn' : tone(order.status)}`}>{waiting ? 'Waiting' : order.status}</span></span>
          </button></li>;
        })}</ul> : <p className="home-empty">No orders yet.</p>}
      </section>
      <details className="home-revenue">
          <summary><strong>Revenue</strong><span>Last 14 days</span><b>{money(chart.total)}</b></summary>
          <div className="home-revenue-body">
          <div className="revenue-total">{money(chart.total)}</div>
          <div className="revenue-readout" aria-live="polite">{point ? <><strong>{point.label}</strong><span>{money(point.revenue)}, {point.orders} orders</span></> : <span>Daily revenue</span>}</div>
          {chart.points.length ? <div className="revenue-chart">
            <svg viewBox="0 0 700 214" role="group" aria-label={`Revenue over the last 14 days: ${money(chart.total)}`}>
              <defs><linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity=".16" /><stop offset="100%" stopColor="var(--accent)" stopOpacity=".01" /></linearGradient></defs>
              {[28, 78, 128, 178].map((y) => <line key={y} x1="12" x2="688" y1={y} y2={y} stroke="var(--line)" strokeDasharray={y === 178 ? undefined : '3 5'} />)}
              {chart.area ? <path d={chart.area} fill="url(#revenue-fill)" /> : null}
              <path d={chart.line} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              {chart.points.map((item, index) => <g key={item.date} tabIndex={0} role="button" aria-label={`${item.label}: ${money(item.revenue)}, ${item.orders} orders`}
                onFocus={() => setSelectedPoint(index)} onBlur={() => setSelectedPoint(null)} onMouseEnter={() => setSelectedPoint(index)} onMouseLeave={() => setSelectedPoint(null)} onClick={() => setSelectedPoint(index)}
                onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedPoint(index); } }}>
                <circle cx={item.x} cy={item.y} r="14" fill="transparent" /><circle cx={item.x} cy={item.y} r={selectedPoint === index || chart.points.length === 1 ? 4 : 2.5} fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" />
                {(index === 0 || index === chart.points.length - 1 || (index % 4 === 0 && index < chart.points.length - 2)) ? <text x={item.x} y="207" textAnchor={index === 0 ? 'start' : index === chart.points.length - 1 ? 'end' : 'middle'} fill="var(--muted)" fontSize="11">{item.label}</text> : null}
              </g>)}
            </svg>
          </div> : <div className="chart-empty">Revenue will appear here after your first order.</div>}
          </div>
      </details>
      {supplier?.is_configured ? <button type="button" className="home-supplier" onClick={() => onOpen('suppliers')}>
        <span>Supplier balance</span><strong>{supplier.account?.currency_symbol || '৳'}{(supplier.account?.balance ?? 0).toFixed(2)}</strong>
      </button> : null}
      <nav className="home-shortcuts" aria-label="Quick actions">
        {shortcuts.map(({ label, screen }) => <button key={screen} type="button" onClick={() => onOpen(screen)}><span>{label}</span></button>)}
      </nav>
    </div>
  );
}
