 'use client';
import { useEffect, useState } from 'react';
import { api, forgetAnswers } from '@/lib/api';
import { errorText, Pager, useConfirm, useDebounced, type Say } from './ui';

export function Activity({say}: {say: Say}) {
  const [search,setSearch] = useState('');
  const query = useDebounced(search);
  const [offset,setOffset] = useState(0);
  const [data,setData] = useState<Awaited<ReturnType<typeof api.auditLogs>> | null>(null);
  const [jobs,setJobs] = useState<Awaited<ReturnType<typeof api.failedJobs>>>([]);
  const [error,setError] = useState('');
  const [revision,setRevision] = useState(0);
  const [busy,setBusy] = useState(false);
  const [confirm,dialog] = useConfirm();
  useEffect(() => {
    let active = true;
    setError('');
    Promise.all([api.auditLogs({search:query,offset}),api.failedJobs()]).then(([log,failed]) => {
      if(active) {setData(log);setJobs(failed);}
    }).catch((cause) => {if(active) setError(errorText(cause));});
    return () => {active=false;};
  },[query,offset,revision]);
  async function retry(job: typeof jobs[number]) {
    if (!await confirm('Retry failed job?', 'A Telegram update may have partly completed. Review its error and related order before replaying it. Notifications may be sent again.', 'Retry')) return;
    setBusy(true);
    try {await api.retryJob(job.kind,job.id);say('Queued for retry.');setRevision(n=>n+1);}
    catch(cause) {say(errorText(cause),'bad');}
    finally {setBusy(false);}
  }
  return <>{dialog}
    <section className="panel"><header><h2>Failed jobs</h2><button className="mini" onClick={()=>{forgetAnswers();setRevision(n=>n+1);}}>Refresh</button></header>
      {error ? <div className="panel-body" role="alert">{error}</div> : <div className="panel-body">{jobs.length ? jobs.map(job=><div key={`${job.kind}-${job.id}`} className="activity-job"><span><strong>{job.kind} #{job.id}</strong><small>{job.error}, {job.attempts} attempts</small></span><button className="mini" disabled={busy} onClick={()=>void retry(job)}>Retry</button></div>) : <p>{data ? 'No failed jobs.' : 'Loading…'}</p>}</div>}
    </section>
    <section className="panel"><header><h2>Admin activity</h2><input type="search" aria-label="Search activity" placeholder="Search activity" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}} /></header>
      <div className="panel-body">{data?.entries.map(entry=><article className="activity-entry" key={entry.id}><strong>{entry.action.replaceAll('_',' ')}</strong><p>{entry.details}</p><small>{entry.actor}, {new Date(entry.created_at).toLocaleString()}</small></article>)}{data && !data.entries.length ? <p>No matching activity.</p> : null}</div>
      <Pager total={data?.total ?? 0} offset={offset} size={50} onChange={setOffset}/>
    </section>
  </>;
}
