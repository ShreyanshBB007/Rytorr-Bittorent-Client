/**
 * RyTorr Web UI - Frontend JavaScript
 */

// State
let ws = null;
let torrents = {};
let selectedFile = null;
let selectedTorrentId = null;

// WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'update') {
            updateUI(data);
        } else if (data.type === 'torrent_added') {
            console.log('Torrent added:', data.id);
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Update UI with new data
function updateUI(data) {
    // Update global stats
    document.getElementById('global-download').textContent = formatSpeed(data.global_stats.total_download_speed);
    document.getElementById('global-upload').textContent = formatSpeed(data.global_stats.total_upload_speed);
    document.getElementById('active-count').textContent = data.global_stats.active_torrents;

    // Update torrents
    torrents = {};
    data.torrents.forEach(t => {
        torrents[t.id] = t;
    });

    renderTorrentList(data.torrents);

    // Update details modal if open
    if (selectedTorrentId && torrents[selectedTorrentId]) {
        updateDetailsModal(torrents[selectedTorrentId]);
    }
}

// Render torrent list
function renderTorrentList(torrentList) {
    const container = document.getElementById('torrent-list');
    const emptyState = document.getElementById('empty-state');

    if (torrentList.length === 0) {
        // Show empty state
        if (!document.getElementById('empty-state')) {
            container.innerHTML = `
                <div class="empty-state" id="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    <h3>No torrents yet</h3>
                    <p>Add a .torrent file to start downloading</p>
                    <button class="btn btn-primary" onclick="openAddModal()">Add Torrent</button>
                </div>
            `;
        } else {
            emptyState.style.display = 'flex';
        }
        return;
    }

    // Hide empty state and show torrent cards
    const html = torrentList.map(t => createTorrentCard(t)).join('');
    container.innerHTML = html;
}

// Create torrent card HTML
function createTorrentCard(torrent) {
    const progressClass = getProgressClass(torrent.status);
    const statusClass = torrent.status;

    // Determine which control button to show
    let controlButton = '';
    if (torrent.status === 'downloading' || torrent.status === 'queued') {
        controlButton = `
            <button class="btn-icon" onclick="pauseTorrent('${torrent.id}')" title="Pause">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="6" y="4" width="4" height="16"></rect>
                    <rect x="14" y="4" width="4" height="16"></rect>
                </svg>
            </button>
        `;
    } else if (torrent.status === 'paused' || torrent.status === 'error') {
        controlButton = `
            <button class="btn-icon" onclick="resumeTorrent('${torrent.id}')" title="Resume">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
            </button>
        `;
    }

    return `
        <div class="torrent-card" onclick="showDetails('${torrent.id}')">
            <div class="torrent-header">
                <div class="torrent-info">
                    <div class="torrent-name">${escapeHtml(torrent.name)}</div>
                    <div class="torrent-meta">
                        <span>${formatSize(torrent.size)}</span>
                        <span class="status-badge ${statusClass}">${torrent.status}</span>
                    </div>
                </div>
                <div class="torrent-actions" onclick="event.stopPropagation()">
                    ${controlButton}
                    <button class="btn-icon" onclick="removeTorrent('${torrent.id}')" title="Remove">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="torrent-progress">
                <div class="progress-bar">
                    <div class="progress-fill ${progressClass}" style="width: ${torrent.progress}%"></div>
                </div>
            </div>
            <div class="torrent-stats">
                <div class="torrent-stat">
                    <span>${torrent.progress.toFixed(1)}%</span>
                </div>
                <div class="torrent-stat download">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    <span>${formatSpeed(torrent.download_speed)}</span>
                </div>
                <div class="torrent-stat upload">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="17 14 12 9 7 14"></polyline>
                        <line x1="12" y1="9" x2="12" y2="21"></line>
                    </svg>
                    <span>${formatSpeed(torrent.upload_speed)}</span>
                </div>
                <div class="torrent-stat">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                    </svg>
                    <span>${torrent.peers_connected} peers</span>
                </div>
                ${torrent.eta_seconds > 0 ? `
                    <div class="torrent-stat">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        <span>${formatETA(torrent.eta_seconds)}</span>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
}

// Get progress bar class based on status
function getProgressClass(status) {
    switch (status) {
        case 'completed': return 'completed';
        case 'paused': return 'paused';
        case 'error': return 'error';
        default: return '';
    }
}

// Format file size
function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Format speed
function formatSpeed(bytesPerSecond) {
    if (bytesPerSecond === 0) return '0 B/s';
    return formatSize(bytesPerSecond) + '/s';
}

// Format ETA
function formatETA(seconds) {
    if (seconds <= 0) return '∞';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Modal functions
function openAddModal() {
    document.getElementById('add-modal').classList.add('active');
    clearSelectedFile();
}

function closeAddModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('add-modal').classList.remove('active');
    clearSelectedFile();
}

function showDetails(torrentId) {
    selectedTorrentId = torrentId;
    const torrent = torrents[torrentId];
    if (!torrent) return;

    updateDetailsModal(torrent);
    document.getElementById('details-modal').classList.add('active');
}

function updateDetailsModal(torrent) {
    document.getElementById('details-name').textContent = torrent.name;

    // Info tab
    document.getElementById('details-info').innerHTML = `
        <div class="info-item">
            <span class="info-label">Status</span>
            <span class="info-value">${torrent.status}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Progress</span>
            <span class="info-value">${torrent.progress.toFixed(2)}%</span>
        </div>
        <div class="info-item">
            <span class="info-label">Size</span>
            <span class="info-value">${formatSize(torrent.size)}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Downloaded</span>
            <span class="info-value">${formatSize(torrent.downloaded_bytes)}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Download Speed</span>
            <span class="info-value">${formatSpeed(torrent.download_speed)}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Upload Speed</span>
            <span class="info-value">${formatSpeed(torrent.upload_speed)}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Peers</span>
            <span class="info-value">${torrent.peers_connected}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Pieces</span>
            <span class="info-value">${torrent.pieces_completed} / ${torrent.pieces_total}</span>
        </div>
    `;

    // Files tab
    const filesHtml = torrent.files.map(f => `
        <div class="file-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
            </svg>
            <div class="file-info">
                <div class="file-name">${escapeHtml(f.path)}</div>
                <div class="file-size">${formatSize(f.size)}</div>
            </div>
        </div>
    `).join('');
    document.getElementById('details-files').innerHTML = filesHtml || '<p>No files</p>';

    // Peers tab
    const peersHtml = torrent.peers.length > 0 ? `
        <table>
            <thead>
                <tr>
                    <th>IP</th>
                    <th>Port</th>
                    <th>Pieces</th>
                </tr>
            </thead>
            <tbody>
                ${torrent.peers.map(p => `
                    <tr>
                        <td>${p.ip}</td>
                        <td>${p.port}</td>
                        <td>${p.pieces_have} / ${p.total_pieces}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    ` : '<p>No connected peers</p>';
    document.getElementById('details-peers').innerHTML = peersHtml;
}

function closeDetailsModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('details-modal').classList.remove('active');
    selectedTorrentId = null;
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.textContent.toLowerCase() === tabName) {
            tab.classList.add('active');
        }
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.style.display = 'none';
    });
    document.getElementById(`tab-${tabName}`).style.display = 'block';
}

// File upload handling
function handleDragOver(event) {
    event.preventDefault();
    document.getElementById('upload-zone').classList.add('dragover');
}

function handleDragLeave(event) {
    event.preventDefault();
    document.getElementById('upload-zone').classList.remove('dragover');
}

function handleDrop(event) {
    event.preventDefault();
    document.getElementById('upload-zone').classList.remove('dragover');

    const files = event.dataTransfer.files;
    if (files.length > 0 && files[0].name.endsWith('.torrent')) {
        selectFile(files[0]);
    }
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (files.length > 0) {
        selectFile(files[0]);
    }
}

function selectFile(file) {
    selectedFile = file;
    document.getElementById('upload-zone').style.display = 'none';
    document.getElementById('selected-file').style.display = 'flex';
    document.getElementById('selected-file-name').textContent = file.name;
    document.getElementById('start-download-btn').disabled = false;
}

function clearSelectedFile() {
    selectedFile = null;
    document.getElementById('upload-zone').style.display = 'flex';
    document.getElementById('selected-file').style.display = 'none';
    document.getElementById('selected-file-name').textContent = '';
    document.getElementById('start-download-btn').disabled = true;
}

// Torrent actions
async function startDownload() {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            closeAddModal();
        } else {
            const error = await response.json();
            alert('Error: ' + (error.detail || 'Upload failed'));
        }
    } catch (error) {
        console.error('Upload error:', error);
        alert('Failed to upload torrent file');
    }
}

function pauseTorrent(id) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'pause', id }));
    }
}

function resumeTorrent(id) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'resume', id }));
    }
}

function removeTorrent(id) {
    if (confirm('Are you sure you want to remove this torrent?')) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'remove', id }));
        }
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
});

// Close modals on Escape key
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeAddModal();
        closeDetailsModal();
    }
});
