export interface SessionResponse {
  signed_in: boolean;
  csrf: string;
  token?: string | null;
  expires_in?: number;
}

export interface OverviewStats {
  total_users: number;
  total_orders: number;
  total_revenue: number;
  delivered_orders?: number;
  available_stock: number;
  pending_deposits: number;
  waiting_orders: number;
  chart_data?: Array<{
    date: string;
    label: string;
    revenue: number;
    orders: number;
  }>;
  recent_orders: Array<{
    id: number;
    user_id: number;
    tg_user_id: number;
    username?: string;
    first_name?: string;
    last_name?: string;
    product_title: string;
    price: number;
    status: string;
    fulfillment?: string;
    source?: string;
    created_at: string;
  }>;
  stock_summary: Array<{
    id: number;
    title: string;
    price: number;
    stock: number;
  }>;
}

export interface Category {
  id: number;
  name: string;
  icon: string;
  sort_order: number;
  is_active: number;
  is_pinned?: number;
  has_validity_filter?: number;
  custom_emoji_id?: string;
}

export interface EmojiLibraryItem {
  id?: number;
  name: string;
  emoji_id: string;
  is_system: boolean;
  category?: string;
  created_at?: string;
}

export interface EmojiLibraryResponse {
  system: EmojiLibraryItem[];
  custom: EmojiLibraryItem[];
  all: EmojiLibraryItem[];
}

export interface Product {
  id: number;
  category_id?: number;
  category_name?: string;
  title: string;
  description: string;
  price: number;
  reseller_price?: number | null;
  icon: string;
  duration_label: string;
  sort_order: number;
  is_active: number;
  delivery_type?: 'stock' | 'manual';
  custom_emoji_id?: string;
  created_at?: string;
  stock?: number;
}

export interface InventoryItem {
  id: number;
  product_id: number;
  product_title?: string;
  content: string;
  status: string;
  order_id?: number;
  created_at: string;
  sold_at?: string;
  expires_at?: string | null;
  /** How many customers this item can go to (7 for an account shared by seven devices), and how many it has. */
  max_uses: number;
  uses: number;
}

export interface Order {
  delivery_status?: string;
  id: number;
  user_id: number;
  tg_user_id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  product_id: number;
  product_title: string;
  base_product_title?: string;
  product_icon?: string;
  duration_label?: string;
  request_id?: string | null;
  price: number;
  delivered_item: string;
  status: string;
  created_at: string;
  /** 'waiting': a paid manual order awaiting fulfillment. */
  fulfillment: 'delivered' | 'waiting';
  /** 'supplier' only appears on orders placed before that integration was removed. */
  source: 'stock' | 'supplier' | 'manual' | 'legacy';
  fulfilled_at?: string | null;
}

export interface OrderDetail {
  order: Order & { customer_balance?: number };
  stock_item: { id: number; max_uses: number; uses: number; status: string } | null;
  messages: { id: number; text: string; status: string; attempts: number; error: string; is_receipt: boolean }[];
}

export interface OrderSummary {
  total_orders: number;
  total_revenue: number;
  delivered_orders: number;
  waiting_orders: number;
}

export interface UserSummary {
  total_users: number;
  total_balance: number;
  with_balance_count: number;
  banned_count: number;
  reseller_count?: number;
}

export interface DepositSummary {
  total_completed_amount: number;
  pending_count: number;
  pending_amount: number;
  today_amount: number;
}

export interface InventorySummary {
  available_units: number;
  sold_units: number;
  expired_units: number;
  in_stock_products: number;
}

export interface Deposit {
  id: number;
  user_id: number;
  tg_user_id: number;
  username?: string;
  first_name?: string;
  method_id: number;
  method_name: string;
  amount: number;
  transaction_id: string;
  status: 'pending' | 'approved' | 'rejected';
  /** Exchange rate and payable amount shown to the customer; null for deposits made before they were recorded. */
  rate_to_currency?: number | null;
  pay_amount?: number | null;
  admin_note?: string;
  created_at: string;
  reviewed_at?: string;
  /** Who checks this deposit's method: 'binance' and 'binance_pay' can be looked up, 'none' is yours to verify. */
  auto_verify?: 'none' | 'binance' | 'binance_pay';
}

export interface PaymentInvoice {
  id: number;
  reference: string;
  provider: string;
  tg_user_id: number;
  username?: string | null;
  first_name?: string | null;
  credit_amount: number;
  pay_amount: number;
  rate: number;
  status: 'created' | 'pending' | 'completed' | 'failed' | 'expired';
  provider_invoice_id?: string | null;
  provider_transaction_id?: string | null;
  payment_method?: string | null;
  deposit_id?: number | null;
  last_error?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface PaymentsStatus {
  enabled: boolean;
  has_api_key: boolean;
  public_url: string;
  webhook_url: string;
  ready: boolean;
  counts: Record<string, number>;
  /** What ZiniPay said the last time it refused a payment, if it ever has. */
  last_error?: string;
  last_error_at?: string | null;
}

export interface BinanceStatus {
  enabled: boolean;
  has_credentials: boolean;
  coin: string;
  ready: boolean;
  methods: { id: number; name: string; network: string; is_active: number }[];
}

export interface DepositMethod {
  id: number;
  name: string;
  account_info: string;
  instructions: string;
  min_deposit: number;
  rate_to_currency: number;
  is_active: number;
  sort_order: number;
  /** Who confirms a payment made with this method: nobody, the shop's Binance deposits, or Binance Pay. */
  auto_verify?: 'none' | 'binance' | 'binance_pay';
  /** The only network accepted when set, e.g. TRX for TRC20 or BSC for BEP20. */
  auto_verify_network?: string;
  custom_emoji_id?: string | null;
  account_type?: 'personal' | 'agent' | 'merchant';
}

export interface User {
  id: number;
  tg_user_id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  balance: number;
  total_spent: number;
  rank: string;
  referred_by?: number;
  is_banned: number;
  created_at: string;
  api_key_prefix?: string | null;
  api_key_active?: number | null;
  api_key_last_used_at?: string | null;
}

export interface ResellerKeyInfo {
  id: number;
  user_id: number;
  tg_user_id: number;
  key_prefix: string;
  name: string;
  is_active: number;
  created_at: string;
  last_used_at?: string | null;
}

export interface ResellerStats {
  total_orders: number;
  total_spent: number;
}

export interface GateChannel {
  id: number;
  channel_username: string;
  chat_id: string;
  title: string;
  invite_link: string;
  is_active: number;
}

export interface UpdateChannel {
  id: number;
  title: string;
  url: string;
  sort_order: number;
  is_active: number;
}

const API_BASE =
  typeof window !== 'undefined' && ['3000', '3001'].includes(window.location.port)
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : '';

/** A path on the API server, for images the console shows (the dev server runs on another port). */
export const apiUrl = (path: string) => `${API_BASE}${path}`;

const TOKEN_KEY = 'admin_session_token';
const CSRF_KEY = 'admin_csrf';

// Clear credentials persisted by older builds; session cookies are HttpOnly.
if (typeof window !== 'undefined') {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(CSRF_KEY);
}
let cachedCsrf = '';
export function setCsrf(token: string) { cachedCsrf = token; }

// Going back to a screen shows what it showed a moment ago instead of waiting on the database again.
// Anything that changes data clears it all, so a save is never followed by a stale list.
const FRESH_FOR_MS = 20_000;
const LIVE_PATHS = ['/api/admin/session', '/health/', '/broadcast/'];
const answers = new Map<string, { at: number; value: Promise<unknown> }>();

/** Forget every remembered answer, for a Refresh button. */
export function forgetAnswers() {
  answers.clear();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method || 'GET';
  if (method !== 'GET') {
    answers.clear();
    return requestUncached<T>(path, options);
  }
  if (LIVE_PATHS.some((live) => path.includes(live))) return requestUncached<T>(path, options);

  const known = answers.get(path);
  if (known && Date.now() - known.at < FRESH_FOR_MS) return known.value as Promise<T>;
  const value = requestUncached<T>(path, options);
  if (answers.size >= 256) answers.delete(answers.keys().next().value!);
  answers.set(path, { at: Date.now(), value });
  value.catch(() => {
    if (answers.get(path)?.value === value) answers.delete(path);
  });
  return value;
}

async function requestUncached<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');

  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const csrf = cachedCsrf;
  if (csrf && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method || 'GET')) {
    headers.set('x-csrf-token', csrf);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (res.status === 401 && !path.endsWith('/login') && !path.endsWith('/session')) {
    cachedCsrf = '';
    answers.clear();
    if (typeof window !== 'undefined') {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(CSRF_KEY);
    }
    window.dispatchEvent(new Event('session-expired'));
  }
  if (!res.ok) {
    let errMessage = `Error ${res.status}: ${res.statusText}`;
    try {
      const data = await res.json();
      if (data.detail) errMessage = typeof data.detail === 'string' ? data.detail : data.detail.map((x: {msg: string}) => x.msg).join('; ');
    } catch {
      // ignore
    }
    throw new Error(errMessage);
  }

  return res.json();
}

export const api = {
  setBan: (id: number, banned: boolean) => request(`/api/admin/users/${id}/ban`, {method: 'POST', body: JSON.stringify({banned})}),
  health: () => request<{status: string; bot: string}>('/health/ready'),
  retryDelivery: (id: number) => request(`/api/admin/orders/${id}/retry-delivery`, {method: 'POST'}),
  broadcastProgress: (id: number) => request<{id:number; success:number; failed:number; pending:number; total:number}>(`/api/admin/broadcast/${id}`),
  session: async () => {
    const data = await request<SessionResponse>('/api/admin/session');
    if (data.csrf) setCsrf(data.csrf);
    if (!data.signed_in) { setCsrf(''); forgetAnswers(); }
    return data;
  },

  login: async (password: string) => {
    const data = await request<{ success: boolean; csrf: string; token?: string | null; expires_in?: number }>('/api/admin/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
    if (data.csrf) setCsrf(data.csrf);
    return data;
  },

  logout: async () => {
    try {
      return await request<{ success: boolean }>('/api/admin/logout', { method: 'POST' });
    } finally {
      cachedCsrf = '';
      if (typeof window !== 'undefined') {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(CSRF_KEY);
      }
    }
  },

  overview: () => request<OverviewStats>('/api/admin/overview'),

  // Categories
  categories: () => request<Category[]>('/api/admin/categories'),
  createCategory: (data: Partial<Category>) =>
    request<{ success: boolean; id: number }>('/api/admin/categories', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCategory: (id: number, data: Partial<Category>) =>
    request<{ success: boolean }>(`/api/admin/categories/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteCategory: (id: number) =>
    request<{ success: boolean }>(`/api/admin/categories/${id}`, { method: 'DELETE' }),

  // Products
  products: (categoryId?: number) =>
    request<Product[]>(`/api/admin/products${categoryId ? `?category_id=${categoryId}` : ''}`),
  createProduct: (data: Partial<Product>) =>
    request<{ success: boolean; id: number }>('/api/admin/products', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateProduct: (id: number, data: Partial<Product>) =>
    request<{ success: boolean }>(`/api/admin/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteProduct: (id: number) =>
    request<{ success: boolean }>(`/api/admin/products/${id}`, { method: 'DELETE' }),
  announceProduct: (id: number) =>
    request<{ success: boolean }>(`/api/admin/products/${id}/announce`, { method: 'POST' }),

  // Inventory
  inventory: (productId?: number, status?: string, offset = 0) => {
    const params = new URLSearchParams({offset: String(offset), limit: '100'});
    if (productId) params.set('product_id', String(productId));
    if (status) params.set('status', status);
    return request<{ items: InventoryItem[]; total: number; summary?: InventorySummary }>(`/api/admin/inventory?${params.toString()}`);
  },
  bulkAddStock: (productId: number, itemsText: string, maxUses = 1, expiresAt?: string) =>
    request<{ success: boolean; added_count: number; skipped_count: number }>('/api/admin/inventory/bulk', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, items_text: itemsText, max_uses: maxUses, expires_at: expiresAt || null }),
    }),
  updateInventoryItem: (id: number, content: string, maxUses: number, expiresAt?: string) =>
    request<{ success: boolean; item: InventoryItem }>(`/api/admin/inventory/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ content, max_uses: maxUses, expires_at: expiresAt || null }),
    }),
  deleteInventoryItem: (id: number) =>
    request<{ success: boolean }>(`/api/admin/inventory/${id}`, { method: 'DELETE' }),

  orders: (
    search = '',
    limit = 50,
    offset = 0,
    waiting = false,
    customer?: number,
    days?: number,
    dateFrom?: string,
    dateTo?: string
  ) => {
    let url = `/api/admin/orders?search=${encodeURIComponent(search)}&limit=${limit}&offset=${offset}${waiting ? '&waiting=true' : ''}`;
    if (customer) url += `&customer=${customer}`;
    if (days) url += `&days=${days}`;
    if (dateFrom) url += `&date_from=${encodeURIComponent(dateFrom)}`;
    if (dateTo) url += `&date_to=${encodeURIComponent(dateTo)}`;
    return request<{ orders: Order[]; total: number; waiting: number; summary?: OrderSummary }>(url);
  },
  orderDetail: (id: number) => request<OrderDetail>(`/api/admin/orders/${id}`),
  deliverOrder: (id: number, content: string) =>
    request<{ success: boolean }>(`/api/admin/orders/${id}/deliver`, { method: 'POST', body: JSON.stringify({ content }) }),
  refundOrder: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/admin/orders/${id}/refund`, {
      method: 'POST',
    }),

  // Deposits
  deposits: (status?: string, limit = 50, offset = 0) =>
    request<{ deposits: Deposit[]; total: number; summary?: DepositSummary }>(
      `/api/admin/deposits?${status ? `status=${status}&` : ''}limit=${limit}&offset=${offset}`
    ),
  approveDeposit: (id: number, adminNote = '') =>
    request<{ success: boolean; message: string }>(`/api/admin/deposits/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ admin_note: adminNote }),
    }),
  rejectDeposit: (id: number, adminNote = 'Invalid transaction ID') =>
    request<{ success: boolean; message: string }>(`/api/admin/deposits/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ admin_note: adminNote }),
    }),
  depositMethods: () => request<DepositMethod[]>('/api/admin/deposit-methods'),
  createDepositMethod: (data: Partial<DepositMethod>) =>
    request<{ success: boolean; id: number }>('/api/admin/deposit-methods', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateDepositMethod: (id: number, data: Partial<DepositMethod>) =>
    request<{ success: boolean }>(`/api/admin/deposit-methods/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteDepositMethod: (id: number) =>
    request<{ success: boolean }>(`/api/admin/deposit-methods/${id}`, { method: 'DELETE' }),

  // Instant payments (ZiniPay)
  paymentsStatus: () => request<PaymentsStatus>('/api/admin/payments/status'),
  testPayments: () => request<{ ok: boolean; message: string }>('/api/admin/payments/test', { method: 'POST' }),
  testPaymentPage: () =>
    request<{ ok: boolean; message: string; payment_url?: string }>('/api/admin/payments/test-invoice', { method: 'POST' }),
  payments: (status?: string, limit = 50, offset = 0) =>
    request<{ invoices: PaymentInvoice[]; total: number }>(
      `/api/admin/payments?${status ? `status=${status}&` : ''}limit=${limit}&offset=${offset}`
    ),
  checkPayment: (reference: string) =>
    request<{ success: boolean; status: PaymentInvoice['status'] }>(`/api/admin/payments/${reference}/check`, { method: 'POST' }),
  checkPendingPayments: () => request<{ checked: number }>('/api/admin/payments/check-pending', { method: 'POST' }),

  // USDT deposits confirmed against the shop's Binance account
  binanceStatus: () => request<BinanceStatus>('/api/admin/payments/binance/status'),
  testBinance: () => request<{ ok: boolean; message: string }>('/api/admin/payments/binance/test', { method: 'POST' }),
  checkDepositOnBinance: (depositId: number) =>
    request<{ checked: boolean; credited: boolean; detail: string }>(`/api/admin/deposits/${depositId}/check`, { method: 'POST' }),
  recheckBinanceDeposits: () => request<{ checked: number }>('/api/admin/payments/binance/check-pending', { method: 'POST' }),

  // Users
  users: (search = '', limit = 50, offset = 0, filter?: string) =>
    request<{ users: User[]; total: number; summary?: UserSummary }>(
      `/api/admin/users?search=${encodeURIComponent(search)}&limit=${limit}&offset=${offset}${filter ? `&filter=${encodeURIComponent(filter)}` : ''}`
    ),
  user: (tgUserId: number) =>
    request<{
      user: User;
      reseller_key?: ResellerKeyInfo | null;
      reseller_stats?: ResellerStats | null;
    }>(`/api/admin/users/${tgUserId}`),
  adjustBalance: (tgUserId: number, delta: number, reason: string) =>
    request<{ success: boolean; user: User }>(`/api/admin/users/${tgUserId}/adjust-balance`, {
      method: 'POST',
      body: JSON.stringify({ delta, reason }),
    }),
  toggleBan: (tgUserId: number) =>
    request<{ success: boolean; is_banned: boolean }>(`/api/admin/users/${tgUserId}/ban`, {
      method: 'POST',
    }),
  setUserRank: (tgUserId: number, rank: string) =>
    request<{ success: boolean; rank: string }>(`/api/admin/users/${tgUserId}/rank`, {
      method: 'POST',
      body: JSON.stringify({ rank }),
    }),
  toggleResellerKey: (tgUserId: number) =>
    request<{ success: boolean; reseller_key: ResellerKeyInfo }>(
      `/api/admin/users/${tgUserId}/reseller-key/toggle`,
      { method: 'POST' }
    ),
  generateResellerKey: (tgUserId: number) =>
    request<{ success: boolean; raw_key: string; reseller_key: ResellerKeyInfo }>(
      `/api/admin/users/${tgUserId}/reseller-key/generate`,
      { method: 'POST' }
    ),

  // Gate channels
  gateChannels: () => request<GateChannel[]>('/api/admin/gate-channels'),
  addGateChannel: (data: Partial<GateChannel>) =>
    request<{ success: boolean; id: number }>('/api/admin/gate-channels', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateGateChannel: (id: number, data: Partial<GateChannel>) =>
    request<{ success: boolean }>(`/api/admin/gate-channels/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteGateChannel: (id: number) =>
    request<{ success: boolean }>(`/api/admin/gate-channels/${id}`, { method: 'DELETE' }),

  // Channels under the bot's 📢 Channel menu
  updateChannels: () => request<UpdateChannel[]>('/api/admin/update-channels'),
  addUpdateChannel: (data: Partial<UpdateChannel>) =>
    request<{ success: boolean; id: number }>('/api/admin/update-channels', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  editUpdateChannel: (id: number, data: Partial<UpdateChannel>) =>
    request<{ success: boolean }>(`/api/admin/update-channels/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteUpdateChannel: (id: number) =>
    request<{ success: boolean }>(`/api/admin/update-channels/${id}`, { method: 'DELETE' }),

  // Broadcast
  broadcast: (text: string) =>
    request<{ id: number; success: number; failed: number; pending: number; total: number }>('/api/admin/broadcast', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  broadcastInfo: () =>
    request<{
      recipient_count: number;
      recent: Array<{
        id: number;
        created_at: string;
        text: string;
        total: number;
        success: number;
        failed: number;
        pending: number;
      }>;
    }>('/api/admin/broadcast'),
  deleteBroadcast: (id: number) =>
    request<{ success: boolean }>(`/api/admin/broadcast/${id}`, { method: 'DELETE' }),

  // Emoji Library
  emojis: () => request<EmojiLibraryResponse>('/api/admin/emojis'),
  createEmoji: (data: { name: string; emoji_id: string }) =>
    request<{ success: boolean; id: number }>('/api/admin/emojis', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteEmoji: (id: string | number) =>
    request<{ success: boolean }>(`/api/admin/emojis/${id}`, { method: 'DELETE' }),

  // Settings
  settings: () => request<Record<string, string>>('/api/admin/settings'),
  updateSettings: (data: Record<string, string>) =>
    request<{ success: boolean }>('/api/admin/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  testAdminNotification: () =>
    request<{
      success: boolean;
      message?: string;
      delivered_count: number;
      total_admins: number;
      results: { chat_id: number; delivered: boolean; error?: string | null }[];
    }>('/api/admin/settings/test-admin-notification', { method: 'POST' }),


  // Audit
  auditLogs: (filters: { search?: string; action?: string; security?: boolean; offset?: number } = {}) => {
    const params = new URLSearchParams({ limit: '50', offset: String(filters.offset ?? 0) });
    if (filters.search) params.set('search', filters.search);
    if (filters.action) params.set('action', filters.action);
    if (filters.security) params.set('security', 'true');
    return request<{ entries: Array<{ id: number; action: string; details: string; created_at: string }>; total: number; actions: string[] }>(
      `/api/admin/audit-logs?${params.toString()}`,
    );
  },
};
