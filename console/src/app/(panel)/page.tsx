'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  X, LayoutDashboard, ShoppingBag, Wallet, UsersRound, Package, Truck,
  Boxes, FolderOpen, CalendarDays, Smile, Megaphone, Handshake, Activity as ActivityIcon,
  Settings as SettingsIcon, LogOut, ChevronRight, ShieldCheck, MoreHorizontal,
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
const ITEMS: { key: Key; label: string }[] = [
  { key: 'overview', label: 'Dashboard' },
  { key: 'orders', label: 'Orders' },
  { key: 'deposits', label: 'Deposits' },
  { key: 'users', label: 'Customers' },
  { key: 'products', label: 'Products' },
  { key: 'suppliers', label: 'Suppliers' },
  { key: 'inventory', label: 'Stock' },
  { key: 'categories', label: 'Categories' },
  { key: 'validities', label: 'Validity' },
  { key: 'emojis', label: 'Emojis' },
  { key: 'broadcast', label: 'Broadcast' },
  { key: 'reseller-apps', label: 'Reseller requests' },
  { key: 'activity', label: 'Activity' },
  { key: 'settings', label: 'Settings' },
];

const NAV_ICONS: Record<Key, LucideIcon> = {
  overview: LayoutDashboard, orders: ShoppingBag, deposits: Wallet, users: UsersRound,
  products: Package, suppliers: Truck, inventory: Boxes, categories: FolderOpen,
  validities: CalendarDays, emojis: Smile, broadcast: Megaphone,
  'reseller-apps': Handshake, activity: ActivityIcon, settings: SettingsIcon,
};
const NAV_GROUPS: { label: string; keys: Key[] }[] = [
  { label: 'Workspace', keys: ['overview', 'orders', 'deposits', 'users'] },
  { label: 'Catalog', keys: ['products', 'inventory', 'suppliers', 'categories', 'validities', 'emojis'] },
  { label: 'Manage', keys: ['broadcast', 'reseller-apps', 'activity', 'settings'] },
];
const MOBILE_KEYS: Key[] = ['overview', 'orders', 'products', 'inventory'];

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
  const mobileMenuButton = useRef<HTMLButtonElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const mainRef = useRef<HTMLElement | null>(null);
  const bottomNavRef = useRef<HTMLElement | null>(null);
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
    if (!mobileMenuOpen) return;
    const prevOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    const background = [workspaceRef.current, mainRef.current, bottomNavRef.current].filter((el): el is HTMLElement => Boolean(el));
    background.forEach((el) => { el.inert = true; });
    const controls = () => Array.from(drawerRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]') ?? []).filter((el) => el.getClientRects().length > 0);
    controls()[0]?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
      }
      if (event.key === 'Tab') {
        const all = controls();
        const first = all[0];
        const last = all[all.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    const closeOnDesktop = () => { if (window.innerWidth > 760) setMobileMenuOpen(false); };
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', closeOnEscape);
    window.addEventListener('resize', closeOnDesktop);
    return () => {
      document.body.style.overflow = prevOverflow;
      background.forEach((el) => { el.inert = false; });
      document.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('resize', closeOnDesktop);
      previousFocus?.focus();
    };
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
        {storeName ? (
          <span className="console-start-store">
            <BrandWordmark name={storeName} />
          </span>
        ) : null}
        <strong>{storeName ? `Getting ${storeName} ready` : 'Getting your store ready'}</strong>
        <span>Checking your session and store data</span>
        <div className="console-start-progress" aria-hidden="true"><span /></div>
      </div>
    </div>
  );
  if (sessionError) return <div className="gate"><div className="console-start" role="alert"><strong>Could not connect</strong><p>Your session could not be checked. Please retry.</p><button className="btn" onClick={() => void check()}>Retry connection</button></div></div>;
  if (!signedIn) return <SignIn onDone={check} storeName={storeName} />;

  const closeMobileMenu = () => {
    setMobileMenuOpen(false);
  };

  /** A screen, optionally with its tab: "orders/waiting". */
  const open = (address: string) => {
    const [key, tab = ''] = address.split('/');
    if (!isKey(key)) return;
    if (mobileMenuOpen) closeMobileMenu();
    if (window.location.hash.slice(1) !== address) {
      window.location.hash = address;
    }
    // hashchange applies navigation after the unsaved-settings guard.
  };
  const label = ITEMS.find((item) => item.key === screen.key)?.label ?? 'Dashboard';
  const navigation = () => NAV_GROUPS.map((group) => (
    <div className="nav-group" key={group.label}>
      <p className="nav-group-label">{group.label}</p>
      {group.keys.map((key) => {
        const Icon = NAV_ICONS[key];
        const item = ITEMS.find((entry) => entry.key === key)!;
        const count = key === 'orders' ? waitingOrders : key === 'deposits' ? pending : key === 'reseller-apps' ? pendingResellerApps : 0;
        return <button key={key} type="button" className={screen.key === key ? 'active' : ''} aria-current={screen.key === key ? 'page' : undefined} onClick={() => open(key)}>
          <Icon size={18} aria-hidden="true" /><span>{item.label}</span>
          {count > 0 ? <span className="count" aria-label={`${count} pending`}>{count}</span> : null}
          {screen.key === key && !count ? <ChevronRight size={14} className="nav-chevron" aria-hidden="true" /> : null}
        </button>;
      })}
    </div>
  ));

  return (
    <div className="console">
      <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>
        Skip to content
      </a>

      {/* Top Mobile Bar */}
      <div ref={workspaceRef} className="workspace-chrome">
      <header className="mobile-header">
        <div className="mobile-app-heading">
          <h1>{screen.key === 'overview' ? 'Home' : label}</h1>
        </div>
        <button
          ref={mobileMenuButton}
          type="button"
          className="hamburger-btn"
          onClick={() => setMobileMenuOpen((open) => !open)}
          aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={mobileMenuOpen}
          aria-controls="mobile-navigation"
        >
          <span className={`menu-toggle-icon menu-bars${mobileMenuOpen ? '' : ' visible'}`} aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <X className={`menu-toggle-icon menu-toggle-close${mobileMenuOpen ? ' visible' : ''}`} size={24} aria-hidden="true" />
        </button>
      </header>
      <header className="workspace-topbar">
        <div className="workspace-breadcrumb"><span>Workspace</span><ChevronRight size={14} aria-hidden="true" /><strong>{label}</strong></div>
        <div className="operator-badge"><ShieldCheck size={15} aria-hidden="true" /><span>Admin workspace</span></div>
      </header>
      </div>

      {/* Off-canvas Mobile Drawer */}
      <div
        className={`drawer-backdrop${mobileMenuOpen ? ' open' : ''}`}
        onClick={closeMobileMenu}
        aria-hidden={!mobileMenuOpen}
      >
        <aside ref={drawerRef} id="mobile-navigation" className="drawer-panel" role={mobileMenuOpen ? 'dialog' : undefined} aria-modal={mobileMenuOpen ? true : undefined} aria-label="Mobile navigation" onClick={(e) => e.stopPropagation()}>
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
              onClick={closeMobileMenu}
              aria-label="Close navigation"
            >
              <X size={20} />
            </button>
          </div>

          <div className="drawer-nav">{navigation()}</div>

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
              <LogOut size={17} aria-hidden="true" /><span>Sign out</span>
            </button>
          </div>
        </aside>
      </div>

      {/* Desktop Sidebar Rail */}
      <nav className="rail" aria-label="Main navigation">
        {(
          <button
            type="button"
            onClick={() => open('overview')}
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', width: '100%' }}
          >
            <Brand name={storeName || 'Store Console'} />
          </button>
        )}
        <div className="rail-items">{navigation()}</div>
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
            <LogOut size={17} aria-hidden="true" /><span>Sign out</span>
          </button>
        </div>
      </nav>

      <main ref={mainRef} className="main" id="main-content" tabIndex={-1}>
        <div className="main-inner" data-screen={screen.key}>
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

      <nav ref={bottomNavRef} className="mobile-dock" aria-label="Quick navigation">
        {MOBILE_KEYS.map((key) => {
          const Icon = NAV_ICONS[key];
          return <button key={key} type="button" className={screen.key === key ? 'active' : ''} aria-current={screen.key === key ? 'page' : undefined} onClick={() => open(key)}><Icon size={20} aria-hidden="true" /><span>{key === 'overview' ? 'Home' : key === 'inventory' ? 'Stock' : ITEMS.find((item) => item.key === key)!.label}</span></button>;
        })}
        <button type="button" className={!MOBILE_KEYS.includes(screen.key) ? 'active' : ''} aria-label="More navigation" aria-expanded={mobileMenuOpen} aria-controls="mobile-navigation" onClick={() => setMobileMenuOpen(true)}><MoreHorizontal size={20} aria-hidden="true" /><span>More</span></button>
      </nav>

      {toast ? (
        <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
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
      <span className="brand-symbol" aria-hidden="true"><Package size={21} /></span>
      <BrandWordmark name={name} />
    </div>
  );
}

function BrandWordmark({ name }: { name: string }) {
  const [initial, ...rest] = Array.from(name.trim());
  if (!initial) return null;
  return (
    <span className="brand-wordmark">
      <span className="brand-wordmark-initial">{initial}</span>
      <span>{rest.join('')}</span>
    </span>
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
        <div className="signin-heading">
          <h1>Welcome back</h1>
          <p>Sign in to manage your store.</p>
        </div>
        <label className="field">
          <span>Password</span>
          <span className="password-input">
            <input type={showPassword ? 'text' : 'password'} autoComplete="current-password" autoFocus required aria-describedby="signin-feedback" aria-invalid={Boolean(error)} value={password} onChange={(event) => setPassword(event.target.value)} />
            <button className="password-toggle" type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((shown) => !shown)}>
              {showPassword ? 'Hide' : 'Show'}
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
