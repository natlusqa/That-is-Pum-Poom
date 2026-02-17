import { useEffect, useRef } from 'react';
import { useKorganStore } from './store/useKorganStore';
import Overlay from './components/Overlay';
import StatusBar from './components/StatusBar';
import ActionLog from './components/ActionLog';
import AutonomyPanel from './components/AutonomyPanel';

const WS_URL = 'ws://localhost:8000/ws';

function App() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const { setStatus, addAction } = useKorganStore();

  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
          addAction('Connected to KORGAN backend', 'success');
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.status) setStatus(data.status);
            if (data.type === 'action') addAction(data.message || 'Action', data.actionType || 'info');
          } catch {
            addAction('Received message', 'info');
          }
        };

        ws.onclose = () => {
          addAction('Disconnected from backend', 'warning');
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        };

        ws.onerror = () => {
          addAction('WebSocket error', 'error');
        };

        wsRef.current = ws;
      } catch (err) {
        addAction('Failed to connect', 'error');
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [setStatus, addAction]);

  return (
    <div className="korgan-app">
      <Overlay />
      <div className="korgan-ui">
        <StatusBar />
        <div className="korgan-panels">
          <ActionLog />
          <AutonomyPanel />
        </div>
      </div>
    </div>
  );
}

export default App;
