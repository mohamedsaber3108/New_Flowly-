import React from 'react';
import {createRoot} from 'react-dom/client';
import FlowlyApp from '../components/FlowlyApp';
import '../app/globals.css';
createRoot(document.getElementById('root')!).render(<FlowlyApp initialPath={window.location.pathname}/>);
