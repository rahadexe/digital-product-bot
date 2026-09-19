'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CircleAlert,
  CircleCheck,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Menu,
  Package,
  Settings as SettingsIcon,
  ShoppingBag,
  Boxes,
  Users as UsersIcon,
  Wallet,
  X,
  FolderTree,
  Clock,
  type LucideIcon,
} from 'lucide-react';
import { api, setCsrf } from '@/lib/api';
import { Broadcast } from '@/components/Broadcast';
import { Categories } from '@/components/Categories';
import { Validities } from '@/components/Validities';
import { Deposits } from '@/components/Deposits';
import { Inventory } from '@/components/Inventory';
import { Orders } from '@/components/Orders';
import { Overview } from '@/components/Overview';
import { Products } from '@/components/Products';
import { Settings, type SettingsTab } from '@/components/Settings';
import { Users } from '@/components/Users';
import { errorText } from '@/components/ui';

type Key =
  | 'overview'
  | 'orders'
  | 'inventory'
  | 'products'
  | 'categories'
  | 'validities'
  | 'deposits'
  | 'users'
  | 'broadcast'
  | 'settings';

/** Ordered by daily importance: the most-used screens stay at the top, setup stays at the bottom. */
const ITEMS: { key: Key; label: string; icon: LucideIcon }[] = [
  { key: 'overview', label: 'Dashboard', icon: LayoutDashboard },
  { key: 'orders', label: 'Orders', icon: ShoppingBag },
  { key: 'inventory', label: 'Stock', icon: Boxes },
  { key: 'products', label: 'Products', icon: Package },
  { key: 'categories', label: 'Categories', icon: FolderTree },
  { key: 'validities', label: 'Validities', icon: Clock },
  { key: 'deposits', label: 'Deposits', icon: Wallet },
  { key: 'users', label: 'Customers', icon: UsersIcon },
  { key: 'broadcast', label: 'Broadcast', icon: Megaphone },
  { key: 'settings', label: 'Settings', icon: SettingsIcon },
];
const isKey = (value: string): value is Key => ITEMS.some((item) => item.key === value);

/** The address holds the screen and, for Settings, the tab (#settings/payments), so a reload lands in the same place. */
function readAddress(): { key: Key; tab: string } {
  const [key, tab = ''] = window.location.hash.slice(1).split('/');
  if (key === 'gate') return { key: 'settings', tab: 'access' };
  if (key === 'instant') return { key: 'deposits', tab: 'instant' };
  return { key: isKey(key) ? key : 'overview', tab };
}

export default function ConsolePage() {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [screen, setScreen] = useState<{ key: Key; tab: string }>({ key: 'overview', tab: '' });
  const [pending, setPending] = useState(0);
  const [waitingOrders, setWaitingOrders] = useState(0);
  const [toast, setToast] = useState<{ message: string; kind: 'good' | 'bad' } | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const say = useCallback((message: string, kind: 'good' | 'bad' = 'good') => {
    setToast({ message, kind });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 3200);
  }, []);

  const check = useCallback(async () => {
    try {
      const session = await api.session();
      if (session.signed_in && session.csrf) setCsrf(session.csrf);
      setSignedIn(session.signed_in);
    } catch {
      try {
        await new Promise((r) => setTimeout(r, 1200));
        const session = await api.session();
        if (session.signed_in && session.csrf) setCsrf(session.csrf);
        setSignedIn(session.signed_in);
      } catch {
        setSignedIn(false);
      }
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    setScreen(readAddress());
    void check();
    const follow = () => {
      const next = readAddress();
      setScreen((prev) => (prev.key === next.key && prev.tab === next.tab ? prev : next));
    };
    const expired = () => setSignedIn(false);
    window.addEventListener('hashchange', follow);
    window.addEventListener('session-expired', expired);
    return () => {
      window.removeEventListener('hashchange', follow);
      window.removeEventListener('session-expired', expired);
      window.clearTimeout(timer.current);
    };
  }, [check]);

  // Lock background body scroll when mobile drawer is open
  useEffect(() => {
    if (mobileMenuOpen) {
      const prevOverflow = document.body.style.overflow;
      const prevTouchAction = document.body.style.touchAction;
      document.body.style.overflow = 'hidden';
      document.body.style.touchAction = 'none';
      return () => {
        document.body.style.overflow = prevOverflow;
        document.body.style.touchAction = prevTouchAction;
      };
    }
  }, [mobileMenuOpen]);

  // The two numbers worth keeping current while the console is open: deposits to review and paid orders not sent.
  useEffect(() => {
    if (!signedIn) return;
    const count = () => {
      api.deposits('pending', 1).then((result) => setPending(result.total)).catch(() => undefined);
      api.orders('', 1, 0, true).then((result) => setWaitingOrders(result.waiting)).catch(() => undefined);
    };
    count();
    const every = window.setInterval(count, 60_000);
    return () => window.clearInterval(every);
  }, [signedIn]);

  if (!ready) return <div className="gate" />;
  if (!signedIn) return <SignIn onDone={check} />;

  /** A screen, optionally with its tab: "orders/waiting". */
  const open = (address: string) => {
    const [key, tab = ''] = address.split('/');
    if (!isKey(key)) return;
    setMobileMenuOpen(false);
    if (window.location.hash.slice(1) !== address) {
      window.location.hash = address;
    }
    setScreen((prev) => (prev.key === key && prev.tab === tab ? prev : { key, tab }));
  };
  const label = ITEMS.find((item) => item.key === screen.key)?.label ?? 'Dashboard';

  return (
    <div className="console">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      {/* Top Mobile Bar */}
      <header className="mobile-header">
        <button
          type="button"
          className="hamburger-btn"
          onClick={() => setMobileMenuOpen(true)}
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>
        <button
          type="button"
          onClick={() => open('overview')}
          className="mobile-brand-title"
          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left' }}
        >
          <span>Bot Admin</span>
          <span className="online-indicator" />
        </button>
      </header>

      {/* Off-canvas Mobile Drawer */}
      <div
        className={`drawer-backdrop${mobileMenuOpen ? ' open' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
        aria-hidden={!mobileMenuOpen}
      >
        <aside className="drawer-panel" onClick={(e) => e.stopPropagation()}>
          <div className="drawer-header">
            <button
              type="button"
              className="drawer-brand"
              onClick={() => open('overview')}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left' }}
            >
              <Brand />
              <span className="online-indicator" />
            </button>
            <button
              type="button"
              className="drawer-close"
              onClick={() => setMobileMenuOpen(false)}
              aria-label="Close navigation"
            >
              <X size={20} />
            </button>
          </div>

          <div className="drawer-nav">
            {ITEMS.map(({ key, label: name, icon: Icon }) => (
              <button
                key={key}
                type="button"
                className={screen.key === key ? 'active' : ''}
                onClick={() => open(key)}
              >
                <Icon size={18} />
                <span>{name}</span>
                {key === 'deposits' && pending > 0 ? <span className="count">{pending}</span> : null}
                {key === 'orders' && waitingOrders > 0 ? <span className="count">{waitingOrders}</span> : null}
              </button>
            ))}
          </div>

          <div className="drawer-footer">
            <button
              type="button"
              className="sign-out"
              onClick={async () => {
                try {
                  await api.logout();
                  setSignedIn(false);
                } catch (cause) {
                  say(errorText(cause, 'Could not sign out.'), 'bad');
                }
              }}
            >
              <LogOut size={16} />
              <span>Sign out</span>
            </button>
          </div>
        </aside>
      </div>

      {/* Desktop Sidebar Rail */}
      <nav className="rail" aria-label="Main navigation">
        <Brand />
        <div className="rail-items">
          {ITEMS.map(({ key, label: name, icon: Icon }) => (
            <button
              key={key}
              type="button"
              className={screen.key === key ? 'active' : ''}
              aria-current={screen.key === key ? 'page' : undefined}
              onClick={() => open(key)}
            >
              <Icon aria-hidden="true" />
              <span>{name}</span>
              {key === 'deposits' && pending > 0 ? <span className="count">{pending}</span> : null}
              {key === 'orders' && waitingOrders > 0 ? <span className="count">{waitingOrders}</span> : null}
            </button>
          ))}
        </div>
        <div className="spacer" />
        <div className="rail-foot">
          <button
            type="button"
            className="sign-out"
            onClick={async () => {
              try {
                await api.logout();
                setSignedIn(false);
              } catch (cause) {
                say(errorText(cause, 'Could not sign out.'), 'bad');
              }
            }}
          >
            <LogOut aria-hidden="true" />
            <span>Sign out</span>
          </button>
        </div>
      </nav>

      <main className="main" id="main-content" tabIndex={-1}>
        <div className="main-inner">
          {screen.key !== 'overview' ? (
            <header className="page-head hide-mobile">
              <h1>{label}</h1>
            </header>
          ) : null}

          {screen.key === 'overview' ? <Overview say={say} onOpen={open} /> : null}
          {screen.key === 'orders' ? (
            <Orders
              key={screen.tab}
              say={say}
              initialWaiting={screen.tab === 'waiting'}
              initialOrderId={/^\d+$/.test(screen.tab) ? Number(screen.tab) : null}
              onWaitingChange={setWaitingOrders}
            />
          ) : null}
          {screen.key === 'deposits' ? <Deposits say={say} initialMode={screen.tab === 'instant' ? 'instant' : 'deposits'} onPendingChange={setPending} /> : null}
          {screen.key === 'products' ? <Products say={say} /> : null}
          {screen.key === 'categories' ? <Categories say={say} /> : null}
          {screen.key === 'validities' ? <Validities say={say} /> : null}
          {screen.key === 'inventory' ? <Inventory say={say} /> : null}
          {screen.key === 'users' ? <Users say={say} /> : null}
          {screen.key === 'broadcast' ? <Broadcast say={say} /> : null}
          {screen.key === 'settings' ? (
            <Settings
              say={say}
              initialTab={screen.tab as SettingsTab}
              onTabChange={(tab) => window.history.replaceState(null, '', `#settings/${tab}`)}
            />
          ) : null}
        </div>
      </main>

      {toast ? (
        <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
          {toast.kind === 'good' ? <CircleCheck aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}
          {toast.message}
        </div>
      ) : null}
    </div>
  );
}

function Brand() {
  return (
    <div className="brand">
      <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="#0f766e" />
        <rect x="8" y="17" width="4" height="7" rx="1.5" fill="#ffffff" />
        <rect x="14" y="13" width="4" height="11" rx="1.5" fill="#ffffff" />
        <rect x="20" y="8" width="4" height="16" rx="1.5" fill="#9fe0d4" />
      </svg>
      <div>
        <b>Bot Admin</b>
      </div>
    </div>
  );
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  return (
    <div className="gate">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError('');
          try {
            await api.login(password);
            setPassword('');
            onDone();
          } catch (cause) {
            setError(errorText(cause, 'Sign in failed.'));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Brand />
        <label className="field">
          <span>Password</span>
          <input type="password" autoComplete="current-password" autoFocus required value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error ? <p className="note bad">{error}</p> : null}
        <button className="btn block" type="submit" disabled={busy}>
          {busy ? 'Checking…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
