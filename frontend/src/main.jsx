import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import Admin from './Admin.jsx';

const root = createRoot(document.getElementById('root'));
root.render(window.location.pathname.startsWith('/admin') ? <Admin /> : <App />);
