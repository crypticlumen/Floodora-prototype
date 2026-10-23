const API = '/api';
const state = { locations: [], scenarios: [], selected: null, baseline: null, assessment: null, assessments: new Map(), liveReadings: new Map(), sensorReadings: new Map(), manualOverrides: new Set(), weatherByLocation: new Map(), siteWeather: null, refreshingLiveData: false, toastTimer: null };
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message = body.detail || message; } catch { /* Keep the HTTP status message. */ }
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json();
}

function notify(message) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.add('visible');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove('visible'), 3500);
}

function riskClass(level) { return `risk-${String(level || 'unknown').toLowerCase()}`; }
function modeLabel(mode) {
  if (mode === 'mixed') return 'LIVE WEATHER · DRAIN DATA';
  if (mode === 'live') return 'LIVE SENSOR DATA';
  return String(mode || 'simulated').replaceAll('_', ' ').toUpperCase();
}
function formatTime(value) {
  if (!value) return 'Time unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function setConnection(connected, label = connected ? 'API connected' : 'API unavailable') {
  $('connection-dot').classList.toggle('connected', connected);
  $('connection-label').textContent = label;
}

async function init() {
  document.body.classList.add('weather-only');
  $('run-all-button').disabled = true;
  $('today-label').textContent = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  $('engine-status').textContent = 'WAITING';
  $('status-summary-foot').textContent = 'Search a location to load its weather';
  document.querySelector('.engine-value .status-pip').classList.replace('green-pip', 'amber-pip');
  $('refresh-button').addEventListener('click', () => state.selected ? Promise.all([loadSiteWeather(state.selected), loadSensorData(state.selected)]) : $('city-search-input').focus());
  $('city-search-form').addEventListener('submit', searchIndianPlaces);
  $('drain-reading-form').addEventListener('submit', saveDrainReadings);
  $('assess-button').addEventListener('click', () => assessSelected(true));
  $('run-all-button').addEventListener('click', () => assessAll(true));
  $('simulate-button').addEventListener('click', simulate);
  $('scenario-select').addEventListener('change', loadPreset);
  $('rain-slider').addEventListener('input', () => $('rain-output').textContent = `${$('rain-slider').value} mm/h`);
  $('blockage-slider').addEventListener('input', () => $('blockage-output').textContent = `${$('blockage-slider').value}%`);
  $('history-refresh').addEventListener('click', loadHistory);
  $('view-sites-button').addEventListener('click', () => state.selected && loadSiteWeather(state.selected));
  $('site-weather-refresh').addEventListener('click', () => state.selected && Promise.all([loadSiteWeather(state.selected), loadSensorData(state.selected)]));
  setInterval(() => state.selected && loadSiteWeather(state.selected, true), 600000);
  setInterval(() => state.selected && loadSensorData(state.selected, true), 60000);
  try {
    const health = await request('/health');
    setConnection(health.status === 'healthy', 'API connected');
    state.scenarios = await request('/scenarios').catch(() => []);
    renderScenarioOptions();
    const saved = sessionStorage.getItem('floodora-weather-location');
    if (saved) {
      const { place, query } = JSON.parse(saved);
      if (place?.latitude && place?.longitude) {
        $('city-search-input').value = query || place.pincode || place.name || '';
        await loadPlaceWeather(place);
      }
    }
  } catch (error) {
    setConnection(false);
    notify(`Could not connect to Floodora API: ${error.message}`);
    $('site-weather-condition').textContent = 'Weather service unavailable';
    $('site-weather-time').textContent = 'Start the backend, then refresh this page.';
    $('engine-status').textContent = 'OFFLINE';
  }
}

async function reload() {
  if (state.selected) return loadSiteWeather(state.selected);
  $('city-search-input').focus();
  notify('Enter a PIN code, city, or district to load its weather.');
}

async function refreshLiveNetwork(showNotice = true) {
  if (!state.locations.length || state.refreshingLiveData) return;
  state.refreshingLiveData = true;
  const button = $('refresh-button');
  button?.classList.add('spinning');
  const weatherResults = await Promise.all(state.locations.map(async (location) => {
    try {
      const weather = await request(`/weather/current?latitude=${encodeURIComponent(location.latitude)}&longitude=${encodeURIComponent(location.longitude)}`);
      state.weatherByLocation.set(location.location_id, weather);
      const reading = {
        ...location.current_readings,
        location_id: location.location_id,
        location_name: location.name,
        capacity_cm: location.capacity_cm,
        rainfall_mm_h: weather.rainfall_mm_h_equivalent,
        data_mode: 'mixed',
      };
      state.liveReadings.set(location.location_id, reading);
      return { location, weather, reading };
    } catch (error) {
      const previous = state.weatherByLocation.get(location.location_id);
      if (previous) state.weatherByLocation.set(location.location_id, { ...previous, stale: true });
      return { location, error };
    }
  }));
  const available = weatherResults.filter((result) => result.weather);
  const fresh = available.filter((result) => !result.weather.stale);
  const badge = $('network-data-badge');
  if (badge) {
    const label = !available.length ? 'WEATHER OFFLINE · SIMULATED READINGS' : !fresh.length ? 'CACHED WEATHER · DRAIN SIMULATED' : fresh.length < state.locations.length ? 'PARTIAL WEATHER FEED · DRAIN SIMULATED' : 'CURRENT WEATHER MODEL · DRAIN SIMULATED';
    badge.innerHTML = `<span></span> ${label}`;
    badge.classList.toggle('weather-stale', !fresh.length);
  }
  if (state.selected) {
    const selectedWeather = state.selected.ward === 'Preset scenario' ? null : state.weatherByLocation.get(state.selected.location_id);
    if (selectedWeather) {
      state.siteWeather = selectedWeather;
      renderSiteWeather(selectedWeather);
      const reading = state.liveReadings.get(state.selected.location_id);
      if (reading) state.baseline = { ...reading };
    }
  }
  await assessAll(false);
  await loadHistory();
  button?.classList.remove('spinning');
  state.refreshingLiveData = false;
  if (showNotice) notify(available.length ? `Updated live weather and reassessed ${available.length} sites.` : 'Weather provider unavailable; showing simulated drainage readings.');
}

function readingFor(location) {
  if (state.liveReadings.has(location.location_id)) return { ...state.liveReadings.get(location.location_id) };
  if (location.is_search_location) return null;
  return { ...location.current_readings, location_id: location.location_id, location_name: location.name, capacity_cm: location.capacity_cm, data_mode: location.current_readings.data_mode || 'simulated' };
}

async function assessAll(showNotice = true) {
  if (!state.locations.length) return;
  $('run-all-button').disabled = true;
  $('run-all-button').textContent = 'Assessing…';
  const results = await Promise.all(state.locations.map(async (location) => {
    const reading = readingFor(location);
    if (!reading) return { location, reading: null, error: new Error('Enter drain measurements before assessment.') };
    try {
      const assessment = await request('/assess', { method: 'POST', body: JSON.stringify(reading) });
      state.assessments.set(location.location_id, assessment);
      return { location, reading, assessment };
    } catch (error) { return { location, reading, error }; }
  }));
  renderSites(results);
  const successful = results.filter((item) => item.assessment);
  $('run-all-button').disabled = false;
  $('run-all-button').innerHTML = '<span>▶</span> Assess all sites';
  if (state.selected) {
    const current = state.locations.find((location) => location.location_id === state.selected.location_id);
    if (current && state.selected.ward !== 'Preset scenario') await selectLocation(current, false);
  } else if (state.locations[0]) {
    await selectLocation(state.locations[0], false);
  }
  if (showNotice) notify(`Updated assessments for ${successful.length} monitored sites.`);
}

function renderSites(rows) {
  $('sites-body').innerHTML = rows.map(({ location, reading, assessment, error }) => {
    const level = assessment?.risk_level || 'UNKNOWN';
    const selected = state.selected?.location_id === location.location_id ? ' selected' : '';
    const locationSubline = location.is_search_location
      ? `${location.pincode ? `PIN ${location.pincode} · ` : ''}${[location.admin2, location.admin1].filter(Boolean).join(' · ')} · WEATHER MODEL`
      : `${location.ward} · ${location.city}`;
    return `<tr class="site-row${selected}" data-id="${escapeHtml(location.location_id)}" tabindex="0" role="button" aria-label="Select ${escapeHtml(location.name)}">
      <td><div class="site-name"><span class="site-pin">⌖</span><span>${escapeHtml(location.name)}</span></div><span class="site-ward">${escapeHtml(locationSubline)}</span></td>
      <td><span class="cell-value">${reading ? `${Number(reading.water_level_cm).toFixed(0)} / ${Number(reading.capacity_cm).toFixed(0)} cm` : 'Not entered'}</span></td>
      <td><span class="cell-value">${reading ? `${Number(reading.rainfall_mm_h).toFixed(1)} mm/h · ${state.sensorReadings.get(location.location_id)?.reading?.rainfall_mm_h != null ? 'sensor' : 'model'}` : `${Number(state.weatherByLocation.get(location.location_id)?.rainfall_mm_h_equivalent || 0).toFixed(1)} mm/h · model`}</span></td>
      <td><span class="cell-value">${reading ? `${Number(reading.blockage_pct).toFixed(0)}%` : 'Not entered'}</span></td>
      <td>${error ? `<span class="risk-pill risk-unknown" title="${escapeHtml(error.message)}">ERROR</span>` : assessment ? `<span class="risk-pill ${riskClass(level)}">${escapeHtml(level)} · ${assessment.risk_score}</span>` : '<span class="risk-pill risk-unknown">NEEDS READINGS</span>'}</td>
    </tr>`;
  }).join('');
  document.querySelectorAll('.site-row').forEach((row) => {
    const activate = () => {
      const location = state.locations.find((item) => item.location_id === row.dataset.id);
      if (location) selectLocation(location);
    };
    row.addEventListener('click', activate);
    row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } });
  });
}

async function selectLocation(location, reassess = true) {
  state.selected = location;
  state.baseline = readingFor(location);
  resetSiteWeather();
  $('scenario-select').value = '';
  $('detail-title').textContent = location.name;
  $('detail-subtitle').textContent = location.is_search_location
    ? `${location.pincode ? `PIN ${location.pincode} · ` : ''}${[location.admin2, location.admin1].filter(Boolean).join(', ')} · local weather model`
    : `${location.ward} ward · ${location.drain_type}`;
  $('detail-mode').textContent = state.baseline ? modeLabel(state.baseline.data_mode) : 'WEATHER + INPUTS NEEDED';
  $('sim-baseline-site').textContent = location.name;
  $('simulate-button').disabled = !state.baseline;
  $('assess-button').disabled = !state.baseline;
  $('rain-slider').value = Math.round(state.baseline?.rainfall_mm_h ?? state.siteWeather?.rainfall_mm_h_equivalent ?? 0);
  $('rain-output').textContent = `${$('rain-slider').value} mm/h`;
  $('blockage-slider').value = Math.round(state.baseline?.blockage_pct ?? 0);
  $('blockage-output').textContent = `${$('blockage-slider').value}%`;
  $('sim-results').innerHTML = '<div class="sim-placeholder"><span class="placeholder-icon">↗</span><h3>Compare a scenario</h3><p>Choose a site, adjust rainfall or blockage, then run the comparison to see how the score changes.</p></div>';
  if (state.baseline && (reassess || !state.assessments.has(location.location_id))) await assessSelected(false);
  else if (state.assessments.has(location.location_id)) renderAssessment(state.assessments.get(location.location_id));
  else resetAssessmentView();
  if (location.latitude && location.longitude) {
    const weather = state.weatherByLocation.get(location.location_id);
    if (weather) { state.siteWeather = weather; renderSiteWeather(weather); }
    else await loadSiteWeather(location);
  } else resetSiteWeather();
  renderSites(state.locations.map((item) => ({ location: item, reading: readingFor(item), assessment: state.assessments.get(item.location_id) })));
}

function resetAssessmentView() {
  $('risk-score').textContent = '—';
  $('risk-level').textContent = 'AWAITING READINGS';
  $('risk-level').className = 'risk-pill risk-unknown';
  $('quality-status').textContent = 'Enter local drain readings to assess this location.';
  $('risk-meter-fill').style.width = '100%';
  $('reading-list').innerHTML = '<span class="empty-note">No drain readings have been entered.</span>';
  $('action-list').innerHTML = '<li class="empty-note">Recommendations appear after local readings are assessed.</li>';
  $('factor-list').innerHTML = '<li class="empty-note">Risk factors appear after assessment.</li>';
  $('assessment-time').textContent = '';
}

function resetSiteWeather() {
  state.siteWeather = null;
  $('site-weather-condition').textContent = 'Search for a PIN code, city, or district.';
  $('site-weather-rain').textContent = '—';
  $('site-weather-temp').textContent = '—';
  $('site-weather-humidity').textContent = '—';
  $('site-weather-wind').textContent = '—';
  $('site-weather-time').textContent = 'Current conditions will appear here.';
  $('apply-rain-button').disabled = true;
}

function activateSearchLocation(place, weather) {
  const locationId = `SEARCH-${place.pincode || place.id || `${place.latitude},${place.longitude}`}`;
  const location = {
    location_id: locationId,
    name: place.name || 'Searched location',
    pincode: place.pincode || '',
    admin1: place.admin1 || '',
    admin2: place.admin2 || '',
    latitude: Number(place.latitude),
    longitude: Number(place.longitude),
    timezone: place.timezone || weather.timezone || 'Asia/Kolkata',
    is_search_location: true,
  };
  state.locations = [location];
  state.selected = location;
  state.siteWeather = weather;
  state.weatherByLocation.clear();
  state.weatherByLocation.set(locationId, weather);
  state.liveReadings.clear();
  state.sensorReadings.clear();
  state.manualOverrides.delete(locationId);
  state.assessments.clear();
  try { sessionStorage.setItem('floodora-weather-location', JSON.stringify({ place, query: $('city-search-input').value.trim() })); } catch { /* The dashboard still works when browser storage is disabled. */ }
  state.baseline = null;
  document.body.classList.remove('weather-only');
  $('site-footnote').textContent = 'Weather is live model data. Drain readings are required for risk scoring.';
  $('drain-reading-status').textContent = 'Waiting for live sensor readings or field measurements. No sample drain values are used.';
  $('drain-reading-form').reset();
  $('run-all-button').disabled = true;
  $('assess-button').disabled = true;
  $('simulate-button').disabled = true;
  if (!document.querySelector('#city-search-results .place-result')) {
    $('city-search-results').innerHTML = `<span class="empty-note">Active dashboard location: ${escapeHtml(location.pincode ? `PIN ${location.pincode} · ` : '')}${escapeHtml([location.name, location.admin1].filter(Boolean).join(', '))}. Search another place to switch.</span>`;
  }
  renderWeatherDashboard(location, weather);
  renderSites([{ location, reading: null, assessment: null }]);
  resetAssessmentView();
  $('sim-baseline-site').textContent = [location.name, location.admin1].filter(Boolean).join(', ');
  $('sim-results').innerHTML = '<div class="sim-placeholder"><span class="placeholder-icon">↗</span><h3>Drain readings needed</h3><p>Enter readings above for this PIN before running a location-specific scenario.</p></div>';
  return location;
}

function renderWeatherDashboard(location, weather) {
  const area = [location.name, location.admin2, location.admin1].filter(Boolean).join(', ');
  const pinLabel = location.pincode ? `PIN ${location.pincode}` : 'INDIA LOCATION';
  const observed = formatTime(weather.observed_at);
  $('network-context').textContent = `${pinLabel} · LIVE WEATHER`;
  $('dashboard-title').textContent = `${location.name} weather`;
  $('dashboard-description').textContent = `Current weather model conditions for ${area}. Updated ${observed} (${weather.timezone || location.timezone}).`;
  $('network-data-badge').innerHTML = `<span></span> ${weather.stale ? 'STALE WEATHER MODEL' : weather.cached ? 'CACHED WEATHER MODEL' : 'LIVE WEATHER MODEL'} · ${pinLabel}`;
  $('network-data-badge').classList.toggle('weather-stale', Boolean(weather.stale));
  $('locations-summary-label').textContent = location.pincode ? 'ENTERED PIN CODE' : 'SELECTED LOCATION';
  $('site-count').textContent = location.pincode || location.name;
  $('locations-summary-foot').textContent = area;
  $('risk-summary-label').textContent = 'CURRENT CONDITION';
  $('high-count').textContent = weather.condition || 'Unavailable';
  $('risk-summary-foot').textContent = `Weather code ${weather.weather_code ?? '—'} · model estimate`;
  $('average-summary-label').textContent = `RAIN · LAST ${Math.round(weather.interval_seconds / 60)} MIN`;
  $('average-score').textContent = Number(weather.precipitation_mm || 0).toFixed(2);
  $('weather-summary-unit').textContent = 'mm';
  $('average-summary-foot').textContent = `Hourly rate equivalent ${Number(weather.rainfall_mm_h_equivalent || 0).toFixed(2)} mm/h`;
  $('status-summary-label').textContent = 'WEATHER FEED';
  $('engine-status').textContent = weather.stale ? 'STALE' : weather.cached ? 'CACHED' : 'LIVE';
  const statusPip = document.querySelector('.engine-value .status-pip');
  statusPip.classList.toggle('amber-pip', Boolean(weather.stale));
  statusPip.classList.toggle('green-pip', !weather.stale);
  $('status-summary-foot').textContent = `Observed ${observed} · ${weather.timezone || location.timezone}`;
  $('detail-title').textContent = area;
  $('detail-subtitle').textContent = `${pinLabel} · ${Number(location.latitude).toFixed(4)}, ${Number(location.longitude).toFixed(4)} · ${weather.timezone || location.timezone}`;
  const sensorData = state.sensorReadings.get(location.location_id);
  $('detail-mode').textContent = sensorData?.connected
    ? (sensorData.stale ? 'STALE SENSOR DATA' : state.manualOverrides.has(location.location_id) ? 'SENSOR + FIELD INPUT' : state.liveReadings.get(location.location_id)?.data_mode === 'live' ? 'LIVE SENSOR DATA' : 'LIVE SENSOR + WEATHER')
    : state.liveReadings.has(location.location_id) ? 'WEATHER + ENTERED DRAIN'
    : weather.stale ? 'STALE MODEL' : weather.cached ? 'CACHED MODEL' : 'LIVE MODEL DATA';
  $('sim-baseline-site').textContent = area;
  renderSiteWeather(weather);
  if (location.is_search_location) {
    const reading = state.liveReadings.get(location.location_id);
    if (reading) {
      const sensorRain = state.sensorReadings.get(location.location_id)?.reading?.rainfall_mm_h;
      if (sensorRain == null) reading.rainfall_mm_h = Number(weather.rainfall_mm_h_equivalent || 0);
      reading.data_mode = sensorRain == null ? 'mixed' : 'live';
      state.baseline = { ...reading };
      $('rain-slider').value = Math.max(0, Math.min(100, Math.round(reading.rainfall_mm_h)));
      $('rain-output').textContent = `${$('rain-slider').value} mm/h`;
      renderSites([{ location, reading, assessment: state.assessments.get(location.location_id) }]);
    }
  }
}

async function loadSiteWeather(location, background = false) {
  if (!location?.latitude || !location?.longitude) return resetSiteWeather();
  if (!background) $('site-weather-condition').textContent = 'Updating local conditions…';
  try {
    const weather = await request(`/weather/current?latitude=${encodeURIComponent(location.latitude)}&longitude=${encodeURIComponent(location.longitude)}`);
    state.siteWeather = weather;
    state.weatherByLocation.set(location.location_id, weather);
    if (location.is_search_location) {
      renderWeatherDashboard(location, weather);
      const reading = state.liveReadings.get(location.location_id);
      if (reading) {
        const sensorRain = state.sensorReadings.get(location.location_id)?.reading?.rainfall_mm_h;
        if (sensorRain == null) reading.rainfall_mm_h = Number(weather.rainfall_mm_h_equivalent || 0);
        reading.data_mode = sensorRain == null ? 'mixed' : 'live';
        state.baseline = { ...reading };
        await assessSelected(false);
      }
      renderSites([{ location, reading: reading || null, assessment: state.assessments.get(location.location_id) }]);
      if (!background) notify(`Updated live weather for ${location.name}.`);
      return;
    }
    const reading = {
      ...readingFor(location),
      rainfall_mm_h: weather.rainfall_mm_h_equivalent,
      data_mode: 'mixed',
    };
    state.liveReadings.set(location.location_id, reading);
    if (state.selected?.location_id === location.location_id) renderSiteWeather(weather);
    if (state.selected?.location_id === location.location_id) {
      state.baseline = { ...reading };
      await assessSelected(false);
    }
  } catch (error) {
    if (location.is_search_location) {
      if (state.siteWeather) renderWeatherDashboard(location, { ...state.siteWeather, stale: true });
      $('engine-status').textContent = 'OFFLINE';
      $('status-summary-foot').textContent = `Weather update failed: ${error.message}`;
      $('detail-mode').textContent = 'FEED UNAVAILABLE';
      if (!background) notify(`Weather update failed: ${error.message}`);
    } else if (!background) {
      $('site-weather-condition').textContent = 'Live weather is temporarily unavailable.';
      $('site-weather-time').textContent = error.message;
      $('apply-rain-button').disabled = true;
    }
  }
}

function renderSiteWeather(weather) {
  $('site-weather-condition').textContent = weather.condition || 'Conditions unavailable';
  $('site-weather-rain').textContent = `${Number(weather.precipitation_mm || 0).toFixed(2)} mm / ${Math.round(weather.interval_seconds / 60)} min`;
  $('site-weather-rain-only').textContent = weather.rain_mm == null ? '—' : `${Number(weather.rain_mm).toFixed(2)} mm`;
  $('site-weather-showers').textContent = weather.showers_mm == null ? '—' : `${Number(weather.showers_mm).toFixed(2)} mm`;
  $('site-weather-temp').textContent = weather.temperature_c == null ? '—' : `${Number(weather.temperature_c).toFixed(1)} °C`;
  $('site-weather-humidity').textContent = weather.humidity_pct == null ? '—' : `${Math.round(weather.humidity_pct)}%`;
  $('site-weather-wind').textContent = weather.wind_speed_kmh == null ? '—' : `${Number(weather.wind_speed_kmh).toFixed(0)} km/h`;
  $('site-weather-wind-direction').textContent = weather.wind_direction_deg == null ? '—' : `${Math.round(weather.wind_direction_deg)}° ${windCompass(weather.wind_direction_deg)}`;
  $('site-weather-wind-gusts').textContent = weather.wind_gusts_kmh == null ? '—' : `${Number(weather.wind_gusts_kmh).toFixed(0)} km/h`;
  const updated = weather.observed_at ? new Date(weather.observed_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Update time unavailable';
  $('site-weather-time').textContent = `${weather.stale ? 'Cached data · ' : weather.cached ? 'Cached · ' : ''}${updated} · ${weather.timezone || 'local time'}`;
  const pill = document.querySelector('.weather-live-pill');
  pill.classList.toggle('stale', Boolean(weather.stale));
  pill.innerHTML = `<i></i> ${weather.stale ? 'STALE' : weather.cached ? 'CACHED' : 'LIVE MODEL'}`;
  $('apply-rain-button').disabled = true;
}

function windCompass(degrees) {
  return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(Number(degrees) / 45) % 8];
}

async function applyLiveRainfall() {
  if (!state.siteWeather || !state.baseline || !state.selected) return;
  state.baseline = { ...state.baseline, rainfall_mm_h: state.siteWeather.rainfall_mm_h_equivalent, data_mode: 'mixed' };
  state.liveReadings.set(state.selected.location_id, { ...state.baseline });
  $('detail-mode').textContent = 'LIVE WEATHER + SIMULATED DRAIN';
  $('rain-slider').value = Math.max(0, Math.min(100, Math.round(state.baseline.rainfall_mm_h)));
  $('rain-output').textContent = `${$('rain-slider').value} mm/h`;
  renderSites(state.locations.map((item) => ({ location: item, reading: readingFor(item), assessment: state.assessments.get(item.location_id) })));
  await assessSelected(true);
  notify('Applied local model rainfall. Drain readings remain simulated.');
}

async function searchIndianPlaces(event) {
  event.preventDefault();
  const query = $('city-search-input').value.trim();
  if (query.length < 2) return;
  $('city-search-button').disabled = true;
  $('city-search-results').innerHTML = '<span class="empty-note">Searching Indian locations…</span>';
  $('city-weather-result').innerHTML = '';
  try {
    const data = await request(`/weather/search?q=${encodeURIComponent(query)}`);
    if (!data.results.length) {
      $('city-search-results').innerHTML = /^\d{6}$/.test(query)
        ? '<span class="empty-note">No coordinates were returned for this PIN. Try its post-office or district name, and confirm the backend has been rebuilt and can reach the location providers.</span>'
        : '<span class="empty-note">No matching Indian places found. Try a city, district, or PIN code.</span>';
      return;
    }
    $('city-search-results').innerHTML = `<span class="empty-note">The first result updates the main dashboard location. Choose another result to switch.</span>` + data.results.map((place, index) => `<button class="place-result" type="button" data-place-index="${index}">${escapeHtml(place.name)} <span>${escapeHtml([place.admin1, place.admin2].filter(Boolean).join(', '))}</span></button>`).join('');
    document.querySelectorAll('.place-result').forEach((button) => button.addEventListener('click', () => loadPlaceWeather(data.results[Number(button.dataset.placeIndex)], button)));
    await loadPlaceWeather(data.results[0]);
  } catch (error) {
    $('city-search-results').innerHTML = `<span class="empty-note">Location search failed: ${escapeHtml(error.message)}</span>`;
  } finally { $('city-search-button').disabled = false; }
}

async function loadPlaceWeather(place, button) {
  if (button) {
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
  }
  $('city-weather-result').innerHTML = '<div class="city-weather-card">Loading weather estimate…</div>';
  try {
    const weather = await request(`/weather/current?latitude=${encodeURIComponent(place.latitude)}&longitude=${encodeURIComponent(place.longitude)}`);
    const location = activateSearchLocation(place, weather);
    await loadSensorData(location);
    notify(`Dashboard updated with current weather for ${place.name}.`);
  } catch (error) {
    $('city-weather-result').innerHTML = `<div class="city-weather-card">Weather unavailable: ${escapeHtml(error.message)}</div>`;
    $('engine-status').textContent = 'OFFLINE';
    $('status-summary-foot').textContent = `Weather fetch failed: ${error.message}`;
    $('site-weather-condition').textContent = 'Weather unavailable for this location';
    $('site-weather-time').textContent = error.message;
    $('detail-mode').textContent = 'FEED UNAVAILABLE';
  } finally {
    if (button) { button.disabled = false; button.removeAttribute('aria-busy'); }
  }
}

async function assessSelected(showNotice = true) {
  if (!state.baseline) return;
  try {
    const assessment = await request('/assess', { method: 'POST', body: JSON.stringify(state.baseline) });
    state.assessment = assessment;
    if (state.selected?.location_id) state.assessments.set(state.selected.location_id, assessment);
    renderAssessment(assessment);
    renderSites(state.locations.map((item) => ({ location: item, reading: readingFor(item), assessment: state.assessments.get(item.location_id) })));
    await loadHistory();
    if (showNotice) notify('Location assessment updated.');
  } catch (error) { notify(`Assessment failed: ${error.message}`); }
}

async function saveDrainReadings(event) {
  event.preventDefault();
  const location = state.selected;
  if (!location?.is_search_location) {
    notify('Search and select an Indian location first.');
    return;
  }
  const values = ['drain-water', 'drain-capacity', 'drain-blockage', 'drain-flow'].map((id) => Number($(id).value));
  if (values.some((value) => !Number.isFinite(value))) {
    notify('Enter all four drain measurements to assess this location.');
    return;
  }
  const [waterLevel, capacity, blockage, flowDrop] = values;
  const weather = state.weatherByLocation.get(location.location_id) || state.siteWeather;
  const reading = {
    water_level_cm: waterLevel,
    capacity_cm: capacity,
    rainfall_mm_h: Number(weather?.rainfall_mm_h_equivalent || 0),
    blockage_pct: blockage,
    flow_drop_pct: flowDrop,
    location_id: location.location_id,
    location_name: [location.name, location.admin1].filter(Boolean).join(', '),
    data_mode: 'mixed',
  };
  state.liveReadings.set(location.location_id, reading);
  state.manualOverrides.add(location.location_id);
  location.capacity_cm = capacity;
  state.baseline = { ...reading };
  $('detail-mode').textContent = modeLabel(reading.data_mode);
  $('drain-reading-status').textContent = `Drain values entered for ${location.name}. Rainfall ${reading.rainfall_mm_h.toFixed(1)} mm/h is from the live weather model; drain values are operator-entered.`;
  $('assess-button').disabled = false;
  $('simulate-button').disabled = false;
  $('run-all-button').disabled = false;
  $('rain-slider').value = Math.max(0, Math.min(100, Math.round(reading.rainfall_mm_h)));
  $('rain-output').textContent = `${$('rain-slider').value} mm/h`;
  $('blockage-slider').value = Math.round(blockage);
  $('blockage-output').textContent = `${$('blockage-slider').value}%`;
  renderSites([{ location, reading, assessment: null }]);
  await assessSelected(true);
}

function renderAssessment(assessment) {
  if (!assessment) return;
  $('risk-score').textContent = assessment.risk_score;
  $('risk-level').textContent = assessment.risk_level;
  $('risk-level').className = `risk-pill ${riskClass(assessment.risk_level)}`;
  $('quality-status').textContent = assessment.input_quality_status;
  const sensorData = state.sensorReadings.get(assessment.location_id);
  $('detail-mode').textContent = sensorData?.connected
    ? (sensorData.stale ? 'STALE SENSOR DATA' : state.manualOverrides.has(assessment.location_id) ? 'SENSOR + FIELD INPUT' : assessment.data_mode === 'live' ? 'LIVE SENSOR DATA' : 'LIVE SENSOR + WEATHER')
    : state.selected?.is_search_location ? 'WEATHER + ENTERED DRAIN' : modeLabel(assessment.data_mode);
  $('assessment-time').textContent = `Assessed ${formatTime(assessment.assessment_timestamp)}`;
  $('risk-meter-fill').style.width = `${100 - Math.max(0, Math.min(100, assessment.risk_score))}%`;
  const c = assessment.risk_components;
  $('reading-list').innerHTML = [
    ['Water level', `${Number(state.baseline.water_level_cm).toFixed(0)} / ${Number(state.baseline.capacity_cm).toFixed(0)} cm`, c.water_fill_component],
    ['Rainfall', `${Number(state.baseline.rainfall_mm_h).toFixed(1)} mm/h`, c.rainfall_component],
    ['Blockage', `${Number(state.baseline.blockage_pct).toFixed(0)}%`, c.blockage_component],
    ['Flow drop', `${Number(state.baseline.flow_drop_pct || 0).toFixed(0)}%`, c.flow_drop_component],
  ].map(([label, value, points]) => `<div class="reading-row"><span>${label}</span><b>${value} <span style="color:#a0aaa4;font-size:8px">· ${Number(points).toFixed(1)} pts</span></b></div>`).join('');
  $('action-list').innerHTML = assessment.recommended_action.map((action) => `<li>${escapeHtml(action)}</li>`).join('');
  $('factor-list').innerHTML = assessment.factors.map((factor) => `<li class="factor-chip">${escapeHtml(factor)}</li>`).join('');
}

async function loadSensorData(location, background = false) {
  if (!location?.pincode) {
    return;
  }
  try {
    const data = await request(`/sensors/current?pincode=${encodeURIComponent(location.pincode)}`);
    state.sensorReadings.set(location.location_id, data);
    if (!data.configured || !data.connected) {
      return;
    }
    const reading = data.reading || {};
    const inputIds = { water_level_cm: 'drain-water', capacity_cm: 'drain-capacity', blockage_pct: 'drain-blockage', flow_drop_pct: 'drain-flow' };
    Object.entries(inputIds).forEach(([field, id]) => {
      if (reading[field] !== undefined && reading[field] !== null) $(id).value = reading[field];
    });
    const received = (data.available_fields || []).join(', ') || 'no recognized fields';
    const freshness = data.observed_at ? ` · ${formatTime(data.observed_at)}` : '';
    $('drain-reading-status').textContent = data.message || 'Live sensor telemetry received.';
    if (!data.assessment_ready) {
      const existing = state.liveReadings.get(location.location_id);
      const required = ['water_level_cm', 'capacity_cm', 'blockage_pct', 'flow_drop_pct'];
      const complete = existing && required.every((key) => Number.isFinite(Number(existing[key])));
      if (complete) {
        const sensorRain = reading.rainfall_mm_h;
        const merged = { ...existing, ...reading, rainfall_mm_h: Number(sensorRain ?? state.siteWeather?.rainfall_mm_h_equivalent ?? existing.rainfall_mm_h), data_mode: 'mixed' };
        state.liveReadings.set(location.location_id, merged);
        state.baseline = { ...merged };
        $('assess-button').disabled = false;
        $('simulate-button').disabled = false;
        $('run-all-button').disabled = false;
        renderSites([{ location, reading: merged, assessment: state.assessments.get(location.location_id) }]);
        await assessSelected(false);
      } else {
        state.baseline = null;
        $('assess-button').disabled = true;
        $('simulate-button').disabled = true;
        $('run-all-button').disabled = true;
        resetAssessmentView();
        renderSites([{ location, reading: null, assessment: null }]);
      }
      return;
    }
    state.manualOverrides.delete(location.location_id);
    const weather = state.weatherByLocation.get(location.location_id) || state.siteWeather;
    const sensorRain = reading.rainfall_mm_h;
    const merged = {
      ...reading,
      rainfall_mm_h: Number(sensorRain ?? weather?.rainfall_mm_h_equivalent ?? 0),
      location_id: location.location_id,
      location_name: [location.name, location.admin1].filter(Boolean).join(', '),
      data_mode: sensorRain == null ? 'mixed' : 'live',
      timestamp: data.observed_at || null,
    };
    state.liveReadings.set(location.location_id, merged);
    location.capacity_cm = merged.capacity_cm;
    state.baseline = { ...merged };
    $('detail-mode').textContent = data.stale ? 'STALE SENSOR DATA' : merged.data_mode === 'live' ? 'LIVE SENSOR DATA' : 'LIVE SENSOR + WEATHER';
    $('assess-button').disabled = false;
    $('simulate-button').disabled = false;
    $('run-all-button').disabled = false;
    $('rain-slider').value = Math.max(0, Math.min(100, Math.round(merged.rainfall_mm_h)));
    $('rain-output').textContent = `${$('rain-slider').value} mm/h`;
    $('blockage-slider').value = Math.round(merged.blockage_pct);
    $('blockage-output').textContent = `${$('blockage-slider').value}%`;
    renderSites([{ location, reading: merged, assessment: state.assessments.get(location.location_id) }]);
    await assessSelected(false);
  } catch (error) {
    const previous = state.sensorReadings.get(location.location_id);
    if (previous?.connected) {
      previous.stale = true;
      $('detail-mode').textContent = 'STALE SENSOR DATA';
    } else {
    }
    if (!background) notify(`Could not fetch drain sensor data: ${error.message}`);
  }
}

function renderScenarioOptions() {
  $('scenario-select').innerHTML = '<option value="">Start with selected site</option>' + state.scenarios.map((scenario) => `<option value="${escapeHtml(scenario.id)}">${escapeHtml(scenario.title)}</option>`).join('');
}

function loadPreset() {
  const preset = state.scenarios.find((item) => item.id === $('scenario-select').value);
  if (!preset) return;
  if (!state.baseline) {
    notify('Enter drain readings for the selected PIN before applying a scenario.');
    $('scenario-select').value = '';
    return;
  }
  $('scenario-name').value = preset.default_overrides.scenario_name || preset.title;
  const rain = preset.default_overrides.rainfall_mm_h ?? state.baseline.rainfall_mm_h;
  const blockage = preset.default_overrides.blockage_pct ?? state.baseline.blockage_pct;
  $('rain-slider').value = Math.min(100, Math.round(rain));
  $('rain-output').textContent = `${$('rain-slider').value} mm/h`;
  $('blockage-slider').value = Math.round(blockage);
  $('blockage-output').textContent = `${$('blockage-slider').value}%`;
  $('sim-baseline-site').textContent = `${state.selected.name} · hypothetical ${preset.title}`;
}

async function simulate() {
  if (!state.baseline) return;
  const button = $('simulate-button');
  button.disabled = true;
  button.textContent = 'Comparing…';
  const overrides = {
    rainfall_mm_h: Number($('rain-slider').value),
    blockage_pct: Number($('blockage-slider').value),
    scenario_name: $('scenario-name').value.trim() || 'What-if scenario',
  };
  try {
    const result = await request('/simulate', { method: 'POST', body: JSON.stringify({ baseline: state.baseline, overrides }) });
    renderSimulation(result);
  } catch (error) { notify(`Scenario comparison failed: ${error.message}`); }
  finally { button.disabled = false; button.innerHTML = 'Compare scenario <span>→</span>'; }
}

function renderSimulation(result) {
  const delta = result.score_delta;
  const deltaClass = delta > 0 ? '' : delta < 0 ? 'negative' : 'neutral';
  const deltaText = delta > 0 ? `+${delta}` : String(delta);
  const baseline = result.baseline;
  const scenario = result.scenario;
  const deltas = result.component_deltas;
  const componentRows = [
    ['Water fill', deltas.water_fill_component_delta],
    ['Blockage', deltas.blockage_component_delta],
    ['Rainfall', deltas.rainfall_component_delta],
    ['Flow drop', deltas.flow_drop_component_delta],
  ];
  $('sim-results').innerHTML = `<div>
    <div class="result-top"><span class="result-title">${escapeHtml(result.scenario_name)}</span><span class="delta-badge ${deltaClass}">${deltaText} points · ${escapeHtml(result.direction)}</span></div>
    <div class="comparison">
      <div class="compare-score"><small>BASELINE</small><strong>${baseline.risk_score}</strong><span class="risk-pill ${riskClass(baseline.risk_level)}">${baseline.risk_level}</span></div>
      <div class="compare-arrow">→</div>
      <div class="compare-score"><small>WHAT-IF</small><strong>${scenario.risk_score}</strong><span class="risk-pill ${riskClass(scenario.risk_level)}">${scenario.risk_level}</span></div>
    </div>
    <div class="section-label">CHANGE BY COMPONENT</div>
    <div class="component-deltas">${componentRows.map(([label, value]) => `<div><span>${label}</span><b>${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(1)} pts</b></div>`).join('')}</div>
    <p class="result-summary">${escapeHtml(result.summary)}</p>
  </div>`;
}

async function loadHistory() {
  try {
    const query = state.selected?.location_id && !String(state.selected.location_id).startsWith('SCEN-') ? `?limit=7&location_id=${encodeURIComponent(state.selected.location_id)}` : '?limit=7';
    const history = await request(`/history${query}`);
    $('history-list').innerHTML = history.length ? history.slice(0, 7).map((entry) => `<div class="history-row"><div class="history-main"><b>${escapeHtml(entry.location_name || entry.location_id || 'Drainage assessment')}</b><span>${escapeHtml(modeLabel(entry.data_mode))} · ${escapeHtml(formatTime(entry.assessment_timestamp))}</span></div><span class="risk-pill ${riskClass(entry.risk_level)}">${escapeHtml(entry.risk_level)}</span><span class="history-score">${Number(entry.risk_score)}<small style="color:#a4ada7;font-size:8px"> /100</small></span></div>`).join('') : '<div class="history-empty">No assessments for this location yet.</div>';
  } catch (error) { $('history-list').innerHTML = `<div class="history-empty">History unavailable: ${escapeHtml(error.message)}</div>`; }
}

document.addEventListener('DOMContentLoaded', init);
