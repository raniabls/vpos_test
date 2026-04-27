import React, { useEffect, useMemo, useState } from 'react';
import './Admin.css';
import { apiFetch } from './api.js';

export default function Admin() {
  const [items, setItems] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [search, setSearch] = useState('');
  const [activeCat, setActiveCat] = useState('all');
  const [edit, setEdit] = useState(null);
  const [toast, setToast] = useState(null);

  async function loadData() {
    const d = await apiFetch('/admin/data');

    setItems(d.items || d.data || d.offers || []);
    setPrompt(d.prompt || '');
  }

  useEffect(() => {
    loadData().catch(e => showToast(e.message, true));
  }, []);

  function showToast(msg, error = false) {
    setToast({ msg, error });
    setTimeout(() => setToast(null), 2500);
  }

  const categories = useMemo(() => {
    const grouped = {};

    items.forEach(item => {
      const cat = item.category || 'general';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(item);
    });

    return grouped;
  }, [items]);

  const categoryList = useMemo(() => {
    return Object.keys(categories).sort();
  }, [categories]);

  const filteredItems = useMemo(() => {
    return items.filter(item => {
      const content = (item.content || '').toLowerCase();
      const category = (item.category || '').toLowerCase();

      const matchesSearch =
        !search ||
        content.includes(search.toLowerCase()) ||
        category.includes(search.toLowerCase());

      const matchesCategory =
        activeCat === 'all' || item.category === activeCat;

      return matchesSearch && matchesCategory;
    });
  }, [items, search, activeCat]);

  async function savePrompt() {
    if (!prompt.trim()) {
      return showToast('Prompt vide !', true);
    }

    const d = await apiFetch('/admin/prompt', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: prompt.trim() })
    });

    d.status === 'ok'
      ? showToast('✅ Prompt sauvegardé')
      : showToast('Erreur !', true);
  }

  async function deleteItem(id) {
    if (!confirm('Supprimer cet élément ?')) return;

    const d = await apiFetch(`/admin/offers/${id}`, {
      method: 'DELETE'
    });

    if (d.status === 'ok') {
      setItems(prev => prev.filter(x => x.id !== id));
      showToast('✅ Élément supprimé');
    }
  }

  async function toggleItem(id, newState) {
    const d = await apiFetch(`/admin/offers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: newState })
    });

    if (d.status === 'ok') {
      showToast('✅ Statut modifié');
      await loadData();
    }
  }

  async function saveEdit() {
    if (!edit?.content?.trim()) {
      return showToast('Contenu vide !', true);
    }

    const d = await apiFetch(`/admin/offers/${edit.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: edit.content.trim(),
        category: edit.category
      })
    });

    if (d.status === 'ok') {
      setEdit(null);
      showToast('✅ Élément modifié');
      await loadData();
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
          <p>
            Gestion complète des offres, FAQ, services et autres données utilisées par le RAG.
          </p>
        </div>

        {/* PROMPT FIRST */}

        <div className="section">
          <div className="section-header">
            <span className="section-title">
              <span>●</span> PROMPT SYSTÈME
            </span>

            <button className="btn btn-red btn-sm" onClick={savePrompt}>
              SAUVEGARDER
            </button>
          </div>

          <div className="section-body">
            <textarea
              className="prompt-editor"
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
            />

            <p className="prompt-hint">
              Placeholders disponibles :
              <code>{'{language_name}'}</code>
              →
              langue détectée
              &nbsp;|&nbsp;
              <code>{'{context}'}</code>
              →
              données pertinentes trouvées par FAISS
            </p>
          </div>
        </div>

        {/* GLOBAL STATS */}

        <div className="stats-row">
          <div className="stat-card">
            <div className="stat-val">{items.length}</div>
            <div className="stat-label">Données totales</div>
          </div>

          <div className="stat-card">
            <div className="stat-val">
              {items.filter(x => x.is_active).length}
            </div>
            <div className="stat-label">Données actives</div>
          </div>

          <div className="stat-card">
            <div className="stat-val">{categoryList.length}</div>
            <div className="stat-label">Types de données</div>
          </div>
        </div>

        {/* SMALL CATEGORY CARDS */}

        <div className="category-grid">
          <button
            className={'category-card ' + (activeCat === 'all' ? 'active' : '')}
            onClick={() => setActiveCat('all')}
          >
            <span className="category-name">TOUT</span>
            <span className="category-count">{items.length}</span>
          </button>

          {categoryList.map(cat => (
            <button
              key={cat}
              className={'category-card ' + (activeCat === cat ? 'active' : '')}
              onClick={() => setActiveCat(cat)}
            >
              <span className="category-name">{cat}</span>
              <span className="category-count">{categories[cat].length}</span>
            </button>
          ))}
        </div>

        {/* DATA LIST */}

        <div className="section">
          <div className="section-header">
            <span className="section-title">
              <span>●</span> BASE DE CONNAISSANCES
            </span>

            <span style={{ fontSize: 10, color: 'var(--dim)' }}>
              {filteredItems.length} éléments
            </span>
          </div>

          <div className="section-body">
            <input
              className="admin-search"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Rechercher dans les offres, FAQ, services..."
            />

            <div className="data-list">
              {filteredItems.map(item => (
                <div key={item.id} className="data-card">
                  <div className="data-card-top">
                    <div>
                      <span className="data-id">#{item.id}</span>
                      <span className="cat-pill">{item.category}</span>
                    </div>

                    <span
                      className={
                        item.is_active
                          ? 'status active'
                          : 'status inactive'
                      }
                    >
                      {item.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>

                  <div className="data-content">
                    {item.content}
                  </div>

                  <div className="data-actions">
                    <button
                      className="btn btn-green"
                      onClick={() => toggleItem(item.id, !item.is_active)}
                    >
                      {item.is_active ? 'DÉSACTIVER' : 'ACTIVER'}
                    </button>

                    <button
                      className="btn btn-outline btn-sm"
                      onClick={() => setEdit({ ...item })}
                    >
                      ÉDITER
                    </button>

                    <button
                      className="btn btn-danger"
                      onClick={() => deleteItem(item.id)}
                    >
                      SUPPRIMER
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {!filteredItems.length && (
              <div className="empty-state">
                <div className="ico">📭</div>
                Aucun résultat trouvé.
              </div>
            )}
          </div>
        </div>

      </div>

      {/* EDIT MODAL */}

      <div
        className={'modal-overlay ' + (edit ? 'show' : '')}
        onClick={e => {
          if (e.target === e.currentTarget) setEdit(null);
        }}
      >
        <div className="modal">
          <div className="modal-title">
            ÉDITER L'ÉLÉMENT
          </div>

          <textarea
            className="form-input prompt-editor"
            value={edit?.content || ''}
            onChange={e =>
              setEdit({
                ...edit,
                content: e.target.value
              })
            }
          />

          <select
            className="form-select"
            value={edit?.category || ''}
            onChange={e =>
              setEdit({
                ...edit,
                category: e.target.value
              })
            }
          >
            {categoryList.map(cat => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>

          <div className="modal-actions">
            <button
              className="btn btn-outline"
              onClick={() => setEdit(null)}
            >
              ANNULER
            </button>

            <button
              className="btn btn-red"
              onClick={saveEdit}
            >
              SAUVEGARDER
            </button>
          </div>
        </div>
      </div>

      <div
        id="toast"
        className={toast ? 'show ' + (toast.error ? 'error' : '') : ''}
      >
        {toast?.msg}
      </div>
    </>
  );
}