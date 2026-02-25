import { useState, useEffect, useRef, useCallback } from 'react';
import { FiBell, FiX, FiVideo, FiUser, FiAlertCircle } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import io from 'socket.io-client';

function NotificationCenter() {
  const [notifications, setNotifications] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const socketRef = useRef(null);
  const panelRef = useRef(null);
  const navigate = useNavigate();

  const addNotification = useCallback((notification) => {
    const id = `notif_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const newNotif = { id, timestamp: new Date(), read: false, ...notification };

    setNotifications(prev => [newNotif, ...prev].slice(0, 50));
    setUnreadCount(prev => prev + 1);

    // Browser notification
    if (Notification.permission === 'granted') {
      try {
        new Notification(notification.title || 'Surveillance AI', {
          body: notification.message,
          icon: '/icons/icon-192.png',
          tag: id,
        });
      } catch {
        // Notifications not supported
      }
    }
  }, []);

  useEffect(() => {
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    // Connect to Socket.IO for real-time events
    try {
      const socket = io('/detections', {
        reconnection: true,
        reconnectionDelay: 2000,
        transports: ['websocket', 'polling'],
      });

      socketRef.current = socket;

      socket.on('connect', () => {
        socket.emit('join_camera', { camera_id: 'all' });
      });

      socket.on('detection', (data) => {
        if (data.faces && data.faces.length > 0) {
          const recognized = data.faces.filter(f => f.name && f.name !== 'Unknown');
          const unknown = data.faces.filter(f => !f.name || f.name === 'Unknown');

          if (recognized.length > 0) {
            addNotification({
              type: 'face',
              title: 'Face Detected',
              message: `${recognized.map(f => f.name).join(', ')} detected on camera`,
              camera_id: data.camera_id,
            });
          }

          if (unknown.length > 0) {
            addNotification({
              type: 'alert',
              title: 'Unknown Person',
              message: `${unknown.length} unknown face(s) detected`,
              camera_id: data.camera_id,
            });
          }
        }
      });
    } catch {
      // Socket connection failed silently
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, [addNotification]);

  // Close panel on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    setUnreadCount(0);
  };

  const clearAll = () => {
    setNotifications([]);
    setUnreadCount(0);
  };

  const handleNotifClick = (notif) => {
    if (notif.camera_id) {
      navigate(`/camera/${notif.camera_id}`);
      setIsOpen(false);
    }
  };

  const getNotifIcon = (type) => {
    switch (type) {
      case 'face': return <FiUser />;
      case 'alert': return <FiAlertCircle />;
      case 'camera': return <FiVideo />;
      default: return <FiBell />;
    }
  };

  const getTimeDiff = (timestamp) => {
    const diff = Date.now() - new Date(timestamp).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  return (
    <div className="notification-center" ref={panelRef}>
      <button
        className="notif-bell"
        onClick={() => {
          setIsOpen(!isOpen);
          if (!isOpen) markAllRead();
        }}
      >
        <FiBell size={18} />
        {unreadCount > 0 && (
          <span className="notif-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>

      {isOpen && (
        <div className="notif-panel">
          <div className="notif-panel-header">
            <span>Notifications</span>
            <div className="notif-panel-actions">
              {notifications.length > 0 && (
                <button onClick={clearAll} className="notif-clear">Clear all</button>
              )}
              <button onClick={() => setIsOpen(false)} className="notif-close-btn">
                <FiX size={16} />
              </button>
            </div>
          </div>

          <div className="notif-list">
            {notifications.length === 0 ? (
              <div className="notif-empty">
                <FiBell size={24} />
                <p>No notifications</p>
              </div>
            ) : (
              notifications.map(notif => (
                <div
                  key={notif.id}
                  className={`notif-item ${notif.read ? '' : 'unread'}`}
                  onClick={() => handleNotifClick(notif)}
                >
                  <div className={`notif-icon notif-icon-${notif.type}`}>
                    {getNotifIcon(notif.type)}
                  </div>
                  <div className="notif-content">
                    <strong>{notif.title}</strong>
                    <span>{notif.message}</span>
                  </div>
                  <div className="notif-time">{getTimeDiff(notif.timestamp)}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <style>{`
        .notification-center {
          position: relative;
        }
        .notif-bell {
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          cursor: pointer;
          padding: 8px 10px;
          display: flex;
          align-items: center;
          position: relative;
          transition: all 150ms;
        }
        .notif-bell:hover {
          background: var(--color-bg-tertiary);
          color: var(--text-primary);
        }
        .notif-badge {
          position: absolute;
          top: -4px;
          right: -4px;
          background: var(--danger);
          color: white;
          font-size: 0.625rem;
          font-weight: 700;
          min-width: 16px;
          height: 16px;
          border-radius: 999px;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0 4px;
          line-height: 1;
        }
        .notif-panel {
          position: absolute;
          top: calc(100% + 8px);
          right: 0;
          width: 360px;
          max-height: 460px;
          background: var(--color-bg-secondary);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-xl);
          z-index: 200;
          display: flex;
          flex-direction: column;
          animation: modalIn 0.2s ease;
          overflow: hidden;
        }
        .notif-panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          border-bottom: 1px solid var(--border-color);
          font-weight: 600;
          font-size: 0.875rem;
          color: var(--text-primary);
        }
        .notif-panel-actions {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .notif-clear {
          background: none;
          border: none;
          color: var(--accent-light);
          cursor: pointer;
          font-size: 0.75rem;
          font-family: inherit;
        }
        .notif-close-btn {
          background: none;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 2px;
          display: flex;
        }
        .notif-list {
          overflow-y: auto;
          flex: 1;
        }
        .notif-item {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 10px 16px;
          border-bottom: 1px solid var(--border-color);
          cursor: pointer;
          transition: background 150ms;
        }
        .notif-item:hover {
          background: var(--color-bg-hover);
        }
        .notif-item.unread {
          background: var(--accent-subtle);
        }
        .notif-item:last-child {
          border-bottom: none;
        }
        .notif-icon {
          width: 28px;
          height: 28px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          font-size: 13px;
        }
        .notif-icon-face {
          background: var(--success-bg);
          color: var(--success);
        }
        .notif-icon-alert {
          background: var(--danger-bg);
          color: var(--danger);
        }
        .notif-icon-camera {
          background: var(--info-bg);
          color: var(--info);
        }
        .notif-content {
          flex: 1;
          min-width: 0;
        }
        .notif-content strong {
          display: block;
          font-size: 0.8125rem;
          font-weight: 600;
          color: var(--text-primary);
          margin-bottom: 2px;
        }
        .notif-content span {
          font-size: 0.75rem;
          color: var(--text-muted);
          display: block;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .notif-time {
          font-size: 0.625rem;
          color: var(--text-muted);
          white-space: nowrap;
          flex-shrink: 0;
        }
        .notif-empty {
          padding: 40px 16px;
          text-align: center;
          color: var(--text-muted);
        }
        .notif-empty svg {
          margin-bottom: 8px;
          opacity: 0.4;
        }
        .notif-empty p {
          font-size: 0.8125rem;
        }
        @media (max-width: 640px) {
          .notif-panel {
            width: calc(100vw - 32px);
            right: -8px;
          }
        }
      `}</style>
    </div>
  );
}

export default NotificationCenter;
