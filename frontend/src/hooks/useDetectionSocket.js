import { useEffect, useRef, useState, useCallback } from 'react';
import io from 'socket.io-client';

/**
 * WebSocket hook for receiving real-time face detection events from the worker.
 * Uses socket.io for reliable WebSocket communication with automatic reconnection.
 * Falls back to HTTP polling if WebSocket is unavailable.
 */
export function useDetectionSocket(cameraId, enabled = true) {
  const [detections, setDetections] = useState(null);
  const socketRef = useRef(null);
  const pollingTimerRef = useRef(null);

  const connect = useCallback(() => {
    if (!enabled || !cameraId) return;

    // Clean up existing connection
    if (socketRef.current) {
      socketRef.current.disconnect();
    }

    try {
      // Connect using socket.io
      const socket = io(`/detections`, {
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: 5,
        transports: ['websocket', 'polling']
      });

      socketRef.current = socket;

      socket.on('connect', () => {
        console.log(`Detection WebSocket connected for camera ${cameraId}`);
        // Join the detection room for this camera
        socket.emit('join_camera', { camera_id: cameraId });
      });

      socket.on('detection', (data) => {
        try {
          setDetections(data);
        } catch (err) {
          console.warn('Invalid detection data:', err);
        }
      });

      socket.on('disconnect', () => {
        console.log('Detection WebSocket disconnected, will auto-reconnect');
      });

      socket.on('error', (error) => {
        console.warn('WebSocket error:', error);
      });

      socket.on('connect_error', (error) => {
        console.warn('WebSocket connection error:', error);
      });
    } catch (err) {
      console.warn('WebSocket connection failed, falling back to polling:', err);
      // Fallback to polling
      startPolling();
    }
  }, [cameraId, enabled]);

  const startPolling = useCallback(async () => {
    const poll = async () => {
      try {
        const response = await fetch(`/api/detections/${cameraId}`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
        if (response.ok) {
          const data = await response.json();
          if (data.detections && data.detections.length > 0) {
            setDetections(data.detections[data.detections.length - 1]);
          }
        }
      } catch (err) {
        console.warn('Detection polling error:', err);
      }
      // Poll every 100ms
      pollingTimerRef.current = setTimeout(poll, 100);
    };

    poll();
  }, [cameraId]);

  useEffect(() => {
    connect();

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current);
      }
    };
  }, [connect]);

  return detections;
}
