'use client';
import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api, forgetAnswers } from '@/lib/api';
import { activityActor, activityLabel, describeActivity } from '@/lib/activity';
import { CustomSelect } from './CustomSelect';
import { errorText, Pager, useConfirm, useDebounced, type Say } from './ui';

export function Activity({ say }: { say: Say }) {
  const [search, setSearch] = useState('');
  const query = useDebounced(search);
  const [action, setAction] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.auditLogs>> | null>(null);
  const [jobs, setJobs] = useState<Awaited<ReturnType<typeof api.failedJobs>>>([]);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirm, dialog] = useConfirm();
  useEffect(() => {
    let active = true;
    setError('');
    setLoading(true);
    Promise.all([api.auditLogs({ search: query, action, offset }), api.failedJobs()]).then(([log, failed]) => {
      if (active) { setData(log); setJobs(failed); }
    }).catch(cause => { if (active) setError(errorText(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, action, offset, revision]);

  async function retry(job: typeof jobs[number]) {
    if (!await confirm('Retry failed task?', 'A Telegram update may have partly completed. Review its error and related order before replaying it. Notifications may be sent again.', 'Retry')) return;
    setBusy(true);
    try { await api.retryJob(job.kind, job.id); say('Queued for retry.'); setRevision(n => n + 1); }
    catch (cause) { say(errorText(cause), 'bad'); }
    finally { setBusy(false); }
  }

  return <>{dialog}
    <section className="panel activity-feed" aria-busy={loading}>
      <header>
        <h2>Activity history</h2>
        <button type="button" className="mini ghost" disabled={loading} onClick={() => { forgetAnswers(); setRevision(n => n + 1); }}><RefreshCw size={14} aria-hidden="true" /> {loading ? 'Refreshing…' : 'Refresh'}</button>
      </header>
      <div className="activity-filters">
        <input type="search" maxLength={100} aria-label="Search activity" placeholder="Search customer, order, product or details" value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} />
        <CustomSelect ariaLabel="Activity type" value={action} onChange={value => { setAction(value); setOffset(0); }} options={[{ value: '', label: 'All activity types' }, ...(data?.actions ?? []).map(value => ({ value, label: activityLabel(value).title }))]} minWidth={0} />
      </div>
      {error ? <div className="panel-body" role="alert">{error}</div> : null}
      <div className="activity-list">
        {loading ? <p className="panel-body" role="status">Loading activity…</p> : data?.entries.map(entry => {
          const event = describeActivity(entry.action, entry.details);
          const date = new Date(entry.created_at);
          const timestamp = Number.isNaN(date.getTime()) ? entry.created_at : date.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' });
          return <article className="activity-event" key={entry.id}>
            <div className="activity-event-heading"><span className="activity-category">{event.category}</span><time dateTime={entry.created_at}>{timestamp}</time></div>
            <h3>{event.title}</h3>
            <p className="activity-summary">{event.summary || 'No additional details were recorded.'}</p>
            {event.facts.length ? <dl className="activity-facts">{event.facts.map(([label, value], index) => <div key={`${label}-${index}`}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : null}
            <div className="activity-source">Recorded by {activityActor(entry.actor)}</div>
            <details className="activity-technical"><summary>Technical details</summary><dl><dt>Event</dt><dd>{entry.action}</dd><dt>Source</dt><dd>{entry.actor || 'Not recorded'}</dd><dt>Log ID</dt><dd>{entry.id}</dd><dt>Original record</dt><dd>{entry.details}</dd></dl></details>
          </article>;
        })}
        {!loading && !error && data && !data.entries.length ? <p className="panel-body">{query || action ? 'No activity matches these filters.' : 'No activity recorded yet.'}</p> : null}
      </div>
      <Pager total={data?.total ?? 0} offset={offset} size={50} onChange={setOffset} />
    </section>
    <section className="panel activity-tasks"><header><h2>Tasks needing attention</h2>{jobs.length ? <span className="pill warn">{jobs.length} failed</span> : null}</header>
      <div className="panel-body">{loading ? <p>Loading tasks…</p> : error ? <p>Could not refresh task status.</p> : jobs.length ? jobs.map(job => <div key={`${job.kind}-${job.id}`} className="activity-job">
        <div className="activity-job-copy"><strong>{job.kind === 'notification' ? 'Notification could not be delivered' : 'Telegram update could not be processed'}</strong><p>{job.attempts} {job.attempts === 1 ? 'attempt' : 'attempts'} made. Review the error before retrying.</p><details className="activity-technical"><summary>Error details</summary><p>{job.error || 'No error message recorded.'}</p><small>Task #{job.id}</small></details></div>
        <button type="button" className="mini" disabled={busy} onClick={() => void retry(job)}>Retry</button>
      </div>) : <p>No failed tasks.</p>}</div>
    </section>
  </>;
}
