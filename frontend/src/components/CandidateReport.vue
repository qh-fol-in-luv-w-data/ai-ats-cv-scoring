<template>
  <div class="wrap">
    <div class="page-title fade-in">
      <h1>AI Candidate Evaluation Persona</h1>
      <p>Automated pipeline analyzing CV, JD, AI & 5G assessments via GPT-4o</p>
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
              <span>Drag & drop CV file here or click to browse</span>
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
          <label>Interview Survey URL <span class="opt">(Optional)</span></label>
          <input v-model="f.survey_url" type="url" placeholder="Leave blank if none" />
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
      <!-- Overview Meta -->
      <section class="glass card fade-up" style="animation-delay: 0.1s">
        <div class="meta-wrap">
          <div class="meta-item main-meta">
            <div class="meta-icon">👤</div>
            <div>
              <div class="meta-lbl">Candidate Name</div>
              <div class="meta-val highlight">{{ r.candidate_name }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon">💼</div>
            <div>
              <div class="meta-lbl">Position</div>
              <div class="meta-val">{{ r.position }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon">✉️</div>
            <div>
              <div class="meta-lbl">Email / Phone</div>
              <div class="meta-val contact">{{ r.email }} <br> {{ r.phone }}</div>
            </div>
          </div>
        </div>

        <div class="section-title">Phần I: Tổng quan Hồ sơ & Điểm số (Executive Summary)</div>
        <div class="score-badges">
          <!-- AI Readiness Index -->
          <div class="score-card glass" :class="aiClass">
            <div class="sc-icon">🤖</div>
            <div class="sc-content">
              <div class="sc-lbl">AI Readiness Index</div>
              <div class="sc-num">{{ r.ai_test_total }}<span>/100</span></div>
            </div>
          </div>

          <!-- Phân loại Ứng viên -->
          <div class="score-card glass final" :class="aiClass">
            <div class="sc-lbl">Phân loại Ứng viên</div>
            <div class="sc-dec">{{ r.ai_test_label }}</div>
          </div>
        </div>
      </section>

      <!-- Tables Grid -->
      <div class="tables-grid">
        <!-- AI Test Details -->
        <section class="glass card fade-up" style="animation-delay: 0.2s">
          <div class="card-header">
            <div class="icon">📊</div>
            <h2>AI Readiness Details</h2>
          </div>
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>#</th><th>Dimension</th><th class="c">Max</th><th class="c">Score</th><th>Evaluation</th></tr></thead>
              <tbody>
                <tr v-for="row in aiRows" :key="row.cau">
                  <td class="c dim">{{ row.cau }}</td>
                  <td class="dim-name">{{ row.noi_dung }}</td>
                  <td class="c">{{ row.diem_toi_da }}</td>
                  <td class="c"><span class="badge-sc" :class="sc(row.diem_cham,row.diem_toi_da)">{{ row.diem_cham }}</span></td>
                  <td class="rsn">{{ row.ly_do }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- SWAT Details -->
        <section class="glass card fade-up" style="animation-delay: 0.3s">
          <div class="card-header">
            <div class="icon">🏆</div>
            <h2>SWAT Elite Framework</h2>
          </div>
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>Pillar</th><th class="c">Weight</th><th class="c">Raw</th><th class="c">W.Score</th><th>Evidence</th></tr></thead>
              <tbody>
                <tr v-for="row in swatRows" :key="row.tru_cot">
                  <td class="dim-name">{{ row.tru_cot }}</td>
                  <td class="c">{{ row.ty_trong }}</td>
                  <td class="c">{{ row.diem_tho }}</td>
                  <td class="c"><span class="badge-sc" :class="sc(row.diem_trong_so,2)">{{ row.diem_trong_so }}</span></td>
                  <td class="rsn">{{ row.co_so }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <!-- Qualitative Analysis (Phần II) -->
      <section class="glass card fade-up" style="animation-delay: 0.4s">
        <div class="card-header">
          <div class="icon">🧠</div>
          <h2>Phần II: Phân tích Năng lực Chuyên sâu (Core Analysis)</h2>
        </div>
        <div class="ana-grid">
          <div class="ana glass s full">
            <div class="ana-hdr">💪 1. ĐIỂM MẠNH (Strengths)</div>
            <ul class="ana-list">
              <li><strong>Kỹ năng công nghệ nổi trội:</strong> {{ r.strength_tech_skills }}</li>
              <li><strong>Chỉ số vượt chuẩn (Exceeding Standards):</strong> {{ r.strength_exceeding }}</li>
            </ul>
          </div>
          <div class="ana glass g full">
            <div class="ana-hdr">⚠️ 2. ĐIỂM HẠN CHẾ (Gaps & Misalignments)</div>
            <ul class="ana-list">
              <li><strong>Kỹ năng/tư duy thiếu hụt:</strong> {{ r.gap_missing_skills }}</li>
              <li><strong>Rủi ro vận hành/bảo mật:</strong> {{ r.gap_risks }}</li>
            </ul>
          </div>
          <div class="ana glass b full">
            <div class="ana-hdr">⭐ 3. NĂNG LỰC NỔI BẬT NHẤT (“BEST AT”)</div>
            <ul class="ana-list">
              <li><strong>Chuyên môn mạnh nhất:</strong> {{ r.best_at_core }}</li>
              <li><strong>Năng lực vận hành 2AS:</strong> {{ r.best_at_2as_ops }}</li>
              <li><strong>Mức độ sẵn sàng sử dụng 2AS:</strong> {{ r.best_at_2as_ready }}</li>
              <li><strong>Ngoại ngữ & Thực chiến:</strong> {{ r.best_at_global }}</li>
            </ul>
          </div>
        </div>
      </section>

      <div class="success-toast fade-up" style="animation-delay: 0.5s">
        <span class="icon">✅</span>
        Data permanently saved to DocType: <strong>{{ r.doctype_name }}</strong>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const f = ref({ ai_test_url:'', g5_test_url:'', eq_test_url:'', survey_url:'', jd_text:'' })
const cvFile = ref(null)
const drag = ref(false)
const loading = ref(false)
const err = ref('')
const r = ref(null)

const parse = (v) => { try { return typeof v==='string' ? JSON.parse(v) : (v||[]) } catch { return [] } }
const aiRows   = computed(() => parse(r.value?.ai_test_table))
const swatRows = computed(() => parse(r.value?.swat_table))

const aiClass   = computed(() => ({ green: ['AI-Ready','Xuất sắc'].includes(r.value?.ai_test_label), yellow: r.value?.ai_test_label==='Theo dõi thêm', red: r.value?.ai_test_label==='Non-AI' }))
const swatClass = computed(() => ({ green: r.value?.swat_label==='ĐẠT', red: r.value?.swat_label==='KHÔNG ĐẠT' }))
const decClass  = computed(() => ({ 'dec-pass': r.value?.decision==='ĐẠT', 'dec-fail': r.value?.decision==='KHÔNG ĐẠT', 'dec-watch': r.value?.decision==='THEO DÕI THÊM' }))

function sc(score, max) { const p=(score/max)*100; return p>=75?'hi':p>=50?'mid':'lo' }
function pickFile(e) { cvFile.value = e.target.files[0]||null }
function dropFile(e) { drag.value=false; cvFile.value=e.dataTransfer.files[0]||null }

async function run() {
  err.value=''; r.value=null
  // Không bắt buộc link nữa, nếu để trống thì gửi rỗng
  loading.value=true
  try {
    const fd = new FormData()
    if (cvFile.value) fd.append('cv_file', cvFile.value)
    Object.entries(f.value).forEach(([k,v]) => fd.append(k,v))
    
    // Disable cache khi test
    fd.append('api_use_cache', '0')

    const res = await fetch('/api/method/ai_ats.api.generate_candidate_report',{ method:'POST', body:fd })
    const js = await res.json()
    if (!res.ok||js.exc) throw new Error(js.exc||'Server Error')
    r.value = js.message
    setTimeout(() => window.scrollTo({ top: 500, behavior: 'smooth' }), 200)
  } catch(e) { err.value=`❌ ${e.message}` }
  finally { loading.value=false }
}
</script>

<style scoped>
.wrap { max-width: 1200px; margin: 0 auto; padding: 3rem 1.5rem; }

/* Headers */
.page-title { text-align: center; margin-bottom: 3rem; }
.page-title h1 { font-size: 2.2rem; font-weight: 800; margin-bottom: 0.5rem; }
.page-title p { color: var(--text-2); font-size: 1rem; }

.card { padding: 2rem; margin-bottom: 2rem; position: relative; overflow: hidden; }
.card::before {
  content:''; position:absolute; top:0; left:0; width:100%; height:1px;
  background: linear-gradient(90deg, transparent, rgba(99,102,241,0.5), transparent);
}
.card-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
.card-header .icon { font-size: 1.5rem; }
.card-header h2 { font-size: 1.15rem; font-weight: 700; color: #fff; }

/* Form Grid */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.field { display: flex; flex-direction: column; gap: 0.5rem; }
.field.full { grid-column: 1 / -1; }
label { font-size: 0.85rem; font-weight: 600; color: var(--text-2); }
.opt { font-weight: 400; opacity: 0.6; font-size: 0.75rem; }

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

/* Upload Zone */
.upload-zone {
  border: 2px dashed var(--border-2);
  border-radius: var(--radius-sm);
  padding: 1.5rem;
  background: rgba(15,23,42,0.3);
  cursor: pointer; transition: all 0.3s;
}
.upload-zone:hover, .upload-zone.over {
  border-color: var(--primary-2);
  background: rgba(99,102,241,0.05);
}
.uz-content { display: flex; align-items: center; justify-content: center; gap: 0.75rem; color: var(--text-2); font-weight: 500; }
.uz-content.ok { color: var(--green); }
.uz-icon { font-size: 1.4rem; }
.btn-clear { background: none; border: none; color: var(--red); cursor: pointer; padding: 0.2rem 0.5rem; border-radius: 4px; }
.btn-clear:hover { background: rgba(239,68,68,0.2); }

/* Run Button */
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

/* ── Result Meta ── */
.meta-wrap {
  display: flex; gap: 2rem; padding-bottom: 2rem;
  border-bottom: 1px solid var(--border); margin-bottom: 2rem;
  flex-wrap: wrap;
}
.meta-item { display: flex; align-items: center; gap: 1rem; }
.meta-icon {
  width: 44px; height: 44px; border-radius: 12px;
  background: rgba(15,23,42,0.6); border: 1px solid var(--border-2);
  display: flex; align-items: center; justify-content: center; font-size: 1.3rem;
}
.meta-lbl { font-size: 0.75rem; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; margin-bottom: 0.2rem; }
.meta-val { font-size: 1rem; font-weight: 600; color: #fff; }
.meta-val.highlight { font-size: 1.4rem; color: var(--primary-2); text-shadow: 0 0 10px rgba(129,140,248,0.4); }
.meta-val.contact { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: var(--text-2); font-weight: 400; line-height: 1.4; }

/* Score Badges */
.score-badges { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem; }
.score-card {
  padding: 1.5rem; border-radius: var(--radius-sm);
  display: flex; align-items: center; gap: 1.25rem;
  border-left: 4px solid transparent;
}
.sc-icon { font-size: 2.2rem; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5)); }
.sc-lbl { font-size: 0.85rem; color: var(--text-2); font-weight: 600; margin-bottom: 0.2rem; }
.sc-num { font-size: 2rem; font-weight: 800; color: #fff; line-height: 1; margin-bottom: 0.4rem; }
.sc-num span { font-size: 0.9rem; color: var(--text-3); font-weight: 600; margin-left: 2px; }
.sc-tag { font-size: 0.8rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 4px; display: inline-block; }

.score-card.green { border-left-color: var(--green); background: linear-gradient(90deg, rgba(16,185,129,0.1), transparent); }
.score-card.green .sc-tag { background: rgba(16,185,129,0.2); color: #34d399; }
.score-card.yellow { border-left-color: var(--yellow); background: linear-gradient(90deg, rgba(245,158,11,0.1), transparent); }
.score-card.yellow .sc-tag { background: rgba(245,158,11,0.2); color: #fbbf24; }
.score-card.red { border-left-color: var(--red); background: linear-gradient(90deg, rgba(239,68,68,0.1), transparent); }
.score-card.red .sc-tag { background: rgba(239,68,68,0.2); color: #fca5a5; }

.score-card.final { flex-direction: column; align-items: flex-start; justify-content: center; gap: 0.5rem; }
.sc-dec { font-size: 1.8rem; font-weight: 900; letter-spacing: 0.02em; }
.final.dec-pass { border-left-color: var(--green); } .final.dec-pass .sc-dec { color: var(--green); text-shadow: 0 0 15px rgba(16,185,129,0.4); }
.final.dec-fail { border-left-color: var(--red); } .final.dec-fail .sc-dec { color: var(--red); text-shadow: 0 0 15px rgba(239,68,68,0.4); }
.final.dec-watch { border-left-color: var(--yellow); } .final.dec-watch .sc-dec { color: var(--yellow); text-shadow: 0 0 15px rgba(245,158,11,0.4); }

/* Tables */
.tables-grid { display: grid; grid-template-columns: 1fr; gap: 2rem; }
.tbl-wrap { overflow-x: auto; margin: 0 -2rem; padding: 0 2rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { text-align: left; padding: 1rem 0.75rem; color: var(--text-3); font-weight: 600; border-bottom: 1px solid var(--border-2); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
td { padding: 1rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.03); vertical-align: top; }
tbody tr:hover { background: rgba(255,255,255,0.02); }
.c { text-align: center; }
.dim { font-family: 'JetBrains Mono', monospace; color: var(--text-3); }
.dim-name { font-weight: 600; color: #fff; }
.rsn { color: var(--text-2); max-width: 350px; line-height: 1.5; font-size: 0.85rem; }

.badge-sc { padding: 0.25rem 0.6rem; border-radius: 6px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.hi { background: rgba(16,185,129,0.2); color: #34d399; }
.mid{ background: rgba(245,158,11,0.2); color: #fbbf24; }
.lo { background: rgba(239,68,68,0.2); color: #fca5a5; }

/* Analysis Grid */
.ana-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.ana { padding: 1.5rem; position: relative; border-left: 3px solid transparent; background: rgba(15,23,42,0.4); }
.ana::before { content: ''; position: absolute; top: 0; left: -3px; width: 3px; height: 100%; box-shadow: 0 0 10px currentColor; opacity: 0.5; }
.ana.s { border-color: var(--green); color: var(--green); }
.ana.g { border-color: var(--yellow); color: var(--yellow); }
.ana.b { border-color: var(--primary-2); color: var(--primary-2); }
.ana.c { border-color: #38bdf8; color: #38bdf8; }
.ana.n { border-color: var(--accent); color: var(--accent); }
.full { grid-column: 1 / -1; }
.ana-hdr { font-weight: 700; font-size: 1.05rem; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem; }
.ana-txt { color: var(--text); line-height: 1.6; font-size: 0.95rem; white-space: pre-wrap; }
.ana-list { list-style: none; padding-left: 0; display: flex; flex-direction: column; gap: 0.8rem; }
.ana-list li { position: relative; padding-left: 1.5rem; line-height: 1.6; color: var(--text); font-size: 0.95rem; }
.ana-list li::before { content: '•'; position: absolute; left: 0.4rem; color: currentColor; font-weight: bold; }
.ana-list li strong { color: #fff; margin-right: 0.3rem; }

/* Success Toast */
.success-toast {
  margin-top: 2rem; padding: 1.25rem;
  background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3);
  border-radius: var(--radius-sm); display: flex; align-items: center; gap: 1rem;
  color: #a7f3d0; font-size: 0.95rem; box-shadow: 0 4px 20px rgba(16,185,129,0.1);
}
.success-toast .icon { font-size: 1.5rem; }

.section-title { font-size: 1.25rem; font-weight: 800; color: var(--primary-2); margin-bottom: 1.5rem; margin-top: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid rgba(99,102,241,0.3); padding-bottom: 0.5rem; display: inline-block; }

/* Utils */
.fade-in { animation: fadeUp 0.6s ease-out both; }
.fade-up { animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }

@media (max-width: 800px) {
  .grid-2, .ana-grid, .score-badges { grid-template-columns: 1fr; }
  .field.full, .full { grid-column: 1; }
  .wrap { padding: 1.5rem 1rem; }
}
</style>
