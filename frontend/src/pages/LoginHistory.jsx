import { useEffect, useState } from 'react';
import { FiClock, FiRefreshCw } from 'react-icons/fi';
import { auditAPI } from '../services/api';
import { useToast } from '../components/ToastProvider';

function LoginHistory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToast();

  const loadHistory = async () => {
    try {
      const res = await auditAPI.getLoginHistory({ page: 1, per_page: 200 });
      setItems(res.data?.items || []);
    } catch {
      addToast('Не удалось загрузить историю входов', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const formatDateTime = (iso) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('ru-RU');
    } catch {
      return iso;
    }
  };

  return (
    <div className="page-container">
      <div className="container">
        <div className="page-header flex-between">
          <h1><FiClock /> История входов</h1>
          <button className="btn btn-secondary btn-sm" onClick={loadHistory}>
            <FiRefreshCw /> Обновить
          </button>
        </div>

        <div className="card">
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Пользователь</th>
                  <th>Событие</th>
                  <th>IP</th>
                  <th>Время</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: '18px' }}>
                      Загрузка...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: '18px' }}>
                      Нет записей о входах
                    </td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.username || '—'}</td>
                      <td>
                        {item.action === 'login_success'
                          ? 'Успешный вход'
                          : 'Неуспешный вход'}
                      </td>
                      <td>{item.ip_address || '—'}</td>
                      <td>{formatDateTime(item.timestamp)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginHistory;
