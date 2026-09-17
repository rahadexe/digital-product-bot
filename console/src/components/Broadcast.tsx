'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { errorText, useConfirm, type Say } from './ui';

type Progress = { id: number; success: number; failed: number; pending: number; total: number };

export function Broadcast({ say }: { say: Say }) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  useEffect(() => {
    if (!progress?.pending) return;
    const every = window.setInterval(() => {
      api.broadcastProgress(progress.id).then(setProgress).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(every);
  }, [progress?.id, progress?.pending]);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim() || !(await confirm('Send broadcast?', 'This message will be sent to every customer.', 'Send to everyone'))) return;
    setSending(true);
    try {
      const result = await api.broadcast(text);
      setProgress(result);
      setText('');
      say(`Sending to ${result.total} customers.`);
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      {confirmDialog}
      <form className="panel" onSubmit={send}>
      <header>
        <div>
          <h2>Message every customer</h2>
          <p>Telegram HTML works: &lt;b&gt;, &lt;i&gt;, &lt;code&gt;, &lt;a href=&quot;…&quot;&gt;.</p>
        </div>
      </header>
      <div className="panel-body stack">
        <textarea rows={8} required placeholder="🔥 20% off all AI subscriptions this weekend." value={text} onChange={(event) => setText(event.target.value)} />
        <div className="filters">
          <button type="submit" className="btn" disabled={sending || Boolean(progress?.pending) || !text.trim()}>
            {sending ? 'Sending…' : 'Send'}
          </button>
          {progress ? (
            <span className="hint">
              {progress.pending ? `Sending… ${progress.success + progress.failed} of ${progress.total}` : `Delivered to ${progress.success} of ${progress.total}`}
              {progress.failed ? ` · ${progress.failed} blocked the bot` : ''}
            </span>
          ) : null}
        </div>
      </div>
      </form>
    </>
  );
}
