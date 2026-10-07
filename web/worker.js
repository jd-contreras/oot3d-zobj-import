// Runs the Python converter (tools/*.py) in Pyodide, off the page's main thread.
// Messages in:  {type: 'scan', inputs: [{name, data}]}
//               {type: 'convert', game: [[name, Uint8Array]], clips: [Int16Array], options}
// Messages out: {type: 'log', text} | {type: 'ready'} | {type: 'scanned', ...} | {type: 'done', zip, report}
//               | {type: 'error', text}
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/';
const TOOLS = ['build', 'voice', 'pack', 'ml64pak', 'zobj', 'cmb', 'cmbskel', 'pose', 'cmbwrite',
  'cmabwrite', 'texenc', 'csab', 'zar', 'pica', 'fit', 'tunics', 'csar', 'voicemap', 'dspadpcm', 'equippak',
  'animconv', 'n64anim', 'anim_tables', 'animview', 'cmbview', 'render'];

importScripts(PYODIDE + 'pyodide.js', 'dspadpcm.js');
self.dspEncode = dspEncode;  // tools/dspadpcm.py picks this up instead of its pure-Python loop

const log = text => postMessage({ type: 'log', text: String(text) });
let py = null;
let scanned = null;  // Python state between scan and convert

async function init() {
  log('Loading Python (first time takes a moment)...');
  py = await loadPyodide({ indexURL: PYODIDE });
  await py.loadPackage(['numpy', 'pillow']);
  py.FS.mkdir('/tools');
  await Promise.all(TOOLS.map(async name => {
    const r = await fetch(`../tools/${name}.py`, { cache: 'no-cache' });  // always the current converter
    if (!r.ok) throw new Error(`could not load tools/${name}.py`);
    py.FS.writeFile(`/tools/${name}.py`, await r.text());
  }));
  py.globals.set('js_log', log);
  py.runPython(`
import sys
sys.path.insert(0, '/tools')
import pack, build, voice
`);
  postMessage({ type: 'ready' });
}
const ready = init().catch(e => postMessage({ type: 'error', text: String(e) }));

onmessage = async ev => {
  await ready;
  const msg = ev.data;
  try {
    if (msg.type === 'scan') {
      py.globals.set('js_inputs', msg.inputs);
      const res = py.runPython(`
files = {}
for item in js_inputs:
    files.update(pack.expand(item.name, item.data.to_bytes()))
models, clips, notes, paks, cands = pack.plan(files)
clip_list = [(sid, i, name, data) for sid in sorted(clips) for i, (name, data) in enumerate(clips[sid])]
need = [build.target_zar(age) for age in models] + (['QueenSound.bcsar'] if clips else [])
# equipment choices for every possible main model (the other models of that age lend equipment)
equipment, names = {}, {}
for age, paths in cands.items():
    equipment[age] = {}
    for main_path in paths:
        m2, _, _, p2, _ = pack.plan(files, {age: main_path})
        names.update(pack.pak_names(p2))
        opts = pack.equipment_options({age: m2[age]}, p2)[age]
        equipment[age][main_path] = [[k, label, list(srcs), default] for k, label, srcs, default in opts]
{'models': {age: list(paths) for age, paths in cands.items()},
 'modelNames': {p: pack.model_name(p) for paths in cands.values() for p in paths},
 'need': need, 'notes': notes, 'equipment': equipment, 'paks': names,
 'anims': (lambda b: {'path': b[0], 'changed': b[2]} if b else None)(pack.anim_bank(files)),
 'clips': [('%04X' % sid, name) for sid, i, name, _ in clip_list]}
`);
      const summary = res.toJs({ dict_converter: Object.fromEntries });
      res.destroy();
      // hand the clip files back for decoding in the page (Web Audio is not available in workers)
      const cd = py.runPython('from pyodide.ffi import to_js\nto_js([memoryview(d) for _, _, _, d in clip_list])');
      const clipData = Array.from(cd, b => b.slice());  // copy out of Python's memory
      scanned = true;
      postMessage({ type: 'scanned', summary, clipData });
    } else if (msg.type === 'convert') {
      if (!scanned) throw new Error('scan the mod files first');
      py.globals.set('js_game', msg.game);
      py.globals.set('js_clips', msg.clips);
      py.globals.set('js_opts', msg.options);
      const res = py.runPython(`
import numpy as np
game = {pair[0]: pair[1].to_bytes() for pair in js_game}
opts = js_opts.to_py()
pcm = [np.frombuffer(c.to_bytes(), dtype='<i2').astype(np.int64) for c in js_clips]
decoded = {}
for (sid, i, name, data), p in zip(clip_list, pcm):
    decoded[data] = p
out, report = pack.make_mod(files, game, opts['rate'], opts['layout'], opts['region'],
                            decode=lambda d: decoded[d], log=js_log,
                            equipment={age: None if v == 'all' else v for age, v in (opts.get('equipment') or {}).items()},
                            hide_back={age: set(kinds) for age, kinds in (opts.get('hideBack') or {}).items()},
                            main=opts.get('main') or {}, child_biggoron=bool(opts.get('childBiggoron')),
                            animations=bool(opts.get('animations', True)))
from pyodide.ffi import to_js
to_js([memoryview(pack.zip_bytes(out)), '\\n'.join(report)])
`);
      const zip = res[0].slice();  // copy out of Python's memory
      const report = res[1];
      postMessage({ type: 'done', zip, report }, [zip.buffer]);
    }
  } catch (e) {
    postMessage({ type: 'error', text: String(e.message || e) });
  }
};
