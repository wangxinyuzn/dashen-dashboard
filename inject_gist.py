#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inject GistStorage module into dashen-dashboard/index.html
"""

import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# 1. GistStorage JS module + UI HTML - inject before </style>
#    We'll inject the CSS into the existing <style> block,
#    and the JS at the top of the <script> block.
# ============================================================

GIST_CSS = """
/* ---- 云同步 UI ---- */
#gist-sync-btn{position:fixed;top:10px;right:16px;z-index:9999;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);color:#fff;padding:3px 11px;border-radius:16px;font-size:12px;cursor:pointer;backdrop-filter:blur(4px);display:flex;align-items:center;gap:5px;transition:background .2s}
#gist-sync-btn:hover{background:rgba(255,255,255,.32)}
#gist-sync-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#ccc;flex-shrink:0}
#gist-sync-dot.ok{background:#52c41a}
#gist-sync-dot.syncing{background:#faad14;animation:gist-spin .8s linear infinite}
#gist-sync-dot.error{background:#ff4d4f}
@keyframes gist-spin{0%{opacity:1}50%{opacity:.3}100%{opacity:1}}
#gist-modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10000;align-items:center;justify-content:center}
#gist-modal-overlay.show{display:flex}
#gist-modal{background:#fff;border-radius:14px;padding:28px 28px 22px;width:440px;max-width:94vw;box-shadow:0 12px 40px rgba(0,0,0,.22)}
#gist-modal h3{margin:0 0 18px;font-size:16px;color:#333;display:flex;align-items:center;gap:8px}
.gist-field{margin-bottom:14px}
.gist-field label{display:block;font-size:13px;color:#555;margin-bottom:5px;font-weight:500}
.gist-field input{width:100%;padding:8px 12px;border:1.5px solid #d9d9d9;border-radius:8px;font-size:13px;outline:none;box-sizing:border-box;transition:border-color .15s}
.gist-field input:focus{border-color:#4f6ef7}
.gist-row{display:flex;gap:8px;margin-top:18px;flex-wrap:wrap}
.gist-btn{padding:8px 18px;border-radius:8px;font-size:13px;cursor:pointer;border:none;font-family:inherit;transition:background .15s}
.gist-btn-primary{background:#4f6ef7;color:#fff}.gist-btn-primary:hover{background:#3d5ce0}
.gist-btn-secondary{background:#f0f3ff;color:#4f6ef7;border:1px solid #c5d3ff}.gist-btn-secondary:hover{background:#e0e7ff}
.gist-btn-cancel{background:#f5f5f5;color:#666;border:1px solid #e0e0e0;margin-left:auto}.gist-btn-cancel:hover{background:#eee}
#gist-status-msg{margin-top:12px;font-size:13px;min-height:20px;padding:6px 10px;border-radius:6px}
#gist-status-msg.ok{background:#f6ffed;color:#389e0d}
#gist-status-msg.error{background:#fff2f0;color:#cf1322}
#gist-status-msg.info{background:#e6f4ff;color:#0958d9}
"""

GIST_HTML = """
<!-- ☁️ 云同步按钮 -->
<button id="gist-sync-btn" onclick="gistOpenModal()">
  <span id="gist-sync-dot"></span>
  <span id="gist-sync-label">云同步</span>
</button>

<!-- ☁️ 云同步配置弹窗 -->
<div id="gist-modal-overlay">
  <div id="gist-modal">
    <h3>⚙️ GitHub Gist 云同步配置</h3>
    <div class="gist-field">
      <label>GitHub Token（需有 gist 权限）</label>
      <input type="password" id="gist-token-input" placeholder="ghp_xxxxxxxxxxxx" autocomplete="off">
    </div>
    <div class="gist-field">
      <label>Gist ID（留空可自动创建新 Gist）</label>
      <input type="text" id="gist-id-input" placeholder="留空则点「创建新 Gist」自动创建">
    </div>
    <div id="gist-status-msg"></div>
    <div class="gist-row">
      <button class="gist-btn gist-btn-primary" onclick="gistSaveConfig()">保存并测试</button>
      <button class="gist-btn gist-btn-secondary" onclick="gistCreateNew()">创建新 Gist</button>
      <button class="gist-btn gist-btn-secondary" id="gist-push-btn" style="display:none" onclick="gistPushNow()">立即同步 →</button>
      <button class="gist-btn gist-btn-cancel" onclick="gistCloseModal()">关闭</button>
    </div>
  </div>
</div>
"""

GIST_JS = r"""
// ============================================================
// GistStorage — GitHub Gist 云端存储模块
// ============================================================
const GistStorage = {
  TOKEN_KEY:  'dashen_gist_token',
  GIST_ID_KEY:'dashen_gist_id',
  FILENAME:   'dashen-dashboard-data.json',
  _saveTimer: null,
  _status:    'idle', // idle | syncing | ok | error

  // ---- 配置读取 ----
  token()  { return localStorage.getItem(this.TOKEN_KEY)   || ''; },
  gistId() { return localStorage.getItem(this.GIST_ID_KEY) || ''; },
  isConfigured() { return !!(this.token() && this.gistId()); },

  // ---- 状态指示器 ----
  _setStatus(s, label) {
    this._status = s;
    const dot = document.getElementById('gist-sync-dot');
    const lbl = document.getElementById('gist-sync-label');
    if (!dot) return;
    dot.className = '';
    if (s === 'ok')      { dot.classList.add('ok');      if(lbl) lbl.textContent = label||'已同步'; }
    else if(s==='syncing'){dot.classList.add('syncing'); if(lbl) lbl.textContent = label||'同步中…';}
    else if(s==='error') { dot.classList.add('error');   if(lbl) lbl.textContent = label||'同步失败';}
    else                 {                               if(lbl) lbl.textContent = label||'云同步'; }
  },

  // ---- 收集所有需同步的 localStorage 数据 ----
  _collectData() {
    const KEYS = [
      'dashen_boom_rows','dashen_boom_title',
      'dashen_analysis','dashen_mkt_cal','dashen_cal_labels','dashen_cal_merge',
      'dashen_cal_colors','dashen_cal_rows','dashen_collapse',
    ];
    for (let i = 0; i < 10; i++) {
      ['_name','_goal','_cur'].forEach(s => KEYS.push('goal_' + i + s));
    }
    const data = {};
    KEYS.forEach(k => { const v = localStorage.getItem(k); if (v !== null) data[k] = v; });
    return data;
  },

  // ---- 从 Gist 拉取数据，写入 localStorage ----
  async pull() {
    if (!this.isConfigured()) return false;
    this._setStatus('syncing', '拉取中…');
    try {
      const resp = await fetch(`https://api.github.com/gists/${this.gistId()}`, {
        headers: { 'Authorization': `Bearer ${this.token()}`, 'Accept': 'application/vnd.github+json' }
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      const file = json.files && json.files[this.FILENAME];
      if (!file || !file.content) { this._setStatus('ok', '已同步(空)'); return true; }
      const data = JSON.parse(file.content);
      Object.entries(data).forEach(([k, v]) => { if (v !== null && v !== undefined) localStorage.setItem(k, v); });
      this._setStatus('ok', '已同步');
      return true;
    } catch(e) {
      console.warn('[GistStorage] pull failed:', e);
      this._setStatus('error', '拉取失败');
      return false;
    }
  },

  // ---- 把 localStorage 数据推送到 Gist ----
  async push() {
    if (!this.isConfigured()) return false;
    this._setStatus('syncing', '保存中…');
    try {
      const data = this._collectData();
      const body = JSON.stringify({
        files: { [this.FILENAME]: { content: JSON.stringify(data, null, 2) } }
      });
      const resp = await fetch(`https://api.github.com/gists/${this.gistId()}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${this.token()}`,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json'
        },
        body
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this._setStatus('ok', '已同步');
      return true;
    } catch(e) {
      console.warn('[GistStorage] push failed:', e);
      this._setStatus('error', '同步失败');
      return false;
    }
  },

  // ---- 防抖推送（编辑后调用）----
  schedulePush() {
    if (!this.isConfigured()) return;
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this.push(), 2000);
  },

  // ---- 创建新 Gist ----
  async createGist(token) {
    const t = token || this.token();
    if (!t) return null;
    try {
      const resp = await fetch('https://api.github.com/gists', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${t}`,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          description: '大圣AI 数据看板 - 云端数据存储',
          public: false,
          files: { [this.FILENAME]: { content: JSON.stringify({_created: new Date().toISOString()}, null, 2) } }
        })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      return json.id || null;
    } catch(e) {
      console.warn('[GistStorage] createGist failed:', e);
      return null;
    }
  },

  // ---- 测试连接 ----
  async testConnection(token, gistId) {
    try {
      const resp = await fetch(`https://api.github.com/gists/${gistId}`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Accept': 'application/vnd.github+json' }
      });
      return resp.ok;
    } catch(e) { return false; }
  },
};

// ---- 弹窗 UI 函数 ----
function gistOpenModal() {
  document.getElementById('gist-token-input').value = GistStorage.token();
  document.getElementById('gist-id-input').value    = GistStorage.gistId();
  document.getElementById('gist-push-btn').style.display = GistStorage.isConfigured() ? 'inline-flex' : 'none';
  gistSetMsg('', '');
  document.getElementById('gist-modal-overlay').classList.add('show');
}
function gistCloseModal() {
  document.getElementById('gist-modal-overlay').classList.remove('show');
}
function gistSetMsg(text, type) {
  const el = document.getElementById('gist-status-msg');
  el.textContent = text;
  el.className = type ? type : '';
}
async function gistSaveConfig() {
  const token  = document.getElementById('gist-token-input').value.trim();
  const gistId = document.getElementById('gist-id-input').value.trim();
  if (!token)  { gistSetMsg('❌ 请填写 GitHub Token', 'error'); return; }
  if (!gistId) { gistSetMsg('❌ 请填写 Gist ID（或点「创建新 Gist」）', 'error'); return; }
  gistSetMsg('🔄 正在测试连接…', 'info');
  const ok = await GistStorage.testConnection(token, gistId);
  if (ok) {
    localStorage.setItem(GistStorage.TOKEN_KEY,   token);
    localStorage.setItem(GistStorage.GIST_ID_KEY, gistId);
    gistSetMsg('✅ 连接成功！数据已保存。', 'ok');
    document.getElementById('gist-push-btn').style.display = 'inline-flex';
    GistStorage._setStatus('ok', '已同步');
  } else {
    gistSetMsg('❌ 连接失败，请检查 Token 和 Gist ID 是否正确。', 'error');
  }
}
async function gistCreateNew() {
  const token = document.getElementById('gist-token-input').value.trim();
  if (!token) { gistSetMsg('❌ 请先填写 GitHub Token', 'error'); return; }
  gistSetMsg('🔄 正在创建新 Gist…', 'info');
  const id = await GistStorage.createGist(token);
  if (id) {
    document.getElementById('gist-id-input').value = id;
    localStorage.setItem(GistStorage.TOKEN_KEY,   token);
    localStorage.setItem(GistStorage.GIST_ID_KEY, id);
    gistSetMsg('✅ 新 Gist 创建成功！ID: ' + id, 'ok');
    document.getElementById('gist-push-btn').style.display = 'inline-flex';
    GistStorage._setStatus('ok', '已同步');
  } else {
    gistSetMsg('❌ 创建失败，请检查 Token 权限（需有 gist scope）。', 'error');
  }
}
async function gistPushNow() {
  gistSetMsg('🔄 正在同步…', 'info');
  const ok = await GistStorage.push();
  gistSetMsg(ok ? '✅ 同步成功！' : '❌ 同步失败，请检查网络。', ok ? 'ok' : 'error');
}
// 点击遮罩关闭弹窗
document.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('gist-modal-overlay');
  if (overlay) overlay.addEventListener('click', e => { if(e.target === overlay) gistCloseModal(); });
});
// ============================================================
// END GistStorage
// ============================================================
"""

# ---- Step 1: Inject CSS into </style> ----
if GIST_CSS.strip() not in content:
    content = content.replace('</style>', GIST_CSS + '\n</style>', 1)
    print("✅ CSS injected")
else:
    print("⚠️  CSS already present")

# ---- Step 2: Inject HTML after <body> ----
if 'gist-modal-overlay' not in content:
    content = content.replace('<body>', '<body>\n' + GIST_HTML, 1)
    print("✅ HTML injected")
else:
    print("⚠️  HTML already present")

# ---- Step 3: Inject JS at the top of <script> ----
if 'GistStorage' not in content:
    content = content.replace('<script>\n', '<script>\n' + GIST_JS + '\n', 1)
    print("✅ JS module injected")
else:
    print("⚠️  JS already present")

# ---- Step 4: Patch boomSave ----
old_boomSave = "function boomSave(rows) { localStorage.setItem(BOOM_KEY, JSON.stringify(rows)); }"
new_boomSave = "function boomSave(rows) { localStorage.setItem(BOOM_KEY, JSON.stringify(rows)); GistStorage.schedulePush(); }"
if old_boomSave in content:
    content = content.replace(old_boomSave, new_boomSave)
    print("✅ boomSave patched")
else:
    print("⚠️  boomSave not found as expected")

# ---- Step 5: Patch calSave ----
old_calSave = "function calSave(data) { localStorage.setItem(CAL_KEY, JSON.stringify(data)); }"
new_calSave = "function calSave(data) { localStorage.setItem(CAL_KEY, JSON.stringify(data)); GistStorage.schedulePush(); }"
if old_calSave in content:
    content = content.replace(old_calSave, new_calSave)
    print("✅ calSave patched")
else:
    print("⚠️  calSave not found")

# ---- Step 6: Patch calSetRows ----
old_calSetRows = "function calSetRows(n) { localStorage.setItem(CAL_ROWS_KEY, n); }"
new_calSetRows = "function calSetRows(n) { localStorage.setItem(CAL_ROWS_KEY, n); GistStorage.schedulePush(); }"
if old_calSetRows in content:
    content = content.replace(old_calSetRows, new_calSetRows)
    print("✅ calSetRows patched")
else:
    print("⚠️  calSetRows not found")

# ---- Step 7: Patch calSaveLabel (calSaveLabels) ----
old_calSaveLabel = "  localStorage.setItem(CAL_LABELS_KEY, JSON.stringify(labels));\n}"
new_calSaveLabel = "  localStorage.setItem(CAL_LABELS_KEY, JSON.stringify(labels));\n  GistStorage.schedulePush();\n}"
if old_calSaveLabel in content:
    content = content.replace(old_calSaveLabel, new_calSaveLabel)
    print("✅ calSaveLabel patched")
else:
    print("⚠️  calSaveLabel not found")

# ---- Step 8: Patch calSaveMerge ----
old_calSaveMerge = "function calSaveMerge(d)  { localStorage.setItem(CAL_MERGE_KEY,  JSON.stringify(d)); }"
new_calSaveMerge = "function calSaveMerge(d)  { localStorage.setItem(CAL_MERGE_KEY,  JSON.stringify(d)); GistStorage.schedulePush(); }"
if old_calSaveMerge in content:
    content = content.replace(old_calSaveMerge, new_calSaveMerge)
    print("✅ calSaveMerge patched")
else:
    print("⚠️  calSaveMerge not found")

# ---- Step 9: Patch calSaveColors ----
old_calSaveColors = "function calSaveColors(d) { localStorage.setItem(CAL_COLORS_KEY, JSON.stringify(d)); }"
new_calSaveColors = "function calSaveColors(d) { localStorage.setItem(CAL_COLORS_KEY, JSON.stringify(d)); GistStorage.schedulePush(); }"
if old_calSaveColors in content:
    content = content.replace(old_calSaveColors, new_calSaveColors)
    print("✅ calSaveColors patched")
else:
    print("⚠️  calSaveColors not found")

# ---- Step 10: Patch analysisSave ----
old_analysisSave = "  localStorage.setItem(ANALYSIS_KEY, JSON.stringify(data));\n}"
new_analysisSave = "  localStorage.setItem(ANALYSIS_KEY, JSON.stringify(data));\n  GistStorage.schedulePush();\n}"
if old_analysisSave in content:
    content = content.replace(old_analysisSave, new_analysisSave)
    print("✅ analysisSave patched")
else:
    print("⚠️  analysisSave not found")

# ---- Step 11: Patch boomEditTitle (BOOM_TITLE_KEY setItem) ----
old_boomTitle = "    localStorage.setItem(BOOM_TITLE_KEY, v.trim());\n    boomRender();"
new_boomTitle = "    localStorage.setItem(BOOM_TITLE_KEY, v.trim());\n    GistStorage.schedulePush();\n    boomRender();"
if old_boomTitle in content:
    content = content.replace(old_boomTitle, new_boomTitle)
    print("✅ boomEditTitle patched")
else:
    print("⚠️  boomEditTitle not found")

# ---- Step 12: Patch goal _name setItem ----
old_goal_name = "    localStorage.setItem(g.key + '_name', new_val.trim());"
new_goal_name = "    localStorage.setItem(g.key + '_name', new_val.trim()); GistStorage.schedulePush();"
if old_goal_name in content:
    content = content.replace(old_goal_name, new_goal_name)
    print("✅ goal _name patched")
else:
    print("⚠️  goal _name not found")

# ---- Step 13: Patch goal _goal setItem (two occurrences) ----
old_goal_goal1 = "      localStorage.setItem(g.key + '_goal', v);\n    } else {"
new_goal_goal1 = "      localStorage.setItem(g.key + '_goal', v); GistStorage.schedulePush();\n    } else {"
if old_goal_goal1 in content:
    content = content.replace(old_goal_goal1, new_goal_goal1)
    print("✅ goal _goal (play) patched")
else:
    print("⚠️  goal _goal (play) not found")

old_goal_goal2 = "      localStorage.setItem(g.key + '_goal', v);\n    }\n  } else if(field === 'cur')"
new_goal_goal2 = "      localStorage.setItem(g.key + '_goal', v); GistStorage.schedulePush();\n    }\n  } else if(field === 'cur')"
if old_goal_goal2 in content:
    content = content.replace(old_goal_goal2, new_goal_goal2)
    print("✅ goal _goal (count) patched")
else:
    print("⚠️  goal _goal (count) not found")

# ---- Step 14: Patch goal _cur setItem ----
old_goal_cur = "    localStorage.setItem(g.key + '_cur', v);\n  }\n  applyDateRange();"
new_goal_cur = "    localStorage.setItem(g.key + '_cur', v); GistStorage.schedulePush();\n  }\n  applyDateRange();"
if old_goal_cur in content:
    content = content.replace(old_goal_cur, new_goal_cur)
    print("✅ goal _cur patched")
else:
    print("⚠️  goal _cur not found")

# ---- Step 15: Patch toggleCollapse (COLLAPSE_KEY) ----
old_collapse = "  localStorage.setItem(COLLAPSE_KEY, JSON.stringify(state));\n}"
new_collapse = "  localStorage.setItem(COLLAPSE_KEY, JSON.stringify(state));\n  GistStorage.schedulePush();\n}"
if old_collapse in content:
    content = content.replace(old_collapse, new_collapse)
    print("✅ toggleCollapse patched")
else:
    print("⚠️  toggleCollapse not found")

# ---- Step 16: Patch window load to pull from Gist first ----
old_load = """window.addEventListener('load', () => {
  
  boomRender();"""
new_load = """window.addEventListener('load', () => {
  // 初始化云同步状态指示器
  if (GistStorage.isConfigured()) {
    GistStorage._setStatus('syncing', '加载中…');
    GistStorage.pull().then(ok => {
      if (ok) {
        boomRender();
        calRender();
        analysisRender();
      }
    });
  }
  boomRender();"""
if old_load in content:
    content = content.replace(old_load, new_load)
    print("✅ window load patched")
else:
    print("⚠️  window load not found as expected")

# ---- Write result ----
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ Done. File written.")
