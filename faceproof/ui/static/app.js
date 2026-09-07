/* FaceProof dashboard client.
 *
 * This file renders. It does not compute. Every score, hash, root, proof,
 * transaction and verdict shown here is read from a JSON artifact that the
 * Python pipeline wrote; the only numbers computed in the browser are bar
 * widths and elapsed seconds. If the backend abstains, the abstain is what
 * gets drawn — there is no success path that can be reached without one.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined && txt !== null) n.textContent = String(txt);
  return n;
};
const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };

const STATE = { app: null, job: null, cursor: 0, poll: null, run: null, selected: null };

/* ── tiny helpers ─────────────────────────────────────────────── */

const short = (h, n = 10) =>
  (typeof h === 'string' && h.length > n * 2 + 3) ? `${h.slice(0, n)}…${h.slice(-6)}` : (h ?? '—');

const num = (v) => (v === null || v === undefined || v === '') ? null : Number(v);

function tag(text, kind) { return el('span', `tag ${kind}`, text); }

function okTag(ok) {
  if (ok === null || ok === undefined) return tag('—', 'na');
  return tag(ok ? 'PASS' : 'FAIL', ok ? 'pass' : 'fail');
}

function kv(pairs) {
  const dl = el('dl', 'kv');
  for (const [k, v] of pairs) {
    if (v === undefined) continue;
    dl.appendChild(el('dt', null, k));
    dl.appendChild(el('dd', null, v === null || v === '' ? '—' : v));
  }
  return dl;
}

function banner(kind, text) { return el('div', `banner ${kind}`, text); }

/** Syntax-highlight JSON without innerHTML on untrusted text. */
function jsonBlock(obj) {
  const pre = el('pre', 'json');
  const text = JSON.stringify(obj, null, 2);
  const re = /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) pre.appendChild(document.createTextNode(text.slice(last, m.index)));
    const cls = m[1] ? 'k' : m[2] ? 's' : m[3] ? 'n' : 'b';
    pre.appendChild(el('span', cls, m[0]));
    last = re.lastIndex;
  }
  pre.appendChild(document.createTextNode(text.slice(last)));
  return pre;
}

function metric(name, value, threshold, higherIsBetter = true) {
  const v = num(value), t = num(threshold);
  const box = el('div', 'metric');
  const top = el('div', 'top');
  top.appendChild(el('span', null, name));
  const b = el('b', null, v === null ? '—' : v);
  top.appendChild(b);
  box.appendChild(top);
  if (v !== null && t !== null) {
    const pass = higherIsBetter ? v >= t : v <= t;
    const frac = Math.max(0.03, Math.min(1, higherIsBetter ? v / (t * 2) : t / Math.max(v, 1e-9) / 2));
    const bar = el('div', 'bar');
    const fill = el('i', pass ? '' : 'bad');
    fill.style.width = `${(frac * 100).toFixed(1)}%`;
    bar.appendChild(fill);
    box.appendChild(bar);
    box.appendChild(el('div', 'note', `${higherIsBetter ? 'min' : 'max'} ${t} · ${pass ? 'pass' : 'FAIL'}`));
  }
  return box;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

/* ── header ───────────────────────────────────────────────────── */

function renderHeader() {
  const a = STATE.app, box = clear($('hdr-badges'));
  if (!a) return;

  const mk = (label, value, kind) => {
    const b = el('span', `badge${kind ? ' ' + kind : ''}`);
    b.appendChild(el('span', null, label));
    b.appendChild(el('b', null, value));
    return b;
  };

  const c = a.chain;
  box.appendChild(mk('chain', `${c.chain}${c.chain_id ? ' · ' + c.chain_id : ''}`,
    c.rpc_configured ? 'ok' : 'warn'));
  box.appendChild(mk('accept_at', a.calibration.in_force ?? a.chain.accept_at,
    a.calibration.present ? 'ok' : 'warn'));
  box.appendChild(mk('index', a.index.present ? 'built' : 'absent',
    a.index.present ? 'ok' : 'warn'));
  box.appendChild(mk('key', c.private_key_present ? 'in env' : 'absent',
    c.private_key_present ? 'ok' : ''));
  box.appendChild(mk('model', a.config.model_id ? 'buffalo_l' : '—'));

  const st = el('span', 'badge');
  st.appendChild(el('span', 'dot' + (STATE.job && STATE.job.status === 'running' ? ' run' : '')));
  st.appendChild(el('span', null, STATE.job ? STATE.job.status : 'idle'));
  box.appendChild(st);
}

/* ── left column ──────────────────────────────────────────────── */

function renderConsent() {
  const a = STATE.app, body = clear($('consent-body'));
  const subs = a.subjects || [];
  $('consent-count').textContent = `${subs.length} subject${subs.length === 1 ? '' : 's'}`;
  if (!subs.length) {
    body.appendChild(el('div', 'note',
      'No consent on record. Stage 1 refuses before any biometric processing.'));
  } else {
    for (const s of subs) {
      const row = el('div', 'run');
      row.appendChild(el('span', 'id', s.subject_id));
      const t = tag(s.valid ? 'valid' : String(s.reason || 'invalid'), s.valid ? 'pass' : 'fail');
      t.classList.add('o'); row.appendChild(t);
      body.appendChild(row);
    }
    body.appendChild(el('div', 'note',
      `scope ${subs[0].scope} · expires ${subs[0].expires_at}`));
  }
  const btns = el('div', 'btn-row');
  const g = el('button', null, 'Grant consent');
  g.onclick = () => consentAction('grant');
  const r = el('button', 'danger', 'Revoke + forget');
  r.onclick = () => consentAction('revoke');
  btns.append(g, r);
  body.appendChild(btns);
}

async function consentAction(action) {
  const subject = $('in-subject').value.trim();
  if (!subject) return;
  if (action === 'revoke' &&
      !confirm(`Revoke consent for "${subject}" and destroy its salt? This is irreversible.`)) return;
  try {
    const { job_id } = await api('/api/consent', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, subject }),
    });
    watch(job_id);
  } catch (e) { logLocal(`consent ${action} failed: ${e.message}`, 'error'); }
}

function renderCalibration() {
  const c = STATE.app.calibration, body = clear($('calib-body'));
  $('calib-src').textContent = c.present ? 'data/calibration.json' : 'not measured';

  if (!c.present) {
    body.appendChild(banner('warn',
      'No calibration measured — the 0.55 placeholder is in force. ' +
      'Run: python -m faceproof.calibrate data/calib'));
    return;
  }

  body.appendChild(kv([
    ['accept_at', c.in_force],
    ['rule', c.rule],
    ['subjects', `${c.dataset.n_subjects} · ${c.dataset.n_images} images`],
    ['genuine', `n=${c.genuine.n}  mean ${c.genuine.mean}  min ${c.genuine.min}`],
    ['impostor', `n=${c.impostor.n}  mean ${c.impostor.mean}  max ${c.impostor.max}`],
    ['separation', c.separation],
    ['TAR / FAR', `${c.true_accept_rate} / ${c.false_accept_rate}`],
    ['measured', c.measured_at],
    ['fingerprint', short(c.dataset.fingerprint, 8)],
  ]));

  if (c.env_override) {
    body.appendChild(banner('warn',
      'FACEPROOF_ACCEPT_AT is set — the environment overrides the measured value.'));
  }
  if (c.overlap_warning) {
    body.appendChild(banner('warn', 'Genuine and impostor distributions overlap.'));
  }
  if (c.dataset.n_subjects < 5) {
    body.appendChild(el('div', 'note warn',
      `Small sample: ${c.dataset.n_subjects} subjects / ${c.impostor.n} impostor pairs. ` +
      `The threshold is genuinely measured, but a ${c.impostor.max} impostor maximum on ` +
      `this few pairs is a weak upper bound — treat ${c.suggested_accept_at} as provisional.`));
  }
}

function renderCorpus() {
  const i = STATE.app.index, body = clear($('corpus-body'));
  if (i.present && i.snapshot) {
    const s = i.snapshot;
    body.appendChild(kv([
      ['snapshot', short(s.snapshot_id, 8)],
      ['faces', s.n_faces], ['images', s.n_images], ['authors', s.n_authors],
      ['model', s.model_id],
    ]));
  } else {
    body.appendChild(banner('abstain',
      'No FAISS index. Channel A cannot search, so Stage 2 will honestly ABSTAIN. ' +
      'This is the correct behaviour, not a failure.'));
    body.appendChild(el('div', 'note',
      `faiss ${i.faiss ? 'available' : 'NOT installed'} · build with the handles of consenting accounts:`));
    const inp = el('input'); inp.type = 'text'; inp.id = 'in-handles';
    inp.placeholder = 'alice.bsky.social bob.bsky.social';
    body.appendChild(inp);
    const b = el('button', null, 'Build corpus');
    b.onclick = async () => {
      const handles = inp.value.split(/[\s,]+/).filter(Boolean);
      try {
        const { job_id } = await api('/api/corpus', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ handles }),
        });
        watch(job_id);
      } catch (e) { logLocal(`corpus build failed: ${e.message}`, 'error'); }
    };
    body.appendChild(el('div', 'btn-row')).appendChild(b);
  }
}

function renderRuns() {
  const runs = STATE.app.runs || [], list = clear($('runs-list'));
  $('runs-count').textContent = runs.length;
  const kinds = { anchored: 'pass', bundle: 'warn', abstain: 'abstain', 'probe-only': 'na', incomplete: 'na' };
  for (const r of runs.slice(0, 40)) {
    const row = el('div', 'run' + (STATE.selected === r.run_id ? ' sel' : ''));
    row.appendChild(el('span', 'id', r.run_id));
    const t = tag(r.outcome, kinds[r.outcome] || 'na'); t.classList.add('o');
    row.appendChild(t);
    row.onclick = () => loadRun(r.run_id);
    list.appendChild(row);
  }
  if (!runs.length) list.appendChild(el('div', 'note', 'No runs under out/ yet.'));
}

/* ── pipeline rail ────────────────────────────────────────────── */

const STEP_LABEL = {
  consent: 'Consent', stage1: 'Stage 1 probe', stage2: 'Stage 2 discovery',
  stage3: 'Stage 3 bundle', anchor: 'Anchor', verify: 'Verify', tamper: 'Tamper',
};
const STEP_TEXT = {
  pending: 'pending', running: 'running…', pass: 'PASS', fail: 'FAIL',
  abstain: 'ABSTAIN', skipped: 'skipped',
};

function renderRail(steps) {
  const rail = clear($('rail'));
  for (const s of steps) {
    const box = el('div', `step ${s.status}`);
    box.appendChild(el('div', 'n', STEP_LABEL[s.name] || s.name));
    box.appendChild(el('div', 's', STEP_TEXT[s.status] || s.status));
    if (s.reason) box.appendChild(el('div', 'note', s.reason));
    rail.appendChild(box);
  }
}

function renderVerdict(job) {
  const box = clear($('verdict'));
  if (!job) return;
  $('rail-sub').textContent = `${job.kind || 'run'} · ${job.elapsed ?? '—'}s`;
  const r = job.result || {};

  if (job.status === 'error') {
    box.appendChild(banner('fail', `ERROR — ${job.error}`));
    return;
  }
  if (r.outcome === 'ABSTAIN') {
    box.appendChild(banner('abstain',
      'ABSTAIN — the pipeline declined to assert a match. No bundle, no proofs, ' +
      'no receipt were produced. This is a real outcome, not an error.'));
  } else if (r.outcome === 'VERIFIED') {
    box.appendChild(banner('ok', 'VERIFIED — every re-verification check passed.'));
  } else if (r.outcome === 'FAILED') {
    box.appendChild(banner('fail', 'FAILED — at least one verification check did not pass.'));
  }
  if (r.synthetic) {
    box.appendChild(banner('warn',
      'Stage 2 used the LABELLED SYNTHETIC fixture (source: synthetic-stub). ' +
      'The cryptography below is real; the match it describes is not a real person.'));
  }
}

/* ── stage renderers ──────────────────────────────────────────── */

function stepOf(job, name) {
  return (job && job.steps || []).find((s) => s.name === name) || { status: 'pending' };
}


/* ── photographs ──────────────────────────────────────────────────
 * Two content-addressed endpoints, never a filesystem path:
 *   /api/probe-image?id=<run>       the probe, from the run directory
 *   /api/corpus-image?sha256=<hex>  an indexed corpus image, by digest
 * A candidate photo is only ever shown for a candidate the search really
 * returned; nothing here can invent one.
 */

function photo(src, captionNodes, cls) {
  const box = el('div', 'photo' + (cls ? ' ' + cls : ''));
  const im = el('img');
  im.src = src;
  im.alt = '';
  im.loading = 'lazy';
  im.onerror = () => {
    box.classList.add('none');
    clear(box).appendChild(el('div', 'cap', 'image not available'));
    for (const n of captionNodes) box.appendChild(n);
  };
  box.appendChild(im);
  for (const n of captionNodes) box.appendChild(n);
  return box;
}

function caption(lines) {
  const c = el('div', 'cap');
  lines.forEach((l, i) => {
    if (i) c.appendChild(document.createElement('br'));
    if (Array.isArray(l)) { c.appendChild(el('b', null, l[0] + ' ')); c.appendChild(document.createTextNode(l[1])); }
    else c.appendChild(document.createTextNode(l));
  });
  return [c];
}

function noPhoto(text) {
  const box = el('div', 'photo none');
  box.appendChild(el('div', 'cap', text));
  return box;
}

function renderStage1(job) {
  const body = clear($('stage1-body'));
  const card = $('c-stage1');
  card.className = 'card';
  const st = stepOf(job, 'stage1');
  const probe = (job.result || {}).probe || (STATE.run && STATE.run.artifacts['probe.json']);
  if (!probe) { body.appendChild(el('div', 'empty', 'No probe.json.')); return; }

  const cst = stepOf(job, 'consent');
  const stageClass = st.status === 'pass' ? 'pass' : st.status === 'abstain' ? 'abstain' : null;
  if (stageClass) card.classList.add(stageClass);

  const cons = probe.consent || {};
  if (STATE.selected && STATE.run && STATE.run.probe_image) {
    const photo = el('div', 'probe-photo');
    const image = el('img');
    image.src = `/api/probe-image?id=${encodeURIComponent(STATE.selected)}`;
    image.alt = probe.image && probe.image.filename ? probe.image.filename : 'probe photo';
    photo.appendChild(image);
    photo.appendChild(kv([
      ['filename', probe.image && probe.image.filename],
      ['sha256', short(probe.image && probe.image.sha256, 10)],
      ['subject', (job.result || {}).params && (job.result || {}).params.subject],
    ]));
    body.appendChild(photo);
  }
  body.appendChild(kv([
    ['consent', cst.status === 'pass' ? 'GRANTED' : String(cst.reason || cst.status)],
    ['scope', cons.scope], ['expires', cons.expires_at],
    ['subject commitment', cons.subject_commitment],
  ]));

  const q = probe.quality || {}, g = probe.quality_gate || {};
  const grid = el('div', 'split');
  grid.appendChild(metric('det_score', q.det_score, g.min_det_score, true));
  grid.appendChild(metric('face_px', q.face_px, g.min_face_px, true));
  grid.appendChild(metric('blur_var', q.blur_var, g.min_blur_var, true));
  grid.appendChild(metric('secondary_ratio', q.secondary_ratio, g.max_secondary_face_ratio, false));
  body.appendChild(grid);

  if (probe.status === 'rejected') {
    body.appendChild(banner('abstain',
      `Quality gate REJECTED this probe: ${probe.rejection_reason}. ` +
      `No embedding was retained and no bundle was built.`));
    return;
  }

  const emb = probe.embedding || {}, img = probe.image || {};

  const runId = (job.result || {}).run_id || STATE.selected;
  const row = el('div', 'photo-row');
  if (runId && STATE.run && STATE.run.probe_image) {
    row.appendChild(photo(`/api/probe-image?id=${encodeURIComponent(runId)}`,
      caption([['probe', img.filename || ''], ['det', q.det_score], ['face', q.face_px + ' px']])));
  } else {
    row.appendChild(noPhoto('probe photo not retained for this run'));
  }
  body.appendChild(row);

  body.appendChild(kv([
    ['image', `${img.filename}`],
    ['image sha256', img.sha256],
    ['model', probe.model_id],
    ['embedding', `${emb.dim}-D ${emb.dtype}${emb.l2_normalised ? ' · L2-normalised' : ''}`],
    ['commitment', emb.commitment],
    ['faces detected', q.n_faces],
    ['bbox', Array.isArray(q.bbox) ? q.bbox.join(', ') : q.bbox],
  ]));
  body.appendChild(el('div', 'note',
    'The 512-D vector never leaves the machine — only keccak256(salt‖embedding) ' +
    'enters the bundle, and destroying the salt makes it unopenable.'));
}

function channelCard(title, data, note) {
  const card = el('div', 'card');
  const h = el('h2', null, title);
  card.appendChild(h);
  const body = el('div', 'body');
  if (!data) {
    body.appendChild(el('div', 'note', note || 'did not run'));
    card.appendChild(body); return card;
  }
  const accepted = data.accepted === true;
  h.appendChild(el('span', 'sub')).appendChild(
    tag(accepted ? 'accepted' : 'no result', accepted ? 'pass' : 'abstain'));

  const rows = [['status', accepted ? 'ACCEPTED' : 'UNAVAILABLE / REJECTED'], ['reason', data.reason]];
  if (data.margin !== undefined) rows.push(['margin', data.margin]);
  if (data.snapshot && data.snapshot.snapshot_id) rows.push(['snapshot', short(data.snapshot.snapshot_id, 8)]);
  body.appendChild(kv(rows));

  const hits = data.hits || [];
  if (hits.length) {
    const t = el('table');
    const hd = el('tr');
    for (const c of ['rank', 'score', 'candidate', 'post']) hd.appendChild(el('th', null, c));
    t.appendChild(hd);
    hits.slice(0, 5).forEach((hit, i) => {
      const tr = el('tr');
      tr.appendChild(el('td', null, hit.rank ?? i + 1));
      tr.appendChild(el('td', 'mono', hit.score ?? '—'));
      tr.appendChild(el('td', 'mono', hit.author_handle ?? '—'));
      tr.appendChild(el('td', 'mono', short(hit.post_url || hit.post_uri || '—', 26)));
      t.appendChild(tr);
    });
    body.appendChild(el('div', 'tbl-scroll')).appendChild(t);
  } else {
    body.appendChild(el('div', 'note', 'no candidates returned'));
  }
  card.appendChild(body);
  return card;
}

function renderStage2(job) {
  const body = clear($('stage2-body'));
  const card = $('c-stage2'); card.className = 'card';
  const st = stepOf(job, 'stage2');
  const s2 = (job.result || {}).stage2 || (STATE.run && STATE.run.artifacts['stage2.json']);
  if (!s2) { body.appendChild(el('div', 'empty', 'Stage 2 did not run.')); return; }

  const abstain = s2.fusion_outcome === 'ABSTAIN';
  card.classList.add(abstain ? 'abstain' : 'pass');

  const head = el('div', 'kv');
  body.appendChild(kv([
    ['fusion outcome', s2.fusion_outcome],
    ['source', s2.source],
    ['channels used', (s2.channels_used || []).join(', ')],
    ['snapshot', s2.snapshot_id || '—'],
    ['threshold in force', s2.threshold ?? STATE.app.calibration.in_force],
    ['retrieved', s2.retrieval_timestamp],
  ]));

  const storedA = s2.channel_a || null, storedB = s2.channel_b || null;
  const det = (job.result || {}).stage2_detail || {};
  const split = el('div', 'split');
  split.appendChild(channelCard('Channel A · self-built FAISS index', det.channel_a || storedA,
    'Channel A did not run (no Stage 2 detail for this run).'));
  split.appendChild(channelCard('Channel B · reverse image search', det.channel_b || storedB,
    'Channel B did not run (no Stage 2 detail for this run).'));
  body.appendChild(split);

  if (abstain) {
    body.appendChild(banner('abstain',
      `ABSTAIN — reason: ${s2.reason || 'fusion_abstain'}. Neither channel cleared its gate, ` +
      `so no match is asserted and Stage 3 will refuse to build a bundle.`));
  } else if (s2.match) {
    const m = s2.match;
    const win = el('div', 'photo-row');
    if (m.image_sha256) {
      win.appendChild(photo(`/api/corpus-image?sha256=${encodeURIComponent(m.image_sha256)}`,
        caption([['winner', m.author_handle || ''], ['cosine', m.cosine ?? m.score],
                 ['margin', s2.margin]]), 'win'));
    } else {
      win.appendChild(noPhoto('winning candidate is not a local corpus image'));
    }
    body.appendChild(win);
    body.appendChild(kv([
      ['platform', m.platform], ['post', m.post_url], ['at-uri', m.post_uri],
      ['author', `${m.author_handle} (${m.author_did})`],
      ['cosine', m.score ?? m.cosine], ['margin', s2.margin], ['threshold', m.threshold],
    ]));
  }

  // top-k gallery: every candidate the search actually returned, in rank order
  const chA = det.channel_a || storedA;
  const hits = (chA && chA.hits) || [];
  if (hits.length) {
    body.appendChild(el('div', 'note',
      `Top-${hits.length} returned by the real FAISS search, in rank order. ` +
      `Threshold ${s2.threshold ?? STATE.app.calibration.in_force} — ` +
      `a candidate below it is shown but not accepted.`));
    const gal = el('div', 'photo-row');
    hits.forEach((h, i) => {
      const accepted = Number(h.score) >= Number(s2.threshold ?? 1e9);
      const cap = caption([[`#${i + 1}`, h.author_handle || h.subject || ''],
                           ['cosine', h.score], [accepted ? 'above' : 'below', 'threshold']]);
      if (h.image_sha256) {
        gal.appendChild(photo(`/api/corpus-image?sha256=${encodeURIComponent(h.image_sha256)}`,
          cap, accepted ? 'win' : ''));
      } else {
        gal.appendChild(noPhoto('no image for this candidate'));
      }
    });
    body.appendChild(gal);
  }
}

const GROUP_NOTE = {
  probe: 'commitment + quality only — never the embedding',
  consent: 'commitment + scope + grant time',
  match_location: 'the group that is selectively disclosed',
  match_author: 'DID and handle of the matched post author',
  match_text: 'sha256 + length — never the post text',
  match_image: 'sha256 + perceptual hash + source URL',
  scores: 'cosine, margin, threshold, fusion verdict',
  provenance: 'pipeline version, index snapshot, retrieval time',
};

function renderStage3(job) {
  const body = clear($('stage3-body'));
  const card = $('c-stage3'); card.className = 'card';
  const st = stepOf(job, 'stage3');
  const r = job.result || {};
  const bundle = r.bundle || (STATE.run && STATE.run.artifacts['bundle.json']);
  const proofs = r.proofs || (STATE.run && STATE.run.artifacts['proofs.json']);

  if (!bundle) {
    card.classList.add('abstain');
    body.appendChild(banner('abstain',
      st.reason ? `No bundle: ${st.reason}` :
      'No bundle was built. Stage 3 only assembles evidence when Stage 2 asserts a match.'));
    const ab = r.abstain || (STATE.run && STATE.run.artifacts['abstain.json']);
    if (ab) body.appendChild(jsonBlock(ab));
    return;
  }
  card.classList.add('pass');

  body.appendChild(kv([
    ['schema', bundle.schema_id],
    ['pipeline', bundle.pipeline_version],
    ['groups', (bundle.group_order || []).length],
    ['merkle root', bundle.merkle_root],
  ]));

  const groups = el('div', 'groups');
  (bundle.group_order || []).forEach((name, i) => {
    const d = el('details', 'group');
    const sum = el('summary');
    sum.appendChild(el('span', 'idx', i));
    sum.appendChild(el('span', 'nm', name));
    const leaf = proofs && proofs.groups && proofs.groups[name];
    sum.appendChild(el('span', 'lf', leaf ? short(leaf.leaf, 10) : ''));
    d.appendChild(sum);
    const gb = el('div', 'group-body');
    gb.appendChild(el('div', 'note', GROUP_NOTE[name] || ''));
    gb.appendChild(jsonBlock(bundle.groups[name]));
    if (leaf) {
      gb.appendChild(kv([
        ['leaf', leaf.leaf],
        ['index', leaf.index],
        ['proof', `${leaf.proof.length} sibling hashes`],
      ]));
    }
    d.appendChild(gb);
    groups.appendChild(d);
  });
  body.appendChild(groups);

  body.appendChild(el('div', 'note',
    'Each leaf is keccak256(keccak256(canonical_json(group))) — RFC-8785-style ' +
    'canonicalisation with floats rejected and all decimals rendered at fixed 6 dp, ' +
    'so the same evidence always produces the same bytes.'));
}

function renderMerkle(job) {
  const body = clear($('merkle-body'));
  const r = job.result || {};
  const bundle = r.bundle || (STATE.run && STATE.run.artifacts['bundle.json']);
  const proofs = r.proofs || (STATE.run && STATE.run.artifacts['proofs.json']);
  if (!bundle || !proofs) { body.appendChild(el('div', 'empty', 'No bundle to draw.')); return; }

  const order = bundle.group_order || [];
  const leaves = order.map((n) => (proofs.groups[n] || {}).leaf || '');
  const discloseIdx = order.indexOf('match_location');
  const pathSet = new Set(((proofs.groups['match_location'] || {}).proof) || []);

  const tree = el('div', 'tree');

  const rootTier = el('div', 'tier');
  rootTier.appendChild(el('div', 'node root', short(bundle.merkle_root, 12)));
  tree.appendChild(el('div', 'tier-label', 'root (anchored on-chain)'));
  tree.appendChild(rootTier);

  tree.appendChild(el('div', 'tier-label', `internal nodes — keccak256(min‖max) · ${proofs.groups[order[0]].proof.length} levels`));
  const mid = el('div', 'tier');
  for (const h of pathSet) mid.appendChild(el('div', 'node path', short(h, 8)));
  tree.appendChild(mid);

  tree.appendChild(el('div', 'tier-label', '8 leaves — keccak256(keccak256(canon(group)))'));
  const leafTier = el('div', 'tier');
  leaves.forEach((h, i) => {
    const n = el('div', 'node leaf' + (i === discloseIdx ? ' disclosed' : ''),
      `${i} ${short(h, 6)}`);
    n.title = `${order[i]}\n${h}`;
    leafTier.appendChild(n);
  });
  tree.appendChild(leafTier);
  body.appendChild(tree);

  body.appendChild(el('div', 'note',
    `Selective disclosure: revealing only the green leaf (match_location) plus the ` +
    `${pathSet.size} amber sibling hashes proves that group is under the anchored root, ` +
    `without revealing the other 7 groups. That is what the on-chain verifyField() call checks.`));
}

function renderChain(job) {
  const body = clear($('chain-body'));
  const card = $('c-chain'); card.className = 'card';
  const r = job.result || {};
  const receipt = r.receipt || (STATE.run && STATE.run.artifacts['receipt.json']);
  const st = stepOf(job, 'anchor');
  const c = STATE.app.chain;
  $('chain-sub').textContent = `${c.chain}${c.chain_id ? ' · chain id ' + c.chain_id : ''}`;

  if (st.status === 'fail') {
    card.classList.add('fail');
    body.appendChild(banner('fail', `Anchoring failed: ${st.reason}`));
    return;
  }
  if (!receipt) {
    body.appendChild(el('div', 'empty',
      st.reason === 'not requested' ? 'Not anchored — "Anchor on-chain" was off.'
                                    : 'Not anchored.'));
    return;
  }
  card.classList.add(receipt.status === 1 ? 'pass' : 'fail');
  body.appendChild(kv([
    ['chain', `${receipt.chain} (${receipt.chain_id})`],
    ['contract', receipt.contract],
    ['tx hash', receipt.tx_hash],
    ['block', receipt.block_number],
    ['gas used', receipt.gas_used],
    ['anchor id', receipt.anchor_id],
    ['submitter', receipt.submitter],
    ['status', receipt.status === 1 ? 'success' : 'reverted'],
    ['root', receipt.root],
  ]));
  if (receipt.explorer_url) {
    const a = el('a', null, 'View on block explorer →');
    a.href = receipt.explorer_url; a.target = '_blank'; a.rel = 'noopener noreferrer';
    body.appendChild(a);
  }
  body.appendChild(el('div', 'note',
    'EvidenceRegistry is append-only and ownerless: anchors cannot be edited or deleted, ' +
    'and only the 32-byte root is stored — no biometric data reaches the chain.'));
}

function renderVerify(job) {
  const body = clear($('verify-body'));
  const card = $('c-verify'); card.className = 'card';
  const v = (job.result || {}).verification;
  const st = stepOf(job, 'verify');
  if (!v || !v.rows || !v.rows.length) {
    body.appendChild(el('div', 'empty', 'Nothing verified yet.'));
    return;
  }
  card.classList.add(st.status === 'pass' ? 'pass' : st.status === 'fail' ? 'fail' : '');

  const t = el('table');
  const hd = el('tr');
  for (const c of ['check', 'value', 'result']) hd.appendChild(el('th', null, c));
  t.appendChild(hd);
  for (const row of v.rows) {
    const tr = el('tr');
    tr.appendChild(el('td', null, row.check));
    tr.appendChild(el('td', 'mono', short(row.value, 18)));
    tr.appendChild(el('td')).appendChild(okTag(row.ok));
    t.appendChild(tr);
  }
  body.appendChild(el('div', 'tbl-scroll')).appendChild(t);

  if (v.chain_error) {
    body.appendChild(banner('fail',
      `On-chain check could not run: ${v.chain_error}. A requested check that cannot ` +
      `run is scored as a FAILURE, never silently skipped.`));
  } else if (!v.chain_checked) {
    body.appendChild(el('div', 'note',
      'On-chain rows are "—" because no anchoring was requested for this run. ' +
      'The two local rows are still fully checked.'));
  }
}

function renderTamper(job) {
  const body = clear($('tamper-body'));
  const card = $('c-tamper'); card.className = 'card';
  const st = stepOf(job, 'tamper');
  if (st.status === 'pending' || st.status === 'skipped') {
    body.appendChild(el('div', 'empty',
      st.reason ? `Not run — ${st.reason}` : 'Not run.'));
    return;
  }
  const detected = st.tamper_detected;
  card.classList.add(detected ? 'pass' : 'fail');
  body.appendChild(kv([
    ['field altered', 'groups.match_location.post_url'],
    ['change', 'exactly 1 character'],
    ['original verified', st.original_passed ? 'yes' : 'no'],
    ['tamper detected', detected ? 'YES' : 'NO'],
  ]));
  body.appendChild(banner(detected ? 'ok' : 'fail', detected
    ? 'DETECTED — one flipped character changes the leaf, which changes the root, '
      + 'which no longer matches the value anchored on-chain.'
    : 'NOT DETECTED — this is a failure of the integrity property and must be investigated.'));
}

function renderPrivacy() {
  const body = clear($('privacy-body'));
  const t = el('table');
  const hd = el('tr');
  for (const c of ['data', 'where it goes']) hd.appendChild(el('th', null, c));
  t.appendChild(hd);
  const rows = [
    ['512-D face embedding', 'stays on this machine (embedding.f32); never in the bundle, never on-chain'],
    ['embedding commitment', 'keccak256(salt‖embedding) — in the bundle; unopenable once the salt is destroyed'],
    ['consent salt', 'data/consent/ · 0600, gitignored, destroyed by "Revoke + forget"'],
    ['post text', 'sha256 + length only'],
    ['matched image', 'sha256 + perceptual hash + source URL only'],
    ['on-chain', 'one 32-byte Merkle root and a schema id — nothing else'],
    ['private key', 'read from the process environment; never sent to this page'],
  ];
  for (const [a, b] of rows) {
    const tr = el('tr');
    tr.appendChild(el('td', null, a));
    tr.appendChild(el('td', 'mono', b));
    t.appendChild(tr);
  }
  body.appendChild(el('div', 'tbl-scroll')).appendChild(t);
}

function renderArtifacts(job) {
  const body = clear($('artifacts-body'));
  const r = job && job.result || {};
  const runId = r.run_id || STATE.selected;
  $('artifacts-sub').textContent = runId ? `run-${runId}` : '';
  if (!runId) { body.appendChild(el('div', 'empty', 'No run selected.')); return; }

  const files = (STATE.run && STATE.run.files) || [];
  if (!files.length) { body.appendChild(el('div', 'note', 'Reading…')); return; }
  const row = el('div', 'btn-row');
  for (const f of files) {
    const a = el('a', 'badge', f);
    a.href = `/api/artifact?id=${encodeURIComponent(runId)}&name=${encodeURIComponent(f)}`;
    a.target = '_blank'; a.rel = 'noopener';
    row.appendChild(a);
  }
  body.appendChild(row);
  body.appendChild(el('div', 'note', (STATE.run && STATE.run.run_dir) || ''));
}

/* ── log console ──────────────────────────────────────────────── */

function appendLines(lines) {
  const box = $('console');
  const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
  for (const l of lines) {
    const ln = el('div', `ln ${l.level}`);
    ln.appendChild(el('span', 't', `${l.t.toFixed(2)}s`));
    ln.appendChild(el('span', 'm', l.text));
    box.appendChild(ln);
  }
  if (stick) box.scrollTop = box.scrollHeight;
}

function logLocal(text, level = 'info') {
  appendLines([{ t: 0, level, text: `[ui] ${text}` }]);
}

/* ── job polling ──────────────────────────────────────────────── */

function renderAll(job) {
  renderRail(job.steps);
  renderVerdict(job);
  renderStage1(job);
  renderStage2(job);
  renderStage3(job);
  renderMerkle(job);
  renderChain(job);
  renderVerify(job);
  renderTamper(job);
  renderArtifacts(job);
  renderHeader();
}

function setBusy(busy) {
  for (const id of ['btn-run', 'btn-verify', 'btn-anchor', 'btn-tamper']) $(id).disabled = busy;
}

async function watch(jobId) {
  STATE.cursor = 0;
  clear($('console'));
  setBusy(true);
  if (STATE.poll) clearInterval(STATE.poll);

  const tick = async () => {
    let job;
    try {
      job = await api(`/api/job?id=${jobId}&cursor=${STATE.cursor}`);
    } catch (e) { logLocal(`poll failed: ${e.message}`, 'error'); return; }
    STATE.cursor = job.cursor;
    appendLines(job.lines || []);
    STATE.job = job;
    if (job.result && job.result.run_id) STATE.selected = job.result.run_id;
    renderAll(job);

    if (job.status !== 'running') {
      clearInterval(STATE.poll); STATE.poll = null;
      setBusy(false);
      if (STATE.selected) await loadRun(STATE.selected, job);
      await refreshState();
    }
  };
  STATE.poll = setInterval(tick, 500);
  tick();
}

async function loadRun(runId, job) {
  STATE.selected = runId;
  try {
    STATE.run = await api(`/api/run?id=${encodeURIComponent(runId)}`);
  } catch (e) { logLocal(`could not read run: ${e.message}`, 'error'); return; }
  renderAll(job || STATE.job || { steps: [], result: {} });
  renderRuns();
}

async function refreshState() {
  STATE.app = await api('/api/state');
  renderHeader(); renderConsent(); renderCalibration(); renderCorpus(); renderRuns();
  const c = STATE.app.chain;
  $('anchor-hint').textContent = c.private_key_present
    ? `${c.chain} · key present` : `${c.chain} · no PRIVATE_KEY in env`;
  $('opt-anchor').disabled = !c.private_key_present;
  if (!$('in-image').value && STATE.app.demo_image) $('in-image').value = STATE.app.demo_image;
}

/* ── wiring ───────────────────────────────────────────────────── */

$('btn-run').onclick = async () => {
  const body = {
    image: $('in-image').value.trim(),
    subject: $('in-subject').value.trim(),
    real_stage2: $('opt-real').checked,
    anchor: $('opt-anchor').checked,
    tamper: $('opt-tamper').checked,
    demo: $('opt-demo').checked,
  };
  if (body.anchor && !confirm(
      `Anchor on "${STATE.app.chain.chain}"? This submits a real transaction and spends gas.`)) return;
  try {
    const { job_id } = await api('/api/pipeline', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    watch(job_id);
  } catch (e) { logLocal(`could not start: ${e.message}`, 'error'); }
};

const runOn = (endpoint, extra) => async () => {
  if (!STATE.selected) { logLocal('select a run first', 'warn'); return; }
  try {
    const { job_id } = await api(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ run_id: STATE.selected }, extra || {})),
    });
    watch(job_id);
  } catch (e) { logLocal(`${endpoint} failed: ${e.message}`, 'error'); }
};

$('btn-verify').onclick = runOn('/api/verify', { check_chain: true });
$('btn-tamper').onclick = runOn('/api/tamper');
$('btn-anchor').onclick = async () => {
  if (!confirm(`Anchor run ${STATE.selected} on "${STATE.app.chain.chain}"? This spends gas.`)) return;
  return runOn('/api/anchor')();
};

$('opt-demo').onchange = () => {
  const box = clear($('demo-warn'));
  if ($('opt-demo').checked) {
    box.appendChild(banner('warn',
      'Synthetic Stage 2 is a labelled fixture used to exercise the crypto path ' +
      'when no corpus exists. It is not a real match and is marked as such everywhere.'));
  }
};

renderPrivacy();
refreshState().catch((e) => logLocal(`startup failed: ${e.message}`, 'error'));
