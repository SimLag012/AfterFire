import { initializeDemo } from './demo/runtime';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './app/App';
import './styles/index.css';

initializeDemo().then(() => ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)).catch(error => { document.getElementById('root')!.textContent = 'Public snapshot unavailable: ' + error.message; });

