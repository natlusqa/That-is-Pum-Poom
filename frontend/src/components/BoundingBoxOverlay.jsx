import React, { useRef, useEffect, useCallback } from 'react';
import { useDetectionSocket } from '../hooks/useDetectionSocket';

/**
 * Canvas overlay that draws bounding boxes over detected faces.
 * Positioned absolutely over a video element.
 * Green boxes for recognized faces, red for unknown.
 */
function BoundingBoxOverlay({ cameraId, videoRef, enabled = true }) {
  const canvasRef = useRef(null);
  const animFrameRef = useRef(null);
  const detectionsRef = useRef(null);

  const detections = useDetectionSocket(cameraId, enabled);

  // Store latest detections in ref to avoid re-render loops
  useEffect(() => {
    detectionsRef.current = detections;
  }, [detections]);

  const drawOverlay = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef?.current;
    if (!canvas || !video) return;

    const ctx = canvas.getContext('2d');
    const videoRect = video.getBoundingClientRect();

    // Match canvas size to video element
    canvas.width = videoRect.width;
    canvas.height = videoRect.height;

    // Clear previous frame
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const data = detectionsRef.current;
    if (!data || !data.faces || !data.frame_width || !data.frame_height) {
      animFrameRef.current = requestAnimationFrame(drawOverlay);
      return;
    }

    const scaleX = canvas.width / data.frame_width;
    const scaleY = canvas.height / data.frame_height;

    for (const face of data.faces) {
      const [x1, y1, x2, y2] = face.bbox;
      const sx = x1 * scaleX;
      const sy = y1 * scaleY;
      const sw = (x2 - x1) * scaleX;
      const sh = (y2 - y1) * scaleY;

      const isRecognized = face.name && face.name !== 'Unknown';
      const color = isRecognized ? '#00ff00' : '#ff0000';
      const confidence = face.confidence ? `${(face.confidence * 100).toFixed(0)}%` : '';
      const label = isRecognized ? `${face.name} ${confidence}` : `Unknown ${confidence}`;

      // Draw bounding box
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(sx, sy, sw, sh);

      // Draw corner brackets for style
      const cornerLen = Math.min(sw, sh) * 0.15;
      ctx.lineWidth = 3;

      // Top-left corner
      ctx.beginPath();
      ctx.moveTo(sx, sy + cornerLen);
      ctx.lineTo(sx, sy);
      ctx.lineTo(sx + cornerLen, sy);
      ctx.stroke();

      // Top-right corner
      ctx.beginPath();
      ctx.moveTo(sx + sw - cornerLen, sy);
      ctx.lineTo(sx + sw, sy);
      ctx.lineTo(sx + sw, sy + cornerLen);
      ctx.stroke();

      // Bottom-left corner
      ctx.beginPath();
      ctx.moveTo(sx, sy + sh - cornerLen);
      ctx.lineTo(sx, sy + sh);
      ctx.lineTo(sx + cornerLen, sy + sh);
      ctx.stroke();

      // Bottom-right corner
      ctx.beginPath();
      ctx.moveTo(sx + sw - cornerLen, sy + sh);
      ctx.lineTo(sx + sw, sy + sh);
      ctx.lineTo(sx + sw, sy + sh - cornerLen);
      ctx.stroke();

      // Draw label background
      ctx.font = '13px Arial, sans-serif';
      const textWidth = ctx.measureText(label).width;
      const labelY = sy > 24 ? sy - 6 : sy + sh + 18;
      const bgY = labelY - 14;

      ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
      ctx.fillRect(sx, bgY, textWidth + 10, 20);

      // Draw label text
      ctx.fillStyle = color;
      ctx.fillText(label, sx + 5, labelY);
    }

    animFrameRef.current = requestAnimationFrame(drawOverlay);
  }, [videoRef]);

  useEffect(() => {
    if (enabled) {
      animFrameRef.current = requestAnimationFrame(drawOverlay);
    }
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [enabled, drawOverlay]);

  if (!enabled) return null;

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 10,
      }}
    />
  );
}

export default BoundingBoxOverlay;
