'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bold, Bot, Check, Code, Copy, Eye, EyeOff, Italic, Link2, RefreshCw, RotateCcw, Send, Trash2, Users } from 'lucide-react';
import { api } from '@/lib/api';
import { errorText, Modal, useConfirm, when, type Say } from './ui';

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
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const [selectedBroadcast, setSelectedBroadcast] = useState<RecentBroadcast | null>(null);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState('https://');
  const [linkText, setLinkText] = useState('');
  const selectionRange = useRef<{ start: number; end: number }>({ start: 0, end: 0 });
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

  function openLinkModal() {
    const el = textareaRef.current;
    if (el) {
      const start = el.selectionStart;
      const end = el.selectionEnd;
      selectionRange.current = { start, end };
      const selected = text.slice(start, end);
      setLinkText(selected || '');
    } else {
      selectionRange.current = { start: text.length, end: text.length };
      setLinkText('');
    }
    setLinkUrl('');
    setLinkModalOpen(true);
  }

  function applyLink(e?: React.FormEvent) {
    if (e) e.preventDefault();
    let url = linkUrl.trim();
    if (!url) return;
    if (!url.startsWith('http://') && !url.startsWith('https://') && !url.startsWith('tg://')) {
      url = `https://${url}`;
    }
    const label = linkText.trim() || url;
    const { start, end } = selectionRange.current;
    const replacement = `<a href="${url}">${label}</a>`;
    const newText = text.slice(0, start) + replacement + text.slice(end);
    setText(newText);
    setLinkModalOpen(false);
    setLinkText('');
    setLinkUrl('');
    setTimeout(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        const pos = start + replacement.length;
        el.setSelectionRange(pos, pos);
      }
    }, 50);
  }

  function copyCommand(cmd: string) {
    void navigator.clipboard.writeText(cmd);
    setCopiedCmd(cmd);
    setTimeout(() => setCopiedCmd(null), 1500);
  }

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;

    const countDesc = recipientCount !== null ? `to ${recipientCount} customers` : 'to all customers';
    const confirmed = await confirm(
      'Send broadcast?',
      `Deliver this message ${countDesc}?`,
      'Send Now',
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

  async function deleteItem(id: number) {
    const confirmed = await confirm(
      `Delete Broadcast #${id}?`,
      'This will remove this broadcast and all associated delivery records from history.',
      'Delete',
      true,
    );
    if (!confirmed) return;

    try {
      await api.deleteBroadcast(id);
      say(`Broadcast #${id} deleted.`);
      if (selectedBroadcast?.id === id) {
        setSelectedBroadcast(null);
      }
      void loadInfo();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  // Basic safe preview transformer for Telegram HTML
  function renderSafeTelegramHtml(raw: string) {
    if (!raw.trim()) {
      return '<span style="color: var(--muted); font-style: italic;">Message preview...</span>';
    }
    let formatted = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    formatted = formatted
      .replace(/&lt;b&gt;(.*?)&lt;\/b&gt;/gi, '<b>$1</b>')
      .replace(/&lt;strong&gt;(.*?)&lt;\/strong&gt;/gi, '<strong>$1</strong>')
      .replace(/&lt;i&gt;(.*?)&lt;\/i&gt;/gi, '<i>$1</i>')
      .replace(/&lt;em&gt;(.*?)&lt;\/em&gt;/gi, '<em>$1</em>')
      .replace(/&lt;code&gt;(.*?)&lt;\/code&gt;/gi, '<code style="background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 4px; font-family: var(--mono); font-size: 12.5px;">$1</code>')
      .replace(/&lt;pre&gt;(.*?)&lt;\/pre&gt;/gi, '<pre style="background: rgba(0,0,0,0.06); padding: 6px 8px; border-radius: 4px; font-family: var(--mono); font-size: 12px; overflow-x: auto;">$1</pre>')
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

      {/* Header Metric & Quick Info */}
      <div className="broadcast-stats-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Active Recipients</span>
            <Users className="stat-card-icon" />
          </div>
          <div className="stat-card-value">
            {recipientCount !== null ? recipientCount : '—'}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Bot Command</span>
            <Bot className="stat-card-icon" />
          </div>
          <div className="stat-card-value" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="copy-chip accent"
              onClick={() => copyCommand('/broadcast')}
              title="Click to copy /broadcast"
            >
              /broadcast
              {copiedCmd === '/broadcast' ? (
                <Check size={12} style={{ color: '#059669' }} />
              ) : (
                <Copy size={12} style={{ color: 'var(--muted)' }} />
              )}
            </button>
            <span style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 500 }}>or</span>
            <button
              type="button"
              className="copy-chip accent"
              onClick={() => copyCommand('/bc')}
              title="Click to copy /bc"
            >
              /bc
              {copiedCmd === '/bc' ? (
                <Check size={12} style={{ color: '#059669' }} />
              ) : (
                <Copy size={12} style={{ color: 'var(--muted)' }} />
              )}
            </button>
          </div>
        </div>
      </div>

      <form className="panel" onSubmit={send}>
        <header>
          <div>
            <h2>New Broadcast</h2>
          </div>
          <div className="actions">
            <button
              type="button"
              className="mini ghost"
              onClick={() => setShowPreview((p) => !p)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
            >
              {showPreview ? <EyeOff size={13} /> : <Eye size={13} />}
              <span>{showPreview ? 'Hide preview' : 'Preview'}</span>
            </button>
            <button
              type="button"
              className="mini ghost"
              onClick={() => void loadInfo()}
              disabled={loadingInfo}
              title="Refresh"
            >
              <RefreshCw size={13} className={loadingInfo ? 'spin' : ''} />
            </button>
          </div>
        </header>

        <div className="panel-body stack" style={{ gap: '16px' }}>
          {/* Active Sending Progress */}
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
                  {progress.pending > 0 ? 'Sending broadcast...' : 'Broadcast delivered'}
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
              <div style={{ display: 'flex', gap: '14px', marginTop: '8px', fontSize: '12px', color: 'var(--muted)' }}>
                <span style={{ color: '#059669', fontWeight: 500 }}>✓ {progress.success} sent</span>
                {progress.failed > 0 && <span style={{ color: 'var(--danger)', fontWeight: 500 }}>✕ {progress.failed} failed</span>}
                {progress.pending > 0 && <span>⏳ {progress.pending} pending</span>}
              </div>
            </div>
          )}

          {/* Responsive Editor & Live Preview Grid */}
          <div
            className={showPreview ? 'broadcast-composer-grid' : ''}
            style={{
              display: showPreview ? undefined : 'block',
              width: '100%',
              minWidth: 0,
            }}
          >
            {/* Unified Composer Box */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                border: '1px solid var(--border)',
                borderRadius: '10px',
                background: 'var(--surface)',
                boxShadow: '0 1px 2px rgba(0, 0, 0, 0.03)',
                overflow: 'hidden',
                width: '100%',
                minWidth: 0,
              }}
            >
              {/* Toolbar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '6px 10px',
                  background: 'var(--surface-2)',
                  borderBottom: '1px solid var(--line)',
                }}
              >
                <button
                  type="button"
                  className="mini ghost fmt-btn"
                  onClick={() => insertTag('<b>', '</b>')}
                  title="Bold"
                >
                  <Bold size={13} />
                </button>
                <button
                  type="button"
                  className="mini ghost fmt-btn"
                  onClick={() => insertTag('<i>', '</i>')}
                  title="Italic"
                >
                  <Italic size={13} />
                </button>
                <button
                  type="button"
                  className="mini ghost fmt-btn"
                  onClick={() => insertTag('<code>', '</code>')}
                  title="Code"
                >
                  <Code size={13} />
                </button>
                <button
                  type="button"
                  className="mini ghost fmt-btn wide"
                  onClick={openLinkModal}
                  title="Link"
                >
                  <Link2 size={12} />
                  <span>Link</span>
                </button>
              </div>

              {/* Textarea */}
              <textarea
                ref={textareaRef}
                rows={8}
                required
                placeholder="Write your message here..."
                value={text}
                onChange={(e) => setText(e.target.value)}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  flex: 1,
                  border: 'none',
                  borderRadius: 0,
                  background: 'transparent',
                  padding: '12px 14px',
                  fontSize: '14px',
                  lineHeight: '1.55',
                  resize: 'vertical',
                  minHeight: '150px',
                  outline: 'none',
                  boxShadow: 'none',
                }}
              />

              {/* Composer Footer */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 12px 10px',
                  borderTop: '1px solid var(--line)',
                  background: 'var(--surface)',
                }}
              >
                <span style={{ fontSize: '12px', color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>
                  {text.length} chars
                </span>

                <button
                  type="submit"
                  className="btn"
                  disabled={sending || Boolean(progress?.pending) || !text.trim()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '7px 16px', fontSize: '13px' }}
                >
                  <Send size={13} />
                  {sending ? 'Sending…' : 'Send Broadcast'}
                </button>
              </div>
            </div>

            {/* Telegram Preview */}
            {showPreview && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  border: '1px solid var(--border)',
                  borderRadius: '10px',
                  background: 'var(--surface-2)',
                  overflow: 'hidden',
                  width: '100%',
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderBottom: '1px solid var(--line)',
                    background: 'var(--surface)',
                  }}
                >
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                    <Bot size={13} style={{ color: 'var(--accent)' }} />
                    Preview
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Telegram</span>
                </div>

                <div
                  style={{
                    padding: '14px',
                    flex: 1,
                    minHeight: '180px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'flex-start',
                  }}
                >
                  <div
                    style={{
                      alignSelf: 'flex-start',
                      width: '100%',
                      maxWidth: '440px',
                      boxSizing: 'border-box',
                      background: '#ffffff',
                      border: '1px solid rgba(0, 0, 0, 0.08)',
                      borderRadius: '12px 12px 12px 3px',
                      padding: '12px 14px 8px',
                      boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
                      color: '#111827',
                      fontSize: '13.5px',
                      lineHeight: '1.5',
                      wordBreak: 'break-word',
                    }}
                  >
                    <div
                      dangerouslySetInnerHTML={{ __html: renderSafeTelegramHtml(text) }}
                      style={{ minHeight: '28px' }}
                    />
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'flex-end',
                        gap: '3px',
                        marginTop: '2px',
                        fontSize: '10.5px',
                        color: '#8e8e93',
                        userSelect: 'none',
                      }}
                    >
                      <span>12:00</span>
                      <span style={{ color: '#059669', fontSize: '10px', fontWeight: 700 }}>✓✓</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </form>

      {/* Recent Broadcasts */}
      <section className="panel" style={{ marginTop: '20px' }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <h2>Recent Broadcasts</h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
            Latest 30 kept · auto-pruned
          </span>
        </header>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Broadcast</th>
                <th>Status</th>
                <th>Delivered</th>
                <th>Date</th>
                <th style={{ textAlign: 'right', width: '90px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty" style={{ textAlign: 'center', padding: '24px', color: 'var(--muted)' }}>
                    No broadcasts sent yet.
                  </td>
                </tr>
              ) : (
                recent.map((b) => {
                  const isDone = b.pending === 0;
                  return (
                    <tr
                      key={b.id}
                      onClick={() => setSelectedBroadcast(b)}
                      style={{ cursor: 'pointer' }}
                      title="Click to view full broadcast details"
                    >
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
                          {b.text || '—'}
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
                            {b.failed} failed
                          </small>
                        ) : null}
                      </td>
                      <td>
                        <small>{when(b.created_at)}</small>
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="mini ghost"
                          onClick={() => setSelectedBroadcast(b)}
                          title="View full broadcast details"
                          style={{ padding: '4px 6px' }}
                        >
                          <Eye size={13} />
                        </button>
                        <button
                          type="button"
                          className="mini ghost"
                          onClick={() => void deleteItem(b.id)}
                          title="Delete broadcast"
                          style={{ padding: '4px 6px', color: 'var(--danger)' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Full Broadcast Message Modal */}
      {selectedBroadcast && (
        <Modal
          title={`Broadcast #${selectedBroadcast.id}`}
          onClose={() => setSelectedBroadcast(null)}
          wide
          footer={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '10px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn bad mini"
                onClick={() => void deleteItem(selectedBroadcast.id)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
              >
                <Trash2 size={12} />
                Delete
              </button>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn secondary mini"
                  onClick={() => {
                    if (selectedBroadcast.text) {
                      void navigator.clipboard.writeText(selectedBroadcast.text);
                      say('Message copied to clipboard.');
                    }
                  }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                >
                  <Copy size={12} />
                  Copy
                </button>
                <button
                  type="button"
                  className="btn mini"
                  onClick={() => {
                    if (selectedBroadcast.text) {
                      setText(selectedBroadcast.text);
                      setSelectedBroadcast(null);
                      say('Loaded into composer.');
                      textareaRef.current?.focus();
                    }
                  }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                >
                  <RotateCcw size={12} />
                  Load in Composer
                </button>
              </div>
            </div>
          }
        >
          <div className="stack" style={{ gap: '14px' }}>
            {/* Delivery Stats Header */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                gap: '10px',
                padding: '12px 14px',
                borderRadius: '8px',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
              }}
            >
              <div>
                <span style={{ fontSize: '10.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', fontWeight: 600 }}>Status</span>
                <span className={`pill ${selectedBroadcast.pending === 0 ? 'good' : 'warn'}`} style={{ marginTop: '4px' }}>
                  {selectedBroadcast.pending === 0 ? 'Completed' : 'Sending...'}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '10.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', fontWeight: 600 }}>Delivered</span>
                <span style={{ fontSize: '13.5px', fontWeight: 700, color: 'var(--text)', marginTop: '4px', display: 'block' }}>
                  {selectedBroadcast.success} / {selectedBroadcast.total}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '10.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', fontWeight: 600 }}>Failed</span>
                <span style={{ fontSize: '13.5px', fontWeight: 700, color: selectedBroadcast.failed > 0 ? 'var(--danger)' : 'var(--muted)', marginTop: '4px', display: 'block' }}>
                  {selectedBroadcast.failed}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '10.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', fontWeight: 600 }}>Date Sent</span>
                <span style={{ fontSize: '12.5px', color: 'var(--text-dim)', marginTop: '4px', display: 'block' }}>
                  {when(selectedBroadcast.created_at)}
                </span>
              </div>
            </div>

            {/* Formatted Message Bubble Preview */}
            <div>
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '8px' }}>
                Full Message Content
              </span>
              <div
                style={{
                  background: '#ffffff',
                  border: '1px solid rgba(0, 0, 0, 0.08)',
                  borderRadius: '12px 12px 12px 3px',
                  padding: '12px 14px',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
                  color: '#111827',
                  fontSize: '14px',
                  lineHeight: '1.6',
                  wordBreak: 'break-word',
                  maxHeight: '300px',
                  overflowY: 'auto',
                }}
                dangerouslySetInnerHTML={{ __html: renderSafeTelegramHtml(selectedBroadcast.text) }}
              />
            </div>
          </div>
        </Modal>
      )}

      {/* Add Link Modal */}
      {linkModalOpen && (
        <Modal
          title="Add Link"
          onClose={() => setLinkModalOpen(false)}
          onSubmit={applyLink}
          footer={
            <>
              <button
                type="button"
                className="btn ghost mini"
                onClick={() => setLinkModalOpen(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn mini"
                disabled={!linkUrl.trim()}
              >
                Insert Link
              </button>
            </>
          }
        >
          <div className="stack" style={{ gap: '14px' }}>
            <label className="field">
              <span>Text to display</span>
              <input
                type="text"
                placeholder="e.g. Join our channel"
                value={linkText}
                onChange={(e) => setLinkText(e.target.value)}
              />
            </label>

            <label className="field">
              <span>Link URL</span>
              <input
                type="url"
                autoFocus
                required
                placeholder="https://t.me/yourchannel"
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
              />
            </label>
          </div>
        </Modal>
      )}
    </>
  );
}
