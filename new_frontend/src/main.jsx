import React from 'react';
import { createRoot } from 'react-dom/client';
import ChatPage from './pages/Chat/ChatPage.jsx';
import AdminPage from './pages/Admin/AdminPage.jsx';
import './styles/global.css';

const root = createRoot(document.getElementById('root'));
const isAdmin = window.location.pathname.startsWith('/admin');

root.render(isAdmin ? <AdminPage /> : <ChatPage />);
