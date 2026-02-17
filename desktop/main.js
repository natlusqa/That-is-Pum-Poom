const { app, BrowserWindow, ipcMain, Tray, Menu, screen, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow = null;
let tray = null;
const isDev = process.env.NODE_ENV !== 'production' || !app.isPackaged;

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width,
    height,
    x: 0,
    y: 0,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    movable: false,
    fullscreen: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'tray-icon.png');
  const icon = fs.existsSync(iconPath) ? iconPath : nativeImage.createEmpty();
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show', click: () => mainWindow?.show() },
    { label: 'Hide', click: () => mainWindow?.hide() },
    { type: 'separator' },
    {
      label: 'Autonomy Level',
      submenu: [
        { label: 'Manual', click: () => sendToRenderer('set-autonomy', 'manual') },
        { label: 'Suggestion', click: () => sendToRenderer('set-autonomy', 'suggestion') },
        { label: 'Conditional', click: () => sendToRenderer('set-autonomy', 'conditional') },
        { label: 'Full Autonomous', click: () => sendToRenderer('set-autonomy', 'full') },
      ],
    },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ]);

  tray.setToolTip('KORGAN AI Desktop');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data);
  }
}

app.whenReady().then(() => {
  createWindow();
  try {
    createTray();
  } catch {
    // Tray creation may fail on some systems
  }

  app.dock?.hide?.();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

ipcMain.on('set-click-through', (_, enabled) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setIgnoreMouseEvents(enabled, { forward: true });
  }
});

ipcMain.on('set-autonomy-level', (_, level) => {
  sendToRenderer('autonomy-changed', level);
});

ipcMain.on('get-status', (event) => {
  event.reply('status-reply', { status: 'idle', autonomy: 'suggestion' });
});
