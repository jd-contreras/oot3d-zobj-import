// Page logic: collects the mod and game files, decodes voice clips with Web Audio, and drives the
// Python converter running in web/worker.js.
const RATE = 22050;  // voice sample rate (same default as tools/voice.py)
const GAME_NAMES = ['zelda_link_boy_new.zar', 'zelda_link_child_new.zar', 'QueenSound.bcsar'];
const LAYOUT_HELP = {
  citra: 'Extract the zip into Citra\'s mods folder (right-click the game in Citra > Open Mods Location, then go up one folder to load/mods).',
  luma: 'Extract the zip to the root of your SD card and enable "game patching" in the Luma3DS config.',
  romfs: 'A plain romfs folder, for other loaders or manual installs.',
};

const $ = id => document.getElementById(id);
const worker = new Worker('web/worker.js');
const modFiles = new Map();   // name -> File
const gameFiles = new Map();  // game file name -> File
let summary = null;           // from the worker's scan
let clips = null;             // decoded voice clips (Int16Array), in scan order
let workerReady = false, busy = false;

function log(text) {
  const el = $('log');
  el.textContent += text + '\n';
  el.scrollTop = el.scrollHeight;
}
function li(cls, text) {
  const e = document.createElement('li');
  e.className = cls;
  e.textContent = text;
  return e;
}

worker.onmessage = async ev => {
  const m = ev.data;
  if (m.type === 'log') log(m.text);
  else if (m.type === 'ready') { workerReady = true; log('Ready.'); if (modFiles.size) scan(); }
  else if (m.type === 'error') { log('Error: ' + m.text); busy = false; refresh(); }
  else if (m.type === 'scanned') {
    summary = m.summary;
    clips = null;
    renderMods();
    if (m.clipData.length) {
      log(`Decoding ${m.clipData.length} voice clips...`);
      try {
        clips = await Promise.all(m.clipData.map(decodeClip));
        log('Voice clips decoded.');
      } catch (e) {
        log('Could not decode a voice clip in this browser: ' + e);
      }
    } else clips = [];
    busy = false;
    refresh();
  } else if (m.type === 'done') {
    const blob = new Blob([m.zip], { type: 'application/zip' });
    const a = $('download');
    if (a.href) URL.revokeObjectURL(a.href);
    a.href = URL.createObjectURL(blob);
    a.download = 'oot3d-' + modName() + '.zip';
    a.hidden = false;
    log('Done. ' + (blob.size / 1048576).toFixed(1) + ' MB');
    busy = false;
    refresh();
  }
};

async function decodeClip(bytes) {
  const ctx = new OfflineAudioContext(1, 1, RATE);
  const buf = await ctx.decodeAudioData(bytes.slice().buffer);  // resampled to RATE
  const n = buf.length, out = new Int16Array(n);
  const ch = [...Array(buf.numberOfChannels).keys()].map(c => buf.getChannelData(c));
  for (let i = 0; i < n; i++) {
    let v = 0;
    for (const c of ch) v += c[i];
    v = v / ch.length;
    out[i] = Math.max(-32768, Math.min(32767, Math.round(v * 32768)));
  }
  return out;
}

function modName() {
  const first = [...modFiles.keys()][0] || 'mod';
  return first.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]+/g, '_');
}

async function scan() {
  if (!workerReady || !modFiles.size) return;
  busy = true;
  summary = null;
  $('download').hidden = true;
  refresh();
  log('Reading mod files...');
  const inputs = await Promise.all([...modFiles.values()].map(async f => ({
    name: f.name, data: new Uint8Array(await f.arrayBuffer()),
  })));
  worker.postMessage({ type: 'scan', inputs });
}

function renderMods() {
  const ul = $('mod-found');
  ul.replaceChildren();
  if (!summary) return;
  for (const age of ['adult', 'child'])
    if (summary.models[age]) ul.append(li('ok', `${age[0].toUpperCase() + age.slice(1)} model: ${summary.models[age]}`));
  if (summary.clips.length) {
    const ids = new Set(summary.clips.map(c => c[0]));
    ul.append(li('ok', `Voice pack: ${summary.clips.length} clips for ${ids.size} sounds`));
  }
  for (const n of summary.notes) ul.append(li('skip', n));
  if (!Object.keys(summary.models).length && !summary.clips.length)
    ul.append(li('missing', 'No OoT player model or voice clips found in these files.'));
  renderEquipment();
}

// Equipment picker: per model, use all / none / some of its N64 items; the rest stay OoT3D's.
function renderEquipment() {
  const box = $('equipment');
  box.replaceChildren();
  for (const age of ['adult', 'child']) {
    const opts = summary && summary.equipment[age];
    if (!opts) continue;
    const fs = document.createElement('fieldset');
    fs.className = 'equip';
    fs.dataset.age = age;
    fs.innerHTML = `<legend>${age === 'adult' ? 'Adult' : 'Child'} model equipment</legend>
      <div class="modes">
        <label><input type="radio" name="mode-${age}" value="all" checked> All from the model</label>
        <label><input type="radio" name="mode-${age}" value="none"> None (OoT3D's)</label>
        <label><input type="radio" name="mode-${age}" value="pick"> Choose</label>
      </div>
      <p class="muted">Items not taken from the model use OoT3D's own. Pick "None" or untick items for models that still carry ModLoader64's default N64 equipment.</p>
      <div class="items" hidden></div>`;
    const items = fs.querySelector('.items');
    for (const [key, label, have] of opts) {
      const l = document.createElement('label');
      l.innerHTML = `<input type="checkbox" value="${key}" ${have ? 'checked' : 'disabled'}> ${label}` +
        (have ? '' : ' <span class="muted">(not in this model)</span>');
      items.append(l);
    }
    fs.addEventListener('change', () => {
      items.hidden = fs.querySelector('input[type=radio]:checked').value !== 'pick';
    });
    box.append(fs);
  }
}

function equipmentChoice() {
  const out = {};
  for (const fs of document.querySelectorAll('fieldset.equip')) {
    const mode = fs.querySelector('input[type=radio]:checked').value;
    out[fs.dataset.age] = mode === 'all' ? null : mode === 'none' ? [] :
      [...fs.querySelectorAll('.items input:checked')].map(i => i.value);
  }
  return out;
}

function renderGame() {
  const ul = $('game-found');
  ul.replaceChildren();
  if (!summary) { ul.append(li('muted', 'Add mod files first to see which game files are needed.')); return; }
  const where = { 'QueenSound.bcsar': 'sound/' };
  for (const n of summary.need)
    ul.append(gameFiles.has(n) ? li('ok', n) : li('missing', `${n} (romfs/${where[n] || 'actor/'}${n})`));
}

function refresh() {
  renderGame();
  const ready = workerReady && summary && clips && summary.need.length &&
    summary.need.every(n => gameFiles.has(n));
  $('convert').disabled = busy || !ready;
  $('layout-help').textContent = LAYOUT_HELP[$('layout').value];
}

function addModFiles(list) {
  for (const f of list) modFiles.set(f.name, f);
  const ul = $('mod-found');
  ul.replaceChildren(...[...modFiles.keys()].map(n => li('muted', n)));
  if (!workerReady) log('Waiting for Python to load...');
  scan();
}

function addGameFiles(list) {
  for (const f of list) if (GAME_NAMES.includes(f.name)) gameFiles.set(f.name, f);
  refresh();
}

$('mod-input').addEventListener('change', e => addModFiles(e.target.files));
const drop = $('mod-drop');
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); addModFiles(e.dataTransfer.files); });
$('game-files').addEventListener('change', e => addGameFiles(e.target.files));
$('game-folder').addEventListener('change', e => addGameFiles(e.target.files));
$('layout').addEventListener('change', refresh);

$('convert').addEventListener('click', async () => {
  busy = true;
  $('download').hidden = true;
  refresh();
  log('Converting (this can take a few minutes)...');
  const game = await Promise.all(summary.need.map(async n => [n, new Uint8Array(await gameFiles.get(n).arrayBuffer())]));
  worker.postMessage({
    type: 'convert', game, clips,
    options: { rate: RATE, layout: $('layout').value, region: $('region').value, equipment: equipmentChoice() },
  });
});

refresh();
