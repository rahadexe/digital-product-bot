'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type GateChannel } from '@/lib/api';
import { FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

type Draft = { id: number | null; title: string; channel_username: string; invite_link: string; chat_id: string; is_active: boolean };

export function GateChannels({ say, isGateEnabled }: { say: Say; isGateEnabled?: boolean }) {
  const [channels, setChannels] = useState<GateChannel[] | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  const load = useCallback(() => api.gateChannels().then(setChannels).catch((cause) => say(errorText(cause), 'bad')), [say]);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(channel: GateChannel) {
    if (!(await confirm(`Remove ${channel.title}?`, 'Customers will no longer be required to join this channel.', 'Remove channel'))) return;
    try {
      await api.deleteGateChannel(channel.id);
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
          <h3>Required Channels</h3>
        </div>
        <div className="actions">
          <button type="button" className="btn small" onClick={() => setDraft({ id: null, title: '', channel_username: '', invite_link: '', chat_id: '', is_active: true })}>
            Add channel
          </button>
        </div>
      </div>
      {channels && channels.length === 0 ? (
        <p className="note" style={{ padding: '12px 18px', margin: 0, color: isGateEnabled ? 'var(--warning, #b45309)' : undefined }}>
          {isGateEnabled
            ? 'Gate is active, but no channels are added. Users will bypass the gate until a channel is added.'
            : 'No channels required.'}
        </p>
      ) : null}
      <div className="rows">
        {(channels ?? []).map((channel) => (
          <div key={channel.id} className={`row${channel.is_active ? '' : ' off'}`}>
            <div className="text">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <strong>{channel.title}</strong>
                {channel.is_active ? (
                  <span className="channel-status-badge active">Active</span>
                ) : (
                  <span className="channel-status-badge inactive">Inactive</span>
                )}
              </div>
              <small>
                {channel.channel_username} ·{' '}
                <a href={channel.invite_link} target="_blank" rel="noreferrer">
                  {channel.invite_link.replace('https://', '')}
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
                    channel_username: channel.channel_username,
                    invite_link: channel.invite_link,
                    chat_id: channel.chat_id || '',
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
    const payload = { title: form.title.trim(), channel_username: form.channel_username.trim(), invite_link: form.invite_link.trim(), chat_id: form.chat_id, is_active: form.is_active ? 1 : 0 };
    try {
      if (form.id) await api.updateGateChannel(form.id, payload);
      else await api.addGateChannel(payload);
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
        <input type="text" required placeholder="Official channel" value={form.title} onChange={(event) => set({ title: event.target.value })} />
      </label>
      <label className="field">
        <span>Username or chat ID</span>
        <input type="text" required placeholder="@YourChannel or -100…" value={form.channel_username} onChange={(event) => set({ channel_username: event.target.value })} />
      </label>
      <label className="field">
        <span>Invite link</span>
        <input type="text" required placeholder="https://t.me/YourChannel" value={form.invite_link} onChange={(event) => set({ invite_link: event.target.value })} />
      </label>
      <FlagRow label="Required" on={form.is_active} onChange={(on) => set({ is_active: on })} />
    </Modal>
  );
}
