'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type UpdateChannel } from '@/lib/api';
import { FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

type Draft = { id: number | null; title: string; url: string; sort_order: string; is_active: boolean };

export function UpdateChannels({ say }: { say: Say }) {
  const [channels, setChannels] = useState<UpdateChannel[] | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(() => api.updateChannels().then(setChannels).catch((cause) => say(errorText(cause), 'bad')), [say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(channel: UpdateChannel) {
    if (!(await confirm(`Remove ${channel.title}?`, 'Its button disappears from the Channel menu.', 'Remove channel'))) return;
    try {
      await api.deleteUpdateChannel(channel.id);
      say('Removed.');
      await load();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  return (
    <>
      {confirmDialog}
      <div className="panel-subhead">
        <div>
          <h3>Buttons shown to customers</h3>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn small"
            onClick={() => setDraft({ id: null, title: '', url: '', sort_order: String((channels?.length ?? 0) + 1), is_active: true })}
          >
            Add channel
          </button>
        </div>
      </div>
      {channels && channels.length === 0 ? <p className="note" style={{ padding: '12px 18px', margin: 0 }}>No channel buttons added yet.</p> : null}
      <div className="rows">
        {(channels ?? []).map((channel) => (
          <div key={channel.id} className={`row${channel.is_active ? '' : ' off'}`}>
            <div className="text">
              <strong>
                {channel.title}
                {channel.is_active ? '' : ' · off'}
              </strong>
              <small>
                #{channel.sort_order} ·{' '}
                <a href={channel.url} target="_blank" rel="noreferrer">
                  {channel.url.replace('https://', '')}
                </a>
              </small>
            </div>
            <div className="row-actions">
              <button
                type="button"
                className="mini"
                onClick={() =>
                  setDraft({
                    id: channel.id,
                    title: channel.title,
                    url: channel.url,
                    sort_order: String(channel.sort_order),
                    is_active: Boolean(channel.is_active),
                  })
                }
              >
                Edit
              </button>
              <button type="button" className="mini danger" onClick={() => remove(channel)}>
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      {draft ? (
        <ChannelForm
          draft={draft}
          say={say}
          onClose={() => setDraft(null)}
          onSaved={async () => {
            setDraft(null);
            await load();
          }}
        />
      ) : null}
    </>
  );
}

function ChannelForm({ draft, say, onClose, onSaved }: { draft: Draft; say: Say; onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState(draft);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<Draft>) => setForm((current) => ({ ...current, ...patch }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const payload = { title: form.title.trim(), url: form.url.trim(), sort_order: Number(form.sort_order) || 0, is_active: form.is_active ? 1 : 0 };
    try {
      if (form.id) await api.editUpdateChannel(form.id, payload);
      else await api.addUpdateChannel(payload);
      say(form.id ? 'Saved.' : 'Channel added.');
      await onSaved();
    } catch (cause) {
      say(errorText(cause), 'bad');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={form.id ? 'Edit channel' : 'Add channel'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={busy}>
            {form.id ? 'Save' : 'Add channel'}
          </button>
        </>
      }
    >
      <label className="field">
        <span>Name on the button</span>
        <input type="text" required maxLength={64} placeholder="Updates Channel" value={form.title} onChange={(event) => set({ title: event.target.value })} />
      </label>
      <label className="field">
        <span>Link</span>
        <input type="text" required placeholder="https://t.me/YourChannel or @YourChannel" value={form.url} onChange={(event) => set({ url: event.target.value })} />
      </label>
      <label className="field">
        <span>Order (smaller shows first)</span>
        <input
          type="number"
          min="0"
          value={form.sort_order}
          onChange={(event) => set({ sort_order: String(Math.max(0, parseInt(event.target.value, 10) || 0)) })}
        />
      </label>
      <FlagRow label="Show in the bot" on={form.is_active} onChange={(on) => set({ is_active: on })} />
    </Modal>
  );
}
