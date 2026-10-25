/* Case Lab report runtime. Every number on the page is computed from DOC; nothing is baked in. */
(() => {
  'use strict';

  const DOC = JSON.parse(document.getElementById('doc').textContent);
  const A = DOC.analysis || {};
  const META = A.meta || {};
  const M = DOC.measure || null;
  const P = DOC.params || {};
  const SEGS = DOC.segments || [];
  const FRAMES = DOC.frames || {};
  const STRIP = DOC.filmstrip || [];
  const DUR = DOC.stats.duration || (M && M.probe.duration) || (SEGS.length ? SEGS[SEGS.length - 1].end : 0) || 1;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const list = (v) => (Array.isArray(v) ? v.filter((x) => x !== '' && x != null) : v ? [v] : []);
  const fmt = (t) => {
    t = Math.max(0, Number(t) || 0);
    const m = Math.floor(t / 60);
    return `${String(m).padStart(2, '0')}:${(t - m * 60).toFixed(2).padStart(5, '0')}`;
  };
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const FN_LABEL = { hook: '钩子', setup: '铺垫', build: '递进', twist: '转折', payoff: '兑现', ending: '收尾' };
  const fnOf = (s) => (FN_LABEL[s.narrative_function] ? s.narrative_function : 'setup');
  const PORTRAIT = M ? M.probe.height > M.probe.width : /^(9:16|3:4|4:5|2:3)$/.test(String(META.aspect_ratio || ''));
  const AR = M && M.probe.width ? `${M.probe.width}/${M.probe.height}` : PORTRAIT ? '9/16' : '16/9';
  document.documentElement.style.setProperty('--ar', AR);

  /* ---------------- small renderers ---------------- */
  const chips = (arr, cls = '') => list(arr).map((x) => `<span class="chip ${cls}">${esc(x)}</span>`).join('');
  const ul = (arr) => {
    const items = list(arr);
    return items.length ? `<ul>${items.map((x) => `<li>${val(x)}</li>`).join('')}</ul>` : '<p class="dim">—</p>';
  };
  function val(v) {
    if (v == null || v === '') return '<span class="dim">—</span>';
    if (Array.isArray(v)) return v.map(val).join('、');
    if (typeof v === 'object') {
      return Object.entries(v).map(([k, x]) => `<b>${esc(k)}</b>：${val(x)}`).join('；');
    }
    if (typeof v === 'boolean') return v ? '是' : '否';
    return esc(v);
  }
  const kv = (pairs) => {
    const rows = pairs.filter(([, v]) => list(v).length || (typeof v === 'string' && v));
    if (!rows.length) return '<p class="dim">—</p>';
    return `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${val(v)}</dd>`).join('')}</dl>`;
  };
  const card = (title, body, extra = '', tag = '') =>
    `<div class="panel card ${extra}"><h4>${esc(title)}${tag ? `<span class="tag">${esc(tag)}</span>` : ''}</h4>${body}</div>`;
  const head = (idx, title, sub = '') =>
    `<div class="block-head"><h2><span class="idx">${idx}</span>${esc(title)}</h2>${sub ? `<p class="sub">${esc(sub)}</p>` : ''}</div>`;
  const fnBadge = (s) => `<span class="fn" data-fn="${fnOf(s)}">${esc(FN_LABEL[fnOf(s)])}</span>`;
  const attDots = (n) => {
    n = clamp(Math.round(Number(n) || 0), 0, 5);
    return `<span class="att" title="注意力 ${n}/5">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</span>`;
  };
  const toast = (msg) => {
    const el = $('#toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.hidden = true; }, 1600);
  };

  function verdictOf(s) {
    if (s.motion == null) return null;
    const claim = s.camera_claim;
    if (claim === 'moving' && s.motion < P.static_max_motion && s.seconds >= 0.8)
      return { cls: 'bad', text: '声称运镜 · 实测几乎不动' };
    if (claim === 'static' && s.motion > P.busy_min_motion && s.seconds >= 0.8)
      return { cls: 'hint', text: '声称固定 · 实测偏动' };
    if (claim === 'moving') return { cls: 'ok', text: '运镜 · 实测吻合' };
    if (claim === 'static') return { cls: 'ok', text: '固定 · 实测吻合' };
    return null;
  }
  const MOTION_MAX = (() => {
    if (!M) return 20;
    const v = [...M.motion.values].sort((a, b) => a - b);
    return Math.max(15, v[Math.floor(v.length * 0.98)] || 0);
  })();

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    toast('已复制到剪贴板');
  }

  /* ---------------- hero ---------------- */
  function renderHero() {
    const S = DOC.stats;
    const sum = A.summary || {};
    const vm = A.viral_mechanics || {};
    const probe = M ? M.probe : null;
    const metaChips = [
      probe ? `<span class="chip"><b>${probe.width}×${probe.height}</b></span>` : META.resolution ? `<span class="chip"><b>${esc(META.resolution)}</b></span>` : '',
      `<span class="chip"><b>${esc(probe ? probe.aspect : META.aspect_ratio || '?')}</b></span>`,
      probe ? `<span class="chip">${probe.fps} fps</span>` : '',
      META.primary_format ? `<span class="chip accent">${esc(META.primary_format)}</span>` : '',
      META.pace ? `<span class="chip">节奏 ${esc(META.pace)}</span>` : '',
      probe ? `<span class="chip">${probe.has_audio ? '有声 · ' + esc(probe.audio_codec) : '无声'}</span>` : '',
      DOC.video.name ? `<span class="chip dim" title="${esc(DOC.video.src)}">${esc(DOC.video.name)}${DOC.video.proxy ? ' · 720p 代理播放' : ''}</span>` : '',
    ].join('');
    const stat = (k, v, unit = '', h = '') =>
      `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v ?? '—'}${v != null && unit ? `<small>${unit}</small>` : ''}</div>${h ? `<div class="h">${esc(h)}</div>` : ''}</div>`;
    const sync = S.sync_rate != null ? Math.round(S.sync_rate * 100) : null;
    const stats = M
      ? [
          stat('片长', S.duration.toFixed(2), 's'),
          stat('实测镜头', S.shots, '镜', `分析节拍 ${S.beats}`),
          stat('平均镜长', S.avg_shot, 's', `${S.min_shot}s – ${S.max_shot}s`),
          stat('每分钟切', S.cuts_per_min, '次'),
          stat('画面运动', S.motion_avg, '', '帧间差均值'),
          stat('音画卡点', sync, sync != null ? '%' : '', `起音点 ${S.onsets} 个 · 估算`),
        ].join('')
      : [stat('片长', S.duration ? S.duration.toFixed(2) : null, 's'), stat('估计镜头', S.shots, '镜'), stat('分析节拍', S.beats, '段')].join('');
    $('#sec-hero').innerHTML = `
      <div>
        <div class="hero-kicker">${esc(DOC.case_id)} · 视频案例拆解</div>
        <h1>${esc(DOC.title)}</h1>
        ${sum.one_sentence ? `<p class="quote">${esc(sum.one_sentence)}</p>` : ''}
        <div class="meta-row">${metaChips}</div>
      </div>
      <div class="hero-side">
        <div class="stat-grid">${stats}</div>
        <div class="hero-note"><b>钩子</b>　${esc(vm.hook_type || '—')}${(A.rhythm_structure || {}).hook_window ? `<br><b>钩子窗口</b>　${esc(A.rhythm_structure.hook_window)}` : ''}${sum.core_appeal ? `<br><b>核心吸引力</b>　${esc(sum.core_appeal)}` : ''}</div>
        ${!M ? `<div class="hero-note dim">${DOC.measure_error ? '实测失败：' + esc(DOC.measure_error) : '未关联原视频：实测轨道与对账已跳过。用 <code>--video</code> 指定后重新生成。'}</div>` : ''}
      </div>`;
  }

  /* ---------------- player ---------------- */
  const video = $('#player');
  const wrap = $('#playerWrap');
  let curIdx = -1;
  let loopOn = false;
  let rafId = 0;

  function initPlayer() {
    $('#sec-monitor .monitor').classList.toggle('portrait', PORTRAIT);
    $('#tcTotal').textContent = fmt(DUR);
    if (DOC.video.src) {
      video.src = DOC.video.src;
    } else {
      wrap.classList.add('empty');
    }
    video.addEventListener('error', () => wrap.classList.add('empty'));
    video.addEventListener('loadedmetadata', () => {
      wrap.classList.remove('empty');
      if (Math.abs(video.duration - DUR) > 0.6) toast(`视频时长 ${video.duration.toFixed(2)}s 与报告 ${DUR.toFixed(2)}s 不一致`);
    });
    $('#pickVideo').addEventListener('change', (e) => {
      const f = e.target.files[0];
      if (f) { video.src = URL.createObjectURL(f); }
    });
    video.addEventListener('play', () => { $('#btnPlay').textContent = '❚❚'; tick(); });
    video.addEventListener('pause', () => { $('#btnPlay').textContent = '▶'; cancelAnimationFrame(rafId); sync(); });
    video.addEventListener('seeked', sync);
    video.addEventListener('timeupdate', () => { if (video.paused) sync(); });
    $('#btnPlay').addEventListener('click', togglePlay);
    $('#rate').addEventListener('change', (e) => { video.playbackRate = Number(e.target.value); });
    $('#btnLoop').addEventListener('click', toggleLoop);
    $('#btnPip').addEventListener('click', togglePip);
  }
  function togglePlay() {
    if (wrap.classList.contains('empty')) return toast('先选择本地视频');
    video.paused ? video.play() : video.pause();
  }
  function toggleLoop() {
    loopOn = !loopOn;
    $('#btnLoop').classList.toggle('on', loopOn);
    toast(loopOn ? '循环当前节拍' : '已关闭循环');
    drawOverlay();
  }
  async function togglePip() {
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await video.requestPictureInPicture();
    } catch { toast('当前浏览器不支持画中画'); }
  }
  function tick() {
    sync();
    if (!video.paused) rafId = requestAnimationFrame(tick);
  }
  function seek(t, play = false) {
    t = clamp(t, 0, DUR);
    if (!wrap.classList.contains('empty')) {
      video.currentTime = t;
      if (play) video.play();
    }
    syncAt(t);
  }
  function beatAt(t) {
    let lo = 0, hi = SEGS.length - 1, ans = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (SEGS[mid].start <= t + 1e-3) { ans = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return ans;
  }
  function sync() { syncAt(video.currentTime || 0); }
  function syncAt(t) {
    if (loopOn && curIdx >= 0 && !video.paused) {
      const s = SEGS[curIdx];
      if (t >= s.end - 0.03 || t < s.start - 0.1) { video.currentTime = s.start; t = s.start; }
    }
    $('#tcNow').textContent = fmt(t);
    const idx = beatAt(t);
    if (idx !== curIdx) setBeat(idx);
    if (curIdx >= 0) {
      const s = SEGS[curIdx];
      const bar = $('#inspProg');
      if (bar) bar.style.width = `${clamp((t - s.start) / Math.max(0.01, s.seconds) * 100, 0, 100)}%`;
    }
    playheadT = t;
    drawOverlay();
  }
  function setBeat(idx) {
    curIdx = idx;
    renderInspector();
    $$('.beat-row').forEach((r) => r.classList.toggle('on', r.dataset.idx === String(idx)));
    $$('#tracksCanvas .beat').forEach((r) => r.classList.toggle('on', r.dataset.idx === String(idx)));
  }
  function stepBeat(d) {
    if (!SEGS.length) return;
    const i = clamp((curIdx < 0 ? 0 : curIdx) + d, 0, SEGS.length - 1);
    seek(SEGS[i].start + 0.001);
  }

  /* ---------------- inspector ---------------- */
  function renderInspector() {
    const el = $('#inspector');
    el.classList.add('panel');
    const s = SEGS[curIdx];
    if (!s) {
      el.innerHTML = `<p class="dim">${SEGS.length ? '播放或点击轨道查看节拍' : 'analysis.json 没有 timeline'}</p>`;
      return;
    }
    const v = verdictOf(s);
    el.innerHTML = `
      <div class="insp-top">
        <div><div class="insp-id">${esc(s.id)}</div><div class="insp-time">${fmt(s.start)} → ${fmt(s.end)} · ${s.seconds.toFixed(2)}s</div></div>
        <div style="text-align:right">${fnBadge(s)}<div style="margin-top:6px">${attDots(s.attention_level)}</div></div>
      </div>
      <div class="insp-progress"><i id="inspProg"></i></div>
      <p class="insp-event">${esc(s.visual_event)}</p>
      <dl class="insp-dl">
        ${s.subject_action ? `<dt>动作</dt><dd>${esc(s.subject_action)}</dd>` : ''}
        ${s.camera_action ? `<dt>运镜</dt><dd>${esc(s.camera_action)}${v ? ` <span class="verdict ${v.cls}">${v.text}</span>` : ''}</dd>` : ''}
        ${s.motion != null ? `<dt>实测</dt><dd class="num">运动 ${s.motion} · 响度 ${s.loudness ?? '—'} dB${s.cuts_inside ? ` · 内含 ${s.cuts_inside} 个切点` : ''}</dd>` : ''}
        ${s.audio_event ? `<dt>声音</dt><dd>${esc(s.audio_event)}</dd>` : ''}
        ${s.lighting_description ? `<dt>光线</dt><dd>${esc(s.lighting_description)}</dd>` : ''}
        ${s.transition_detail ? `<dt>转场</dt><dd>${esc(s.transition_detail)}</dd>` : ''}
      </dl>
      <div class="insp-nav">
        <button class="btn" data-step="-1">← 上一拍</button>
        <button class="btn" data-replay>⟲ 重播此拍</button>
        <button class="btn" data-step="1">下一拍 →</button>
      </div>`;
    el.querySelectorAll('[data-step]').forEach((b) => b.addEventListener('click', () => stepBeat(Number(b.dataset.step))));
    el.querySelector('[data-replay]').addEventListener('click', () => seek(s.start + 0.001, true));
  }

  /* ---------------- tracks ---------------- */
  const canvas = $('#tracksCanvas');
  let geo = null;
  let playheadT = 0;
  let hoverT = null;

  function lanes() {
    const L = [{ key: 'axis', h: 18 }];
    if (list(A.rhythm_structure?.peak_moments).length) L.push({ key: 'peaks', h: 16, label: '峰值' });
    if (M) L.push({ key: 'shots', h: 22, label: '实测镜头' });
    L.push({ key: 'beats', h: 26, label: '分析节拍' });
    L.push({ key: 'att', h: 38, label: '注意力' });
    if (M && M.motion.values.length) L.push({ key: 'motion', h: 42, label: '画面运动' });
    if (M && M.audio.values.length) L.push({ key: 'audio', h: 42, label: '音频响度' });
    if (M && M.brightness.values.length) L.push({ key: 'bright', h: 24, label: '亮度' });
    return L;
  }

  function renderTracks() {
    const legend = [
      M ? '<span><i style="background:var(--ink-2)"></i>场景检测切点</span><span><i style="background:var(--good)"></i>卡在起音点上的切点</span>' : '',
      ...Object.keys(FN_LABEL).filter((k) => SEGS.some((s) => fnOf(s) === k)).map((k) => `<span><i style="background:var(--fn-${k})"></i>${FN_LABEL[k]}</span>`),
      M ? '<span><i style="background:var(--track-motion)"></i>运动</span><span><i style="background:var(--track-audio)"></i>响度 / 起音</span>' : '',
    ].join('');
    $('#tracksLegend').innerHTML = legend;
    $('#tracks').classList.add('panel');
    drawTracks();
    new ResizeObserver(() => drawTracks()).observe(canvas);

    let dragging = false;
    const tAt = (e) => {
      const r = canvas.getBoundingClientRect();
      return clamp(((e.clientX - r.left) - geo.x0) / (geo.x1 - geo.x0) * DUR, 0, DUR);
    };
    canvas.addEventListener('pointerdown', (e) => {
      const peak = e.target.closest('[data-peak]');
      if (peak) return seek(Number(peak.dataset.peak));
      dragging = true;
      canvas.setPointerCapture(e.pointerId);
      seek(tAt(e));
    });
    canvas.addEventListener('pointermove', (e) => {
      hoverT = tAt(e);
      if (dragging) seek(hoverT);
      showTip(e, hoverT);
      drawOverlay();
    });
    canvas.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('pointerleave', () => { hoverT = null; $('#scrubTip').hidden = true; drawOverlay(); });
  }

  function areaPath(values, hz, x, yOf, base) {
    if (!values.length) return '';
    const n = values.length;
    const px = Math.max(1, Math.floor(geo.x1 - geo.x0));
    const step = Math.max(1, Math.floor(n / px));
    let d = `M${x(0).toFixed(1)},${base}`;
    for (let i = 0; i < n; i += step) {
      let v = values[i];
      for (let j = i + 1; j < Math.min(n, i + step); j++) v = Math.max(v, values[j]);
      d += `L${x(i / hz).toFixed(1)},${yOf(v).toFixed(1)}`;
    }
    d += `L${x((n - 1) / hz).toFixed(1)},${base}Z`;
    return d;
  }
  function linePath(values, hz, x, yOf) {
    const n = values.length;
    const step = Math.max(1, Math.floor(n / Math.max(1, geo.x1 - geo.x0)));
    let d = '';
    for (let i = 0; i < n; i += step) d += `${d ? 'L' : 'M'}${x(i / hz).toFixed(1)},${yOf(values[i]).toFixed(1)}`;
    return d;
  }

  function drawTracks() {
    const W = canvas.clientWidth || 800;
    const LS = lanes();
    const gap = 6;
    const x0 = 72, x1 = W - 6;
    const x = (t) => x0 + (t / DUR) * (x1 - x0);
    let y = 0;
    LS.forEach((l) => { l.y = y; y += l.h + gap; });
    const H = y;
    geo = { W, H, x0, x1, x, lanes: LS };
    const out = [];
    const lane = (k) => LS.find((l) => l.key === k);

    // ticks
    const ax = lane('axis');
    const rough = DUR / 6;
    const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
    const st = steps.find((s) => s >= rough) || 600;
    const ticks = [];
    for (let t = 0; t < DUR - st * 0.4; t += st) ticks.push(t);
    ticks.push(DUR);
    ticks.forEach((t, i) => {
      const last = i === ticks.length - 1;
      out.push(`<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${ax.h - 4}" y2="${H}"/>`);
      out.push(`<text class="axis" x="${x(t) + (last ? -3 : 3)}" y="${ax.h - 7}" text-anchor="${last ? 'end' : 'start'}">${last ? fmt(t) : fmt(t).replace(/\.\d+$/, '')}</text>`);
    });
    LS.forEach((l) => {
      if (!l.label) return;
      out.push(`<rect class="lane" x="${x0}" y="${l.y}" width="${x1 - x0}" height="${l.h}" rx="3"/>`);
      out.push(`<text class="lbl" x="0" y="${l.y + l.h / 2 + 4}">${l.label}</text>`);
    });

    const pk = lane('peaks');
    if (pk) {
      list(A.rhythm_structure.peak_moments).forEach((p) => {
        const t = Number(p.time) || 0, cx = x(t), cy = pk.y + pk.h / 2;
        out.push(`<path class="peak" data-peak="${t}" d="M${cx},${cy - 6}L${cx + 6},${cy}L${cx},${cy + 6}L${cx - 6},${cy}Z"><title>${esc(fmt(t))} ${esc(p.reason)}</title></path>`);
      });
    }

    const sh = lane('shots');
    if (sh) {
      const hits = new Set((M.sync.hits || []).map(String));
      M.shots.forEach((s, i) => {
        out.push(`<rect class="shot ${i % 2 ? 'alt' : ''}" x="${x(s.start)}" y="${sh.y}" width="${Math.max(1, x(s.end) - x(s.start))}" height="${sh.h}" rx="2"><title>${s.id} ${fmt(s.start)}–${fmt(s.end)} · ${s.seconds}s · 运动 ${s.motion ?? '—'}</title></rect>`);
        if (i > 0) out.push(`<line class="cut ${hits.has(String(s.start)) ? 'sync' : ''}" x1="${x(s.start)}" x2="${x(s.start)}" y1="${sh.y - 2}" y2="${sh.y + sh.h + 2}"/>`);
      });
    }

    const bt = lane('beats');
    SEGS.forEach((s, i) => {
      const w = Math.max(1, x(s.end) - x(s.start));
      out.push(`<rect class="beat ${i === curIdx ? 'on' : ''}" data-idx="${i}" x="${x(s.start) + 0.5}" y="${bt.y}" width="${w - 1}" height="${bt.h}" rx="3" fill="var(--fn-${fnOf(s)})"><title>${esc(s.id)} ${esc(FN_LABEL[fnOf(s)])} · ${esc(s.visual_event)}</title></rect>`);
      if (w > 28) out.push(`<text class="beat-t" x="${x(s.start) + 5}" y="${bt.y + bt.h / 2 + 4}">${esc(s.id)}</text>`);
    });

    const at = lane('att');
    if (SEGS.length) {
      const yOf = (v) => at.y + at.h - 3 - (clamp(Number(v) || 0, 0, 5) / 5) * (at.h - 6);
      let d = `M${x(SEGS[0].start)},${at.y + at.h}`;
      SEGS.forEach((s) => { d += `L${x(s.start)},${yOf(s.attention_level)}L${x(s.end)},${yOf(s.attention_level)}`; });
      d += `L${x(SEGS[SEGS.length - 1].end)},${at.y + at.h}Z`;
      out.push(`<path class="curve-att" d="${d}"/>`);
    }

    const mo = lane('motion');
    if (mo) {
      const yOf = (v) => mo.y + mo.h - (clamp(v, 0, MOTION_MAX) / MOTION_MAX) * (mo.h - 3);
      out.push(`<path class="curve-motion" d="${areaPath(M.motion.values, M.motion.hz, x, yOf, mo.y + mo.h)}"/>`);
      const sy = yOf(P.static_max_motion);
      out.push(`<line class="grid" x1="${x0}" x2="${x1}" y1="${sy}" y2="${sy}" stroke-dasharray="2 3"><title>静止阈值 ${P.static_max_motion}</title></line>`);
    }

    const au = lane('audio');
    if (au) {
      const yOf = (v) => au.y + au.h - (clamp((v + 60) / 60, 0, 1)) * (au.h - 3);
      out.push(`<path class="curve-audio" d="${areaPath(M.audio.values, M.audio.hz, x, yOf, au.y + au.h)}"/>`);
      (M.onsets || []).forEach((t) => out.push(`<line class="onset" x1="${x(t)}" x2="${x(t)}" y1="${au.y}" y2="${au.y + 6}"/>`));
    }

    const br = lane('bright');
    if (br) {
      const yOf = (v) => br.y + br.h - (clamp(v, 0, 255) / 255) * (br.h - 2);
      out.push(`<path class="curve-bright" d="${linePath(M.brightness.values, M.brightness.hz, x, yOf)}"/>`);
    }

    canvas.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}">${out.join('')}<g id="overlay"></g></svg>`;
    drawOverlay();
  }

  function drawOverlay() {
    const g = $('#overlay');
    if (!g || !geo) return;
    const { x, H } = geo;
    let s = '';
    if (loopOn && SEGS[curIdx]) {
      const b = SEGS[curIdx];
      s += `<rect class="loop" x="${x(b.start)}" y="14" width="${x(b.end) - x(b.start)}" height="${H - 14}"/>`;
    }
    if (hoverT != null) s += `<line class="hoverline" x1="${x(hoverT)}" x2="${x(hoverT)}" y1="0" y2="${H}"/>`;
    s += `<line class="playhead" x1="${x(playheadT)}" x2="${x(playheadT)}" y1="0" y2="${H}"/>`;
    s += `<circle cx="${x(playheadT)}" cy="3" r="4" fill="var(--accent)"/>`;
    g.innerHTML = s;
  }

  function nearestStrip(t) {
    if (!STRIP.length) return null;
    let best = STRIP[0];
    for (const f of STRIP) if (Math.abs(f.t - t) < Math.abs(best.t - t)) best = f;
    return best;
  }
  function showTip(e, t) {
    const tip = $('#scrubTip');
    const f = nearestStrip(t);
    const idx = beatAt(t);
    const s = SEGS[idx];
    const at = (track) => (track && track.values.length ? track.values[clamp(Math.round(t * track.hz), 0, track.values.length - 1)] : null);
    tip.innerHTML = `
      ${f ? `<img src="${f.src}" alt="">` : ''}
      <div class="tt">${fmt(t)}${s ? ` · ${esc(s.id)}` : ''}</div>
      ${s ? `<div class="row"><span>${esc(FN_LABEL[fnOf(s)])}</span><b>注意力 ${esc(s.attention_level ?? '—')}</b></div>` : ''}
      ${M ? `<div class="row"><span>运动</span><b>${at(M.motion) ?? '—'}</b></div><div class="row"><span>响度</span><b>${at(M.audio) ?? '—'} dB</b></div>` : ''}`;
    tip.hidden = false;
    const r = $('#tracks').getBoundingClientRect();
    const left = clamp(e.clientX - r.left + 14, 8, r.width - 200);
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(8, e.clientY - r.top - tip.offsetHeight - 12)}px`;
  }

  /* ---------------- beats table ---------------- */
  let view = 'list';
  let fnFilter = 'all';
  let query = '';
  let lbItems = [];
  let lbIdx = 0;

  function renderBeatFilters() {
    const counts = {};
    SEGS.forEach((s) => { counts[fnOf(s)] = (counts[fnOf(s)] || 0) + 1; });
    const btn = (k, label, n) => `<button data-fn="${k}" class="${fnFilter === k ? 'on' : ''}">${esc(label)}<span class="n">${n}</span></button>`;
    $('#fnFilter').innerHTML = btn('all', '全部', SEGS.length)
      + Object.keys(FN_LABEL).filter((k) => counts[k]).map((k) => btn(k, FN_LABEL[k], counts[k])).join('');
    $$('#fnFilter button').forEach((b) => b.addEventListener('click', () => { fnFilter = b.dataset.fn; renderBeatFilters(); renderBeats(); }));
  }
  const hl = (text) => {
    const e = esc(text);
    if (!query) return e;
    const q = esc(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return e.replace(new RegExp(q, 'gi'), (m) => `<mark>${m}</mark>`);
  };
  function renderBeats() {
    const box = $('#beats');
    box.className = `beats ${view}`;
    const q = query.toLowerCase();
    const rows = SEGS.map((s, i) => ({ s, i })).filter(({ s }) => {
      if (fnFilter !== 'all' && fnOf(s) !== fnFilter) return false;
      if (!q) return true;
      return [s.id, s.visual_event, s.subject_action, s.camera_action, s.audio_event, s.subject_description, s.environment_description]
        .some((v) => String(v || '').toLowerCase().includes(q));
    });
    lbItems = [];
    if (!rows.length) { box.innerHTML = '<div class="empty-note">没有匹配的节拍</div>'; return; }
    box.innerHTML = rows.map(({ s, i }) => {
      const fr = FRAMES[s.id] || {};
      const thumb = (tag, label) => {
        if (!fr[tag]) return tag === 'a' ? '<div class="none">无帧</div>' : '';
        lbItems.push({ src: fr[tag], cap: `${s.id}${tag} · ${label} · ${s.visual_event || ''}` });
        return `<figure data-lb="${lbItems.length - 1}"><img loading="lazy" src="${fr[tag]}" alt=""><figcaption>${s.id}${tag}</figcaption></figure>`;
      };
      const v = verdictOf(s);
      const pct = s.motion != null ? clamp(s.motion / MOTION_MAX * 100, 2, 100) : 0;
      return `
      <article class="beat-row ${i === curIdx ? 'on' : ''}" data-idx="${i}" id="${esc(s.id)}">
        <div class="thumbs ${PORTRAIT ? 'portrait' : ''}">${thumb('a', '起')}${thumb('b', '收')}</div>
        <div class="beat-meta">
          <span class="bid">${esc(s.id)}</span>
          <span class="bt">${fmt(s.start)}<br>${s.seconds.toFixed(2)}s</span>
          <span>${fnBadge(s)}</span>
          ${attDots(s.attention_level)}
        </div>
        <div class="beat-main">
          <p class="ev">${hl(s.visual_event)}</p>
          <p class="act">${hl(s.subject_action)}</p>
        </div>
        <div class="beat-col cam">
          <h5>运镜</h5>
          ${s.motion != null ? `<div class="motion-meter"><span class="bar"><i style="width:${pct}%"></i></span><span class="num">${s.motion}</span>${v ? `<span class="verdict ${v.cls}">${v.text}</span>` : ''}</div>` : ''}
          <p>${hl(s.camera_action)}</p>
        </div>
        <div class="beat-col">
          <h5>声音</h5><p>${hl(s.audio_event || '—')}</p>
          ${s.transition_type ? `<h5>转场</h5><p>${esc(s.transition_type)}</p>` : ''}
        </div>
      </article>`;
    }).join('');
    $$('.beat-row', box).forEach((r) => r.addEventListener('click', (e) => {
      const fig = e.target.closest('[data-lb]');
      if (fig) return openLb(Number(fig.dataset.lb));
      seek(SEGS[Number(r.dataset.idx)].start + 0.001);
      $('#sec-monitor').scrollIntoView({ block: 'start' });
    }));
  }
  function initBeats() {
    renderBeatFilters();
    renderBeats();
    $('#search').addEventListener('input', (e) => { query = e.target.value.trim(); renderBeats(); });
    $$('#viewToggle button').forEach((b) => b.addEventListener('click', () => {
      view = b.dataset.view;
      $$('#viewToggle button').forEach((x) => x.classList.toggle('on', x === b));
      renderBeats();
    }));
  }

  /* ---------------- lightbox ---------------- */
  function openLb(i) {
    if (!lbItems.length) return;
    lbIdx = (i + lbItems.length) % lbItems.length;
    $('#lbImg').src = lbItems[lbIdx].src;
    $('#lbCap').textContent = lbItems[lbIdx].cap;
    $('#lightbox').hidden = false;
  }
  const closeLb = () => { $('#lightbox').hidden = true; };
  $('#lbClose').addEventListener('click', closeLb);
  $('#lbPrev').addEventListener('click', () => openLb(lbIdx - 1));
  $('#lbNext').addEventListener('click', () => openLb(lbIdx + 1));
  $('#lightbox').addEventListener('click', (e) => { if (e.target.id === 'lightbox') closeLb(); });

  /* ---------------- analysis sections ---------------- */
  function renderWhy() {
    const E = A.emotion_and_psychology || {};
    const V = A.viral_mechanics || {};
    const S = A.summary || {};
    $('#sec-why').innerHTML = head('03', '为什么抓人', '模型判断 · 机制层') + `
      <div class="grid c3">
        ${card('核心吸引力', `<p class="big">${esc(S.core_appeal || '—')}</p>${S.likely_intent ? `<p class="dim">意图：${esc(S.likely_intent)}</p>` : ''}`, 'feature', 'appeal')}
        ${card('情绪', kv([['主导情绪', E.dominant_emotion], ['情绪曲线', E.emotion_curve]]), '', 'emotion')}
        ${card('钩子', kv([['类型', V.hook_type], ['窗口', A.rhythm_structure?.hook_window]]), '', 'hook')}
      </div>
      <div class="grid c4" style="margin-top:14px">
        ${card('观众为什么停下', ul(E.viewer_pull_factors), '', 'pull')}
        ${card('为什么看完', ul(V.retention_drivers), '', 'retention')}
        ${card('为什么转发', ul(V.shareability_drivers), '', 'share')}
        ${card('为什么复看', ul(V.repeat_watch_drivers), '', 'repeat')}
      </div>
      ${list(E.why_it_feels_premium).length ? `<div class="grid" style="margin-top:14px">${card('高级感从哪来', ul(E.why_it_feels_premium), '', 'premium')}</div>` : ''}`;
  }

  function renderVisual() {
    const VL = A.visual_language || {};
    const pal = M && M.palette && M.palette.length
      ? `<div class="palette">${M.palette.map((c) => `<div style="background:${esc(c.hex)};flex:${c.pct}" title="${esc(c.hex)} · ${Math.round(c.pct * 100)}%"><span>${esc(c.hex)}</span></div>`).join('')}</div>`
      : '<p class="dim">无实测色板（需要原视频）</p>';
    const chars = list(A.characters_detected);
    const CHAR_KEYS = {
      brief_description: '简述', distinguishing_features: '辨识特征', state_changes: '状态变化',
      appearance_count: '出场次数', first_seen_at: '首次出现', last_seen_at: '最后出现', role: '角色',
      gender: '性别', age_range: '年龄', outfit: '服装', hairstyle: '发型', makeup: '妆容',
    };
    const charKv = (c) => kv(Object.entries(c).filter(([k]) => !['name', 'id'].includes(k))
      .map(([k, v]) => [CHAR_KEYS[k] || k, /seen_at$/.test(k) && typeof v === 'number' ? `${v}s` : v]));
    $('#sec-visual').innerHTML = head('04', '视觉语言') + `
      <div class="grid c2">
        ${card('色板', `${pal}<p style="margin-top:12px" class="dim">实测（像素聚类）↑　　模型描述 ↓</p><div class="tagset">${chips(VL.palette)}</div>`, '', 'palette')}
        ${card('风格关键词', `<div class="tagset">${chips(VL.style_keywords, 'accent')}</div>${VL.global_style_direction ? `<p style="margin-top:12px">${esc(VL.global_style_direction)}</p>` : ''}`, '', 'style')}
      </div>
      <div class="grid c2" style="margin-top:14px">
        ${card('质感与成像', kv([['真实度', VL.realism_level], ['制作观感', VL.production_look], ['设备感', VL.camera_equipment_feel], ['皮肤', VL.skin_texture], ['质感特效', VL.texture_fx]]), '', 'look')}
        ${card('光线与环境', kv([['光线', VL.lighting], ['环境', VL.environment_traits], ['主体设计', VL.subject_design_traits]]), '', 'light')}
      </div>
      ${chars.length ? `<div class="grid c${Math.min(3, chars.length)}" style="margin-top:14px">${chars.map((c, i) => card(c.name || c.id || `角色 ${i + 1}`, typeof c === 'object' ? charKv(c) : `<p>${esc(c)}</p>`, '', 'character')).join('')}</div>` : ''}`;
  }

  function renderCamera() {
    const C = A.camera_language || {};
    const R = A.rhythm_structure || {};
    const AV = A.audio_visual_sync || {};
    const S = DOC.stats;
    const peaks = list(R.peak_moments);
    const sync = S.sync_rate != null ? Math.round(S.sync_rate * 100) : null;
    $('#sec-camera').innerHTML = head('05', '镜头 · 节奏 · 音画') + `
      <div class="grid c3">
        ${card('镜头语言', kv([['主导运镜', C.dominant_movement], ['景别', C.shot_types], ['运动模式', C.movement_patterns], ['构图', C.framing_traits], ['连续性', C.continuity_strategy || C.movement_continuity]]), '', 'camera')}
        ${card('节奏结构', kv([['模式', R.pattern], ['强度曲线', R.intensity_curve]]) + (peaks.length ? `<h4 style="margin-top:14px">峰值时刻</h4><div class="peaks">${peaks.map((p) => `<div class="peak-item" data-seek="${Number(p.time) || 0}"><span class="tc">${fmt(p.time)}</span><span>${esc(p.reason)}</span></div>`).join('')}</div>` : ''), '', 'rhythm')}
        ${card('音画关系', (M ? `<div style="display:flex;gap:22px;align-items:flex-end;margin-bottom:12px"><div><div class="big-num">${sync ?? '—'}<small>${sync != null ? '%' : ''}</small></div><div class="dim" style="font-size:12px">切点落在起音点 ±${P.sync_tolerance}s</div></div><div><div class="big-num" style="font-size:28px">${S.onsets}</div><div class="dim" style="font-size:12px">起音点（估算）</div></div></div>` : '') + kv([['音乐类型', AV.music_genre], ['节拍对画面', AV.beat_impact_on_visuals], ['人物律动', AV.character_rhythm_sync], ['推荐 BGM', AV.recommended_bgm_reference || AV.recommended_bgm_style], ['BPM', AV.recommended_bpm], ['卡点方案', AV.music_sync_plan]]), '', 'a/v')}
      </div>`;
    $$('#sec-camera [data-seek]').forEach((el) => el.addEventListener('click', () => { seek(Number(el.dataset.seek)); $('#sec-monitor').scrollIntoView(); }));
  }

  function renderTransfer() {
    const T = A.transferable_pattern || {};
    $('#sec-transfer').innerHTML = head('06', '可迁移骨架', '换角色、换题材之后仍然成立的结构') + `
      ${T.abstract_pattern ? `<div class="panel card feature" style="margin-bottom:14px"><h4>抽象骨架<span class="tag">pattern</span></h4><p class="big">${esc(T.abstract_pattern)}</p></div>` : ''}
      <div class="grid c3">
        ${card('必须保留', ul(T.must_keep), 'transfer-col col-keep', 'keep')}
        ${card('可以替换', ul(T.replaceable), 'transfer-col col-swap', 'swap')}
        ${card('不要照抄', ul(T.do_not_copy_literally), 'transfer-col col-no', 'avoid')}
      </div>`;
  }

  function renderSeedance() {
    const S = A.seedance_translation || {};
    const N = A.next_step_assets || {};
    const variants = list(N.variants);
    $('#sec-seedance').innerHTML = head('07', 'Seedance 转译') + `
      <div class="grid c2">
        ${card('推荐生成方式', `<p><span class="chip accent">${esc(S.recommended_mode || '—')}</span>${S.shot_plan_needed != null ? ` <span class="chip">${S.shot_plan_needed ? '需要分镜计划' : '无需分镜计划'}</span>` : ''}</p><p>${esc(S.why || '')}</p><h4 style="margin-top:12px">参考素材</h4>${ul(S.reference_asset_suggestion)}`, '', 'mode')}
        ${card('翻车风险', ul(S.risk_points), 'transfer-col col-no', 'risk')}
      </div>
      ${S.seedance_ready_prompt_template ? `<div class="panel prompt-block" style="margin-top:14px"><div class="prompt-head"><h4>提示词模板（分析阶段）</h4><span class="count">${String(S.seedance_ready_prompt_template).length} 字</span><button class="btn" data-copy-tpl>复制</button></div><pre class="prompt-body">${esc(S.seedance_ready_prompt_template)}</pre></div>` : ''}
      ${variants.length ? `<div class="grid c${Math.min(3, variants.length)}" style="margin-top:14px">${variants.map((v) => card(v.name || '变体', `<p>${esc(v.direction || '')}</p>${kv([['改变', v.what_changes], ['保留', v.what_stays]])}`, '', 'variant')).join('')}</div>` : ''}`;
    const b = $('[data-copy-tpl]');
    if (b) b.addEventListener('click', () => copyText(S.seedance_ready_prompt_template));
  }

  let promptTab = 0;
  function renderPrompts() {
    const PR = DOC.prompts;
    const sec = $('#sec-prompts');
    if (!PR || !PR.versions || !PR.versions.length) {
      sec.innerHTML = head('08', '生成 Prompt') + '<div class="empty-note">这个 case 还没有 prompts.md</div>';
      return;
    }
    const TS = /\[?\d+(?:\.\d+)?\s*[-–~至到]\s*\d+(?:\.\d+)?\s*(?:秒|s|S)\]?/g;
    const fmtBody = (t) => esc(t)
      .replace(/^(\s*)(Shot\s*\d+\s*[|｜:：]|[^\s：:\n\d][^\s：:\n]{0,9}：)/gm, '$1<span class="lead">$2</span>')
      .replace(TS, (m) => `<mark title="违反「禁止时间戳」契约">${m}</mark>`);
    const v = PR.versions[promptTab] || PR.versions[0];
    const full = v.blocks.filter((b) => !b.partial);
    const legacyNote = PR.legacy ? `
      <div class="panel prompt-legacy">这个 case 早于 A/B/C 版本规范，Prompt 从旧文件（${esc(PR.source)}）原样整理：每张卡片都是可直接粘贴的完整文本；
        变体页已自动带上共用的人物参考图 Prompt。标「局部片段」的卡片只是替换段，需要和完整版合并后再用。</div>` : '';
    const directions = PR.directions && PR.directions.length ? `
      <div class="panel prompt-directions"><h4>变体方向 · 只有思路，没有完整 Prompt</h4>
        <ul>${PR.directions.map((d) => `<li><b>${esc(d.title)}</b>${d.text ? ` — ${esc(d.text)}` : ''}</li>`).join('')}</ul>
        <p class="dim">需要的话用 shot_prompt_generator.py 重新生成 prompts.md，会产出完整的 A/B/C 版本。</p></div>` : '';
    sec.innerHTML = head('08', '生成 Prompt', `来自 ${PR.source} · 每段可单独复制粘贴`) + legacyNote + `
      ${PR.intro ? `<div class="panel prompt-intro">${esc(PR.intro)}</div>` : ''}
      <div class="tabs">${PR.versions.map((x, i) => `<button data-tab="${i}" class="${i === promptTab ? 'on' : ''}${x.partial ? ' partial' : ''}"><span class="k">${i + 1}</span>${esc(x.title)}</button>`).join('')}</div>
      <div class="prompt-tabbar">
        <span class="dim">${v.source ? `出自 ${esc(v.source)} · ` : ''}${v.updated_at ? `最近更新 ${esc(v.updated_at)} · ` : ''}${v.blocks.length} 段${v.blocks.length - full.length ? `（含 ${v.blocks.length - full.length} 段局部片段）` : ''}</span>
        ${full.length > 1 ? '<button class="btn ghost" data-copy-all>复制本版全部</button>' : ''}
      </div>
      <div class="prompt-blocks">${v.blocks.map((b, i) => `
        <div class="panel prompt-block${b.partial ? ' partial' : ''}">
          <div class="prompt-head"><h4>${esc(b.title || '正文')}</h4>${b.partial ? '<span class="badge-partial" title="只替换完整版中的一部分，不能单独使用">局部片段 · 需与完整版合并</span>' : ''}<span class="count">${b.updated_at ? `更新于 ${esc(b.updated_at)} · ` : ''}${b.body.length} 字</span>
            <button class="btn ghost" data-expand="${i}">展开</button><button class="btn primary" data-copy="${i}">复制</button></div>
          <pre class="prompt-body">${fmtBody(b.body)}</pre>
        </div>`).join('')}</div>${directions}`;
    $$('[data-tab]', sec).forEach((b) => b.addEventListener('click', () => { promptTab = Number(b.dataset.tab); renderPrompts(); }));
    $$('[data-copy]', sec).forEach((b) => b.addEventListener('click', () => copyText(v.blocks[Number(b.dataset.copy)].body)));
    $('[data-copy-all]', sec)?.addEventListener('click', () => copyText(full.map((b) => `【${b.title}】\n${b.body}`).join('\n\n')));
    $$('[data-expand]', sec).forEach((b) => b.addEventListener('click', () => {
      const blk = b.closest('.prompt-block');
      blk.classList.toggle('expanded');
      b.textContent = blk.classList.contains('expanded') ? '收起' : '展开';
    }));
  }

  function renderChecks() {
    const C = DOC.checks || [];
    const n = (s) => C.filter((c) => c.status === s).length;
    const ICON = { pass: '✓', warn: '!', fail: '×', skip: '–' };
    const idxOf = (id) => SEGS.findIndex((s) => s.id === id);
    $('#sec-checks').innerHTML = head('09', '质量对账', '模型声称 vs 代码实测 · 跳过不等于通过') + `
      <div class="panel checks">${C.map((c) => `
        <div class="check ${c.status}">
          <span class="ico">${ICON[c.status]}</span>
          <span class="nm">${esc(c.name)}</span>
          <span class="dt">${esc(c.detail)}${c.refs.length ? `<span class="refs">${c.refs.map((r) => `<button data-ref="${esc(r)}">${esc(r)}</button>`).join('')}</span>` : ''}</span>
        </div>`).join('')}</div>
      <p class="dim" style="font-size:12px;margin-top:10px">阈值：场景切点 ${M ? M.params.scene_threshold : P.scene_threshold} · 静止 &lt; ${P.static_max_motion} · 偏动 &gt; ${P.busy_min_motion} · 起音 +${P.onset_rise_db} dB · 卡点容差 ±${P.sync_tolerance}s。起音点与卡点率是基于响度曲线的估算。</p>`;
    $$('#sec-checks [data-ref]').forEach((b) => b.addEventListener('click', () => {
      const i = idxOf(b.dataset.ref);
      if (i >= 0) { seek(SEGS[i].start + 0.001); $(`#${CSS.escape(b.dataset.ref)}`)?.scrollIntoView({ block: 'center' }); }
    }));
    const pill = $('#checkPill');
    pill.innerHTML = `<b class="ok">${n('pass')}</b> 通过${n('warn') ? ` · <b class="w">${n('warn')}</b> 提示` : ''}${n('fail') ? ` · <b class="f">${n('fail')}</b> 未过` : ''}${n('skip') ? ` · ${n('skip')} 跳过` : ''}`;
    pill.addEventListener('click', () => $('#sec-checks').scrollIntoView());
  }

  function renderFoot() {
    $('#foot').innerHTML = `
      <span>生成于 ${esc(DOC.generated_at)} · ${esc(DOC.case_id)}</span>
      <span>切点、时长、运动、响度、色板由 ffmpeg 实测；节拍、机制与判断来自 analysis.json</span>`;
  }

  /* ---------------- toc / theme / export / keys ---------------- */
  function initToc() {
    const items = [['sec-hero', '概览'], ['sec-monitor', '监看台'], ['sec-beats', '节拍'], ['sec-why', '机制'], ['sec-visual', '视觉'],
      ['sec-camera', '节奏'], ['sec-transfer', '迁移'], ['sec-seedance', 'Seedance'], ['sec-prompts', 'Prompt'], ['sec-checks', '对账']];
    $('#toc').innerHTML = items.map(([id, l]) => `<a href="#${id}" data-id="${id}">${l}</a>`).join('');
    const io = new IntersectionObserver((ents) => {
      ents.forEach((e) => {
        if (e.isIntersecting) $$('#toc a').forEach((a) => a.classList.toggle('on', a.dataset.id === e.target.id));
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    items.forEach(([id]) => { const el = document.getElementById(id); if (el) io.observe(el); });
  }
  function initTheme() {
    const saved = localStorage.getItem('vca-theme');
    if (saved) document.documentElement.dataset.theme = saved;
    $('#btnTheme').addEventListener('click', toggleTheme);
  }
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('vca-theme', next);
  }
  function initExport() {
    $('#btnExport').addEventListener('click', () => {
      const { frames, filmstrip, ...rest } = DOC;
      const blob = new Blob([JSON.stringify(rest, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${DOC.case_id}_report.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  }
  function initKeys() {
    $('#btnKeys').addEventListener('click', () => { $('#keys').hidden = false; });
    $('#keys').addEventListener('click', () => { $('#keys').hidden = true; });
    document.addEventListener('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
      if (e.key === 'Escape') {
        closeLb(); $('#keys').hidden = true;
        if (typing) document.activeElement.blur();
        return;
      }
      if (typing) return;
      if (!$('#lightbox').hidden) {
        if (e.key === 'ArrowLeft') openLb(lbIdx - 1);
        if (e.key === 'ArrowRight') openLb(lbIdx + 1);
        return;
      }
      const fps = (M && M.probe.fps) || 30;
      const k = e.key;
      const now = video.currentTime || playheadT;
      if (k === ' ') { e.preventDefault(); togglePlay(); }
      else if (k === 'ArrowLeft') { e.preventDefault(); stepBeat(-1); }
      else if (k === 'ArrowRight') { e.preventDefault(); stepBeat(1); }
      else if (k === 'j' || k === 'J') seek(now - 1);
      else if (k === 'l' || k === 'L') seek(now + 1);
      else if (k === ',') { video.pause(); seek(now - 1 / fps); }
      else if (k === '.') { video.pause(); seek(now + 1 / fps); }
      else if (k === 'r' || k === 'R') toggleLoop();
      else if (k === 'p' || k === 'P') togglePip();
      else if (k === 't' || k === 'T') toggleTheme();
      else if (k === '/') { e.preventDefault(); $('#search').focus(); }
      else if (k === '?') $('#keys').hidden = false;
      else if (/^[1-9]$/.test(k) && DOC.prompts && DOC.prompts.versions[Number(k) - 1]) { promptTab = Number(k) - 1; renderPrompts(); }
    });
  }

  /* ---------------- boot ---------------- */
  renderHero();
  initPlayer();
  renderTracks();
  initBeats();
  renderWhy();
  renderVisual();
  renderCamera();
  renderTransfer();
  renderSeedance();
  renderPrompts();
  renderChecks();
  renderFoot();
  initToc();
  initTheme();
  initExport();
  initKeys();
  setBeat(SEGS.length ? 0 : -1);
  if (location.hash) {
    const i = SEGS.findIndex((s) => `#${s.id}` === location.hash);
    if (i >= 0) seek(SEGS[i].start + 0.001);
  }
})();
