<template>
  <div class="wrap">
    <div class="page-title fade-in">
      <h1>AI Candidate Evaluation Persona</h1>
      <p>Automated pipeline analyzing CV, JD, AI &amp; 5G assessments via GPT-4o</p>
    </div>

    <!-- ── INPUT FORM ── -->
    <section class="glass card fade-up" style="animation-delay: 0.1s">
      <div class="card-header">
        <div class="icon">📥</div>
        <h2>Data Input Sources</h2>
      </div>

      <div class="grid-2">
        <div class="field full">
          <label>Candidate Resume / CV (PDF or DOCX)</label>
          <div class="upload-zone" :class="{over:drag}" @dragover.prevent="drag=true"
            @dragleave="drag=false" @drop.prevent="dropFile" @click="$refs.fi.click()">
            <div v-if="!cvFile" class="uz-content">
              <span class="uz-icon">📄</span>
              <span>Drag &amp; drop CV file here or click to browse</span>
            </div>
            <div v-else class="uz-content ok">
              <span class="uz-icon">✅</span>
              <span>{{ cvFile.name }} ({{(cvFile.size/1024).toFixed(1)}} KB)</span>
              <button class="btn-clear" @click.stop="cvFile=null">✕</button>
            </div>
          </div>
          <input ref="fi" type="file" accept=".pdf,.docx" hidden @change="pickFile" />
        </div>

        <div class="field full">
          <label>Job Description Content</label>
          <textarea v-model="f.jd_text" rows="3" placeholder="Paste the job description text here..." />
        </div>

        <div class="field">
          <label>Odoo: AI Test URL</label>
          <input v-model="f.ai_test_url" type="url" placeholder="http://..." />
        </div>
        <div class="field">
          <label>Odoo: 5G Competency URL</label>
          <input v-model="f.g5_test_url" type="url" placeholder="http://..." />
        </div>
        <div class="field">
          <label>jobtest.vn: EQ/IQ Report URL</label>
          <input v-model="f.eq_test_url" type="url" placeholder="https://..." />
        </div>
        <div class="field">
          <label>Interview Survey URL <span class="req">*</span></label>
          <input v-model="f.survey_url" type="url" placeholder="http://10.6.10.12:8069/survey/..." required />
        </div>
      </div>

      <button class="btn-run" :class="{loading}" :disabled="loading" @click="run">
        <span class="btn-txt" v-if="!loading">🚀 Generate Candidate Persona Report</span>
        <span class="btn-load" v-else>
          <span class="spinner"></span>
          <i>Analyzing across multiple dimensions...</i>
        </span>
      </button>
      <div v-if="err" class="err-msg">❌ {{ err }}</div>
    </section>

    <!-- ── REPORT OUTPUT ── -->
    <template v-if="r">

      <!-- ── HEADER: Name + Decision ── -->
      <section class="glass card fade-up report-header" style="animation-delay: 0.15s">
        <div class="rh-left">
          <div class="candidate-avatar">{{ initials }}</div>
          <div>
            <div class="candidate-name">{{ r.candidate_name }}</div>
            <div class="candidate-meta">
              <span class="badge-role">{{ r.position }}</span>
              <span class="contact-info" v-if="r.email">✉ {{ r.email }}</span>
              <span class="contact-info" v-if="r.phone">📞 {{ r.phone }}</span>
            </div>
          </div>
        </div>
        <div class="decision-badge" :class="decClass">
          <div class="dec-label">QUYẾT ĐỊNH</div>
          <div class="dec-value">{{ r.decision }}</div>
        </div>
      </section>

      <!-- ── SCORE CARDS ── -->
      <div class="scores-row fade-up" style="animation-delay: 0.2s">
        <!-- AI Readiness -->
        <div class="score-card glass" :class="aiClass">
          <div class="sc-top">
            <span class="sc-icon">🤖</span>
            <span class="sc-label">AI Readiness Index</span>
          </div>
          <div class="sc-number">{{ r.ai_test_total }}<span class="sc-max">/100</span></div>
          <div class="sc-bar"><div class="sc-bar-fill" :style="{width: r.ai_test_total+'%', background: aiBarColor}"></div></div>
          <div class="sc-tag" :class="aiClass">{{ r.ai_test_label }}</div>
        </div>

        <!-- SWAT Elite -->
        <div class="score-card glass" :class="swatClass">
          <div class="sc-top">
            <span class="sc-icon">🏆</span>
            <span class="sc-label">SWAT Elite Score</span>
          </div>
          <div class="sc-number">{{ r.swat_total?.toFixed(1) }}<span class="sc-max">/10</span></div>
          <div class="sc-bar"><div class="sc-bar-fill" :style="{width: (r.swat_total*10)+'%', background: swatBarColor}"></div></div>
          <div class="sc-tag" :class="swatClass">{{ r.swat_label }}</div>
        </div>

        <!-- 5G Test -->
        <div class="score-card glass" :class="g5Class">
          <div class="sc-top">
            <span class="sc-icon">🌟</span>
            <span class="sc-label">5G Potential Score</span>
          </div>
          <div class="sc-number">{{ r.g5_total?.toFixed(1) }}<span class="sc-max">/100</span></div>
          <div class="sc-bar"><div class="sc-bar-fill" :style="{width: r.g5_total+'%', background: g5BarColor}"></div></div>
          <div class="sc-tag" :class="g5Class">{{ g5Label }}</div>
        </div>
      </div>

      <!-- ── AI TEST TABLE ── -->
      <section class="glass card fade-up" style="animation-delay: 0.25s">
        <div class="card-header">
          <div class="icon">📊</div>
          <h2>Chi tiết chấm điểm AI Readiness (10 tiêu chí)</h2>
          <div class="total-pill" :class="aiClass">Tổng: {{ r.ai_test_total }}/100</div>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>#</th><th>Tiêu chí</th><th class="c">Max</th><th class="c">Điểm</th><th class="c">Tỉ lệ</th><th>Nhận xét & Dẫn chứng</th></tr></thead>
            <tbody>
              <tr v-for="row in aiRows" :key="row.cau">
                <td class="c idx">{{ row.cau }}</td>
                <td class="dim-name">{{ row.noi_dung }}</td>
                <td class="c muted">{{ row.diem_toi_da }}</td>
                <td class="c"><span class="badge-sc" :class="sc(row.diem_cham,row.diem_toi_da)">{{ row.diem_cham }}</span></td>
                <td class="c">
                  <div class="mini-bar"><div class="mini-fill" :class="sc(row.diem_cham,row.diem_toi_da)" :style="{width:(row.diem_cham/row.diem_toi_da*100)+'%'}"></div></div>
                </td>
                <td class="rsn"><div class="rsn-lines" v-html="fmt(row.ly_do)"></div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── SWAT TABLE ── -->
      <section class="glass card fade-up" style="animation-delay: 0.3s">
        <div class="card-header">
          <div class="icon">🏆</div>
          <h2>SWAT Elite Framework (4 trụ cột)</h2>
          <div class="total-pill" :class="swatClass">Tổng: {{ r.swat_total?.toFixed(2) }}/10 · {{ r.swat_label }}</div>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Trụ cột</th><th class="c">Trọng số</th><th class="c">Điểm thô</th><th class="c">Điểm quy đổi</th><th>Cơ sở đánh giá & Dẫn chứng</th></tr></thead>
            <tbody>
              <tr v-for="row in swatRows" :key="row.tru_cot">
                <td class="dim-name">{{ row.tru_cot }}</td>
                <td class="c weight-pill">{{ row.ty_trong }}</td>
                <td class="c muted">{{ row.diem_tho }}</td>
                <td class="c"><span class="badge-sc" :class="sc(row.diem_trong_so, 5)">{{ row.diem_trong_so?.toFixed(2) }}</span></td>
                <td class="rsn"><div class="rsn-lines" v-html="fmt(row.co_so)"></div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── 5G TABLE ── -->
      <section class="glass card fade-up" style="animation-delay: 0.35s">
        <div class="card-header">
          <div class="icon">🌟</div>
          <h2>5G Tiềm năng Quản lý (G1–G5 + 4 kỹ năng)</h2>
          <div class="total-pill" :class="g5Class">Tổng: {{ r.g5_total?.toFixed(1) }}/100 · {{ g5Label }}</div>
        </div>

        <!-- Summary by group -->
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Tiêu chí</th><th class="c">Max</th><th class="c">Điểm</th><th class="c">Tỉ lệ</th><th>Nhận xét & Dẫn chứng</th></tr></thead>
            <tbody>
              <tr v-for="row in g5Rows" :key="row.tieu_chi">
                <td class="dim-name">{{ row.tieu_chi }}</td>
                <td class="c muted">{{ row.diem_toi_da }}</td>
                <td class="c"><span class="badge-sc" :class="sc(row.diem_cham, row.diem_toi_da)">{{ row.diem_cham }}</span></td>
                <td class="c">
                  <div class="mini-bar"><div class="mini-fill" :class="sc(row.diem_cham,row.diem_toi_da)" :style="{width:(row.diem_cham/row.diem_toi_da*100)+'%'}"></div></div>
                </td>
                <td class="rsn"><div class="rsn-lines" v-html="fmt(row.ly_do)"></div></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Detail per-question (collapsible) -->
        <div class="detail-toggle" v-if="g5DetailRows.length">
          <button class="btn-toggle" @click="showG5Detail=!showG5Detail">
            {{ showG5Detail ? '▲ Ẩn' : '▼ Xem' }} chi tiết chấm điểm từng câu (30 câu)
          </button>
          <div class="detail-wrap" v-if="showG5Detail">
            <!-- Section A: Multiple choice -->
            <div class="detail-section-hdr">📝 Phần A – Trắc nghiệm (Câu 1–15, mỗi câu 2đ)</div>
            <table class="detail-table">
              <thead><tr><th class="c">Câu</th><th>Nội dung</th><th class="c">Đáp án đúng</th><th class="c">Ứng viên chọn</th><th class="c">Điểm</th></tr></thead>
              <tbody>
                <tr v-for="row in g5DetailRows.filter(r=>r.loai==='TN')" :key="row.cau">
                  <td class="c idx">{{ row.cau }}</td>
                  <td class="dim-name-sm">{{ row.noi_dung }}</td>
                  <td class="c"><span class="ans-badge correct">{{ row.dap_an_dung }}</span></td>
                  <td class="c">
                    <span class="ans-badge" :class="row.dap_an_chon===row.dap_an_dung?'correct':row.dap_an_chon?'wrong':'empty-ans'">
                      {{ row.dap_an_chon || '—' }}
                    </span>
                  </td>
                  <td class="c"><span class="badge-sc" :class="row.diem_cham>0?'hi':'lo'">{{ row.diem_cham }}</span></td>
                </tr>
              </tbody>
            </table>
            <!-- Section B: Essay -->
            <div class="detail-section-hdr" style="margin-top:1.5rem">✍️ Phần B – Tự luận (Câu 16–30, rubric từng câu)</div>
            <table class="detail-table">
              <thead><tr><th class="c">Câu</th><th>Nội dung</th><th class="c">Max</th><th class="c">Điểm</th><th>Nhận xét</th></tr></thead>
              <tbody>
                <tr v-for="row in g5DetailRows.filter(r=>r.loai==='TL')" :key="row.cau">
                  <td class="c idx">{{ row.cau }}</td>
                  <td class="dim-name-sm">{{ row.noi_dung }}</td>
                  <td class="c muted">{{ row.diem_toi_da }}</td>
                  <td class="c"><span class="badge-sc" :class="sc(row.diem_cham,row.diem_toi_da)">{{ row.diem_cham }}</span></td>
                  <td class="rsn sm"><div class="rsn-lines" v-html="fmt(row.ly_do)"></div></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- ── QUALITATIVE ANALYSIS ── -->
      <section class="glass card fade-up" style="animation-delay: 0.4s">
        <div class="card-header">
          <div class="icon">🧠</div>
          <h2>Phần II: Phân tích Năng lực Chuyên sâu (Core Analysis)</h2>
        </div>

        <div class="ana-grid">
          <!-- Strengths -->
          <div class="ana-block strength">
            <div class="ana-title"><span>💪</span> ĐIỂM MẠNH (Strengths)</div>
            <div class="ana-sub">
              <div class="ana-sub-title">🔧 Kỹ năng công nghệ & Chuyên môn</div>
              <div class="ana-body" v-html="fmt(r.strength_tech_skills)"></div>
            </div>
            <div class="ana-sub">
              <div class="ana-sub-title">⭐ Năng lực vượt chuẩn JD</div>
              <div class="ana-body" v-html="fmt(r.strength_exceeding)"></div>
            </div>
          </div>

          <!-- Gaps -->
          <div class="ana-block gap">
            <div class="ana-title"><span>⚠️</span> ĐIỂM HẠN CHẾ (Gaps)</div>
            <div class="ana-sub">
              <div class="ana-sub-title">🚫 Kỹ năng & Tư duy thiếu hụt</div>
              <div class="ana-body" v-html="fmt(r.gap_missing_skills)"></div>
            </div>
            <div class="ana-sub">
              <div class="ana-sub-title">🛡️ Rủi ro vận hành & Bảo mật</div>
              <div class="ana-body" v-html="fmt(r.gap_risks)"></div>
            </div>
          </div>

          <!-- Best At -->
          <div class="ana-block best full-col">
            <div class="ana-title"><span>🎯</span> NĂNG LỰC NỔI BẬT NHẤT (Best At)</div>
            <div class="best-grid">
              <div class="ana-sub">
                <div class="ana-sub-title">🏅 Chuyên môn mạnh nhất</div>
                <div class="ana-body" v-html="fmt(r.best_at_core)"></div>
              </div>
              <div class="ana-sub">
                <div class="ana-sub-title">🤖 Năng lực vận hành AI / 2AS</div>
                <div class="ana-body" v-html="fmt(r.best_at_2as_ops)"></div>
              </div>
              <div class="ana-sub">
                <div class="ana-sub-title">✅ Mức độ AI-readiness</div>
                <div class="ana-body" v-html="fmt(r.best_at_2as_ready)"></div>
              </div>
              <div class="ana-sub">
                <div class="ana-sub-title">🌐 Ngoại ngữ & Thực chiến quốc tế</div>
                <div class="ana-body" v-html="fmt(r.best_at_global)"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div class="success-toast fade-up" style="animation-delay: 0.5s">
        <span class="icon">✅</span>
        Đã lưu vào DocType: <strong>{{ r.doctype_name }}</strong>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { getCsrfToken, getSessionId } from '../utils/session'

const f = ref({ ai_test_url:'', g5_test_url:'', eq_test_url:'', survey_url:'', jd_text:'' })
const cvFile = ref(null)
const drag = ref(false)
const loading = ref(false)
const err = ref('')
const r = ref(null)
const showG5Detail = ref(false)

const parse = (v) => { try { return typeof v==='string' ? JSON.parse(v) : (v||[]) } catch { return [] } }
const aiRows   = computed(() => parse(r.value?.ai_test_table))
const swatRows = computed(() => parse(r.value?.swat_table))
const g5Rows   = computed(() => parse(r.value?.g5_table))
const g5DetailRows = computed(() => parse(r.value?.g5_detail_table))

const initials = computed(() => {
  const n = r.value?.candidate_name || ''
  return n.split(' ').map(w=>w[0]).slice(-2).join('').toUpperCase() || '?'
})

const aiClass   = computed(() => {
  const l = r.value?.ai_test_label
  return { green: l==='AI-Ready', red: l==='Non-AI', yellow: !['AI-Ready','Non-AI'].includes(l) }
})
const swatClass = computed(() => ({
  green: r.value?.swat_label==='Swat-Elite' || r.value?.swat_label==='ĐẠT',
  red: r.value?.swat_label==='KHÔNG ĐẠT'
}))
const g5Class   = computed(() => {
  const t = r.value?.g5_total || 0
  return { green: t>=80, yellow: t>=60 && t<80, red: t<60 }
})
const g5Label   = computed(() => {
  const t = r.value?.g5_total || 0
  return t>=80 ? 'Giỏi' : t>=60 ? 'Trung bình' : 'Không phù hợp'
})
const decClass  = computed(() => ({
  'dec-pass': r.value?.decision==='ĐẠT',
  'dec-fail': r.value?.decision==='KHÔNG ĐẠT',
  'dec-watch': !['ĐẠT','KHÔNG ĐẠT'].includes(r.value?.decision)
}))

const aiBarColor   = computed(() => aiClass.value.green ? '#10b981' : aiClass.value.red ? '#ef4444' : '#f59e0b')
const swatBarColor = computed(() => swatClass.value.green ? '#10b981' : '#ef4444')
const g5BarColor   = computed(() => g5Class.value.green ? '#10b981' : g5Class.value.yellow ? '#f59e0b' : '#ef4444')

function sc(score, max) {
  const p = (score / max) * 100
  return p >= 75 ? 'hi' : p >= 50 ? 'mid' : 'lo'
}

// Rich text renderer — handles both multiline (→ on own line) and inline (• text → ev → ev)
function fmt(text) {
  if (!text) return '<span class="empty">—</span>'

  const esc = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  const bold = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Normalise: split inline → within a bullet line into multiple lines
  // e.g. "• Python → CV: 'x' → AI Test: 'y'" → ["• Python", "→ CV: 'x'", "→ AI Test: 'y'"]
  const rawLines = text.split('\n')
  const lines = []
  for (const raw of rawLines) {
    const t = raw.trim()
    if (!t) { lines.push(''); continue }

    // If it's a bullet with inline → evidence, split them out
    if (/^[•\-]/.test(t) && t.includes('→')) {
      const parts = t.split(/\s*→\s*/)
      lines.push(parts[0].trim())                        // bullet text
      for (let p = 1; p < parts.length; p++) {
        if (parts[p].trim()) lines.push('→ ' + parts[p].trim()) // each evidence as own line
      }
    } else {
      lines.push(t)
    }
  }

  const out = []
  let i = 0

  while (i < lines.length) {
    const trimmed = lines[i].trim()
    if (!trimmed) { i++; continue }

    // Section header [X]
    if (/^\[.+\]/.test(trimmed)) {
      out.push(`<div class="sec-label">${bold(trimmed)}</div>`)
      i++; continue
    }

    // Bullet line — collect following → evidence lines
    if (/^[•\-]/.test(trimmed)) {
      const bulletTxt = bold(trimmed.replace(/^[•\-]\s*/, ''))
      const evidences = []
      i++
      while (i < lines.length) {
        const nTrimmed = lines[i].trim()
        if (!nTrimmed) { i++; break }
        if (nTrimmed.startsWith('→')) {
          evidences.push(`<div class="ev-line"><span class="ev-arrow">→</span><span class="ev-text">${bold(nTrimmed.slice(1).trim())}</span></div>`)
          i++
        } else { break }
      }
      const evHtml = evidences.length ? `<div class="ev-block">${evidences.join('')}</div>` : ''
      out.push(`<div class="bul-item"><div class="bul-line"><span class="bul-dot">●</span><span class="bul-txt">${bulletTxt}</span></div>${evHtml}</div>`)
      continue
    }

    // Standalone evidence line →
    if (trimmed.startsWith('→')) {
      out.push(`<div class="ev-line standalone"><span class="ev-arrow">→</span><span class="ev-text">${bold(trimmed.slice(1).trim())}</span></div>`)
      i++; continue
    }

    // Normal text
    out.push(`<div class="txt-line">${bold(trimmed)}</div>`)
    i++
  }

  return out.join('')
}

function pickFile(e) { cvFile.value = e.target.files[0]||null }
function dropFile(e) { drag.value=false; cvFile.value=e.dataTransfer.files[0]||null }

async function run() {
  err.value=''; r.value=null
  if (!cvFile.value) return err.value = '⚠️ Vui lòng tải CV lên trước.'
  if (!f.value.survey_url) return err.value = '⚠️ Interview Survey URL là bắt buộc.'
  loading.value=true
  try {
    const fd = new FormData()
    if (cvFile.value) fd.append('cv_file', cvFile.value)
    Object.entries(f.value).forEach(([k,v]) => fd.append(k,v))
    fd.append('api_use_cache', '0')

    const res = await fetch('/api/method/ai_ats.api.generate_candidate_report', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-Frappe-CSRF-Token': getCsrfToken(),
        'X-App-Session-Id': getSessionId(),
      },
      body: fd,
    })
    const js = await res.json()
    if (!res.ok || js.exc) throw new Error(js._server_messages ? JSON.parse(JSON.parse(js._server_messages)[0]).message : (js.exc || 'Server Error'))
    r.value = js.message
    setTimeout(() => window.scrollTo({ top: 500, behavior: 'smooth' }), 200)
  } catch(e) { err.value = `❌ ${e.message}` }
  finally { loading.value = false }
}
</script>

<style scoped>
.wrap { max-width: 1280px; margin: 0 auto; padding: 3rem 1.5rem; }

/* Page title */
.page-title { text-align: center; margin-bottom: 3rem; }
.page-title h1 { font-size: 2.2rem; font-weight: 800; margin-bottom: 0.5rem; }
.page-title p { color: var(--text-2); font-size: 1rem; }

/* Card base */
.card { padding: 2rem; margin-bottom: 2rem; position: relative; overflow: hidden; }
.card::before {
  content:''; position:absolute; top:0; left:0; width:100%; height:1px;
  background: linear-gradient(90deg, transparent, rgba(99,102,241,0.5), transparent);
}
.card-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.card-header .icon { font-size: 1.5rem; }
.card-header h2 { font-size: 1.1rem; font-weight: 700; color: #fff; flex: 1; }
.total-pill { font-size: 0.8rem; font-weight: 700; padding: 0.3rem 0.8rem; border-radius: 20px; white-space: nowrap; }
.total-pill.green { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
.total-pill.yellow { background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }
.total-pill.red { background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.3); }

/* ── REPORT HEADER ── */
.report-header { display: flex; align-items: center; justify-content: space-between; gap: 2rem; flex-wrap: wrap; padding: 1.75rem 2rem; }
.rh-left { display: flex; align-items: center; gap: 1.5rem; }
.candidate-avatar {
  width: 64px; height: 64px; border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  display: flex; align-items: center; justify-content: center;
  font-size: 1.4rem; font-weight: 800; color: #fff;
  box-shadow: 0 4px 20px rgba(99,102,241,0.4); flex-shrink: 0;
}
.candidate-name { font-size: 1.6rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; }
.candidate-meta { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.badge-role { font-size: 0.8rem; font-weight: 600; padding: 0.25rem 0.75rem; background: rgba(99,102,241,0.2); color: var(--primary-2); border-radius: 20px; border: 1px solid rgba(99,102,241,0.3); }
.contact-info { font-size: 0.85rem; color: var(--text-2); }

.decision-badge {
  text-align: center; padding: 1rem 2rem; border-radius: 12px;
  border: 2px solid transparent; flex-shrink: 0;
}
.dec-label { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.3rem; opacity: 0.7; }
.dec-value { font-size: 1.8rem; font-weight: 900; letter-spacing: 0.03em; }
.decision-badge.dec-pass { background: rgba(16,185,129,0.1); border-color: rgba(16,185,129,0.4); }
.decision-badge.dec-pass .dec-value { color: #34d399; text-shadow: 0 0 20px rgba(16,185,129,0.5); }
.decision-badge.dec-fail { background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.4); }
.decision-badge.dec-fail .dec-value { color: #fca5a5; text-shadow: 0 0 20px rgba(239,68,68,0.5); }
.decision-badge.dec-watch { background: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.4); }
.decision-badge.dec-watch .dec-value { color: #fbbf24; text-shadow: 0 0 20px rgba(245,158,11,0.5); }

/* ── SCORE CARDS ROW ── */
.scores-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.25rem; margin-bottom: 2rem; }
.score-card { padding: 1.5rem; border-radius: 14px; border-left: 4px solid transparent; display: flex; flex-direction: column; gap: 0.5rem; }
.score-card.green { border-left-color: #10b981; background: linear-gradient(135deg, rgba(16,185,129,0.08), rgba(16,185,129,0.02)); }
.score-card.yellow { border-left-color: #f59e0b; background: linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.02)); }
.score-card.red { border-left-color: #ef4444; background: linear-gradient(135deg, rgba(239,68,68,0.08), rgba(239,68,68,0.02)); }

.sc-top { display: flex; align-items: center; gap: 0.5rem; }
.sc-icon { font-size: 1.4rem; }
.sc-label { font-size: 0.8rem; font-weight: 600; color: var(--text-2); text-transform: uppercase; letter-spacing: 0.04em; }
.sc-number { font-size: 2.2rem; font-weight: 900; color: #fff; line-height: 1; }
.sc-max { font-size: 0.9rem; font-weight: 600; color: var(--text-3); margin-left: 3px; }
.sc-bar { height: 4px; border-radius: 2px; background: rgba(255,255,255,0.06); overflow: hidden; }
.sc-bar-fill { height: 100%; border-radius: 2px; transition: width 1s cubic-bezier(0.16,1,0.3,1); }
.sc-tag { font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px; align-self: flex-start; }
.green .sc-tag { background: rgba(16,185,129,0.2); color: #34d399; }
.yellow .sc-tag { background: rgba(245,158,11,0.2); color: #fbbf24; }
.red .sc-tag { background: rgba(239,68,68,0.2); color: #fca5a5; }

/* ── TABLES ── */
.tbl-wrap { overflow-x: auto; margin: 0 -2rem; padding: 0 2rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th { text-align: left; padding: 0.75rem; color: var(--text-3); font-weight: 600; border-bottom: 1px solid var(--border-2); text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em; white-space: nowrap; }
td { padding: 0.9rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.03); vertical-align: top; }
tbody tr:hover { background: rgba(255,255,255,0.02); }
.c { text-align: center; }
.idx { font-family: 'JetBrains Mono', monospace; color: var(--text-3); font-size: 0.8rem; width: 32px; }
.muted { color: var(--text-3); }
.dim-name { font-weight: 600; color: #fff; min-width: 160px; }
.weight-pill { font-weight: 700; color: var(--primary-2); }
.rsn { min-width: 280px; max-width: 420px; }

.badge-sc { padding: 0.25rem 0.55rem; border-radius: 6px; font-weight: 700; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
.hi { background: rgba(16,185,129,0.2); color: #34d399; }
.mid{ background: rgba(245,158,11,0.2); color: #fbbf24; }
.lo { background: rgba(239,68,68,0.2); color: #fca5a5; }

.mini-bar { width: 60px; height: 4px; border-radius: 2px; background: rgba(255,255,255,0.06); overflow: hidden; margin: 0 auto; }
.mini-fill { height: 100%; border-radius: 2px; }
.mini-fill.hi { background: #10b981; }
.mini-fill.mid{ background: #f59e0b; }
.mini-fill.lo { background: #ef4444; }

/* ── QUALITATIVE TEXT RENDERER ── */
.rsn-lines, .ana-body { font-size: 0.875rem; line-height: 1.7; color: var(--text); }

.txt-line { margin-bottom: 0.5rem; color: var(--text); line-height: 1.65; }

/* Bullet item wrapper — space between groups */
.bul-item { margin-bottom: 1.1rem; }
.bul-item:last-child { margin-bottom: 0; }

/* Bullet text row */
.bul-line { display: flex; gap: 0.6rem; align-items: flex-start; }
.bul-dot {
  color: var(--primary-2); font-size: 0.65rem; font-weight: 900;
  flex-shrink: 0; margin-top: 5px;
}
.bul-txt { color: #e2e8f0; font-weight: 500; line-height: 1.6; }
.bul-txt strong { color: #fff; font-weight: 700; }

/* Evidence block — indented under bullet */
.ev-block { margin: 0.55rem 0 0 1.2rem; display: flex; flex-direction: column; gap: 0.4rem; }

.ev-line {
  display: flex; gap: 0.5rem; align-items: flex-start;
  padding: 0.45rem 0.85rem;
  background: rgba(99,102,241,0.07);
  border-left: 2px solid rgba(99,102,241,0.45);
  border-radius: 0 8px 8px 0;
}
.ev-line.standalone {
  margin: 0.4rem 0; background: rgba(99,102,241,0.05);
}
.ev-arrow {
  color: var(--primary-2); font-weight: 900; flex-shrink: 0;
  font-size: 0.8rem; margin-top: 2px;
}
.ev-text {
  color: #94a3b8; font-size: 0.84rem; line-height: 1.55;
  font-style: italic;
}
.ev-text strong { color: #cbd5e1; font-style: normal; font-weight: 600; }

/* Section headers [A], [B], [THIẾU CỨNG] */
.sec-label {
  display: inline-block;
  font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.07em; color: var(--primary-2);
  margin: 1rem 0 0.6rem; padding: 0.25rem 0.65rem;
  background: rgba(99,102,241,0.1);
  border: 1px solid rgba(99,102,241,0.25);
  border-radius: 5px;
}

.empty { color: var(--text-3); font-style: italic; }

/* ── ANALYSIS GRID ── */
.ana-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.ana-block { border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
.ana-block.strength { background: rgba(16,185,129,0.05); border: 1px solid rgba(16,185,129,0.15); }
.ana-block.gap      { background: rgba(245,158,11,0.05); border: 1px solid rgba(245,158,11,0.15); }
.ana-block.best     { background: rgba(99,102,241,0.05); border: 1px solid rgba(99,102,241,0.15); }
.full-col { grid-column: 1 / -1; }

.ana-title { font-size: 1rem; font-weight: 800; color: #fff; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; }
.ana-sub { border-radius: 8px; padding: 1rem 1.25rem; background: rgba(0,0,0,0.2); }
.ana-sub-title { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-2); margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }

.best-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }

/* Form styles */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.field { display: flex; flex-direction: column; gap: 0.5rem; }
.field.full { grid-column: 1 / -1; }
label { font-size: 0.85rem; font-weight: 600; color: var(--text-2); }
.req { color: #ef4444; font-weight: 700; margin-left: 2px; }

input, textarea {
  background: rgba(15,23,42,0.4);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  padding: 0.8rem 1rem;
  color: var(--text);
  font-family: inherit; font-size: 0.95rem;
  transition: all 0.3s ease;
}
input:focus, textarea:focus {
  outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.2);
  background: rgba(15,23,42,0.8);
}
textarea { resize: vertical; min-height: 80px; }

.upload-zone {
  border: 2px dashed var(--border-2);
  border-radius: var(--radius-sm);
  padding: 1.5rem;
  background: rgba(15,23,42,0.3);
  cursor: pointer; transition: all 0.3s;
}
.upload-zone:hover, .upload-zone.over { border-color: var(--primary-2); background: rgba(99,102,241,0.05); }
.uz-content { display: flex; align-items: center; justify-content: center; gap: 0.75rem; color: var(--text-2); font-weight: 500; }
.uz-content.ok { color: var(--green); }
.uz-icon { font-size: 1.4rem; }
.btn-clear { background: none; border: none; color: var(--red); cursor: pointer; padding: 0.2rem 0.5rem; border-radius: 4px; }
.btn-clear:hover { background: rgba(239,68,68,0.2); }

.btn-run {
  margin-top: 2rem; width: 100%; padding: 1.1rem;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  color: #fff; font-weight: 700; font-size: 1.05rem;
  border: none; border-radius: var(--radius-sm);
  cursor: pointer; transition: all 0.3s;
  position: relative; overflow: hidden;
  box-shadow: 0 4px 15px rgba(99,102,241,0.4);
}
.btn-run::after {
  content:''; position:absolute; top:0; left:0; width:200%; height:100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
  transform: translateX(-100%);
}
.btn-run:hover:not(:disabled)::after { transform: translateX(50%); transition: transform 0.8s; }
.btn-run:disabled { opacity: 0.8; cursor: not-allowed; filter: grayscale(40%); }
.btn-load { display: flex; align-items: center; justify-content: center; gap: 0.75rem; }
.spinner {
  width: 20px; height: 20px;
  border: 3px solid rgba(255,255,255,0.3);
  border-top-color: #fff; border-radius: 50%;
  animation: spin 1s linear infinite;
}

.err-msg { margin-top: 1rem; padding: 1rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: var(--radius-sm); color: #fca5a5; font-weight: 500; }

.success-toast {
  margin-top: 2rem; padding: 1.25rem;
  background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3);
  border-radius: var(--radius-sm); display: flex; align-items: center; gap: 1rem;
  color: #a7f3d0; font-size: 0.95rem;
}
.success-toast .icon { font-size: 1.5rem; }

/* Detail table (collapsible) */
.detail-toggle { margin-top: 1.5rem; }
.btn-toggle {
  background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.25);
  color: var(--primary-2); font-size: 0.82rem; font-weight: 600;
  padding: 0.5rem 1.2rem; border-radius: 20px; cursor: pointer;
  transition: all 0.2s;
}
.btn-toggle:hover { background: rgba(99,102,241,0.2); }
.detail-wrap { margin-top: 1.25rem; }
.detail-section-hdr {
  font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--text-2);
  padding: 0.4rem 0; border-bottom: 1px solid var(--border); margin-bottom: 0.75rem;
}
.detail-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.detail-table th { padding: 0.5rem 0.6rem; color: var(--text-3); font-weight: 600; border-bottom: 1px solid var(--border-2); text-transform: uppercase; font-size: 0.68rem; letter-spacing: 0.04em; }
.detail-table td { padding: 0.6rem 0.6rem; border-bottom: 1px solid rgba(255,255,255,0.02); vertical-align: top; }
.detail-table tbody tr:hover { background: rgba(255,255,255,0.015); }
.dim-name-sm { font-weight: 500; color: var(--text); font-size: 0.82rem; }
.rsn.sm { font-size: 0.8rem; }

.ans-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 6px;
  font-weight: 800; font-size: 0.85rem; font-family: 'JetBrains Mono', monospace;
}
.ans-badge.correct { background: rgba(16,185,129,0.2); color: #34d399; }
.ans-badge.wrong   { background: rgba(239,68,68,0.2);  color: #fca5a5; }
.ans-badge.empty-ans { background: rgba(255,255,255,0.06); color: var(--text-3); font-size: 1rem; font-weight: 400; }

.fade-in { animation: fadeUp 0.6s ease-out both; }
.fade-up { animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }

@media (max-width: 900px) {
  .grid-2, .ana-grid, .scores-row, .best-grid { grid-template-columns: 1fr; }
  .field.full, .full-col { grid-column: 1; }
  .report-header { flex-direction: column; align-items: flex-start; }
  .wrap { padding: 1.5rem 1rem; }
}
</style>
