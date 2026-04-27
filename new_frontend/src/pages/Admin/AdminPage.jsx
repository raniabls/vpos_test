import React, { useEffect, useMemo, useState } from 'react';
import './AdminPage.css';
import { apiFetch } from '../../services/api.js';

export default function AdminPage() {
  const [items, setItems] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [edit, setEdit] = useState(null);
  const [toast, setToast] = useState(null);

  async function loadData() {
    const data = await apiFetch('/admin/data');
    setItems(data.items || data.data || data.offers || []);
    setPrompt(data.prompt || '');
  }

  useEffect(() => {
    loadData().catch((error) => showToast(error.message, true));
  }, []);

  function showToast(message, error = false) {
    setToast({ message, error });
    setTimeout(() => setToast(null), 2500);
  }

  const categories = useMemo(() => {
    const grouped = {};

    items.forEach((item) => {
      const category = item.category || 'general';
      if (!grouped[category]) grouped[category] = [];
      grouped[category].push(item);
    });

    return grouped;
  }, [items]);

  const categoryList = useMemo(() => Object.keys(categories).sort(), [categories]);

  const activeItems = useMemo(() => items.filter((item) => item.is_active), [items]);

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();

    return items.filter((item) => {
      const category = (item.category || '').toLowerCase();
      const content = (item.content || '').toLowerCase();

      const matchCategory = activeCategory === 'all' || item.category === activeCategory;
      const matchSearch = !query || category.includes(query) || content.includes(query);

      return matchCategory && matchSearch;
    });
  }, [items, search, activeCategory]);

  async function savePrompt() {
    if (!prompt.trim()) return showToast('Prompt vide !', true);

    const result = await apiFetch('/admin/prompt', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: prompt.trim() })
    });

    result.status === 'ok'
      ? showToast('✅ Prompt sauvegardé')
      : showToast('Erreur !', true);
  }

  async function toggleItem(id, newState) {
    const result = await apiFetch(`/admin/offers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: newState })
    });

    if (result.status === 'ok') {
      showToast('✅ Statut modifié');
      await loadData();
    }
  }

  async function deleteItem(id) {
    if (!confirm('Supprimer cet élément ?')) return;

    const result = await apiFetch(`/admin/offers/${id}`, { method: 'DELETE' });

    if (result.status === 'ok') {
      setItems((previous) => previous.filter((item) => item.id !== id));
      showToast('✅ Élément supprimé');
    }
  }

  async function saveEdit() {
    if (!edit?.content?.trim()) return showToast('Contenu vide !', true);

    const result = await apiFetch(`/admin/offers/${edit.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: edit.content.trim(),
        category: edit.category || 'general'
      })
    });

    if (result.status === 'ok') {
      setEdit(null);
      showToast('✅ Élément modifié');
      await loadData();
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div className="admin-brand">
          <div className="admin-diamond" />
          <div>
            <div className="admin-logo">IZZY</div>
            <div className="admin-subtitle">Knowledge Base Manager</div>
          </div>
          <span className="admin-badge">ADMIN</span>
        </div>

        <a href="/" className="back-btn">← RETOUR CHAT</a>
      </header>

      <main className="admin-container">
        <section className="admin-hero">
          <div>
            <p className="eyebrow">Djezzy AI Assistant</p>
            <h1>Base de connaissances</h1>
            <p>Gère le prompt système et toutes les données utilisées par FAISS : offres, FAQ, services, roaming, internet et autres catégories.</p>
          </div>
        </section>

        <section className="section prompt-section">
          <div className="section-header">
            <div>
              <span className="section-title"><span>●</span> PROMPT SYSTÈME</span>
              <p className="section-caption">Ce prompt guide Izzy avant chaque réponse.</p>
            </div>
            <button className="btn btn-red btn-sm" onClick={savePrompt}>SAUVEGARDER</button>
          </div>

          <div className="section-body">
            <textarea
              className="prompt-editor compact"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <p className="prompt-hint">
              Placeholders disponibles : <code>{'{language_name}'}</code> langue détectée | <code>{'{context}'}</code> données pertinentes trouvées par FAISS
            </p>
          </div>
        </section>

        <section className="stats-row">
          <div className="stat-card">
            <div className="stat-val">{items.length}</div>
            <div className="stat-label">Données totales</div>
          </div>
          <div className="stat-card">
            <div className="stat-val">{activeItems.length}</div>
            <div className="stat-label">Données actives</div>
          </div>
          <div className="stat-card">
            <div className="stat-val">{categoryList.length}</div>
            <div className="stat-label">Types de données</div>
          </div>
        </section>

        <section className="category-grid">
          <button
            className={'category-card ' + (activeCategory === 'all' ? 'active' : '')}
            onClick={() => setActiveCategory('all')}
          >
            <span className="category-name">Tout</span>
            <span className="category-count">{items.length}</span>
          </button>

          {categoryList.map((category) => (
            <button
              key={category}
              className={'category-card ' + (activeCategory === category ? 'active' : '')}
              onClick={() => setActiveCategory(category)}
            >
              <span className="category-name">{category}</span>
              <span className="category-count">{categories[category].length}</span>
            </button>
          ))}
        </section>

        <section className="section">
          <div className="section-header">
            <div>
              <span className="section-title"><span>●</span> EXPLORATION DES DONNÉES</span>
              <p className="section-caption">Recherche dans toutes les lignes migrées vers PostgreSQL.</p>
            </div>
            <span className="result-count">{filteredItems.length} élément(s)</span>
          </div>

          <div className="section-body">
            <input
              className="admin-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher dans FAQ, offres, services, internet..."
            />

            <div className="data-list">
              {filteredItems.map((item) => (
                <article key={item.id} className="data-card">
                  <div className="data-card-top">
                    <div className="data-meta">
                      <span className="data-id">#{item.id}</span>
                      <span className="cat-pill">{item.category || 'general'}</span>
                    </div>
                    <span className={item.is_active ? 'status active' : 'status inactive'}>
                      {item.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>

                  <p className="data-content">{item.content}</p>

                  <div className="data-actions">
                    <button className="btn btn-green" onClick={() => toggleItem(item.id, !item.is_active)}>
                      {item.is_active ? 'DÉSACTIVER' : 'ACTIVER'}
                    </button>
                    <button className="btn btn-outline btn-sm" onClick={() => setEdit({ ...item })}>ÉDITER</button>
                    <button className="btn btn-danger" onClick={() => deleteItem(item.id)}>SUPPRIMER</button>
                  </div>
                </article>
              ))}
            </div>

            {!filteredItems.length && (
              <div className="empty-state">
                <div className="ico">📭</div>
                Aucun résultat trouvé.
              </div>
            )}
          </div>
        </section>
      </main>

      <div
        className={'modal-overlay ' + (edit ? 'show' : '')}
        onClick={(e) => {
          if (e.target === e.currentTarget) setEdit(null);
        }}
      >
        <div className="modal">
          <div className="modal-title">ÉDITER L'ÉLÉMENT</div>

          <textarea
            className="form-input prompt-editor"
            value={edit?.content || ''}
            onChange={(e) => setEdit({ ...edit, content: e.target.value })}
          />

          <select
            className="form-select"
            value={edit?.category || ''}
            onChange={(e) => setEdit({ ...edit, category: e.target.value })}
          >
            {categoryList.map((category) => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>

          <div className="modal-actions">
            <button className="btn btn-outline" onClick={() => setEdit(null)}>ANNULER</button>
            <button className="btn btn-red" onClick={saveEdit}>SAUVEGARDER</button>
          </div>
        </div>
      </div>

      <div id="toast" className={toast ? 'show ' + (toast.error ? 'error' : '') : ''}>
        {toast?.message}
      </div>
    </div>
  );
}
