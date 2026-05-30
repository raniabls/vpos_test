import React, { useEffect, useMemo, useState } from 'react';
import './Admin.css';
import { apiFetch } from './api.js';

const DATA_TYPES = [
  { key: 'offers', label: 'Offres', icon: '📦', endpoint: 'offers', defaultCategory: 'general' },
  { key: 'faqs', label: 'FAQ', icon: '❓', endpoint: 'faqs', defaultCategory: 'faq' },
  { key: 'services', label: 'Services', icon: '🛠️', endpoint: 'services', defaultCategory: 'service' }
];

export default function Admin() {
  const [items, setItems] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [search, setSearch] = useState('');
  const [activeType, setActiveType] = useState('offers');
  const [activeCat, setActiveCat] = useState('all');
  const [edit, setEdit] = useState(null);
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [itemFeedback, setItemFeedback] = useState({});
  const [busyItem, setBusyItem] = useState(null);
  const [promptBusy, setPromptBusy] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [newItem, setNewItem] = useState({ content: '', category: 'general' });

  const activeTypeInfo = DATA_TYPES.find(t => t.key === activeType) || DATA_TYPES[0];

  function itemKey(item) {
    return `${item.table}-${item.id}`;
  }

  function normalizeList(list, table) {
    const typeInfo = DATA_TYPES.find(t => t.key === table);
    return (list || []).map(item => ({
      ...item,
      table,
      type: table,
      type_label: typeInfo?.label || table,
      category: item.category || typeInfo?.defaultCategory || 'general',
      is_active: item.is_active !== false
    }));
  }

  async function loadData() {
    setLoading(true);
    try {
      const d = await apiFetch('/admin/data');

      const loadedItems = [
        ...normalizeList(d.offers, 'offers'),
        ...normalizeList(d.faqs, 'faqs'),
        ...normalizeList(d.services, 'services')
      ];

      setItems(loadedItems);
      setPrompt(d.prompt || '');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData().catch(e => showToast(e.message || 'Erreur chargement admin', true));
  }, []);

  useEffect(() => {
    setNewItem({ content: '', category: activeTypeInfo.defaultCategory || 'general' });
  }, [activeType]);

  function showToast(msg, error = false) {
    setToast({ msg, error });
    setTimeout(() => setToast(null), 2800);
  }

  function markItem(item, message, type = 'success') {
    const key = itemKey(item);

    setItemFeedback(prev => ({
      ...prev,
      [key]: { message, type }
    }));

    setTimeout(() => {
      setItemFeedback(prev => {
        const copy = { ...prev };
        delete copy[key];
        return copy;
      });
    }, 3500);
  }

  const typeCounts = useMemo(() => {
    const counts = {};
    DATA_TYPES.forEach(t => {
      const typeItems = items.filter(item => item.table === t.key);
      counts[t.key] = {
        total: typeItems.length,
        active: typeItems.filter(item => item.is_active).length
      };
    });
    return counts;
  }, [items]);

  const itemsByType = useMemo(() => {
    return items.filter(item => item.table === activeType);
  }, [items, activeType]);

  const categories = useMemo(() => {
    const grouped = {};

    itemsByType.forEach(item => {
      const cat = item.category || activeTypeInfo.defaultCategory || 'general';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(item);
    });

    return grouped;
  }, [itemsByType, activeTypeInfo.defaultCategory]);

  const categoryList = useMemo(() => {
    return Object.keys(categories).sort();
  }, [categories]);

  const filteredItems = useMemo(() => {
    return itemsByType.filter(item => {
      const content = (item.content || '').toLowerCase();
      const category = (item.category || '').toLowerCase();
      const q = search.toLowerCase().trim();

      const matchesSearch =
        !q ||
        content.includes(q) ||
        category.includes(q) ||
        String(item.id).includes(q);

      const matchesCategory =
        activeCat === 'all' || item.category === activeCat;

      return matchesSearch && matchesCategory;
    });
  }, [itemsByType, search, activeCat]);

  function changeType(type) {
    setActiveType(type);
    setActiveCat('all');
    setSearch('');
  }

  async function savePrompt() {
    if (!prompt.trim()) {
      return showToast('Prompt vide !', true);
    }

    setPromptBusy(true);
    try {
      const d = await apiFetch('/admin/prompt', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: prompt.trim() })
      });

      d.status === 'ok'
        ? showToast('✅ Prompt sauvegardé')
        : showToast('Erreur !', true);
    } catch (e) {
      showToast(e.message || 'Erreur sauvegarde prompt', true);
    } finally {
      setPromptBusy(false);
    }
  }

  async function addItem() {
    if (!newItem.content.trim()) {
      return showToast('Contenu vide !', true);
    }

    setAddBusy(true);
    try {
      const d = await apiFetch(`/admin/${activeTypeInfo.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: newItem.content.trim(),
          category: newItem.category.trim() || activeTypeInfo.defaultCategory || 'general'
        })
      });

      if (d.status === 'ok') {
        showToast(`✅ ${activeTypeInfo.label} ajouté(e)`);
        setNewItem({ content: '', category: activeTypeInfo.defaultCategory || 'general' });
        await loadData();
      }
    } catch (e) {
      showToast(e.message || 'Erreur ajout', true);
    } finally {
      setAddBusy(false);
    }
  }

  async function deleteItem(item) {
    if (!confirm('Supprimer cet élément ?')) return;

    const key = itemKey(item);
    setBusyItem(key);

    try {
      const typeInfo = DATA_TYPES.find(t => t.key === item.table);
      const d = await apiFetch(`/admin/${typeInfo.endpoint}/${item.id}`, {
        method: 'DELETE'
      });

      if (d.status === 'ok') {
        markItem(item, 'Supprimé ✅', 'danger');
        showToast('✅ Élément supprimé et index reconstruit');

        setTimeout(() => {
          setItems(prev =>
            prev.filter(x => !(x.id === item.id && x.table === item.table))
          );
        }, 500);
      }
    } catch (e) {
      showToast(e.message || 'Erreur suppression', true);
    } finally {
      setBusyItem(null);
    }
  }

  async function toggleItem(item, newState) {
    const key = itemKey(item);
    setBusyItem(key);

    try {
      const typeInfo = DATA_TYPES.find(t => t.key === item.table);
      const d = await apiFetch(`/admin/${typeInfo.endpoint}/${item.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: newState })
      });

      if (d.status === 'ok') {
        markItem(
          item,
          newState ? 'Activé ✅' : 'Désactivé ⛔',
          newState ? 'success' : 'warning'
        );
        showToast(newState ? '✅ Élément activé' : '⛔ Élément désactivé');
        await loadData();
      }
    } catch (e) {
      showToast(e.message || 'Erreur changement de statut', true);
    } finally {
      setBusyItem(null);
    }
  }

  async function saveEdit() {
    if (!edit?.content?.trim()) {
      return showToast('Contenu vide !', true);
    }

    const key = itemKey(edit);
    setBusyItem(key);

    try {
      const typeInfo = DATA_TYPES.find(t => t.key === edit.table);
      const d = await apiFetch(`/admin/${typeInfo.endpoint}/${edit.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: edit.content.trim(),
          category: edit.category || typeInfo.defaultCategory || 'general',
          is_active: edit.is_active
        })
      });

      if (d.status === 'ok') {
        const editedItem = { ...edit };
        setEdit(null);
        markItem(editedItem, 'Modifié ✅', 'success');
        showToast('✅ Élément modifié et index reconstruit');
        await loadData();
      }
    } catch (e) {
      showToast(e.message || 'Erreur modification', true);
    } finally {
      setBusyItem(null);
    }
  }

  return (
    <>
      <header>
        <div className="logo">
          <div className="logo-mark"></div>
          IZZY
          <span className="admin-badge">ADMIN</span>
        </div>

        <a href="/" className="back-btn">
          ← RETOUR
        </a>
      </header>

      <div className="container">
        <div className="admin-title-block">
          <h1>Base de connaissances Izzy</h1>
          <p>Gestion des offres, des FAQ et des services utilisés par le RAG.</p>
        </div>

        {/* <div className="section">
          <div className="section-header">
            <span className="section-title">
              <span>●</span> PROMPT SYSTÈME
            </span>

            <button
              className="btn btn-red btn-sm"
              onClick={savePrompt}
              disabled={promptBusy}
            >
              {promptBusy ? 'SAUVEGARDE...' : 'SAUVEGARDER'}
            </button>
          </div>

          <div className="section-body">
            <textarea
              className="prompt-editor"
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
            />

            <p className="prompt-hint">
              Placeholders disponibles : <code>{'{language_name}'}</code> langue détectée &nbsp;|&nbsp;
              <code>{'{context}'}</code> données pertinentes trouvées par le RAG
            </p>
          </div>
        </div> */}

        <div className="stats-row">
          <div className="stat-card">
            <div className="stat-val">{items.length}</div>
            <div className="stat-label">Données totales</div>
          </div>

          {/* <div className="stat-card">
            <div className="stat-val">{items.filter(x => x.is_active).length}</div>
            <div className="stat-label">Données actives</div>
          </div>

          <div className="stat-card">
            <div className="stat-val">{items.filter(x => !x.is_active).length}</div>
            <div className="stat-label">Données désactivées</div>
          </div> */}
        </div>

        <div className="section">
          <div className="section-header">
            <span className="section-title">
              <span>●</span> CHOISIR LE TYPE DE DONNÉES
            </span>
          </div>

          <div className="section-body">
            <div className="category-grid">
              {DATA_TYPES.map(type => (
                <button
                  key={type.key}
                  className={'category-card ' + (activeType === type.key ? 'active' : '')}
                  onClick={() => changeType(type.key)}
                >
                  <span className="category-name">{type.icon} {type.label}</span>
                  <span className="category-count">{typeCounts[type.key]?.total || 0}</span>
                  <span className="offer-count-label">
                    {typeCounts[type.key]?.active || 0} actifs
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="section">
          <div className="section-header">
            <span className="section-title">
              <span>●</span> AJOUTER : {activeTypeInfo.icon} {activeTypeInfo.label.toUpperCase()}
            </span>

            {/* <button
              className="btn btn-red btn-sm"
              onClick={addItem}
              disabled={addBusy}
            >
              {addBusy ? 'AJOUT...' : 'AJOUTER'}
            </button> */}
          </div>

          <div className="section-body">
            <div className="offer-form">
              <textarea
                className="form-input"
                style={{ minHeight: 70, resize: 'vertical' }}
                value={newItem.content}
                onChange={e => setNewItem({ ...newItem, content: e.target.value })}
                placeholder={`Contenu ${activeTypeInfo.label.toLowerCase()}...`}
              />

              <input
                className="form-input"
                value={newItem.category}
                onChange={e => setNewItem({ ...newItem, category: e.target.value })}
                placeholder="Catégorie"
              />

              <button
                className="btn btn-red"
                onClick={addItem}
                disabled={addBusy}
              >
                {addBusy ? 'TRAITEMENT...' : 'AJOUTER'}
              </button>
            </div>
          </div>
        </div>

        <div className="section">
          <div className="section-header">
            <span className="section-title">
              <span>●</span> {activeTypeInfo.icon} {activeTypeInfo.label.toUpperCase()}
            </span>

            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              {filteredItems.length} élément(s)
            </span>
          </div>

          <div className="section-body">
            <div className="filter-bar">
              <input
                className="filter-input"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={`Rechercher dans ${activeTypeInfo.label.toLowerCase()}...`}
              />

              <button
                className={'cat-filter ' + (activeCat === 'all' ? 'active' : '')}
                onClick={() => setActiveCat('all')}
              >
                Tout ({itemsByType.length})
              </button>

              {/* {categoryList.map(cat => (
                <button
                  key={cat}
                  className={'cat-filter ' + (activeCat === cat ? 'active' : '')}
                  onClick={() => setActiveCat(cat)}
                >
                  {cat} ({categories[cat].length})
                </button>
              ))} */}
            </div>

            {loading ? (
              <div className="empty-state">
                <div className="ico">⏳</div>
                Chargement...
              </div>
            ) : (
              <div className="data-list">
                {filteredItems.map(item => {
                  const key = itemKey(item);
                  const isBusy = busyItem === key;
                  const feedback = itemFeedback[key];

                  return (
                    <div key={key} className={'data-card ' + (isBusy ? 'card-busy' : '')}>
                      <div className="data-card-top">
                        <div>
                          <span className="data-id">#{item.id}</span>
                          <span className="cat-pill">{item.type_label}</span>{' '}
                          <span className="cat-pill">{item.category}</span>
                        </div>

                        <div className="status-zone">
                          {/* <span className={item.is_active ? 'status active' : 'status inactive'}>
                            <span className={'status-dot ' + (item.is_active ? 'active' : 'inactive')}></span>
                            {item.is_active ? 'Active' : 'Inactive'}
                          </span> */}

                          {isBusy && (
                            <span className="inline-feedback loading">
                              Traitement... reconstruction index
                            </span>
                          )}

                          {!isBusy && feedback && (
                            <span className={`inline-feedback ${feedback.type}`}>
                              {feedback.message}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="data-content">
                        {item.content}
                      </div>

                      <div className="data-actions">
                        {/* <button
                          className="btn btn-green"
                          disabled={isBusy}
                          onClick={() => toggleItem(item, !item.is_active)}
                        >
                          {isBusy ? 'TRAITEMENT...' : item.is_active ? 'DÉSACTIVER' : 'ACTIVER'}
                        </button> */}

                        <button
                          className="btn btn-outline btn-sm"
                          disabled={isBusy}
                          onClick={() => setEdit({ ...item })}
                        >
                          ÉDITER
                        </button>

                        <button
                          className="btn btn-danger"
                          disabled={isBusy}
                          onClick={() => deleteItem(item)}
                        >
                          SUPPRIMER
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {!loading && !filteredItems.length && (
              <div className="empty-state">
                <div className="ico">📭</div>
                Aucun résultat trouvé.
              </div>
            )}
          </div>
        </div>
      </div>

      <div
        className={'modal-overlay ' + (edit ? 'show' : '')}
        onClick={e => {
          if (e.target === e.currentTarget && !busyItem) setEdit(null);
        }}
      >
        <div className="modal">
          <div className="modal-title">
            ÉDITER : {edit?.type_label || edit?.table} #{edit?.id}
          </div>

          <div className="modal-group">
            <div className="modal-label">Contenu</div>
            <textarea
              className="modal-textarea"
              value={edit?.content || ''}
              disabled={busyItem === (edit ? itemKey(edit) : null)}
              onChange={e => setEdit({ ...edit, content: e.target.value })}
            />
          </div>

          <div className="modal-group">
            <div className="modal-label">Catégorie</div>
            <input
              className="form-input"
              value={edit?.category || ''}
              disabled={busyItem === (edit ? itemKey(edit) : null)}
              onChange={e => setEdit({ ...edit, category: e.target.value })}
            />
          </div>

          <div className="modal-group">
            <div className="modal-label">Statut</div>
            <select
              className="form-select"
              value={edit?.is_active ? 'active' : 'inactive'}
              disabled={busyItem === (edit ? itemKey(edit) : null)}
              onChange={e =>
                setEdit({ ...edit, is_active: e.target.value === 'active' })
              }
            >
              <option value="active">Actif</option>
              <option value="inactive">Désactivé</option>
            </select>
          </div>

          {busyItem === (edit ? itemKey(edit) : null) && (
            <div className="modal-processing">
              ⏳ Modification en cours... PostgreSQL est mis à jour puis l'index est reconstruit.
            </div>
          )}

          <div className="modal-actions">
            <button
              className="btn btn-outline"
              disabled={busyItem === (edit ? itemKey(edit) : null)}
              onClick={() => setEdit(null)}
            >
              ANNULER
            </button>

            <button
              className="btn btn-red"
              disabled={busyItem === (edit ? itemKey(edit) : null)}
              onClick={saveEdit}
            >
              {busyItem === (edit ? itemKey(edit) : null) ? 'TRAITEMENT...' : 'SAUVEGARDER'}
            </button>
          </div>
        </div>
      </div>

      <div id="toast" className={toast ? 'show ' + (toast.error ? 'error' : '') : ''}>
        {toast?.msg}
      </div>
    </>
  );
}
