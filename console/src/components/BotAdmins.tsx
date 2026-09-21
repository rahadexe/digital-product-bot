'use client';

// Who runs the shop. These Telegram accounts are not only the alert recipients:
// they are the accounts the bot accepts /broadcast from, the ones that pass the
// force-join gate, and the ones the emoji-id helper answers. That is why this
// lives with the store rather than under notifications.

import { useState } from 'react';
import { CheckCircle, Plus, Send, ShieldAlert, Trash2, UserCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { errorText, type Say } from './ui';

interface BotAdminsProps {
  say: Say;
  values: Record<string, string>;
  setValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setSaved: React.Dispatch<React.SetStateAction<Record<string, string> | null>>;
}

type TestResult = {
  success: boolean;
  delivered_count: number;
  total_admins: number;
  message?: string;
  results: { chat_id: number; delivered: boolean; error?: string | null }[];
};

export function BotAdmins({ say, values, setValues, setSaved }: BotAdminsProps) {
  const [newAdminId, setNewAdminId] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  // admin_tg_ids holds the list; admin_tg_id is the first of them, kept for the
  // bot's own fallback when the list has never been written.
  const rawAdminIds = values.admin_tg_ids || values.admin_tg_id || '';
  const adminIds = Array.from(
    new Set(
      rawAdminIds
        .split(/[\s,;]+/)
        .map((s) => s.trim())
        .filter((s) => /^\d{5,20}$/.test(s))
    )
  );

  async function updateAdminIds(nextIds: string[]) {
    const formatted = nextIds.join(', ');
    const primaryId = nextIds[0] || '0';
    setValues((prev) => ({ ...prev, admin_tg_ids: formatted, admin_tg_id: primaryId }));
    try {
      await api.updateSettings({ admin_tg_ids: formatted, admin_tg_id: primaryId });
      setSaved((prev) => ({ ...(prev ?? {}), admin_tg_ids: formatted, admin_tg_id: primaryId }));
      say('Administrators updated.');
    } catch (cause) {
      say(errorText(cause, 'Could not save the administrators.'), 'bad');
    }
  }

  function handleAddAdmin(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const cleaned = newAdminId.trim();
    if (!cleaned) return;

    const parts = cleaned.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    const validParts = parts.filter((s) => /^\d{5,20}$/.test(s));
    if (validParts.length === 0) {
      say('Please enter a valid numeric Telegram ID (usually 8-12 digits).', 'bad');
      return;
    }

    void updateAdminIds(Array.from(new Set([...adminIds, ...validParts])));
    setNewAdminId('');
    setIsAdding(false);
  }

  function handleRemoveAdmin(idToRemove: string) {
    if (adminIds.length <= 1) {
      const warning =
        'This is the only administrator. Removing it means no one receives alerts and no one can '
        + 'use the bot admin commands. Remove anyway?';
      if (!confirm(warning)) return;
    }
    void updateAdminIds(adminIds.filter((id) => id !== idToRemove));
  }

  async function handleSendTestAlert() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testAdminNotification();
      setTestResult(res);
      if (res.success) {
        say(`Test alert sent! Delivered to ${res.delivered_count} of ${res.total_admins} admin(s).`);
      } else {
        say(res.message || 'Could not deliver test notification.', 'bad');
      }
    } catch (cause) {
      say(errorText(cause, 'Failed to send test alert.'), 'bad');
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <div className="panel-subhead">
        <div>
          <h3>
            <UserCheck size={15} style={{ color: 'var(--positive)', flexShrink: 0 }} />
            <span>Administrators</span>
          </h3>
          <small>Telegram accounts that run the bot and receive its alerts.</small>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn small ghost"
            disabled={testing || adminIds.length === 0}
            onClick={handleSendTestAlert}
            title="Sends a test ping to every administrator to verify delivery"
          >
            <Send size={14} style={{ marginRight: 6 }} />
            {testing ? 'Sending…' : 'Send test alert'}
          </button>
        </div>
      </div>

      <div className="panel-body">
        {testResult && (
          <div className={`admin-test-result ${testResult.success ? 'success' : 'error'}`}>
            <div className="admin-test-result-header">
              {testResult.success ? <CheckCircle size={16} /> : <ShieldAlert size={16} />}
              <span>
                {testResult.success
                  ? `Delivered to ${testResult.delivered_count} of ${testResult.total_admins} admin Telegram accounts!`
                  : testResult.message || 'Delivery failed for all admins.'}
              </span>
            </div>
            {testResult.results.some((r) => !r.delivered) && (
              <ul style={{ marginTop: 8, paddingLeft: 20, color: 'var(--muted)', fontSize: '0.8rem' }}>
                {testResult.results
                  .filter((r) => !r.delivered)
                  .map((r) => (
                    <li key={r.chat_id}>
                      UID <code>{r.chat_id}</code>: {r.error || 'Failed to deliver message'}
                    </li>
                  ))}
              </ul>
            )}
          </div>
        )}

        <div className="admin-ids-list" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {adminIds.length === 0 ? (
            <div className="empty-state" style={{ padding: '14px 0', textAlign: 'center', color: 'var(--muted)' }}>
              No administrators yet. The bot will accept admin commands from no one.
            </div>
          ) : (
            <div className="admin-chips-wrap">
              {adminIds.map((id, index) => (
                <div key={id} className="admin-chip">
                  <UserCheck size={16} style={{ color: index === 0 ? 'var(--positive)' : 'var(--muted)', flexShrink: 0 }} />
                  <span className="admin-chip-id">{id}</span>
                  <span className={`admin-chip-badge ${index === 0 ? 'primary' : 'coadmin'}`}>
                    {index === 0 ? 'Primary' : 'Co-Admin'}
                  </span>
                  <button
                    type="button"
                    className="admin-chip-remove"
                    onClick={() => handleRemoveAdmin(id)}
                    title="Remove this administrator"
                    aria-label={`Remove administrator ${id}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {isAdding ? (
            <div className="admin-add-form">
              <input
                type="text"
                autoFocus
                placeholder="Telegram User ID (e.g. 100200300)"
                value={newAdminId}
                onChange={(e) => setNewAdminId(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddAdmin();
                  }
                }}
              />
              <div className="admin-add-form-actions">
                <button type="button" className="btn small" onClick={() => handleAddAdmin()}>
                  Add
                </button>
                <button
                  type="button"
                  className="btn small ghost"
                  onClick={() => {
                    setIsAdding(false);
                    setNewAdminId('');
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 4 }}>
              <button
                type="button"
                className="btn small ghost"
                onClick={() => setIsAdding(true)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                <Plus size={14} />
                Add administrator
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
