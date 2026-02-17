const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('korgan', {
  sendMessage: (channel, data) => {
    const validChannels = [
      'set-click-through',
      'set-autonomy-level',
      'get-status',
      'status-change',
      'response',
    ];
    if (validChannels.includes(channel)) {
      ipcRenderer.send(channel, data);
    }
  },

  onStatusChange: (callback) => {
    ipcRenderer.on('status-change', (_, data) => callback(data));
  },

  onResponse: (callback) => {
    ipcRenderer.on('response', (_, data) => callback(data));
  },

  onAutonomyChanged: (callback) => {
    ipcRenderer.on('autonomy-changed', (_, level) => callback(level));
  },

  getStatus: () => {
    ipcRenderer.send('get-status');
    return new Promise((resolve) => {
      ipcRenderer.once('status-reply', (_, data) => resolve(data));
    });
  },

  setAutonomyLevel: (level) => {
    ipcRenderer.send('set-autonomy-level', level);
  },
});
