'use client';

import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, Clock, FolderTree, Package, Plus, Trash2, Edit3, Check, Sparkles } from 'lucide-react';
import { api, type Category, type Product } from '@/lib/api';
import { EmptyRow, Modal, errorText, useConfirm, type Say } from './ui';

const POPULAR_SUGGESTIONS = [
  '1 Day',
  '3 Days',
  '7 Days',
  '14 Days',
  '30 Days',
  '1 Month',
  '2 Months',
  '3 Months',
  '6 Months',
  '1 Year',
  'Lifetime',
];

interface EditDraft {
  mode: 'new' | 'edit';
  originalLabel?: string;
  label: string;
  updateProducts: boolean;
}

export function Validities({ say }: { say: Say }) {
  const [presets, setPresets] = useState<string[]>([]);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, confirmDialog] = useConfirm();

  const loadData = useCallback(async () => {
    try {
      const [sets, prods, cats] = await Promise.all([
        api.settings(),
        api.products(),
        api.categories(),
      ]);

      let loadedPresets: string[] = [];
      if (sets && sets.validity_presets) {
        loadedPresets = sets.validity_presets
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
      } else {
        loadedPresets = ['3 Days', '7 Days', '14 Days', '30 Days', '90 Days', '1 Year'];
      }
      setPresets(loadedPresets);
      setProducts(prods);
      setCategories(cats);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [say]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Save updated presets to backend settings
  async function savePresets(newPresets: string[]) {
    await api.updateSettings({ validity_presets: newPresets.join(', ') });
    setPresets(newPresets);
  }

  // Quick add a preset
  async function quickAdd(label: string) {
    if (presets.some((p) => p.toLowerCase() === label.toLowerCase())) {
      say(`"${label}" already exists.`, 'bad');
      return;
    }
    const updated = [...presets, label];
    try {
      await savePresets(updated);
      say(`Added "${label}" to validity presets.`);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  // Delete a preset
  async function handleDelete(label: string) {
    const usingProducts = (products ?? []).filter(
      (p) => p.duration_label && p.duration_label.trim().toLowerCase() === label.toLowerCase()
    );

    const warning =
      usingProducts.length > 0
        ? `⚠️ Note: ${usingProducts.length} product(s) are currently tagged with "${label}". Removing this validity from presets will not delete those products, but the duration won't be listed in presets.`
        : 'This will remove the validity duration from the presets list.';

    if (
      !(await confirm(
        `Delete validity "${label}"?`,
        warning,
        'Delete Validity'
      ))
    ) {
      return;
    }

    const updated = presets.filter((p) => p.toLowerCase() !== label.toLowerCase());
    try {
      await savePresets(updated);
      say(`Deleted validity "${label}".`);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  // Submit modal form (create or edit)
  async function handleModalSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const trimmed = draft.label.trim();
    if (!trimmed) {
      say('Validity duration label is required.', 'bad');
      return;
    }

    setBusy(true);
    try {
      if (draft.mode === 'new') {
        if (presets.some((p) => p.toLowerCase() === trimmed.toLowerCase())) {
          say(`"${trimmed}" already exists in presets.`, 'bad');
          setBusy(false);
          return;
        }
        const updated = [...presets, trimmed];
        await savePresets(updated);
        say(`Created validity "${trimmed}".`);
      } else if (draft.mode === 'edit' && draft.originalLabel) {
        const oldLabel = draft.originalLabel;
        const updated = presets.map((p) =>
          p.toLowerCase() === oldLabel.toLowerCase() ? trimmed : p
        );
        await savePresets(updated);

        // If user wants to update products using this label
        if (draft.updateProducts) {
          const matchingProds = (products ?? []).filter(
            (p) => p.duration_label && p.duration_label.trim().toLowerCase() === oldLabel.toLowerCase()
          );
          for (const prod of matchingProds) {
            await api.updateProduct(prod.id, { duration_label: trimmed });
          }
          if (matchingProds.length > 0) {
            say(`Updated validity and synced ${matchingProds.length} product(s).`);
          } else {
            say(`Updated validity "${trimmed}".`);
          }
        } else {
          say(`Updated validity "${trimmed}".`);
        }
      }

      setDraft(null);
      await loadData();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(false);
    }
  }

  // Detect any products with custom validity labels that aren't yet in presets
  const discoveredLabels = Array.from(
    new Set(
      (products ?? [])
        .map((p) => p.duration_label?.trim())
        .filter((lbl): lbl is string => Boolean(lbl) && !presets.some((p) => p.toLowerCase() === lbl.toLowerCase()))
    )
  );

  async function syncDiscovered() {
    if (discoveredLabels.length === 0) return;
    const updated = [...presets, ...discoveredLabels];
    try {
      await savePresets(updated);
      say(`Imported ${discoveredLabels.length} validity duration(s) from products.`);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  // Stats calculation
  const totalValidities = presets.length;
  const productsWithValidity = (products ?? []).filter(
    (p) => Boolean(p.duration_label && p.duration_label.trim())
  ).length;
  const categoriesWithFilter = (categories ?? []).filter(
    (c) => Boolean(c.has_validity_filter)
  ).length;

  // Filtered presets
  const filteredPresets = presets.filter((p) =>
    p.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      {confirmDialog}

      {/* Summary Stat Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Validities</span>
            <CalendarClock className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{totalValidities}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Products with Validity</span>
            <Package className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{productsWithValidity}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Categories with Validity Filter</span>
            <FolderTree className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{categoriesWithFilter}</div>
        </div>
      </div>

      {/* Notice if products have unlisted validities */}
      {discoveredLabels.length > 0 && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(15, 118, 110, 0.12), rgba(14, 165, 233, 0.12))',
            border: '1px solid rgba(15, 118, 110, 0.25)',
            borderRadius: '12px',
            padding: '12px 18px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Sparkles size={20} color="#0f766e" />
            <div>
              <strong>Found unlisted validities in products:</strong>{' '}
              <span style={{ color: 'var(--text-dim)' }}>
                {discoveredLabels.join(', ')}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn mini"
            style={{ background: '#0f766e', color: '#fff', padding: '6px 14px' }}
            onClick={syncDiscovered}
          >
            Import All to Presets
          </button>
        </div>
      )}

      {/* Quick Add Suggestions */}
      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          padding: '14px 18px',
          marginBottom: '16px',
        }}
      >
        <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-dim)', marginBottom: '8px' }}>
          ⚡ Quick Add Common Durations:
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {POPULAR_SUGGESTIONS.map((sug) => {
            const exists = presets.some((p) => p.toLowerCase() === sug.toLowerCase());
            return (
              <button
                key={sug}
                type="button"
                className={`mini ${exists ? 'ghost' : 'btn'}`}
                style={{
                  fontSize: '12px',
                  padding: '4px 10px',
                  borderRadius: '20px',
                  opacity: exists ? 0.6 : 1,
                  cursor: exists ? 'default' : 'pointer',
                  borderColor: exists ? 'var(--line)' : 'var(--accent)',
                }}
                disabled={exists}
                onClick={() => !exists && quickAdd(sug)}
                title={exists ? 'Already added' : `Add ${sug}`}
              >
                {exists ? (
                  <>
                    <Check size={12} style={{ marginRight: 4 }} /> {sug}
                  </>
                ) : (
                  <>
                    <Plus size={12} style={{ marginRight: 4 }} /> {sug}
                  </>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Table Section */}
      <section className="panel">
        <header>
          <div className="filters">
            <input
              type="search"
              placeholder="Search validities (e.g. 7 Days, 1 Month)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn"
            onClick={() =>
              setDraft({
                mode: 'new',
                label: '',
                updateProducts: false,
              })
            }
          >
            <Plus size={16} style={{ marginRight: 4 }} /> New Validity
          </button>
        </header>

        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Validity Duration</th>
                <th>Products Tagged</th>
                <th>Categories</th>
                <th>Bot Display Preview</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {filteredPresets.map((val) => {
                const matchingProducts = (products ?? []).filter(
                  (p) => p.duration_label && p.duration_label.trim().toLowerCase() === val.toLowerCase()
                );
                const categoryNames = Array.from(
                  new Set(
                    matchingProducts
                      .map((p) => p.category_name)
                      .filter((name): name is string => Boolean(name))
                  )
                );

                return (
                  <tr key={val}>
                    <td className="name">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Clock size={16} color="var(--accent)" />
                        <strong>{val}</strong>
                      </div>
                    </td>
                    <td>
                      {matchingProducts.length > 0 ? (
                        <div>
                          <span
                            className="pill good"
                            style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 600 }}
                          >
                            {matchingProducts.length} product{matchingProducts.length > 1 ? 's' : ''}
                          </span>
                          <div
                            style={{
                              fontSize: '11px',
                              color: 'var(--muted)',
                              marginTop: '4px',
                              maxWidth: '260px',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                            title={matchingProducts.map((p) => p.title).join(', ')}
                          >
                            {matchingProducts.map((p) => p.title).join(', ')}
                          </div>
                        </div>
                      ) : (
                        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>0 products</span>
                      )}
                    </td>
                    <td>
                      {categoryNames.length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                          {categoryNames.map((cName) => (
                            <span
                              key={cName}
                              style={{
                                fontSize: '11px',
                                background: 'var(--subtle)',
                                padding: '2px 6px',
                                borderRadius: '4px',
                              }}
                            >
                              {cName}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>—</span>
                      )}
                    </td>
                    <td>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          background: 'rgba(15, 118, 110, 0.08)',
                          color: 'var(--accent)',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 500,
                          border: '1px solid rgba(15, 118, 110, 0.15)',
                        }}
                      >
                        ⏳ {val}
                      </span>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="mini"
                          onClick={() =>
                            setDraft({
                              mode: 'edit',
                              originalLabel: val,
                              label: val,
                              updateProducts: true,
                            })
                          }
                        >
                          <Edit3 size={13} style={{ marginRight: 3 }} /> Edit
                        </button>
                        <button
                          type="button"
                          className="mini danger"
                          onClick={() => handleDelete(val)}
                        >
                          <Trash2 size={13} style={{ marginRight: 3 }} /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {presets && filteredPresets.length === 0 ? (
                <EmptyRow columns={5}>
                  {search ? 'Nothing matches.' : 'No validities yet. Click "New Validity" above.'}
                </EmptyRow>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Create / Edit Modal */}
      {draft ? (
        <Modal
          title={draft.mode === 'new' ? 'Add New Validity Duration' : `Edit Validity "${draft.originalLabel}"`}
          onClose={() => setDraft(null)}
          onSubmit={handleModalSubmit}
          footer={
            <>
              <button
                type="button"
                className="btn ghost"
                onClick={() => setDraft(null)}
              >
                Cancel
              </button>
              <button type="submit" className="btn" disabled={busy}>
                {draft.mode === 'new' ? 'Add Validity' : 'Save Changes'}
              </button>
            </>
          }
        >
          <label className="field">
            <span>Validity Label</span>
            <input
              type="text"
              required
              placeholder="e.g. 3 Days, 7 Days, 1 Month, 1 Year"
              value={draft.label}
              autoFocus
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            />
            <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: 4 }}>
              💡 এই মেয়াদটি প্রোডাক্ট যোগ করার সময় ড্রপডাউনে থাকবে এবং টেলিগ্রাম বটে ভ্যালিডিটি ফিল্টার হিসেবে কাস্টমার দেখতে পাবে।
            </small>
          </label>

          <div style={{ marginTop: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
              Quick Suggestions:
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {['1 Day', '3 Days', '7 Days', '14 Days', '30 Days', '1 Month', '3 Months', '6 Months', '1 Year', 'Lifetime'].map(
                (presetVal) => (
                  <button
                    key={presetVal}
                    type="button"
                    className="mini ghost"
                    style={{ fontSize: '11px', padding: '2px 8px' }}
                    onClick={() => setDraft({ ...draft, label: presetVal })}
                  >
                    {presetVal}
                  </button>
                )
              )}
            </div>
          </div>

          {draft.mode === 'edit' && (
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginTop: '14px',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={draft.updateProducts}
                onChange={(e) =>
                  setDraft({ ...draft, updateProducts: e.target.checked })
                }
              />
              <span>
                Also update all products currently using &quot;{draft.originalLabel}&quot; to &quot;{draft.label}&quot;
              </span>
            </label>
          )}
        </Modal>
      ) : null}
    </>
  );
}
