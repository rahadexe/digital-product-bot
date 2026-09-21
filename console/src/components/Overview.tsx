'use client';

import { useMemo, useState, useEffect } from 'react';
import {
  ArrowUpRight,
  PackageCheck,
  ShoppingBag,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react';
import { api, type OverviewStats } from '@/lib/api';
import { useMoney } from '@/lib/currency';
import { PageLoading, EmptyRow, errorText, tone, when, type Say } from './ui';

export function Overview({ say, onOpen }: { say: Say; onOpen: (screen: string) => void }) {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [failed, setFailed] = useState(false);
  const [hoverPoint, setHoverPoint] = useState<{ x: number; y: number; label: string; revenue: number; orders: number } | null>(null);
  const money = useMoney();

  useEffect(() => {
    api
      .overview()
      .then(setStats)
      .catch((cause) => {
        setFailed(true);
        say(errorText(cause, 'Could not load the dashboard.'), 'bad');
      });
  }, [say]);

  // Generate SVG smooth area curve points
  const chartPoints = useMemo(() => {
    const rawData = stats?.chart_data && stats.chart_data.length > 0 ? stats.chart_data : [];
    if (!rawData.length) return { path: '', area: '', points: [], maxVal: 0, totalRev: 0, totalOrders: 0 };

    const totalRev = rawData.reduce((sum, item) => sum + item.revenue, 0);
    const totalOrders = rawData.reduce((sum, item) => sum + item.orders, 0);
    const maxVal = Math.max(...rawData.map((d) => d.revenue), 100);

    const width = 800;
    const height = 150;
    const paddingX = 20;
    const paddingY = 20;

    const effectiveWidth = width - paddingX * 2;
    const effectiveHeight = height - paddingY * 2;

    const points = rawData.map((d, i) => {
      const x = paddingX + (i / Math.max(rawData.length - 1, 1)) * effectiveWidth;
      const y = height - paddingY - (d.revenue / maxVal) * effectiveHeight;
      return { x, y, data: d };
    });

    if (points.length === 1) {
      return { path: `M ${points[0].x} ${points[0].y}`, area: '', points, maxVal, totalRev, totalOrders };
    }

    // Smooth cubic bezier spline
    let path = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const curr = points[i];
      const next = points[i + 1];
      const cpX1 = curr.x + (next.x - curr.x) / 3;
      const cpY1 = curr.y;
      const cpX2 = curr.x + (2 * (next.x - curr.x)) / 3;
      const cpY2 = next.y;
      path += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
    }

    const last = points[points.length - 1];
    const first = points[0];
    const area = `${path} L ${last.x} ${height} L ${first.x} ${height} Z`;

    return { path, area, points, maxVal, totalRev, totalOrders };
  }, [stats]);

  if (failed && !stats) return <p className="note bad">Could not load the dashboard.</p>;
  if (!stats) return <PageLoading label="Loading dashboard…" />;

  const deliveredCount = stats.delivered_orders ?? Math.max(0, stats.total_orders - stats.waiting_orders);

  return (
    <>
      {/* Top Header */}
      <div className="dash-header">
        <h1>Dashboard</h1>
      </div>

      {(stats.waiting_orders > 0 || stats.pending_deposits > 0) ? (
        <div className="dashboard-actions" aria-label="Needs attention">
          {stats.waiting_orders > 0 ? <button type="button" onClick={() => onOpen('orders/waiting')}>
            <ShoppingBag size={18} aria-hidden="true" />
            <span><strong>{stats.waiting_orders} orders to deliver</strong><small>Open waiting orders</small></span>
            <ArrowUpRight size={17} aria-hidden="true" />
          </button> : null}
          {stats.pending_deposits > 0 ? <button type="button" onClick={() => onOpen('deposits')}>
            <Wallet size={18} aria-hidden="true" />
            <span><strong>{stats.pending_deposits} deposits to review</strong><small>Review payments</small></span>
            <ArrowUpRight size={17} aria-hidden="true" />
          </button> : null}
        </div>
      ) : null}

      {/* Top 4 Stat Metric Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total revenue</span>
            <Wallet className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{money(stats.total_revenue)}</div>
        </div>

        <button
          type="button"
          className="stat-card"
          onClick={() => { window.location.hash = '#orders'; }}
          title="View orders"
        >
          <div className="stat-card-top">
            <span className="stat-card-label">Orders</span>
            <ShoppingBag className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{stats.total_orders}</div>
        </button>

        <button
          type="button"
          className="stat-card"
          onClick={() => { window.location.hash = '#users'; }}
          title="View all customers"
        >
          <div className="stat-card-top">
            <span className="stat-card-label">Customers</span>
            <Users className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{stats.total_users}</div>
        </button>

        <button
          type="button"
          className="stat-card"
          onClick={() => { window.location.hash = '#orders'; }}
          title="View delivered orders"
        >
          <div className="stat-card-top">
            <span className="stat-card-label">Delivered</span>
            <PackageCheck className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{deliveredCount}</div>
        </button>
      </div>

      {/* Analytics Chart Card */}
      <div className="analytics-card">
        <div className="analytics-card-header">
          <div>
            <div className="label">Revenue · last 14 days</div>
            <div className="metric">{money(chartPoints.totalRev)}</div>
          </div>
          <div className="analytics-badge">
            <TrendingUp size={14} style={{ color: 'var(--positive)' }} />
            <span>{chartPoints.totalOrders} orders</span>
          </div>
        </div>

        <div className="chart-svg-container">
          {hoverPoint ? (
            <div className="chart-tooltip" style={{ left: `${(hoverPoint.x / 800) * 100}%`, top: hoverPoint.y }}>
              {hoverPoint.label}: <strong>{money(hoverPoint.revenue)}</strong> ({hoverPoint.orders} orders)
            </div>
          ) : null}

          <svg
            viewBox="0 0 800 170"
            style={{ width: '100%', height: '100%', overflow: 'visible' }}
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
                <stop offset="85%" stopColor="var(--accent)" stopOpacity="0.03" />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* Horizontal Grid lines */}
            <line x1="0" y1="20" x2="800" y2="20" stroke="var(--line)" strokeDasharray="3 3" />
            <line x1="0" y1="75" x2="800" y2="75" stroke="var(--line)" strokeDasharray="3 3" />
            <line x1="0" y1="130" x2="800" y2="130" stroke="var(--line)" />

            {/* Area fill */}
            {chartPoints.area ? <path d={chartPoints.area} fill="url(#chartGradient)" /> : null}

            {/* Line stroke */}
            {chartPoints.path ? (
              <path
                d={chartPoints.path}
                fill="none"
                stroke="var(--accent)"
                strokeWidth="2.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            ) : null}

            {/* Interactive Data Points */}
            {chartPoints.points.map((pt, idx) => (
              <g
                key={idx}
                onMouseEnter={() =>
                  setHoverPoint({
                    x: pt.x,
                    y: pt.y,
                    label: pt.data.label,
                    revenue: pt.data.revenue,
                    orders: pt.data.orders,
                  })
                }
                onMouseLeave={() => setHoverPoint(null)}
                style={{ cursor: 'pointer' }}
              >
                <circle cx={pt.x} cy={pt.y} r={pt.data.revenue > 0 ? 4 : 2.5} fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" />
                <circle cx={pt.x} cy={pt.y} r="14" fill="transparent" />
              </g>
            ))}

            {/* X-axis date labels */}
            {chartPoints.points
              .filter((_, idx) => (idx % 4 === 0 && idx < chartPoints.points.length - 2) || idx === chartPoints.points.length - 1)
              .map((pt, idx) => (
                <text
                  key={idx}
                  x={pt.x}
                  y="162"
                  textAnchor="middle"
                  fill="var(--muted)"
                  fontSize="10"
                  fontFamily="inherit"
                >
                  {pt.data.label}
                </text>
              ))}
          </svg>
        </div>
      </div>

      {/* Recent Orders Section (Burmese Market Table Style) */}
      <section className="panel" style={{ marginBottom: 20 }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2>Recent orders</h2>
          </div>
          <button
            type="button"
            className="btn ghost small"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
            onClick={() => onOpen('orders')}
          >
            <span>View all</span>
            <ArrowUpRight size={14} />
          </button>
        </header>

        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Status</th>
                <th>Delivery</th>
                <th className="right">Total</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_orders.map((order) => {
                const customerName = [order.first_name, order.last_name].filter(Boolean).join(' ') || order.username || `User ${order.tg_user_id}`;
                const isWaiting = order.status === 'completed' && order.fulfillment === 'waiting';

                return (
                  <tr key={order.id} onClick={() => onOpen(`orders/${order.id}`)} style={{ cursor: 'pointer' }}>
                    <td className="name">
                      <strong>#{order.id}</strong>
                      <small>{when(order.created_at)}</small>
                    </td>
                    <td>
                      <div>{customerName}</div>
                      <small className="hint">{order.username ? `@${order.username}` : order.tg_user_id}</small>
                    </td>
                    <td>
                      {isWaiting ? (
                        <span className="pill warn">waiting to send</span>
                      ) : (
                        <span className={`pill ${tone(order.status)}`}>{order.status}</span>
                      )}
                    </td>
                    <td>
                      <span className="pill" style={{ background: 'var(--surface-2)', border: '1px solid var(--line)' }}>
                        {order.source === 'manual' ? 'Manual' : order.source === 'stock' ? 'Instant' : order.source || 'Instant'}
                      </span>
                    </td>
                    <td className="right money">
                      <strong>{money(order.price)}</strong>
                    </td>
                  </tr>
                );
              })}
              {stats.recent_orders.length === 0 ? <EmptyRow columns={5}>No orders yet.</EmptyRow> : null}
            </tbody>
          </table>
        </div>
      </section>

    </>
  );
}
