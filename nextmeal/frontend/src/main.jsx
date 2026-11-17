import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.jsx';
import ServerApp from './IntegratedApp.jsx';
import './styles.css';
const Root = import.meta.env.VITE_APP_MODE === 'demo' ? App : ServerApp;
createRoot(document.getElementById('root')).render(<React.StrictMode><Root/></React.StrictMode>);
