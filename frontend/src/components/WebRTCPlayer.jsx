import React, { useRef, useEffect, useCallback, useState } from 'react';

/**
 * WebRTC player using go2rtc's WebRTC signaling API.
 * Provides sub-second latency compared to 2-5s for MP4/MJPEG.
 */
function WebRTCPlayer({ cameraUrl, onError, onConnected, style, className }) {
  const videoRef = useRef(null);
  const pcRef = useRef(null);
  const [status, setStatus] = useState('connecting');

  const cleanup = useCallback(() => {
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!cameraUrl) return;
    cleanup();
    setStatus('connecting');

    try {
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      });
      pcRef.current = pc;

      pc.ontrack = (event) => {
        if (videoRef.current && event.streams[0]) {
          videoRef.current.srcObject = event.streams[0];
          setStatus('connected');
          onConnected?.();
        }
      };

      pc.oniceconnectionstatechange = () => {
        if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'disconnected') {
          setStatus('error');
          onError?.('WebRTC connection failed');
        }
      };

      // Add transceivers for receiving audio and video
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // Wait for ICE gathering to complete (or timeout after 2s)
      await new Promise((resolve) => {
        if (pc.iceGatheringState === 'complete') {
          resolve();
          return;
        }
        const timeout = setTimeout(resolve, 2000);
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === 'complete') {
            clearTimeout(timeout);
            resolve();
          }
        };
      });

      // Send offer to go2rtc WebRTC API
      const encodedSrc = encodeURIComponent(cameraUrl);
      const response = await fetch(`/go2rtc/api/webrtc?src=${encodedSrc}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: pc.localDescription.sdp,
      });

      if (!response.ok) {
        throw new Error(`WebRTC signaling failed: ${response.status}`);
      }

      const answerSdp = await response.text();
      await pc.setRemoteDescription(
        new RTCSessionDescription({ type: 'answer', sdp: answerSdp })
      );
    } catch (err) {
      console.error('WebRTC connection error:', err);
      setStatus('error');
      onError?.(err.message || 'WebRTC connection failed');
    }
  }, [cameraUrl, cleanup, onError, onConnected]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  return (
    <div style={{ position: 'relative', ...style }} className={className}>
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        controls
        style={{ width: '100%', height: '100%', objectFit: 'contain', backgroundColor: '#000' }}
      />
      {status === 'connecting' && (
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          color: '#fff', fontSize: '14px', background: 'rgba(0,0,0,0.6)',
          padding: '8px 16px', borderRadius: '4px'
        }}>
          Подключение WebRTC...
        </div>
      )}
    </div>
  );
}

export default WebRTCPlayer;
