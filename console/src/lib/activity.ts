const events: Record<string, [string, string]> = {
  adjust_balance: ['Wallet balance changed', 'Wallet'],
  approve_deposit: ['Deposit approved', 'Payments'], reject_deposit: ['Deposit rejected', 'Payments'],
  deposit_check_flagged: ['Deposit needs review', 'Payments'], deposit_amount_adjusted: ['Deposit credit corrected', 'Payments'],
  deposit_cancelled_by_customer: ['Customer cancelled a deposit', 'Payments'],
  payment_invoice_created: ['Payment request created', 'Payments'], payment_invoice_cancelled: ['Payment request cancelled', 'Payments'],
  payment_completed: ['Payment received and wallet credited', 'Payments'], payment_failed: ['Payment verification failed', 'Payments'],
  refund_order: ['Order refunded', 'Orders'], order_delivered_manually: ['Order delivered by admin', 'Orders'],
  supplier_order_retried: ['Supplier order fulfilled after retry', 'Orders'],
  referral_recovery_needed: ['Referral reward needs recovery', 'Wallet'], referral_reward_paid: ['Referral reward credited', 'Wallet'],
  user_banned: ['Customer blocked', 'Customers'], user_unbanned: ['Customer unblocked', 'Customers'], user_rank_updated: ['Customer account tier changed', 'Customers'],
  product_created: ['Product added', 'Catalog'], product_updated: ['Product updated', 'Catalog'], product_archived: ['Product archived', 'Catalog'], product_deleted: ['Product deleted', 'Catalog'],
  products_bulk_updated: ['Product availability changed', 'Catalog'], products_bulk_deleted: ['Products deleted', 'Catalog'],
  category_created: ['Category added', 'Catalog'], category_updated: ['Category updated', 'Catalog'], category_deleted: ['Category deleted', 'Catalog'],
  bulk_stock_added: ['Stock added', 'Stock'], stock_item_edited: ['Stock item updated', 'Stock'], stock_item_removed: ['Stock item removed', 'Stock'], stock_item_retired: ['Stock item taken off sale', 'Stock'],
  deposit_method_created: ['Payment method added', 'Settings'], deposit_method_updated: ['Payment method updated', 'Settings'], deposit_method_deleted: ['Payment method deleted', 'Settings'], deposit_method_archived: ['Payment method archived', 'Settings'],
  gate_channel_added: ['Required channel added', 'Channels'], gate_channel_updated: ['Required channel updated', 'Channels'], gate_channel_removed: ['Required channel removed', 'Channels'],
  update_channel_added: ['Store link added', 'Channels'], update_channel_updated: ['Store link updated', 'Channels'], update_channel_removed: ['Store link removed', 'Channels'],
  settings_updated: ['Store settings changed', 'Settings'], emoji_created: ['Custom emoji added', 'Catalog'], emoji_deleted: ['Custom emoji removed', 'Catalog'],
  broadcast_queued: ['Broadcast queued for delivery', 'Messages'], broadcast_deleted: ['Broadcast history deleted', 'Messages'],
  job_retry: ['Failed task queued for retry', 'System'], login_failed: ['Sign-in rejected', 'Security'], login_rate_limited: ['Sign-in attempts temporarily blocked', 'Security'],
};

const fields: Record<string, string> = {
  price: 'Retail price', reseller_price: 'Reseller price', is_active: 'Availability', is_pinned: 'Pinned status',
  title: 'Product name', category_id: 'Category', description: 'Description', icon: 'Icon', custom_emoji_id: 'Custom emoji',
  sort_order: 'Display order', duration_label: 'Validity', warranty_label: 'Warranty', delivery_type: 'Delivery method',
  requires_customer_input: 'Required customer information', customer_input_prompt: 'Customer information prompt',
  max_deposit_limit: 'Maximum deposit', usd_rate: 'BDT exchange rate', store_name: 'Store name',
  referral_reward: 'Referral reward', admin_tg_ids: 'Bot administrators', min_deposit: 'Minimum deposit',
  account_info: 'Payment account', account_type: 'Account type', auto_verify: 'Verification method',
  api_key: 'API key', api_secret: 'API secret', instructions: 'Payment instructions',
};

export function readableField(value: string): string {
  return fields[value] || value.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase());
}

export function activityLabel(action: string) {
  const [title, category] = events[action] || [readableField(action), 'Other'];
  return { title, category };
}

export function activityActor(actor: string): string {
  if (actor.startsWith('admin-session:')) return 'Admin console';
  if (actor === 'system') return 'System';
  if (actor.startsWith('telegram:')) return `Telegram user ${actor.slice(9)}`;
  return actor || 'Not recorded';
}

/** Older entries are immutable text. Only interpret known formats; preserve everything else. */
export function describeActivity(action: string, details: string) {
  let { title, category } = activityLabel(action);
  let summary = details;
  const facts: Array<[string, string]> = [];
  const balance = action === 'adjust_balance' && details.match(/^Adjusted balance of (\d+) by ([+-][\d.]+) \(new balance: ([\d.]+)\)\. Reason: ([\s\S]*)$/);
  if (balance) {
    title = balance[2].startsWith('-') ? 'Wallet balance deducted' : 'Wallet balance added';
    summary = `Customer ${balance[1]}`;
    facts.push(['Change', balance[2]], ['Balance after change', balance[3]], ['Reason', balance[4] || 'Not recorded']);
  }
  if (action === 'settings_updated' && details.startsWith('Changed: ')) {
    summary = `Updated: ${details.slice(9).split(', ').map(readableField).join(', ')}.`;
  }
  const update = ['product_updated', 'deposit_method_updated'].includes(action) && details.match(/^(Product|Method) #(\d+): ([a-z_]+(?:, [a-z_]+)*)(.*)$/s);
  if (update) {
    summary = `${update[1] === 'Method' ? 'Payment method' : 'Product'} #${update[2]}`;
    facts.push(['Fields changed', update[3].split(', ').map(readableField).join(', ')]);
    for (const change of update[4].split(';').filter(Boolean)) {
      const price = change.trim().match(/^(price|reseller_price) (.+) -> (.+)$/);
      if (price) facts.push([readableField(price[1]), `From ${price[2] === 'None' ? 'not set' : price[2]} to ${price[3] === 'None' ? 'not set' : price[3]}`]);
      else facts.push(['Change', change.trim()]);
    }
  }
  const bulk = action === 'products_bulk_updated' && details.match(/^(\d+) products set is_active=([01])$/);
  if (bulk) summary = `${bulk[1]} products ${bulk[2] === '1' ? 'made available for purchase' : 'hidden from the store'}.`;
  if (action === 'job_retry') summary = details.replace(/^notification job/, 'Notification task').replace(/^telegram job/, 'Telegram update') + ' queued. Completion is not confirmed yet.';
  if (action === 'login_failed') summary = details.replace('Invalid admin password from ', 'An incorrect admin password was submitted from ');
  return { title, category, summary, facts };
}
