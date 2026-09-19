'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, Check, CheckCircle2, Clock, Eye, Info, Link2, MessageSquare, RefreshCw, Send, Users, X } from 'lucide-react';
import { api } from '@/lib/api';
import { errorText, useConfirm, when, type Say } from './ui';

type Progress = { id: number; success: number; failed: number; pending: number; total: number };
type RecentBroadcast = {
  id: number;
  created_at: string;
  text: string;
  total: number;
  success: number;
  failed: number;
  pending: number;
};

export function Broadcast({ say }: { say: Say }) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [recipientCount, setRecipientCount] = useState<number | null>(null);
  const [recent, setRecent] = useState<RecentBroadcast[]>([]);
  const [loadingInfo, setLoadingInfo] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [confirm, confirmDialog] = useConfirm();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadInfo = useCallback(async () => {
    setLoadingInfo(true);
    try {
      const data = await api.broadcastInfo();
      setRecipientCount(data.recipient_count);
      setRecent(data.recent);
    } catch {
      // ignore
    } finally {
      setLoadingInfo(false);
    }
  }, []);

  useEffect(() => {
    void loadInfo();
  }, [loadInfo]);

  useEffect(() => {
    if (!progress?.pending) return;
    const every = window.setInterval(() => {
      api.broadcastProgress(progress.id).then((p) => {
        setProgress(p);
        if (p.pending === 0) {
          void loadInfo();
        }
      }).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(every);
  }, [progress?.id, progress?.pending, loadInfo]);

  function insertTag(openTag: string, closeTag: string) {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = text.slice(start, end);
    const replacement = `${openTag}${selected || 'text'}${closeTag}`;
    const newText = text.slice(0, start) + replacement + text.slice(end);
    setText(newText);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + openTag.length, start + openTag.length + (selected ? selected.length : 4));
    }, 10);
  }

  function insertLink() {
    const url = window.prompt('Enter URL (https://...):', 'https://');
    if (!url) return;
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = text.slice(start, end) || 'link text';
    const replacement = `<a href="${url}">${selected}</a>`;
    const newText = text.slice(0, start) + replacement + text.slice(end);
    setText(newText);
    setTimeout(() => {
      el.focus();
    }, 10);
  }

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;

    const countDesc = recipientCount !== null ? `to all ${recipientCount} active customers` : 'to every customer';
    const confirmed = await confirm(
      'Send broadcast message?',
      `This announcement will be delivered ${countDesc}. Are you sure you want to proceed?`,
      'Send Broadcast Now',
    );
    if (!confirmed) return;

    setSending(true);
    try {
      const result = await api.broadcast(text);
      setProgress(result);
      setText('');
      say(`Broadcast queued for ${result.total} customers.`);
      void loadInfo();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setSending(false);
    }
  }

  // Basic safe preview transformer for Telegram HTML
  function renderSafeTelegramHtml(raw: string) {
    if (!raw.trim()) {
      return '<span style="color: #8e8e93; font-style: italic;">Preview will appear here as you type...</span>';
    }
    // Replace newlines with <br>
    let formatted = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Re-enable supported telegram tags
    formatted = formatted
      .replace(/&lt;b&gt;(.*?)&lt;\/b&gt;/gi, '<b>$1</b>')
      .replace(/&lt;strong&gt;(.*?)&lt;\/strong&gt;/gi, '<strong>$1</strong>')
      .replace(/&lt;i&gt;(.*?)&lt;\/i&gt;/gi, '<i>$1</i>')
      .replace(/&lt;em&gt;(.*?)&lt;\/em&gt;/gi, '<em>$1</em>')
      .replace(/&lt;code&gt;(.*?)&lt;\/code&gt;/gi, '<code style="background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 4px; font-family: monospace;">$1</code>')
      .replace(/&lt;pre&gt;(.*?)&lt;\/pre&gt;/gi, '<pre style="background: rgba(0,0,0,0.06); padding: 6px; border-radius: 4px; font-family: monospace; overflow-x: auto;">$1</pre>')
      .replace(/&lt;a href=&quot;(.*?)&quot;&gt;(.*?)&lt;\/a&gt;/gi, '<a href="$1" target="_blank" rel="noopener noreferrer" style="color: #2481cc; text-decoration: underline;">$2</a>')
      .replace(/\n/g, '<br/>');

    return formatted;
  }

  const completionPercent = progress && progress.total > 0
    ? Math.min(100, Math.round(((progress.success + progress.failed) / progress.total) * 100))
    : 0;

  return (
    <>
      {confirmDialog}

      {/* Header Metric & Info */}
      <div className="stat-cards-grid" style={{ marginBottom: '16px' }}>
        <div className="stat-card">
          <span className="stat-card-title">
            <Users size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />
            Active Recipients
          </span>
          <span className="stat-card-value">
            {recipientCount !== null ? recipientCount : '...'}
          </span>
          <span className="stat-card-sub">
            All registered unbanned Telegram bot customers
          </span>
        </div>

        <div className="stat-card">
          <span className="stat-card-title">
            <Bot size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />
            Telegram Admin Commands
          </span>
          <span className="stat-card-value" style={{ fontSize: '18px', fontWeight: 600, color: 'var(--accent)' }}>
            /broadcast &nbsp;or&nbsp; /bc
          </span>
          <span className="stat-card-sub">
            Admins can broadcast directly inside Telegram bot
          </span>
        </div>
      </div>

      <form className="panel" onSubmit={send}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h2>Message Every Customer</h2>
            <p style={{ margin: 0 }}>Send announcements, promotions, or store updates directly to customer Telegram inboxes.</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              className="mini ghost"
              onClick={() => setShowPreview((p) => !p)}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Eye size={13} />
              {showPreview ? 'Hide Preview' : 'Show Preview'}
            </button>
            <button
              type="button"
              className="mini ghost"
              onClick={() => void loadInfo()}
              disabled={loadingInfo}
              title="Refresh recipients and history"
            >
              <RefreshCw size={13} className={loadingInfo ? 'spin' : ''} />
            </button>
          </div>
        </header>

        <div className="panel-body stack" style={{ gap: '16px' }}>
          {/* Active Sending Progress Bar */}
          {progress && (
            <div
              style={{
                padding: '12px 14px',
                borderRadius: '8px',
                background: progress.pending > 0 ? 'rgba(15, 118, 110, 0.08)' : 'rgba(5, 150, 105, 0.08)',
                border: `1px solid ${progress.pending > 0 ? 'var(--accent)' : '#059669'}`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
                  {progress.pending > 0 ? '🚀 Delivering Broadcast...' : '✅ Broadcast Delivered'}
                </span>
                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)' }}>
                  {progress.success + progress.failed} / {progress.total} ({completionPercent}%)
                </span>
              </div>
              <div style={{ width: '100%', height: '6px', background: 'var(--surface-2)', borderRadius: '999px', overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${completionPercent}%`,
                    background: 'var(--accent)',
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '12px', color: 'var(--muted)' }}>
                <span style={{ color: '#059669' }}>✓ {progress.success} Sent</span>
                {progress.failed > 0 && <span style={{ color: 'var(--danger)' }}>✕ {progress.failed} Failed / Blocked</span>}
                {progress.pending > 0 && <span>⏳ {progress.pending} Pending</span>}
              </div>
            </div>
          )}

          {/* Two-Column Editor & Preview */}
          <div style={{ display: 'grid', gridTemplateColumns: showPreview ? 'repeat(auto-fit, minmax(300px, 1fr))' : '1fr', gap: '16px', alignItems: 'start' }}>
            {/* Compose Column */}
            <div>
              {/* Quick formatting toolbar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600, marginRight: '4px' }}>FORMAT:</span>
                <button type="button" className="mini ghost" onClick={() => insertTag('<b>', '</b>')} style={{ fontWeight: 700 }}>
                  B
                </button>
                <button type="button" className="mini ghost" onClick={() => insertTag('<i>', '</i>')} style={{ fontStyle: 'italic' }}>
                  I
                </button>
                <button type="button" className="mini ghost" onClick={() => insertTag('<code>', '</code>')} style={{ fontFamily: 'monospace' }}>
                  &lt;/&gt;
                </button>
                <button type="button" className="mini ghost" onClick={insertLink} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                  <Link2 size={12} /> Link
                </button>
              </div>

              <textarea
                ref={textareaRef}
                rows={9}
                required
                placeholder="Type your announcement or update here... (HTML tags <b>, <i>, <code>, <a href='...'> supported)"
                value={text}
                onChange={(e) => setText(e.target.value)}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '12px' }}>
                <button
                  type="submit"
                  className="btn"
                  disabled={sending || Boolean(progress?.pending) || !text.trim()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <Send size={14} />
                  {sending ? 'Sending…' : 'Send Broadcast'}
                </button>

                <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
                  {text.length} characters
                </span>
              </div>
            </div>

            {/* Live Telegram Bubble Preview Column */}
            {showPreview && (
              <div
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: '10px',
                  background: 'var(--surface-2)',
                  padding: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Bot size={14} style={{ color: 'var(--accent)' }} />
                    Telegram Message Live Preview
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Customer View</span>
                </div>

                {/* Simulated Telegram Chat Bubble */}
                <div
                  style={{
                    background: '#ffffff',
                    border: '1px solid rgba(0, 0, 0, 0.08)',
                    borderRadius: '12px 12px 12px 4px',
                    padding: '12px 14px',
                    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
                    color: '#000000',
                    fontSize: '13.5px',
                    lineHeight: '1.5',
                    wordBreak: 'break-word',
                    minHeight: '80px',
                  }}
                  dangerouslySetInnerHTML={{ __html: renderSafeTelegramHtml(text) }}
                />
              </div>
            )}
          </div>
        </div>
      </form>

      {/* Recent Broadcasts History */}
      <section className="panel" style={{ marginTop: '20px' }}>
        <header>
          <div>
            <h2>Recent Broadcasts History</h2>
            <p>Past broadcast deliveries and reports</p>
          </div>
        </header>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Broadcast</th>
                <th>Status</th>
                <th>Delivered</th>
                <th>Sent Date</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 ? (
                <tr>
                  <td colSpan={4} className="empty" style={{ textAlign: 'center', padding: '24px', color: 'var(--muted)' }}>
                    No previous broadcasts yet. Send your first broadcast above or via Telegram with <code>/broadcast</code>.
                  </td>
                </tr>
              ) : (
                recent.map((b) => {
                  const isDone = b.pending === 0;
                  return (
                    <tr key={b.id}>
                      <td style={{ maxWidth: '350px' }}>
                        <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text)' }}>
                          Broadcast #{b.id}
                        </div>
                        <div
                          style={{
                            fontSize: '12px',
                            color: 'var(--muted)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: '350px',
                            marginTop: '2px',
                          }}
                        >
                          {b.text || '(No text stored)'}
                        </div>
                      </td>
                      <td>
                        {isDone ? (
                          <span className="pill good">Completed</span>
                        ) : (
                          <span className="pill warn">Sending...</span>
                        )}
                      </td>
                      <td>
                        <span style={{ fontWeight: 600, color: 'var(--text)' }}>
                          {b.success} / {b.total}
                        </span>
                        {b.failed > 0 ? (
                          <small style={{ display: 'block', color: 'var(--danger)', fontSize: '11px' }}>
                            {b.failed} failed/blocked
                          </small>
                        ) : null}
                      </td>
                      <td>
                        <small>{when(b.created_at)}</small>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
