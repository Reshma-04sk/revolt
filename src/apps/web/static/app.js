/**
 * ReVolt — AI-Powered Lithium-Ion Battery Management Platform
 * Modern Vanilla JavaScript Frontend Controller
 */

// Application State
const state = {
  batteries: [],
  facilities: [],
  overview: null,
  analytics: null,
  activeView: 'overview',
  selectedBatteryId: null,
  map: null,
  mapMarkers: [],
  smartscanPresets: {},
  smartscanPhotoDataUrl: null,
  smartscanPhotoFile: null,
};

// DOM Content Loaded
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initModals();
  initSmartScan();
  initTelemetryLab();
  initAssessment();
  initPassport();
  initFacilities();

  // Initial Data Load
  loadAllData();
});

// Toast Notification
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'error' ? 'toast-error' : ''}`;
  toast.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      ${type === 'error'
        ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>'
        : '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'
      }
    </svg>
    <span>${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

// Navigation Handler
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const viewHeaders = {
    overview: { title: 'Executive Overview', subtitle: 'End-to-end lithium-ion battery lifecycle, safety triage & circular routing' },
    registry: { title: 'Battery Asset Registry', subtitle: 'Search, filter, and inspect registered battery packs across all circular stages' },
    smartscan: { title: 'SmartScan OCR Studio', subtitle: 'Extract technical specifications from battery labels with field provenance tracking' },
    'telemetry-lab': { title: 'Mock Telemetry Lab', subtitle: 'Virtual workbench multimeter probes and discharge cycler testing bench' },
    assessment: { title: 'Diagnostic Assessment Engine', subtitle: 'Explainable deterministic evaluation with chemistry-specific safety operating limits' },
    facilities: { title: 'Authorized Facility Directory & Map', subtitle: 'Discover certified hydrometallurgical recyclers, second-life labs, and quarantine depots' },
    passport: { title: 'Digital Battery Passport', subtitle: 'Traceable circular asset passport with tamper-evident lifecycle audit history' },
    analytics: { title: 'Quantified Impact Analytics', subtitle: 'Avoided CO₂ emissions, critical mineral extraction yields, and landfill diversion' },
  };

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const viewId = item.getAttribute('data-view');
      switchView(viewId);
    });
  });
}

function switchView(viewId, batteryIdToSelect = null) {
  state.activeView = viewId;

  // Update Nav
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-view') === viewId);
  });

  // Update Sections
  document.querySelectorAll('.view-section').forEach(sec => {
    sec.classList.remove('active');
  });
  const targetSection = document.getElementById(`view-${viewId}`);
  if (targetSection) targetSection.classList.add('active');

  // Update Header Title
  const headers = {
    overview: { title: 'Executive Overview', subtitle: 'End-to-end lithium-ion battery lifecycle, safety triage & circular routing' },
    registry: { title: 'Battery Asset Registry', subtitle: 'Search, filter, and inspect registered battery packs across all circular stages' },
    smartscan: { title: 'SmartScan OCR Studio', subtitle: 'Extract technical specifications from battery labels with field provenance tracking' },
    'telemetry-lab': { title: 'Mock Telemetry Lab', subtitle: 'Virtual workbench multimeter probes and discharge cycler testing bench' },
    assessment: { title: 'Diagnostic Assessment Engine', subtitle: 'Explainable deterministic evaluation with chemistry-specific safety operating limits' },
    facilities: { title: 'Authorized Facility Directory & Map', subtitle: 'Discover certified hydrometallurgical recyclers, second-life labs, and quarantine depots' },
    passport: { title: 'Digital Battery Passport', subtitle: 'Traceable circular asset passport with tamper-evident lifecycle audit history' },
    analytics: { title: 'Quantified Impact Analytics', subtitle: 'Avoided CO₂ emissions, critical mineral extraction yields, and landfill diversion' },
  };
  const headerInfo = headers[viewId] || { title: 'ReVolt Platform', subtitle: 'Battery Lifecycle Intelligence' };
  document.getElementById('headerPageTitle').textContent = headerInfo.title;
  document.getElementById('headerPageSubtitle').textContent = headerInfo.subtitle;

  // View specific activations
  if (viewId === 'facilities') {
    setTimeout(renderFacilityMap, 100);
  } else if (viewId === 'telemetry-lab') {
    populateBatterySelectors();
    if (batteryIdToSelect) {
      document.getElementById('telemetryBatterySelect').value = batteryIdToSelect;
      loadBatteryIntoBench(batteryIdToSelect);
    }
  } else if (viewId === 'assessment') {
    populateBatterySelectors();
    if (batteryIdToSelect) {
      document.getElementById('assessmentBatterySelect').value = batteryIdToSelect;
      renderAssessmentForBattery(batteryIdToSelect);
    }
  } else if (viewId === 'passport') {
    populateBatterySelectors();
    const targetId = batteryIdToSelect || document.getElementById('passportBatterySelect').value || (state.batteries.length > 0 ? state.batteries[0].id : null);
    if (targetId) {
      document.getElementById('passportBatterySelect').value = targetId;
      renderPassportForBattery(targetId);
    }
  }
}

// Master Data Fetching
async function loadAllData() {
  try {
    const [overviewRes, batteriesRes, facilitiesRes, analyticsRes] = await Promise.all([
      fetch('/api/v1/revolt/overview').then(r => r.json()),
      fetch('/api/v1/revolt/batteries').then(r => r.json()),
      fetch('/api/v1/revolt/facilities').then(r => r.json()),
      fetch('/api/v1/revolt/analytics').then(r => r.json()),
    ]);

    state.overview = overviewRes;
    state.batteries = batteriesRes;
    state.facilities = facilitiesRes;
    state.analytics = analyticsRes;

    document.getElementById('navBatteryCount').textContent = batteriesRes.length;

    renderOverview();
    renderRegistry();
    populateBatterySelectors();
    renderAnalytics();
    renderFacilities();
  } catch (err) {
    console.error('Failed to load platform data:', err);
    showToast('Failed to connect to ReVolt API server', 'error');
  }
}

// 1. OVERVIEW RENDERING
function renderOverview() {
  if (!state.overview) return;
  const { kpis, pathway_distribution, safety_alert, recent_activities } = state.overview;

  // KPIs
  document.getElementById('kpiTotal').textContent = kpis.total_registered;
  document.getElementById('kpiAssessed').textContent = kpis.total_assessed;
  document.getElementById('kpiAwaiting').textContent = kpis.awaiting_collection;
  document.getElementById('kpiCO2').textContent = kpis.co2_avoided_kg.toLocaleString();

  // Pathways
  document.getElementById('countReuse').textContent = pathway_distribution.reuse;
  document.getElementById('countRefurbish').textContent = pathway_distribution.refurbish;
  document.getElementById('countRecycle').textContent = pathway_distribution.recycle;
  document.getElementById('countHazardous').textContent = pathway_distribution.hazardous;

  // Hero Lifecycle Overview Chart & Metrics
  const totalTriaged = (pathway_distribution.reuse || 0) +
                       (pathway_distribution.refurbish || 0) +
                       (pathway_distribution.recycle || 0) +
                       (pathway_distribution.hazardous || 0);

  const reusePct = totalTriaged > 0 ? Math.round(((pathway_distribution.reuse || 0) / totalTriaged) * 100) : 25;
  const refurbishPct = totalTriaged > 0 ? Math.round(((pathway_distribution.refurbish || 0) / totalTriaged) * 100) : 25;
  const recyclePct = totalTriaged > 0 ? Math.round(((pathway_distribution.recycle || 0) / totalTriaged) * 100) : 25;
  const hazPct = totalTriaged > 0 ? Math.max(0, 100 - reusePct - refurbishPct - recyclePct) : 25;

  const segReuse = document.getElementById('barSegReuse');
  if (segReuse) segReuse.style.width = `${reusePct}%`;
  const segRefurb = document.getElementById('barSegRefurbish');
  if (segRefurb) segRefurb.style.width = `${refurbishPct}%`;
  const segRecycle = document.getElementById('barSegRecycle');
  if (segRecycle) segRecycle.style.width = `${recyclePct}%`;
  const segHaz = document.getElementById('barSegHazardous');
  if (segHaz) segHaz.style.width = `${hazPct}%`;

  const legReuse = document.getElementById('heroLegendReuse');
  if (legReuse) legReuse.textContent = pathway_distribution.reuse || 0;
  const legRefurb = document.getElementById('heroLegendRefurbish');
  if (legRefurb) legRefurb.textContent = pathway_distribution.refurbish || 0;
  const legRecycle = document.getElementById('heroLegendRecycle');
  if (legRecycle) legRecycle.textContent = pathway_distribution.recycle || 0;
  const legHaz = document.getElementById('heroLegendHazardous');
  if (legHaz) legHaz.textContent = pathway_distribution.hazardous || 0;

  const circPct = document.getElementById('heroCircularityPct');
  if (circPct) {
    if (totalTriaged > 0) {
      const safeCircular = ((pathway_distribution.reuse || 0) + (pathway_distribution.refurbish || 0) + (pathway_distribution.recycle || 0));
      const pct = Math.round((safeCircular / totalTriaged) * 100);
      circPct.textContent = `${pct}% Circular Rate`;
    } else {
      circPct.textContent = 'Verified Triage';
    }
  }

  // Hero Interactive Buttons
  const btnScan = document.getElementById('heroBtnScanBattery');
  if (btnScan && !btnScan._bound) {
    btnScan._bound = true;
    btnScan.addEventListener('click', () => switchView('smartscan'));
  }
  const btnReg = document.getElementById('heroBtnRegisterBattery');
  if (btnReg && !btnReg._bound) {
    btnReg._bound = true;
    btnReg.addEventListener('click', () => {
      document.getElementById('registerModal').classList.add('active');
    });
  }

  // Optional Alert Container (if present in custom views)
  const alertContainer = document.getElementById('overviewAlertContainer');
  if (alertContainer) {
    if (safety_alert && safety_alert.has_critical_hazards && safety_alert.quarantined_batteries && safety_alert.quarantined_batteries.length > 0) {
      const haz = safety_alert.quarantined_batteries[0];
      const isSimulated = Boolean(haz.is_simulated);
      const countBreakdown = (safety_alert.simulated_count > 0 && safety_alert.genuine_count > 0)
        ? ` <span style="font-size: 0.8rem; font-weight: 500; opacity: 0.85;">(${safety_alert.genuine_count} Genuine, ${safety_alert.simulated_count} Simulated)</span>`
        : '';

      if (isSimulated) {
        alertContainer.innerHTML = `
          <div class="alert-banner alert-warning" id="safetyAlertBanner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
            <div class="alert-content">
              <h4>
                SAFETY ALERT [SIMULATED DATA]: ${safety_alert.quarantined_count} Quarantined Unit(s)${countBreakdown}
                <span class="badge" style="background: rgba(245, 158, 11, 0.25); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.5); font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; margin-left: 0.5rem; vertical-align: middle;">SIMULATED TELEMETRY</span>
              </h4>
              <p>Battery <strong style="cursor: pointer; text-decoration: underline;" onclick="switchView('passport', '${haz.id}')">${haz.id} (${haz.name})</strong> has triggered safety quarantine based on simulated test bench data (Field Provenance: SIMULATED): ${haz.warnings.join(' ')} <em>(Simulated telemetry — virtual test protocol active).</em></p>
            </div>
          </div>
        `;
      } else {
        alertContainer.innerHTML = `
          <div class="alert-banner" id="safetyAlertBanner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
            <div class="alert-content">
              <h4>
                CRITICAL SAFETY ALERT: ${safety_alert.quarantined_count} Quarantined Unit(s) Requiring Physical Isolation${countBreakdown}
                <span class="badge" style="background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.5); font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; margin-left: 0.5rem; vertical-align: middle;">GENUINE HAZARD</span>
              </h4>
              <p>Battery <strong style="cursor: pointer; text-decoration: underline;" onclick="switchView('passport', '${haz.id}')">${haz.id} (${haz.name})</strong> has triggered immediate safety quarantine (Status: ${haz.status}): ${haz.warnings.join(' ')} Place in non-flammable sand container and route via UN 3480 Hazmat transport only.</p>
            </div>
          </div>
        `;
      }
    } else {
      alertContainer.innerHTML = '';
    }
  }

  // Recent Activity Stream
  const streamContainer = document.getElementById('overviewActivityStream');
  if (!recent_activities || recent_activities.length === 0) {
    streamContainer.innerHTML = '<p style="color: var(--text-dim); padding: 1rem 0;">No recorded lifecycle events.</p>';
    return;
  }

  streamContainer.innerHTML = recent_activities.map(act => {
    const timeFormatted = new Date(act.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `
      <div class="timeline-item">
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <div class="timeline-header">
            <span class="timeline-title">${act.title} — <strong style="color: var(--cyan-400);">${act.battery_id}</strong> (${act.battery_name})</span>
            <span class="timeline-time">${timeFormatted}</span>
          </div>
          <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.25rem;">${act.description}</p>
          <span class="timeline-actor">Actor: ${act.actor}</span>
        </div>
      </div>
    `;
  }).join('');
}

// 2. BATTERY REGISTRY RENDERING
function renderRegistry() {
  const tbody = document.getElementById('registryTableBody');
  const search = document.getElementById('registrySearch').value.toLowerCase().trim();
  const pathwayFilter = document.getElementById('registryFilterPathway').value;
  const chemFilter = document.getElementById('registryFilterChemistry').value;
  const statusFilter = document.getElementById('registryFilterStatus').value;

  const filtered = state.batteries.filter(b => {
    if (search) {
      const match = b.id.toLowerCase().includes(search) ||
                    b.name.toLowerCase().includes(search) ||
                    (b.device_model && b.device_model.toLowerCase().includes(search)) ||
                    (b.owner_notes && b.owner_notes.toLowerCase().includes(search));
      if (!match) return false;
    }
    if (pathwayFilter && b.recommended_pathway !== pathwayFilter) return false;
    if (chemFilter && b.chemistry !== chemFilter) return false;
    if (statusFilter && b.status !== statusFilter) return false;
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 2.5rem 0;">No batteries matching selected filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(b => {
    const soh = b.assessment && b.assessment.soh_percentage !== null
      ? `<span style="font-weight: 700; color: ${b.assessment.soh_percentage >= 75 ? 'var(--emerald-400)' : b.assessment.soh_percentage >= 60 ? 'var(--cyan-400)' : 'var(--amber-400)'};">${b.assessment.soh_percentage}%</span>`
      : '<span style="color: var(--text-dim);">Unmeasured</span>';

    const voltCap = `${b.measured_voltage_v ? b.measured_voltage_v.toFixed(1) + 'V' : b.nominal_voltage_v + 'V (nom)'} / ${(b.measured_capacity_mah || b.rated_capacity_mah).toFixed(0)} mAh`;

    const pathwayBadgeClass = {
      REUSE: 'badge-reuse',
      REFURBISH: 'badge-refurbish',
      RECYCLE: 'badge-recycle',
      HAZARDOUS: 'badge-hazardous',
      PENDING_VERIFICATION: 'badge-pending',
      PENDING: 'badge-status',
    }[b.recommended_pathway] || 'badge-status';

    return `
      <tr>
        <td style="font-family: var(--font-mono); font-weight: 600; color: var(--cyan-400);">${b.id}</td>
        <td>
          <div style="font-weight: 600;">${b.name}</div>
          <div style="font-size: 0.75rem; color: var(--text-dim);">${b.device_model || 'Standard Module'}</div>
        </td>
        <td><span class="badge badge-status">${b.chemistry}</span></td>
        <td style="color: var(--text-muted);">${b.original_application}</td>
        <td>${soh}</td>
        <td style="font-family: var(--font-mono); font-size: 0.78rem;">${voltCap}</td>
        <td><span class="badge badge-status">${b.status}</span></td>
        <td><span class="badge ${pathwayBadgeClass}">${b.recommended_pathway}</span></td>
        <td>
          <div style="display: flex; gap: 0.35rem;">
            <button class="btn btn-outline btn-sm" onclick="viewBatteryPassport('${b.id}')" title="View Digital Passport">Passport</button>
            <button class="btn btn-outline btn-sm" onclick="openInTelemetryBench('${b.id}')" title="Test on Workbench">Bench</button>
            <button class="btn btn-outline btn-sm" onclick="runAssessmentFor('${b.id}')" title="Run Assessment">Assess</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// Registry Filter Listeners
document.getElementById('registrySearch').addEventListener('input', renderRegistry);
document.getElementById('registryFilterPathway').addEventListener('change', renderRegistry);
document.getElementById('registryFilterChemistry').addEventListener('change', renderRegistry);
document.getElementById('registryFilterStatus').addEventListener('change', renderRegistry);

// Quick Action Helpers
window.viewBatteryPassport = function(id) {
  switchView('passport', id);
};

window.openInTelemetryBench = function(id) {
  switchView('telemetry-lab', id);
};

window.runAssessmentFor = async function(id) {
  try {
    const res = await fetch(`/api/v1/revolt/batteries/${id}/assess`, { method: 'POST' });
    if (!res.ok) throw new Error('Assessment failed');
    const updated = await res.json();
    showToast(`Assessment complete for ${updated.id}: ${updated.recommended_pathway}`);
    await loadAllData();
    switchView('assessment', id);
  } catch (err) {
    showToast('Failed to run battery assessment', 'error');
  }
};

// 3. SMARTSCAN INITIALIZATION
async function initSmartScan() {
  try {
    const presets = await fetch('/api/v1/revolt/smartscan/presets').then(r => r.json());
    state.smartscanPresets = presets;

    const pillsContainer = document.getElementById('smartscanPresetPills');
    pillsContainer.innerHTML = Object.entries(presets).map(([key, item]) => `
      <div class="preset-pill" data-preset="${key}">
        ${item.title}
      </div>
    `).join('');

    pillsContainer.querySelectorAll('.preset-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        pillsContainer.querySelectorAll('.preset-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        const key = pill.getAttribute('data-preset');
        const preset = state.smartscanPresets[key];
        if (preset) {
          document.getElementById('smartscanRawText').value = preset.raw_text;
          executeSmartScanOCR(preset.raw_text);
        }
      });
    });

    // Image Upload & Camera Control
    const fileInput = document.getElementById('smartscanFileInput');
    const btnUpload = document.getElementById('btnUploadLabelPhoto');
    const btnReplace = document.getElementById('btnReplacePhoto');
    const btnRemove = document.getElementById('btnRemovePhoto');

    if (btnUpload && fileInput) {
      btnUpload.addEventListener('click', () => fileInput.click());
    }
    if (btnReplace && fileInput) {
      btnReplace.addEventListener('click', () => fileInput.click());
    }
    if (btnRemove) {
      btnRemove.addEventListener('click', removeSmartScanPhoto);
    }
    if (fileInput) {
      fileInput.addEventListener('change', handleSmartScanFileSelect);
    }

    document.getElementById('btnRunOCR').addEventListener('click', () => {
      const text = document.getElementById('smartscanRawText').value;
      if (!text.trim()) {
        showToast('Please enter or paste label text to scan', 'error');
        return;
      }
      executeSmartScanOCR(text);
    });

    document.getElementById('btnRegisterFromScan').addEventListener('click', registerFromSmartScan);
  } catch (err) {
    console.error('Failed to init SmartScan presets:', err);
  }
}

function handleSmartScanFileSelect(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;

  if (!file.type.startsWith('image/')) {
    showToast('Please select a valid image file (PNG, JPG, WebP)', 'error');
    return;
  }

  state.smartscanPhotoFile = file;

  const reader = new FileReader();
  reader.onload = async (evt) => {
    const dataUrl = evt.target.result;
    state.smartscanPhotoDataUrl = dataUrl;

    const previewContainer = document.getElementById('smartscanImagePreviewContainer');
    const previewImg = document.getElementById('smartscanImagePreview');
    const nameEl = document.getElementById('smartscanImageName');
    const metaEl = document.getElementById('smartscanImageMeta');
    const statusEl = document.getElementById('smartscanOcrStatus');

    if (previewImg) previewImg.src = dataUrl;
    if (nameEl) nameEl.textContent = file.name;
    if (metaEl) {
      const sizeKb = Math.round(file.size / 1024);
      metaEl.textContent = `${file.type || 'image'} • ${sizeKb} KB`;
    }
    if (previewContainer) previewContainer.style.display = 'block';

    // Perform OCR recognition
    await runImageOCR(file, statusEl);
  };
  reader.readAsDataURL(file);
}

async function runImageOCR(file, statusEl) {
  if (!statusEl) return;
  statusEl.style.display = 'block';
  statusEl.style.color = 'var(--cyan-400)';

  if (typeof Tesseract === 'undefined') {
    statusEl.textContent = 'Photo attached and previewed. Optical character recognition engine is not loaded in this environment. Please paste or type the battery label text in the box below to extract specifications.';
    statusEl.style.color = 'var(--amber-400)';
    const rawArea = document.getElementById('smartscanRawText');
    if (rawArea) rawArea.focus();
    return;
  }

  statusEl.textContent = 'Initializing optical character recognition (OCR)...';

  try {
    const res = await Tesseract.recognize(file, 'eng', {
      logger: m => {
        if (m.status === 'recognizing text' && m.progress !== undefined) {
          statusEl.textContent = `Scanning label text: ${Math.round(m.progress * 100)}%`;
        }
      }
    });

    const recognizedText = res && res.data && res.data.text ? res.data.text.trim() : '';

    if (recognizedText.length > 0) {
      statusEl.textContent = 'Label text successfully extracted via OCR! Review specs below.';
      statusEl.style.color = 'var(--emerald-400)';
      document.getElementById('smartscanRawText').value = recognizedText;
      // Feed directly into existing SmartScan parsing flow
      await executeSmartScanOCR(recognizedText);
      showToast('Label text extracted via OCR and parsed');
    } else {
      // Do not pretend OCR succeeded if no image text was recognized
      statusEl.textContent = 'No readable text was detected from this image. Please ensure the label is clearly lit and legible, or paste/type the label text below.';
      statusEl.style.color = 'var(--amber-400)';
      showToast('No readable text detected. Please enter label text manually.', 'warning');
      const rawArea = document.getElementById('smartscanRawText');
      if (rawArea) rawArea.focus();
    }
  } catch (err) {
    console.warn('Tesseract OCR error:', err);
    statusEl.textContent = 'OCR processing was unable to read this image. Please paste or type the label text in the box below.';
    statusEl.style.color = 'var(--amber-400)';
    showToast('OCR could not read image. Please enter label text manually.', 'warning');
    const rawArea = document.getElementById('smartscanRawText');
    if (rawArea) rawArea.focus();
  }
}

function removeSmartScanPhoto() {
  state.smartscanPhotoFile = null;
  state.smartscanPhotoDataUrl = null;
  const input = document.getElementById('smartscanFileInput');
  if (input) input.value = '';
  const previewContainer = document.getElementById('smartscanImagePreviewContainer');
  if (previewContainer) previewContainer.style.display = 'none';
  const statusEl = document.getElementById('smartscanOcrStatus');
  if (statusEl) statusEl.style.display = 'none';
  showToast('Label photo removed');
}

async function executeSmartScanOCR(rawText) {
  try {
    const res = await fetch('/api/v1/revolt/smartscan/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText }),
    });
    const parsed = await res.json();

    document.getElementById('smartscanResultsEmpty').style.display = 'none';
    document.getElementById('smartscanResultsContent').style.display = 'block';

    const fields = parsed.extracted_fields;
    document.getElementById('scanExtModel').value = fields.model;
    document.getElementById('scanExtChem').value = fields.chemistry;
    document.getElementById('scanExtApp').value = fields.original_application;
    document.getElementById('scanExtCap').value = fields.rated_capacity_mah;
    document.getElementById('scanExtVolt').value = fields.nominal_voltage_v;

    showToast('Specifications extracted via SmartScan OCR');
  } catch (err) {
    showToast('SmartScan parsing error', 'error');
  }
}

async function registerFromSmartScan() {
  const modelName = document.getElementById('scanExtModel').value;
  const payload = {
    name: modelName || 'Scanned Battery Pack',
    device_model: modelName,
    chemistry: document.getElementById('scanExtChem').value,
    original_application: document.getElementById('scanExtApp').value,
    rated_capacity_mah: parseFloat(document.getElementById('scanExtCap').value) || 5000,
    nominal_voltage_v: parseFloat(document.getElementById('scanExtVolt').value) || 18.0,
    age_months: 36,
    physical_condition: 'GOOD',
    owner_notes: 'Extracted via SmartScan OCR studio. Ready for bench testing.',
    ocr_raw_text: document.getElementById('smartscanRawText').value,
    photo_data_url: state.smartscanPhotoDataUrl || null,
  };

  try {
    const res = await fetch('/api/v1/revolt/batteries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Registration failed');
    const created = await res.json();
    showToast(`Registered ${created.id}. Opening in Telemetry Lab...`);
    await loadAllData();
    switchView('telemetry-lab', created.id);
  } catch (err) {
    showToast('Registration failed', 'error');
  }
}

// 4. MOCK TELEMETRY LAB INITIALIZATION
function initTelemetryLab() {
  const select = document.getElementById('telemetryBatterySelect');
  select.addEventListener('change', () => {
    const val = select.value;
    if (val) loadBatteryIntoBench(val);
  });

  const voltSlider = document.getElementById('benchVoltSlider');
  const capSlider = document.getElementById('benchCapSlider');

  voltSlider.addEventListener('input', updateBenchCalculations);
  capSlider.addEventListener('input', updateBenchCalculations);

  // Scenario Presets
  document.getElementById('btnPresetReuse').addEventListener('click', () => {
    applyBenchPreset(88, 52.4, 'GOOD', 'NORMAL', 'Healthy battery module candidate for second-life BESS.');
  });
  document.getElementById('btnPresetRefurbish').addEventListener('click', () => {
    applyBenchPreset(68, 48.0, 'CORRODED_TERMINALS', 'NORMAL', 'Terminal oxidation detected; cells sound.');
  });
  document.getElementById('btnPresetRecycle').addEventListener('click', () => {
    applyBenchPreset(45, 42.0, 'SCRATCHED', 'ELEVATED', 'End-of-life capacity; ready for hydrometallurgical recycling.');
  });
  document.getElementById('btnPresetHazard').addEventListener('click', () => {
    applyBenchPreset(30, 24.0, 'SWOLLEN_SEVERE', 'OVERHEATED', 'Critical bulging and severe undervoltage. Quarantine mandatory.');
  });

  // Inject Telemetry Button
  document.getElementById('btnInjectTelemetry').addEventListener('click', injectBenchTelemetry);
}

function loadBatteryIntoBench(batteryId) {
  const b = state.batteries.find(x => x.id === batteryId);
  if (!b) return;

  const benchArea = document.getElementById('benchWorkbenchArea');
  benchArea.style.opacity = '1';
  benchArea.style.pointerEvents = 'auto';

  document.getElementById('telemetrySelectedBanner').innerHTML = `
    <strong>Connected:</strong> ${b.id} — ${b.name} (${b.chemistry}, Rated ${b.rated_capacity_mah} mAh, ${b.nominal_voltage_v}V)
  `;

  // Calibrate Sliders
  const voltSlider = document.getElementById('benchVoltSlider');
  const capSlider = document.getElementById('benchCapSlider');

  voltSlider.max = Math.round(b.nominal_voltage_v * 1.35);
  voltSlider.min = 0;
  voltSlider.value = b.measured_voltage_v || b.nominal_voltage_v;

  capSlider.max = Math.round(b.rated_capacity_mah * 1.05);
  capSlider.min = 0;
  capSlider.value = b.measured_capacity_mah || Math.round(b.rated_capacity_mah * 0.80);

  document.getElementById('benchPhysical').value = b.physical_condition || 'GOOD';
  const validThermals = ['NORMAL', 'ELEVATED', 'OVERHEATED', 'EXTREME', 'UNKNOWN'];
  document.getElementById('benchThermal').value = validThermals.includes(b.temperature_history) ? b.temperature_history : 'NORMAL';

  updateBenchCalculations();
}

function updateBenchCalculations() {
  const select = document.getElementById('telemetryBatterySelect');
  const b = state.batteries.find(x => x.id === select.value);
  if (!b) return;

  const voltVal = parseFloat(document.getElementById('benchVoltSlider').value);
  const capVal = parseFloat(document.getElementById('benchCapSlider').value);

  document.getElementById('benchVoltDisplay').textContent = `${voltVal.toFixed(2)} V`;
  document.getElementById('benchCapDisplay').textContent = `${capVal.toFixed(0)} mAh`;
  document.getElementById('benchRatedRef').textContent = `Rated: ${b.rated_capacity_mah} mAh`;

  // Estimate series cell count
  const nomCell = b.chemistry === 'LFP' ? 3.2 : 3.7;
  const seriesCount = Math.max(1, Math.round(b.nominal_voltage_v / nomCell));
  const cellV = voltVal / seriesCount;
  document.getElementById('benchCellCalc').textContent = `~${cellV.toFixed(2)} V / cell (${seriesCount}S)`;

  // Cell status badge
  const cellStatus = document.getElementById('benchCellStatus');
  if (cellV <= (b.chemistry === 'LFP' ? 1.8 : 2.0)) {
    cellStatus.textContent = 'Dendrite Hazard';
    cellStatus.className = 'badge badge-hazardous';
  } else if (cellV >= (b.chemistry === 'LFP' ? 3.85 : 4.35)) {
    cellStatus.textContent = 'Thermal Overvoltage';
    cellStatus.className = 'badge badge-hazardous';
  } else {
    cellStatus.textContent = 'Safe Window';
    cellStatus.className = 'badge badge-status';
  }

  // SoH Calculation
  const soh = Math.round((capVal / b.rated_capacity_mah) * 100);
  const sohBadge = document.getElementById('benchSoHBadge');
  const sohBar = document.getElementById('benchSoHBar');

  sohBadge.textContent = `SoH: ${soh}%`;
  sohBar.style.width = `${Math.min(100, Math.max(0, soh))}%`;

  if (soh >= 75) {
    sohBadge.className = 'badge badge-reuse';
    sohBar.style.backgroundColor = 'var(--emerald-500)';
  } else if (soh >= 60) {
    sohBadge.className = 'badge badge-refurbish';
    sohBar.style.backgroundColor = 'var(--cyan-500)';
  } else {
    sohBadge.className = 'badge badge-recycle';
    sohBar.style.backgroundColor = 'var(--amber-500)';
  }
}

function applyBenchPreset(targetSoH, targetVolt, condition, thermal, note) {
  const select = document.getElementById('telemetryBatterySelect');
  const b = state.batteries.find(x => x.id === select.value);
  if (!b) return;

  const targetCap = Math.round(b.rated_capacity_mah * (targetSoH / 100));
  document.getElementById('benchCapSlider').value = targetCap;
  document.getElementById('benchVoltSlider').value = targetVolt;
  document.getElementById('benchPhysical').value = condition;
  document.getElementById('benchThermal').value = thermal;
  document.getElementById('benchNotes').value = note;
  updateBenchCalculations();
}

async function injectBenchTelemetry() {
  const batteryId = document.getElementById('telemetryBatterySelect').value;
  if (!batteryId) {
    showToast('Please select a battery asset to inject telemetry', 'error');
    return;
  }

  const rawThermal = document.getElementById('benchThermal').value;
  const thermalVal = ['NORMAL', 'ELEVATED', 'OVERHEATED', 'EXTREME', 'UNKNOWN'].includes(rawThermal) ? rawThermal : 'NORMAL';

  const payload = {
    measured_voltage_v: parseFloat(document.getElementById('benchVoltSlider').value),
    measured_capacity_mah: parseFloat(document.getElementById('benchCapSlider').value),
    internal_resistance_mohm: parseFloat(document.getElementById('benchIR').value) || 18.0,
    temperature_history: thermalVal,
    physical_condition: document.getElementById('benchPhysical').value,
    technician_notes: document.getElementById('benchNotes').value,
  };

  try {
    const res = await fetch(`/api/v1/revolt/batteries/${batteryId}/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      let errorMsg = `Server error (${res.status})`;
      try {
        const errData = await res.json();
        if (errData && errData.detail) {
          if (Array.isArray(errData.detail)) {
            errorMsg = errData.detail.map(e => `${e.loc ? e.loc.slice(1).join('.') + ': ' : ''}${e.msg}`).join('; ');
          } else {
            errorMsg = errData.detail;
          }
        }
      } catch (_) {}
      throw new Error(errorMsg);
    }
    const updated = await res.json();
    showToast(`Telemetry injected! Assessed as ${updated.recommended_pathway}`);
    await loadAllData();
    switchView('assessment', batteryId);
  } catch (err) {
    showToast(`Telemetry Injection Failed: ${err.message}`, 'error');
  }
}

// 5. AI ASSESSMENT VIEW
function initAssessment() {
  const select = document.getElementById('assessmentBatterySelect');
  select.addEventListener('change', () => {
    if (select.value) renderAssessmentForBattery(select.value);
  });

  document.getElementById('btnAssessDispatch').addEventListener('click', () => {
    const bid = document.getElementById('assessmentBatterySelect').value;
    if (bid) openBookingModal(bid);
  });

  document.getElementById('btnAssessViewPassport').addEventListener('click', () => {
    const bid = document.getElementById('assessmentBatterySelect').value;
    if (bid) switchView('passport', bid);
  });
}

function renderAssessmentForBattery(batteryId) {
  const b = state.batteries.find(x => x.id === batteryId);
  if (!b || !b.assessment) {
    document.getElementById('assessmentEmptyPrompt').style.display = 'block';
    document.getElementById('assessmentContent').style.display = 'none';
    return;
  }

  document.getElementById('assessmentEmptyPrompt').style.display = 'none';
  document.getElementById('assessmentContent').style.display = 'block';

  const a = b.assessment;
  const heroBox = document.getElementById('assessmentHeroBox');
  const title = document.getElementById('assessPathwayTitle');
  const conf = document.getElementById('assessConfidenceVal');
  const basis = document.getElementById('assessConfidenceBasis');
  const completeness = document.getElementById('assessCompletenessVal');

  title.textContent = a.pathway;
  conf.textContent = `${Math.round(a.confidence_score * 100)}%`;
  if (basis) {
    basis.textContent = a.confidence_basis || '';
  }
  if (completeness) {
    const compVal = a.data_completeness_score !== undefined ? Math.round(a.data_completeness_score * 100) : (b.data_completeness_pct || 100);
    completeness.textContent = `Telemetry Completeness: ${compVal}%`;
  }

  // Hero Styling
  const colorMap = {
    REUSE: { bg: 'rgba(16, 185, 129, 0.15)', border: 'var(--emerald-500)', color: 'var(--emerald-400)' },
    REFURBISH: { bg: 'rgba(6, 182, 212, 0.15)', border: 'var(--cyan-500)', color: 'var(--cyan-400)' },
    RECYCLE: { bg: 'rgba(245, 158, 11, 0.15)', border: 'var(--amber-500)', color: 'var(--amber-400)' },
    HAZARDOUS: { bg: 'rgba(239, 68, 68, 0.2)', border: 'var(--rose-500)', color: 'var(--rose-400)' },
    PENDING_VERIFICATION: { bg: 'rgba(139, 92, 246, 0.15)', border: 'var(--pathway-pending)', color: 'var(--pathway-pending)' },
  };
  const theme = colorMap[a.pathway] || colorMap.REUSE;
  heroBox.style.background = theme.bg;
  heroBox.style.border = `1px solid ${theme.border}`;
  title.style.color = theme.color;

  document.getElementById('assessSummaryDesc').textContent =
    a.is_hazardous
      ? 'CRITICAL SAFETY THREAT DETECTED: Battery violates operating boundaries. Mandatory isolation protocol active.'
      : `Qualified for ${a.pathway} circular pathway based on measured degradation and physical integrity.`;

  // Safety Warnings
  const warningsCard = document.getElementById('cardSafetyWarnings');
  const warningsList = document.getElementById('assessWarningsList');
  if (a.safety_warnings && a.safety_warnings.length > 0) {
    warningsCard.style.display = 'block';
    warningsList.innerHTML = a.safety_warnings.map(w => `
      <li>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--rose-400);"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <span>${w}</span>
      </li>
    `).join('');
  } else {
    warningsCard.style.display = 'none';
  }

  // Contributing Factors
  document.getElementById('assessFactorsList').innerHTML = a.contributing_factors.map(f => `
    <li>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
      <span>${f}</span>
    </li>
  `).join('');

  // Next Steps Checklist
  document.getElementById('assessNextStepsList').innerHTML = a.recommended_next_steps.map(s => `
    <li>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
      <span>${s}</span>
    </li>
  `).join('');
}

// 6. FACILITY LOCATOR RENDERING & MAP
function initFacilities() {
  document.getElementById('facilitySearch').addEventListener('input', renderFacilities);
  document.getElementById('facilityFilterPathway').addEventListener('change', renderFacilities);
}

function renderFacilities() {
  const container = document.getElementById('facilityCardsContainer');
  const search = document.getElementById('facilitySearch').value.toLowerCase().trim();
  const filterPathway = document.getElementById('facilityFilterPathway').value;

  const filtered = state.facilities.filter(f => {
    if (search) {
      const match = f.name.toLowerCase().includes(search) ||
                    f.city.toLowerCase().includes(search) ||
                    f.facility_type.toLowerCase().includes(search) ||
                    f.services_offered.some(s => s.toLowerCase().includes(search));
      if (!match) return false;
    }
    if (filterPathway && !f.supported_pathways.includes(filterPathway)) return false;
    return true;
  });

  document.getElementById('facilityCountLabel').textContent = `${filtered.length} certified locations`;

  container.innerHTML = filtered.map(f => `
    <div class="facility-card">
      <div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
          <h4 style="font-size: 1rem; font-weight: 700; color: var(--text-main);">${f.name}</h4>
          <span class="badge badge-status">${f.city}</span>
        </div>
        <div style="font-size: 0.78rem; color: var(--emerald-400); font-weight: 600; margin-bottom: 0.5rem;">${f.facility_type}</div>
        <p style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.75rem;">${f.address}, ${f.city}, ${f.state}</p>

        <div style="margin-bottom: 0.75rem;">
          <span style="font-size: 0.7rem; color: var(--text-dim); text-transform: uppercase;">Capabilities:</span>
          <div style="display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.3rem;">
            ${f.supported_pathways.map(p => `<span class="badge badge-status" style="font-size: 0.65rem;">${p}</span>`).join('')}
          </div>
        </div>

        <div style="margin-bottom: 1rem;">
          <span style="font-size: 0.7rem; color: var(--text-dim); text-transform: uppercase;">Certifications:</span>
          <div style="display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.3rem;">
            ${f.certifications.map(c => `<span style="font-size: 0.7rem; color: var(--cyan-400); background: rgba(6, 182, 212, 0.1); padding: 0.1rem 0.35rem; border-radius: 4px;">${c}</span>`).join('')}
          </div>
        </div>
      </div>

      <div style="border-top: 1px solid var(--border-subtle); padding-top: 0.75rem; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 0.75rem; color: var(--text-dim);">${f.phone}</span>
        <button class="btn btn-outline btn-sm" onclick="openBookingModalForFacility('${f.id}')">Book Logistics</button>
      </div>
    </div>
  `).join('');
}

function renderFacilityMap() {
  if (typeof L === 'undefined') return;

  if (!state.map) {
    const mapEl = document.getElementById('facilityMap');
    if (!mapEl) return;

    // Centered around Tamil Nadu / South India
    state.map = L.map('facilityMap').setView([12.5, 78.8], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(state.map);
  }

  // Clear existing markers
  state.mapMarkers.forEach(m => m.remove());
  state.mapMarkers = [];

  state.facilities.forEach(fac => {
    const marker = L.marker([fac.latitude, fac.longitude]).addTo(state.map);
    marker.bindPopup(`
      <div style="color: #0A0F12; font-family: sans-serif; min-width: 180px;">
        <strong style="font-size: 0.9rem;">${fac.name}</strong><br>
        <span style="font-size: 0.75rem; color: #475569;">${fac.facility_type}</span><br>
        <span style="font-size: 0.72rem; color: #64748B;">${fac.city}, ${fac.state}</span><br>
        <button style="margin-top: 6px; padding: 4px 8px; background: #10B981; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.75rem;" onclick="openBookingModalForFacility('${fac.id}')">Select Facility</button>
      </div>
    `);
    state.mapMarkers.push(marker);
  });

  state.map.invalidateSize();
}

// 7. DIGITAL BATTERY PASSPORT
function initPassport() {
  const select = document.getElementById('passportBatterySelect');
  select.addEventListener('change', () => {
    if (select.value) {
      renderPassportForBattery(select.value);
    } else {
      document.getElementById('passportContentArea').style.display = 'none';
    }
  });

  document.getElementById('btnExecuteTransition').addEventListener('click', executeLifecycleTransition);
}

function updateTransitionControllerUI(b, allowedNext) {
  const statusSelect = document.getElementById('passNextStatusSelect');
  const btn = document.getElementById('btnExecuteTransition');
  const noticeEl = document.getElementById('passTransitionNotice');

  if (!statusSelect || !btn) return;

  if (!allowedNext || allowedNext.length === 0) {
    statusSelect.disabled = true;
    btn.disabled = true;
    if (b.status === 'COMPLETED') {
      statusSelect.innerHTML = '<option value="">No further transitions (Completed)</option>';
      if (noticeEl) {
        noticeEl.style.display = 'block';
        noticeEl.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        noticeEl.style.color = 'var(--emerald-400)';
        noticeEl.innerHTML = '<strong>Lifecycle Completed:</strong> This battery has reached its terminal lifecycle status. Physical-world chain of custody is finalized; no further state transitions are permitted.';
      }
    } else {
      statusSelect.innerHTML = `<option value="">No valid transitions from ${b.status}</option>`;
      if (noticeEl) {
        noticeEl.style.display = 'block';
        noticeEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        noticeEl.style.color = 'var(--amber-400)';
        noticeEl.innerHTML = `<strong>No Transitions Available:</strong> Current battery status is <strong>${b.status}</strong> with no further valid state transitions in the circular pipeline.`;
      }
    }
  } else {
    statusSelect.disabled = false;
    btn.disabled = false;
    if (noticeEl) {
      noticeEl.style.display = 'none';
      noticeEl.innerHTML = '';
    }
    statusSelect.innerHTML = allowedNext.map(st => `<option value="${st}">${st}</option>`).join('');
  }
}

function renderPassportForBattery(batteryId) {
  const b = state.batteries.find(x => x.id === batteryId);
  if (!b) return;

  document.getElementById('passportContentArea').style.display = 'block';

  document.getElementById('passId').textContent = b.id;
  document.getElementById('passName').textContent = b.name;
  document.getElementById('passChemApp').textContent = `${b.chemistry} / ${b.original_application}`;
  document.getElementById('passVoltCap').textContent = `${b.measured_voltage_v ? b.measured_voltage_v.toFixed(1) + 'V' : b.nominal_voltage_v + 'V'} / ${(b.measured_capacity_mah || b.rated_capacity_mah).toFixed(0)} mAh`;
  document.getElementById('passSoH').textContent = b.assessment && b.assessment.soh_percentage ? `${b.assessment.soh_percentage}%` : 'Unmeasured';
  document.getElementById('passFacility').textContent = b.assigned_facility_name || 'Unassigned';

  const badge = document.getElementById('passPathwayBadge');
  badge.textContent = b.recommended_pathway;
  badge.className = `badge badge-${b.recommended_pathway.toLowerCase()}`;

  // SVG QR Code Generation
  document.getElementById('passportQRCode').innerHTML = `
    <svg width="56" height="56" viewBox="0 0 29 29" shape-rendering="crispEdges">
      <rect width="29" height="29" fill="#FFFFFF"/>
      <!-- QR Alignment Patterns -->
      <path fill="#0A0F12" d="M2 2h7v7H2zm1 1v5h5V3zM4 4h3v3H4zm16-2h7v7h-7zm1 1v5h5V3zm1 1h3v3h-3zM2 20h7v7H2zm1 1v5h5v-5zM4 22h3v3H4zm12 0h2v2h-2zm3 0h4v2h-4zm-3 3h3v2h-3zm4 0h3v2h-3zm-6-8h4v2h-4zm6 0h2v4h-2zm-2 2h2v3h-2zm-8-3h2v4h-2zm-3 2h2v2h-2zm16-8h2v2h-2zm-4 4h3v2h-3z"/>
    </svg>
  `;

  // Lifecycle Stepper
  const stages = [
    { key: 'REGISTERED', label: 'Registered' },
    { key: 'ASSESSED', label: 'Assessed' },
    { key: 'AWAITING_COLLECTION', label: 'Awaiting Collection' },
    { key: 'IN_TRANSIT', label: 'In Transit' },
    { key: 'RECEIVED_AT_FACILITY', label: 'At Facility' },
    { key: 'PROCESSING', label: 'Processing' },
    { key: 'COMPLETED', label: 'Completed' },
  ];

  const stageKeys = stages.map(s => s.key);
  let currentIndex = stageKeys.indexOf(b.status);
  if (currentIndex === -1) {
    if (b.status === 'ROUTED_FOR_PROCESSING') currentIndex = 4;
    else if (['REUSED', 'REFURBISHED', 'RECYCLED', 'SPECIALIST_HANDLING'].includes(b.status)) currentIndex = 5;
    else if (b.status === 'PENDING_VERIFICATION') currentIndex = 0;
  }

  document.getElementById('passStepper').innerHTML = stages.map((st, idx) => {
    let nodeClass = '';
    if (idx < currentIndex) nodeClass = 'completed';
    else if (idx === currentIndex) nodeClass = 'current';

    return `
      <div class="step-node ${nodeClass}">
        <div class="step-circle">${idx < currentIndex ? '✓' : idx + 1}</div>
        <span class="step-label">${st.label}</span>
      </div>
    `;
  }).join('');

  // Valid Next Transitions
  const isHazardous = b.recommended_pathway === 'HAZARDOUS' || (b.assessment && b.assessment.is_hazardous);
  const validTransitionsMap = {
    REGISTERED: ['ASSESSED', 'PENDING_VERIFICATION'],
    PENDING_VERIFICATION: ['ASSESSED'],
    ASSESSED: ['AWAITING_COLLECTION', 'IN_TRANSIT'],
    AWAITING_COLLECTION: ['IN_TRANSIT', 'RECEIVED_AT_FACILITY'],
    IN_TRANSIT: ['RECEIVED_AT_FACILITY'],
    RECEIVED_AT_FACILITY: ['PROCESSING', 'ROUTED_FOR_PROCESSING'],
    ROUTED_FOR_PROCESSING: ['PROCESSING'],
    PROCESSING: isHazardous
      ? ['SPECIALIST_HANDLING', 'RECYCLED', 'COMPLETED']
      : ['COMPLETED', 'REUSED', 'REFURBISHED', 'RECYCLED', 'SPECIALIST_HANDLING'],
    SPECIALIST_HANDLING: ['COMPLETED'],
    REUSED: ['COMPLETED'],
    REFURBISHED: ['COMPLETED'],
    RECYCLED: ['COMPLETED'],
    COMPLETED: [],
  };

  const initialAllowed = validTransitionsMap[b.status] || [];
  updateTransitionControllerUI(b, initialAllowed);

  // Reconcile directly with backend valid transition rules endpoint
  fetch(`/api/v1/revolt/batteries/${batteryId}/transitions`)
    .then(r => r.ok ? r.json() : null)
    .then(serverAllowed => {
      if (Array.isArray(serverAllowed)) {
        updateTransitionControllerUI(b, serverAllowed);
      }
    })
    .catch(() => {});

  // Timeline
  document.getElementById('passEventCount').textContent = `${b.timeline.length} events`;
  document.getElementById('passTimelineContainer').innerHTML = b.timeline.slice().reverse().map(ev => `
    <div class="timeline-item">
      <div class="timeline-dot"></div>
      <div class="timeline-content">
        <div class="timeline-header">
          <span class="timeline-title">${ev.title}</span>
          <span class="timeline-time">${new Date(ev.timestamp).toLocaleString()}</span>
        </div>
        <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.25rem;">${ev.description}</p>
        <span class="timeline-actor">Authorized Actor: ${ev.actor}</span>
      </div>
    </div>
  `).join('');
}

async function executeLifecycleTransition() {
  const batteryId = document.getElementById('passportBatterySelect').value;
  const statusSelect = document.getElementById('passNextStatusSelect');
  const btn = document.getElementById('btnExecuteTransition');
  const newStatus = statusSelect ? statusSelect.value : '';
  const actor = document.getElementById('passActorName').value;
  const note = document.getElementById('passAuditNote').value;

  if (btn && btn.disabled) {
    showToast('No valid transition available for this battery', 'error');
    return;
  }

  if (!newStatus) {
    showToast('No valid transition selected', 'error');
    return;
  }

  try {
    const res = await fetch(`/api/v1/revolt/batteries/${batteryId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, actor: actor, note: note }),
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Transition rejected');
    }
    const updated = await res.json();
    showToast(`Status updated to ${updated.status}`);
    await loadAllData();
    renderPassportForBattery(batteryId);
  } catch (err) {
    showToast(`State Machine Error: ${err.message}`, 'error');
  }
}

// 8. IMPACT ANALYTICS
function renderAnalytics() {
  if (!state.analytics) return;
  const a = state.analytics;

  document.getElementById('anCO2').textContent = a.estimated_co2_avoided_kg.toLocaleString();
  document.getElementById('anWeight').textContent = a.estimated_landfill_diversion_kg.toLocaleString();
  document.getElementById('anLithium').textContent = a.estimated_lithium_carbonate_kg.toLocaleString();
  document.getElementById('anCoNi').textContent = (a.estimated_cobalt_kg + a.estimated_nickel_kg).toLocaleString();
  document.getElementById('anMethodologyText').textContent = a.methodology_note;
}

// Helper: Populate Battery Selectors in Lab, Assessment, and Passport
function populateBatterySelectors() {
  const labSel = document.getElementById('telemetryBatterySelect');
  const assessSel = document.getElementById('assessmentBatterySelect');
  const passSel = document.getElementById('passportBatterySelect');

  const optionsHtml = '<option value="">Select Battery Asset...</option>' + state.batteries.map(b => `
    <option value="${b.id}">${b.id} — ${b.name} (${b.recommended_pathway})</option>
  `).join('');

  const prevLab = labSel.value;
  const prevAssess = assessSel.value;
  const prevPass = passSel.value;

  labSel.innerHTML = optionsHtml;
  assessSel.innerHTML = optionsHtml;
  passSel.innerHTML = optionsHtml;

  if (prevLab) labSel.value = prevLab;
  if (prevAssess) assessSel.value = prevAssess;
  if (prevPass) passSel.value = prevPass;
}

// Modals Handling
function initModals() {
  // Register Modal
  const regModal = document.getElementById('modalRegister');
  document.getElementById('btnOpenRegisterModal').addEventListener('click', () => {
    regModal.classList.add('active');
  });
  document.getElementById('btnCloseRegisterModal').addEventListener('click', () => {
    regModal.classList.remove('active');
  });
  document.getElementById('btnCancelRegisterModal').addEventListener('click', () => {
    regModal.classList.remove('active');
  });

  document.getElementById('formRegisterBattery').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      name: document.getElementById('regName').value,
      chemistry: document.getElementById('regChemistry').value,
      original_application: document.getElementById('regApplication').value,
      rated_capacity_mah: parseFloat(document.getElementById('regRatedCap').value),
      measured_capacity_mah: document.getElementById('regMeasuredCap').value ? parseFloat(document.getElementById('regMeasuredCap').value) : null,
      nominal_voltage_v: parseFloat(document.getElementById('regNomVoltage').value),
      measured_voltage_v: document.getElementById('regMeasuredVoltage').value ? parseFloat(document.getElementById('regMeasuredVoltage').value) : null,
      cycle_count: document.getElementById('regCycles').value ? parseInt(document.getElementById('regCycles').value) : null,
      age_months: parseInt(document.getElementById('regAge').value) || 24,
      physical_condition: document.getElementById('regCondition').value,
      temperature_history: document.getElementById('regThermal').value,
      owner_notes: document.getElementById('regNotes').value,
    };

    try {
      const res = await fetch('/api/v1/revolt/batteries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Registration failed');
      const created = await res.json();
      showToast(`Battery registered successfully: ${created.id}`);
      regModal.classList.remove('active');
      document.getElementById('formRegisterBattery').reset();
      await loadAllData();
      switchView('registry');
    } catch (err) {
      showToast('Registration error', 'error');
    }
  });

  // Booking Modal
  const bookModal = document.getElementById('modalBooking');
  document.getElementById('btnCloseBookingModal').addEventListener('click', () => {
    bookModal.classList.remove('active');
  });
  document.getElementById('btnCancelBookingModal').addEventListener('click', () => {
    bookModal.classList.remove('active');
  });

  document.getElementById('bookFacilitySelect').addEventListener('change', () => {
    const batteryId = document.getElementById('bookBatteryId').value;
    const b = state.batteries.find(x => x.id === batteryId);
    const facId = document.getElementById('bookFacilitySelect').value;
    const fac = state.facilities.find(f => f.id === facId);
    const noticeEl = document.getElementById('bookFacilityNotice');
    if (!b || !fac || !noticeEl) return;

    const isHaz = b.recommended_pathway === 'HAZARDOUS' || (b.assessment && b.assessment.is_hazardous);
    const isCompat = isHaz
      ? fac.supported_pathways.includes('HAZARDOUS')
      : fac.supported_pathways.includes(b.recommended_pathway);

    noticeEl.style.display = 'block';
    if (isCompat) {
      noticeEl.style.color = 'var(--emerald-400)';
      noticeEl.innerHTML = `✓ Certified for ${b.recommended_pathway} intake: ${fac.name}`;
    } else {
      noticeEl.style.color = 'var(--rose-400)';
      noticeEl.innerHTML = `⚠️ Incompatible: Facility does not support ${b.recommended_pathway}. Please select a compatible facility.`;
    }
  });

  document.getElementById('formScheduleBooking').addEventListener('submit', async (e) => {
    e.preventDefault();
    const batteryId = document.getElementById('bookBatteryId').value;
    const facilityId = document.getElementById('bookFacilitySelect').value;

    if (!batteryId) {
      showToast('No battery asset selected', 'error');
      return;
    }
    if (!facilityId) {
      showToast('No eligible facility selected for this pathway', 'error');
      return;
    }

    const b = state.batteries.find(x => x.id === batteryId);
    const fac = state.facilities.find(x => x.id === facilityId);
    if (b && fac) {
      const isHaz = b.recommended_pathway === 'HAZARDOUS' || (b.assessment && b.assessment.is_hazardous);
      if (isHaz && !fac.supported_pathways.includes('HAZARDOUS')) {
        showToast(`Safety violation: Facility '${fac.name}' is not authorized for HAZARDOUS battery intake`, 'error');
        return;
      }
      if (!isHaz && ['REUSE', 'REFURBISH', 'RECYCLE'].includes(b.recommended_pathway)) {
        if (!fac.supported_pathways.includes(b.recommended_pathway)) {
          showToast(`Facility '${fac.name}' does not support the recommended '${b.recommended_pathway}' circular pathway`, 'error');
          return;
        }
      }
    }

    const payload = {
      facility_id: facilityId,
      logistics_type: document.getElementById('bookLogisticsType').value,
      scheduled_date: document.getElementById('bookDate').value,
      time_slot: document.getElementById('bookTimeSlot').value,
      contact_name: document.getElementById('bookContactName').value,
      contact_phone: document.getElementById('bookContactPhone').value,
      pickup_address: document.getElementById('bookAddress').value,
      special_instructions: document.getElementById('bookInstructions').value,
    };

    try {
      const res = await fetch(`/api/v1/revolt/batteries/${batteryId}/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Booking failed' }));
        throw new Error(errData.detail || 'Booking failed');
      }
      const updated = await res.json();
      showToast(`Logistics booked! Booking ID: ${updated.booking.booking_id}`);
      bookModal.classList.remove('active');
      await loadAllData();
      switchView('passport', batteryId);
    } catch (err) {
      showToast(`Booking error: ${err.message}`, 'error');
    }
  });
}

window.openBookingModal = function(batteryId, preferredFacilityId = null) {
  const b = state.batteries.find(x => x.id === batteryId);
  if (!b) return;

  document.getElementById('bookBatteryId').value = b.id;
  document.getElementById('bookBatteryDisplay').value = `${b.id} — ${b.name} (${b.recommended_pathway})`;

  const pathway = b.recommended_pathway;
  const isHazardous = pathway === 'HAZARDOUS' || (b.assessment && b.assessment.is_hazardous);
  const facSelect = document.getElementById('bookFacilitySelect');
  const logSelect = document.getElementById('bookLogisticsType');
  const noticeEl = document.getElementById('bookFacilityNotice');
  const submitBtn = document.getElementById('btnSubmitBooking');

  // Pre-set date to tomorrow
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  document.getElementById('bookDate').value = tomorrow.toISOString().split('T')[0];

  // Logistics type restrictions for hazardous
  if (isHazardous) {
    logSelect.value = 'HAZMAT_PICKUP';
    const stdOpt = logSelect.querySelector('option[value="STANDARD_PICKUP"]');
    const dropOpt = logSelect.querySelector('option[value="DEPOT_DROP_OFF"]');
    if (stdOpt) stdOpt.disabled = true;
    if (dropOpt) dropOpt.disabled = true;
    document.getElementById('bookInstructions').value = 'MANDATORY HAZMAT DISPATCH (UN 3480): Specialist containment required.';
  } else {
    const stdOpt = logSelect.querySelector('option[value="STANDARD_PICKUP"]');
    const dropOpt = logSelect.querySelector('option[value="DEPOT_DROP_OFF"]');
    if (stdOpt) stdOpt.disabled = false;
    if (dropOpt) dropOpt.disabled = false;
    if (logSelect.value === 'HAZMAT_PICKUP') logSelect.value = 'STANDARD_PICKUP';
    document.getElementById('bookInstructions').value = '';
  }

  // Filter facilities strictly by the battery's recommended circular pathway
  let compatibleFacilities = [];
  if (isHazardous) {
    compatibleFacilities = state.facilities.filter(f => f.supported_pathways.includes('HAZARDOUS'));
  } else if (pathway === 'REUSE') {
    compatibleFacilities = state.facilities.filter(f => f.supported_pathways.includes('REUSE'));
  } else if (pathway === 'REFURBISH') {
    compatibleFacilities = state.facilities.filter(f => f.supported_pathways.includes('REFURBISH'));
  } else if (pathway === 'RECYCLE') {
    compatibleFacilities = state.facilities.filter(f => f.supported_pathways.includes('RECYCLE'));
  } else {
    // PENDING_VERIFICATION / PENDING: allow non-hazmat diagnostic / testing facilities
    compatibleFacilities = state.facilities.filter(f => !f.supported_pathways.every(p => p === 'HAZARDOUS'));
  }

  if (compatibleFacilities.length === 0) {
    facSelect.innerHTML = `<option value="">No authorized facilities configured for ${pathway}</option>`;
    facSelect.disabled = true;
    if (submitBtn) submitBtn.disabled = true;
    if (noticeEl) {
      noticeEl.style.display = 'block';
      noticeEl.style.color = 'var(--rose-400)';
      noticeEl.innerHTML = `⚠️ No certified facilities are configured to accept <strong>${pathway}</strong> batteries. Dispatch is unavailable until an authorized partner is configured.`;
    }
  } else {
    facSelect.disabled = false;
    if (submitBtn) submitBtn.disabled = false;
    facSelect.innerHTML = compatibleFacilities.map(f => `
      <option value="${f.id}">${f.name} (${f.city} — ${f.facility_type}) [Supports: ${f.supported_pathways.join(', ')}]</option>
    `).join('');

    if (preferredFacilityId) {
      const isPrefCompatible = compatibleFacilities.some(f => f.id === preferredFacilityId);
      if (isPrefCompatible) {
        facSelect.value = preferredFacilityId;
        if (noticeEl) {
          noticeEl.style.display = 'block';
          noticeEl.style.color = 'var(--emerald-400)';
          noticeEl.innerHTML = `✓ Facility certified for ${pathway} circular pathway.`;
        }
      } else {
        const prefFac = state.facilities.find(f => f.id === preferredFacilityId);
        const prefName = prefFac ? prefFac.name : preferredFacilityId;
        const prefPathways = prefFac ? prefFac.supported_pathways.join(', ') : 'None';
        if (noticeEl) {
          noticeEl.style.display = 'block';
          noticeEl.style.color = 'var(--amber-400)';
          noticeEl.innerHTML = `⚠️ Facility '<strong>${prefName}</strong>' supports [${prefPathways}], which is incompatible with this battery's recommended '<strong>${pathway}</strong>' pathway. Please select from the compatible facilities listed above.`;
        }
      }
    } else {
      if (noticeEl) {
        noticeEl.style.display = 'block';
        noticeEl.style.color = 'var(--emerald-400)';
        noticeEl.innerHTML = `✓ Showing ${compatibleFacilities.length} authorized ${compatibleFacilities.length === 1 ? 'facility' : 'facilities'} configured for ${pathway} intake.`;
      }
    }
  }

  document.getElementById('modalBooking').classList.add('active');
};

window.openBookingModalForFacility = function(facilityId) {
  const fac = state.facilities.find(f => f.id === facilityId);
  if (!fac) {
    showToast(`Facility '${facilityId}' not found`, 'error');
    return;
  }
  if (state.batteries.length === 0) {
    showToast('No registered batteries available to dispatch', 'error');
    return;
  }

  // Find a battery compatible with this facility's supported pathways
  let compatibleBattery = state.batteries.find(b => {
    const isHaz = b.recommended_pathway === 'HAZARDOUS' || (b.assessment && b.assessment.is_hazardous);
    if (isHaz) return fac.supported_pathways.includes('HAZARDOUS');
    return fac.supported_pathways.includes(b.recommended_pathway);
  });

  if (!compatibleBattery && !fac.supported_pathways.includes('HAZARDOUS')) {
    compatibleBattery = state.batteries.find(b => b.recommended_pathway === 'PENDING_VERIFICATION');
  }

  if (compatibleBattery) {
    openBookingModal(compatibleBattery.id, facilityId);
  } else {
    // If no battery matches, open with the first battery and let the modal display the clear incompatibility notice
    const defaultBattery = state.batteries[0];
    openBookingModal(defaultBattery.id, facilityId);
  }
};
