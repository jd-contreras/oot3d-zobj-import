// Page logic: collects the mod and game files, decodes voice clips with Web Audio, and drives the
// Python converter running in web/worker.js.
const RATE = 22050;  // voice sample rate (same default as tools/voice.py)
const GAME_NAMES = ['zelda_link_boy_new.zar', 'zelda_link_child_new.zar', 'QueenSound.bcsar'];
const LAYOUT_HELP = {
  citra: 'Extract the zip into Citra\'s mods folder (right-click the game in Citra > Open Mods Location, then go up one folder to load/mods).',
  luma: 'Extract the zip into your Luma luma/titles folder on the SD card, and enable "game patching" in the Luma3DS config.',
  romfs: 'A plain romfs folder, for other loaders or manual installs.',
};

const $ = id => document.getElementById(id);
const worker = new Worker('web/worker.js?v=20261013a');  // bump with index.html's version
const modFiles = new Map();   // name -> File
const gameFiles = new Map();  // game file name -> File
let seedFile = null;          // an OoT3D Randomizer seed's code.ips (gets the Extra Buttons patch)
// Default tunic colours (tools/tunics.py), and the ones picked per age.
const TUNIC_DEFAULTS = { kokiri: '#1ab31a', goron: '#c30819', zora: '#1144bb' };
const TUNIC_LABELS = { kokiri: 'Kokiri', goron: 'Goron', zora: 'Zora' };
const tunicChoice = { adult: { ...TUNIC_DEFAULTS }, child: { kokiri: TUNIC_DEFAULTS.kokiri } };
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
  else if (m.type === 'ready') { workerReady = true; log('Ready.'); scan(); }
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
  const first = [...modFiles.keys()][0] || (seedFile ? 'extra-buttons' : 'mod');
  return first.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]+/g, '_');
}

async function scan() {
  if (!workerReady || !(modFiles.size || seedFile)) return;
  busy = true;
  summary = null;
  $('download').hidden = true;
  refresh();
  log('Reading mod files...');
  let inputs;
  try {
    inputs = await Promise.all([...modFiles.values()].map(async f => ({
      name: f.name, data: new Uint8Array(await f.arrayBuffer()),
    })));
  } catch (e) {
    log('Error: a mod file changed on disk after it was picked. Add it again.');
    busy = false;
    refresh();
    return;
  }
  worker.postMessage({ type: 'scan', inputs });
}

function renderMods() {
  const ul = $('mod-found');
  ul.replaceChildren();
  if (!summary) return;
  if (seedFile) {
    ul.append(li('ok', `Randomizer seed: ${seedFile.name} (Extra Buttons will be added: ZL / ZR = items I / II, D-pad = four more item slots)`));
  }
  for (const age of ['adult', 'child']) {
    const paths = summary.models[age] || [];
    const cap = age[0].toUpperCase() + age.slice(1);
    if (paths.length === 1) ul.append(li('ok', `${cap} model: ${summary.modelNames[paths[0]]}`));
    else if (paths.length > 1)
      ul.append(li('ok', `${cap} models: ${paths.map(p => summary.modelNames[p]).join(', ')} (pick the main one below; the others can lend equipment)`));
  }
  if (summary.clips.length) {
    const ids = new Set(summary.clips.map(c => c[0]));
    ul.append(li('ok', `Voice pack: ${summary.clips.length} clips for ${ids.size} sounds`));
  }
  if (summary.anims) {
    const a = summary.anims;
    const row = li('ok', '');
    row.innerHTML = a.changed.length
      ? `<label><input type="checkbox" id="use-anims" checked> Use the pack's custom animations</label> <span class="muted">(${a.changed.length} changed: ${a.changed.join(', ')})</span>`
      : `Animation bank found, but it doesn't change any animation`;
    ul.append(row);
  }
  for (const n of summary.notes) if (!/equipment source: .*\(model\)/.test(n)) ul.append(li('skip', n));
  if (!Object.keys(summary.models).length && !summary.clips.length && !seedFile)
    ul.append(li('missing', 'No OoT player model or voice clips found in these files.'));
  renderEquipment();
}

// Equipment picker, per age: the main model (when several were added), then where each item comes
// from: the main model, an equipment pack, another model, or OoT3D's own.
const mainChoice = {};

function renderEquipment() {
  const box = $('equipment');
  box.replaceChildren();
  for (const age of ['adult', 'child']) {
    const paths = summary && summary.models[age];
    if (!paths || !paths.length) continue;
    if (!paths.includes(mainChoice[age])) mainChoice[age] = paths[0];
    const fs = document.createElement('fieldset');
    fs.className = 'equip';
    fs.dataset.age = age;
    const cap = age === 'adult' ? 'Adult' : 'Child';
    fs.innerHTML = `<legend>${cap} model and equipment</legend>
      <label class="main-model" ${paths.length > 1 ? '' : 'hidden'}>Main ${age} model <select class="main"></select></label>
      <div class="modes">
        <label><input type="radio" name="mode-${age}" value="all" checked> <span class="all-label"></span></label>
        <label><input type="radio" name="mode-${age}" value="none"> None (OoT3D's)</label>
        <label><input type="radio" name="mode-${age}" value="pick"> Choose per item</label>
      </div>
      <p class="muted">Anything not taken from the model, an equipment pack or another model uses OoT3D's own. Use "None" or choose per item for models that still carry ModLoader64's default N64 equipment.</p>
      <div class="items" hidden></div>
      <div class="hide-back">
        <label><input type="checkbox" value="shield"> Hide shield on back</label>
        <label><input type="checkbox" value="sword"> Hide sword on back</label>
        <span class="muted">Still shown when held. For long hair or a cape they would clip into.</span>
      </div>
      <div class="tunics">
        <span class="tunic-title">${age === 'adult' ? 'Tunic colours' : 'Tunic colour'}</span>
        ${Object.keys(tunicChoice[age]).map(k => `<label>${age === 'adult' ? TUNIC_LABELS[k] : ''}
          <input type="color" data-tunic="${k}" value="${tunicChoice[age][k]}"></label>`).join('')}
        <button type="button" class="small random">Randomize</button>
        <button type="button" class="small secondary reset">Reset</button>
        <span class="muted">Recolours the parts of the model that change with the tunic.${age === 'child' ? ' The child has one tunic, as in the base game.' : ''}</span>
      </div>
      ${age === 'adult' ? `<label class="child-bgs"><input type="checkbox" class="oot3d-scabbard"> Use OoT3D Biggoron scabbard
        <span class="muted">(the Biggoron hilt still comes from your choice; default: the model's Master Sword sheath)</span></label>` : ''}
      ${age === 'child' ? `<label class="child-bgs"><input type="checkbox" class="child-biggoron"> Import child Biggoron Sword
        <span class="muted">(the adult model's Biggoron Sword, held right side up, replaces the pedestal Master Sword the game also uses for a child holding the Biggoron Sword)</span></label>` : ''}`;
    const sel = fs.querySelector('select.main');
    for (const p of paths) {
      const o = document.createElement('option');
      o.value = p;
      o.textContent = summary.modelNames[p];
      o.selected = p === mainChoice[age];
      sel.append(o);
    }
    sel.addEventListener('change', () => { mainChoice[age] = sel.value; fillItems(fs, age); });
    const pickers = [...fs.querySelectorAll('.tunics input')];
    const setTunics = fn => pickers.forEach(p => { p.value = tunicChoice[age][p.dataset.tunic] = fn(p.dataset.tunic); });
    pickers.forEach(p => p.addEventListener('input', () => { tunicChoice[age][p.dataset.tunic] = p.value; }));
    fs.querySelector('.tunics .random').addEventListener('click', () => setTunics(randomColor));
    fs.querySelector('.tunics .reset').addEventListener('click', () => setTunics(k => TUNIC_DEFAULTS[k]));
    fs.addEventListener('change', () => {
      fs.querySelector('.items').hidden = fs.querySelector('input[type=radio]:checked').value !== 'pick';
    });
    fillItems(fs, age);
    box.append(fs);
  }
}

function randomColor() {
  return '#' + [0, 0, 0].map(() => Math.floor(Math.random() * 256).toString(16).padStart(2, '0')).join('');
}

// {age: {tunic: [r, g, b]}} for the converter.
function tunicColors() {
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return Object.fromEntries(Object.entries(tunicChoice).map(
    ([age, cols]) => [age, Object.fromEntries(Object.entries(cols).map(([k, hex]) => [k, rgb(hex)]))]));
}

function fillItems(fs, age) {
  const opts = summary.equipment[age][mainChoice[age]];
  const items = fs.querySelector('.items');
  items.replaceChildren();
  const hasPaks = opts.some(o => o[2].some(s => s !== 'model' && !summary.models[age].includes(s)));
  fs.querySelector('.all-label').textContent = hasPaks ? 'Equipment packs, then the model' : 'All from the model';
  for (const [key, label, srcs, def] of opts) {
    const row = document.createElement('label');
    row.className = 'item';
    const sel = document.createElement('select');
    sel.dataset.key = key;
    for (const src of [...srcs, 'oot3d']) {
      const o = document.createElement('option');
      o.value = src;
      o.textContent = src === 'model' ? 'The model' : src === 'oot3d' ? 'OoT3D' : summary.paks[src] || src;
      o.selected = src === def;
      sel.append(o);
    }
    row.append(label, sel);
    items.append(row);
  }
}

function equipmentChoice() {
  const out = {};
  for (const fs of document.querySelectorAll('fieldset.equip')) {
    const mode = fs.querySelector('input[type=radio]:checked').value;
    out[fs.dataset.age] = mode === 'all' ? 'all' : mode === 'none' ? [] :
      Object.fromEntries([...fs.querySelectorAll('.items select')].map(s => [s.dataset.key, s.value]));
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
  if (seedFile) ul.append(li('ok', `${seedFile.name} (randomizer seed)`));
}

function refresh() {
  renderGame();
  const ready = workerReady && summary && clips && (summary.need.length || seedFile) &&
    summary.need.every(n => gameFiles.has(n));
  $('convert').disabled = busy || !ready;
  $('layout-help').textContent = LAYOUT_HELP[$('layout').value];
}

function addModFiles(list) {
  for (const f of list) {
    // a randomizer seed's files are kept apart from the mod files the converter scans
    if (/\.ips$/i.test(f.name)) seedFile = f;
    else modFiles.set(f.name, f);
  }
  const ul = $('mod-found');
  const names = [...modFiles.keys(), ...(seedFile ? [seedFile.name] : [])];
  ul.replaceChildren(...names.map(n => li('muted', n)));
  if (!workerReady) log('Waiting for Python to load...');
  scan();
}

function addGameFiles(list) {
  let seedAdded = false;
  for (const f of list) {
    if (/\.ips$/i.test(f.name)) { seedFile = f; seedAdded = true; continue; }  // a randomizer seed's code.ips
    if (!GAME_NAMES.includes(f.name)) continue;
    if (!f.size) { log(`Skipped ${f.name}: it is empty (0 bytes).`); continue; }
    gameFiles.set(f.name, f);
  }
  if (seedAdded) scan();  // the seed is listed with the mod files too
  else refresh();
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
  let game, seed;
  try {
    if (seedFile) seed = new Uint8Array(await seedFile.arrayBuffer());
    game = await Promise.all(summary.need.map(async n => {
      const f = gameFiles.get(n);
      if (!f.size) throw new Error(`${n} is empty (0 bytes). Pick the original from your extracted OoT3D romfs (actor/${n}).`);
      return [n, new Uint8Array(await f.arrayBuffer())];
    }));
  } catch (e) {
    // e.g. the file was moved, renamed or changed on disk after it was picked
    log('Error: ' + (e.name === 'NotFoundError' || e.name === 'NotReadableError'
      ? 'a file changed on disk after it was picked. Pick it again.' : e.message));
    busy = false;
    refresh();
    return;
  }
  worker.postMessage({
    type: 'convert', game, clips, seed,
    options: {
      tunics: tunicColors(),
      rate: RATE, layout: $('layout').value, region: $('region').value, equipment: equipmentChoice(),
      main: { ...mainChoice },
      childBiggoron: !!document.querySelector('.child-biggoron:checked'),
      animations: !!document.querySelector('#use-anims:checked'),
      oot3dScabbard: !!document.querySelector('.oot3d-scabbard:checked'),
      hideBack: Object.fromEntries([...document.querySelectorAll('fieldset.equip')].map(
        fs => [fs.dataset.age, [...fs.querySelectorAll('.hide-back input:checked')].map(i => i.value)])),
    },
  });
});

refresh();
