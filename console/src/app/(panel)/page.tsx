'use client';

import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import {
  Eye,
  EyeOff,
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
  Sparkles,
  Globe,
  Briefcase,
  type LucideIcon,
} from 'lucide-react';
import { api, setCsrf } from '@/lib/api';
import { Broadcast } from '@/components/Broadcast';
import { Categories } from '@/components/Categories';
import { Validities } from '@/components/Validities';
import { Emojis } from '@/components/Emojis';
import { Suppliers } from '@/components/Suppliers';
import { Deposits } from '@/components/Deposits';
import { Inventory } from '@/components/Inventory';
import { Orders } from '@/components/Orders';
import { Overview } from '@/components/Overview';
import { Products } from '@/components/Products';
import { Settings, type SettingsTab } from '@/components/Settings';
import { Activity } from '@/components/Activity';
import { Users } from '@/components/Users';
import { ResellerApps } from '@/components/ResellerApps';
import { errorText } from '@/components/ui';

type Key =
  | 'activity'
  | 'overview'
  | 'orders'
  | 'inventory'
  | 'products'
  | 'suppliers'
  | 'categories'
  | 'validities'
  | 'emojis'
  | 'deposits'
  | 'users'
  | 'reseller-apps'
  | 'broadcast'
  | 'settings';

/** Ordered by daily importance: the most-used screens stay at the top, setup stays at the bottom. */
const ITEMS: { key: Key; label: string; icon: LucideIcon; group?: string }[] = [
  { key: 'overview', label: 'Dashboard', icon: LayoutDashboard, group: 'Workspace' },
  { key: 'orders', label: 'Orders', icon: ShoppingBag },
  { key: 'deposits', label: 'Deposits', icon: Wallet },
  { key: 'users', label: 'Customers', icon: UsersIcon },
  { key: 'products', label: 'Products', icon: Package, group: 'Catalog' },
  { key: 'suppliers', label: 'Suppliers', icon: Globe },
  { key: 'inventory', label: 'Stock', icon: Boxes },
  { key: 'categories', label: 'Categories', icon: FolderTree },
  { key: 'validities', label: 'Durations', icon: Clock },
  { key: 'emojis', label: 'Emojis', icon: Sparkles },
  { key: 'broadcast', label: 'Broadcast', icon: Megaphone, group: 'Manage' },
  { key: 'reseller-apps', label: 'Reseller Apps', icon: Briefcase },
  { key: 'activity', label: 'Activity', icon: Clock },
  { key: 'settings', label: 'Settings', icon: SettingsIcon },
];

const isKey = (value: string): value is Key => ITEMS.some((item) => item.key === value);

/** The address holds the screen and, for Settings, the tab (#settings/payments), so a reload lands in the same place. */
function readAddress(): { key: Key; tab: string } {
  const [key, tab = ''] = window.location.hash.slice(1).split('/');
  if (key === 'gate') return { key: 'settings', tab: 'channels' };
  if (key === 'instant') return { key: 'deposits', tab: 'instant' };
  return { key: isKey(key) ? key : 'overview', tab };
}

export default function ConsolePage() {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [sessionError, setSessionError] = useState(false);
  const [storeName, setStoreName] = useState<string>('');
  const [screen, setScreen] = useState<{ key: Key; tab: string }>({ key: 'overview', tab: '' });
  const activeScreen = useRef(screen);
  activeScreen.current = screen;
  const [pending, setPending] = useState(0);
  const [waitingOrders, setWaitingOrders] = useState(0);
  const [pendingResellerApps, setPendingResellerApps] = useState(0);
  const [toast, setToast] = useState<{ message: string; kind: 'good' | 'bad' } | null>(null);

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const say = useCallback((message: string, kind: 'good' | 'bad' = 'good') => {
    setToast({ message, kind });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 3200);
  }, []);

  const check = useCallback(async () => {
    setSessionError(false);
    try {
      const session = await api.session();
      if (session.signed_in && session.csrf) setCsrf(session.csrf);
      if (session.store_name !== undefined) setStoreName(session.store_name.trim());
      setSignedIn(session.signed_in);
    } catch {
      try {
        await new Promise((r) => setTimeout(r, 1200));
        const session = await api.session();
        if (session.signed_in && session.csrf) setCsrf(session.csrf);
        if (session.store_name !== undefined) setStoreName(session.store_name.trim());
        setSignedIn(session.signed_in);
      } catch {
        setSessionError(true);
      }
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    const handleStoreNameUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail !== undefined) {
        setStoreName((customEvent.detail || '').trim());
      }
    };
    window.addEventListener('store-name-updated', handleStoreNameUpdate);
    return () => window.removeEventListener('store-name-updated', handleStoreNameUpdate);
  }, []);

  useEffect(() => {
    if (storeName) {
      document.title = storeName;
    } else {
      document.title = 'Console';
    }
  }, [storeName]);

  useEffect(() => {
    if (!signedIn) return;
    api.settings()
      .then((s) => {
        if (s?.store_name !== undefined) {
          setStoreName(s.store_name.trim());
        }
      })
      .catch(() => undefined);
  }, [signedIn]);

  useEffect(() => {
    setScreen(readAddress());
    void check();
    const follow = () => {
      const next = readAddress();
      if (activeScreen.current.key === 'settings' && next.key !== 'settings' && !window.dispatchEvent(new Event('console-leave-settings', { cancelable: true }))) {
        window.history.replaceState(null, '', '#settings/' + activeScreen.current.tab);
        return;
      }
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

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [screen.key]);

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

  if (!ready) return (
    <div className="gate">
      <div className="console-start" role="status" aria-live="polite">
        {storeName ? <Brand name={storeName} /> : null}
        <div className="console-start-progress" aria-hidden="true" />
        <strong>Opening your workspace</strong>
        <span>Connecting securely…</span>
      </div>
    </div>
  );
  if (sessionError) return <div className="gate"><div className="console-start" role="alert"><strong>Could not connect</strong><p>Your session could not be checked. Please retry.</p><button className="btn" onClick={() => void check()}>Retry connection</button></div></div>;
  if (!signedIn) return <SignIn onDone={check} storeName={storeName} />;

  /** A screen, optionally with its tab: "orders/waiting". */
  const open = (address: string) => {
    const [key, tab = ''] = address.split('/');
    if (!isKey(key)) return;
    setMobileMenuOpen(false);
    if (window.location.hash.slice(1) !== address) {
      window.location.hash = address;
    }
    // hashchange applies navigation after the unsaved-settings guard.
  };
  const label = ITEMS.find((item) => item.key === screen.key)?.label ?? 'Dashboard';

  return (
    <div className="console">
      <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>
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
        {storeName ? (
          <button
            type="button"
            onClick={() => open('overview')}
            className="mobile-brand-title"
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left' }}
          >
            <span>{storeName}</span>
          </button>
        ) : null}
      </header>

      {/* Off-canvas Mobile Drawer */}
      <div
        className={`drawer-backdrop${mobileMenuOpen ? ' open' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
        aria-hidden={!mobileMenuOpen}
      >
        <aside className="drawer-panel" onClick={(e) => e.stopPropagation()}>
          <div className="drawer-header">
            {storeName ? (
              <button
                type="button"
                className="drawer-brand"
                onClick={() => open('overview')}
                style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left' }}
              >
                <Brand name={storeName} />
              </button>
            ) : <div />}
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
            {ITEMS.map(({ key, label: name, icon: Icon, group }) => (
              <Fragment key={key}>
              {group ? <h2 className="nav-section">{group}</h2> : null}
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
                {key === 'reseller-apps' && pendingResellerApps > 0 ? <span className="count">{pendingResellerApps}</span> : null}

              </button>
              </Fragment>
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
        {storeName ? (
          <button
            type="button"
            onClick={() => open('overview')}
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', width: '100%' }}
          >
            <Brand name={storeName} />
          </button>
        ) : null}
        <div className="rail-items">
          {ITEMS.map(({ key, label: name, icon: Icon, group }) => (
            <Fragment key={key}>
            {group ? <h2 className="nav-section">{group}</h2> : null}
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
              {key === 'reseller-apps' && pendingResellerApps > 0 ? <span className="count">{pendingResellerApps}</span> : null}

            </button>
            </Fragment>
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
          {screen.key !== 'overview' && !(screen.key === 'users' && screen.tab) ? (
            <header className="page-head">
              <h1>{label}</h1>
            </header>
          ) : null}

          {screen.key === 'overview' ? <Overview say={say} onOpen={open} /> : null}
          {screen.key === 'orders' ? (
            <Orders
              key={screen.tab === 'waiting' ? 'waiting' : 'all'}
              say={say}
              initialWaiting={screen.tab === 'waiting'}
              initialOrderId={/^\d+$/.test(screen.tab) ? Number(screen.tab) : null}
              onWaitingChange={setWaitingOrders}
            />
          ) : null}
          {screen.key === 'deposits' ? <Deposits say={say} initialMode={screen.tab === 'instant' ? 'instant' : 'deposits'} onPendingChange={setPending} /> : null}
          {screen.key === 'products' ? <Products say={say} /> : null}
          {screen.key === 'suppliers' ? <Suppliers say={say} onOpen={open} /> : null}
          {screen.key === 'categories' ? <Categories say={say} /> : null}
          {screen.key === 'validities' ? <Validities say={say} /> : null}
          {screen.key === 'emojis' ? <Emojis say={say} /> : null}
          {screen.key === 'inventory' ? <Inventory say={say} /> : null}
          {screen.key === 'users' ? (
            <Users
              key={screen.tab}
              say={say}
              initialUserId={/^\d+$/.test(screen.tab) ? Number(screen.tab) : null}
              onNavigate={(userId) => {
                const target = userId ? `users/${userId}` : 'users';
                window.location.hash = target;
              }}
            />
          ) : null}
          {screen.key === 'activity' ? <Activity say={say} /> : null}
          {screen.key === 'reseller-apps' ? (
            <ResellerApps say={say} onPendingChange={setPendingResellerApps} />
          ) : null}
          {screen.key === 'broadcast' ? <Broadcast say={say} /> : null}

          {screen.key === 'settings' ? (
            <Settings
              say={say}
              initialTab={screen.tab as SettingsTab}
              onTabChange={(tab) => { window.history.replaceState(null, '', `#settings/${tab}`); setScreen({key: 'settings', tab}); }}
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

function Brand({ name }: { name?: string }) {
  if (!name) return null;
  return (
    <div className="brand">
      <b>{name}</b>
    </div>
  );
}

function SignIn({ onDone, storeName }: { onDone: () => void; storeName?: string }) {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  return (
    <div className="gate">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
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
        {storeName ? <Brand name={storeName} /> : null}
        <label className="field">
          <span>Password</span>
          <span className="password-input">
            <input type={showPassword ? 'text' : 'password'} autoComplete="current-password" autoFocus required aria-describedby="signin-feedback" aria-invalid={Boolean(error)} value={password} onChange={(event) => setPassword(event.target.value)} />
            <button className="password-toggle" type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((shown) => !shown)}>
              {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
            </button>
          </span>
        </label>
        <p id="signin-feedback" className="signin-feedback" role="status" aria-live="polite">{error}</p>
        <button className="btn block" type="submit" disabled={busy}>
          {busy ? 'Checking…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
