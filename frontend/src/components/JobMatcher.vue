<template>
  <div class="wrap">
    <div class="page-title">
      <h1>💼 Match 1 CV - N Jobs</h1>
      <p>Sàng lọc hàng loạt vị trí công việc cho một ứng viên</p>
    </div>

    <!-- Đầu vào -->
    <div class="card glass">
      <div class="card-header">
        <div class="icon">📤</div>
        <h2>1. Tải lên CV Ứng viên</h2>
      </div>
      <div class="upload-box" @click="$refs.fileInput.click()" @dragover.prevent="drag=true" @dragleave.prevent="drag=false" @drop.prevent="dropFile" :class="{ dragging: drag }">
        <input type="file" ref="fileInput" accept=".pdf,.docx" hidden @change="pickFile">
        <div class="upload-icon">📄</div>
        <p v-if="!cvFile">Kéo thả file CV (PDF/DOCX) hoặc <span>Nhấn để chọn</span></p>
        <p v-else class="file-selected">Đã chọn: <strong>{{ cvFile.name }}</strong></p>
      </div>
    </div>

    <div class="card glass">
      <div class="card-header">
        <div class="icon">📋</div>
        <h2>2. Danh sách Job Description (JD)</h2>
      </div>
      
      <div class="jobs-list">
        <div v-for="(job, idx) in jobs" :key="idx" class="job-item">
          <div class="job-header">
            <h3>Job #{{ idx + 1 }}</h3>
            <button class="btn-remove" @click="removeJob(idx)" v-if="jobs.length > 1">✕ Xóa</button>
          </div>
          <div class="input-group">
            <label>Tên Vị Trí (Title)</label>
            <input type="text" v-model="job.title" placeholder="VD: Data Engineer...">
          </div>
          <div class="input-group">
            <label>Mô tả công việc (JD Text)</label>
            <textarea v-model="job.jd_text" rows="3" placeholder="Paste nội dung JD vào đây..."></textarea>
          </div>
        </div>
      </div>
      <button class="btn-outline" @click="addJob" style="margin-top: 1rem;">+ Thêm Job Mới</button>
    </div>

    <!-- Submit -->
    <div class="submit-wrap">
      <button class="btn-primary glow" @click="run" :disabled="loading || !cvFile">
        <span class="btn-text">{{ loading ? 'Đang phân tích...' : 'Bắt đầu Matching 🚀' }}</span>
        <div class="loader" v-if="loading"></div>
      </button>
      <p class="error-msg" v-if="err">{{ err }}</p>
    </div>

    <!-- Kết quả -->
    <div v-if="result" class="results-grid">
      <div v-for="match in result.matches" :key="match.job_id" class="result-card glass">
        <div class="match-header">
          <h3>{{ match.job_name }}</h3>
          <div class="score-circle" :style="`--p: ${match.score}%`" :class="scoreClass(match.score)">
            <span>{{ match.score }}%</span>
          </div>
        </div>
        <div class="match-body">
          <p class="reason">{{ match.reason }}</p>
          <div class="keywords">
            <div class="kw-group">
              <strong>✅ Tìm thấy:</strong>
              <span v-for="kw in match.keywords_found" :key="kw" class="badge kw-found">{{ kw }}</span>
            </div>
            <div class="kw-group" v-if="match.keywords_missing && match.keywords_missing.length">
              <strong>❌ Cần bổ sung:</strong>
              <span v-for="kw in match.keywords_missing" :key="kw" class="badge kw-miss">{{ kw }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { getCsrfToken, getSessionId } from '../utils/session'

const drag = ref(false)
const cvFile = ref(null)
const jobs = ref([
  { id: 1, title: 'Flutter Developer', jd_text: 'Yêu cầu 3 năm kinh nghiệm lập trình Flutter, Dart, có làm việc với Firebase.' },
  { id: 2, title: 'Backend Golang', jd_text: 'Yêu cầu kinh nghiệm Golang, xây dựng hệ thống Microservice, database PostgreSQL.' }
])
const loading = ref(false)
const err = ref('')
const result = ref(null)

function addJob() {
  jobs.value.push({ id: jobs.value.length + 1, title: '', jd_text: '' })
}
function removeJob(idx) {
  jobs.value.splice(idx, 1)
}

function pickFile(e) { cvFile.value = e.target.files[0] || null }
function dropFile(e) { drag.value = false; cvFile.value = e.dataTransfer.files[0] || null }

function scoreClass(score) {
  if (score >= 80) return 'excellent'
  if (score >= 60) return 'good'
  return 'poor'
}

async function run() {
  err.value = ''; result.value = null
  if (!cvFile.value) return err.value = '⚠️ Vui lòng tải CV lên trước.'
  if (!jobs.value.length || !jobs.value[0].title) return err.value = '⚠️ Cần ít nhất 1 Job để Match.'

  loading.value = true
  try {
    const fd = new FormData()
    fd.append('cv_file', cvFile.value)
    
    // Đánh lại ID cho jobs trước khi gửi
    const formattedJobs = jobs.value.map((j, i) => ({ ...j, id: i + 1 }))
    fd.append('jobs_json', JSON.stringify(formattedJobs))

    const res = await fetch('/api/method/ai_ats.job_matcher.match_candidate_jobs', {
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

    result.value = js.message
    setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }), 300)
  } catch(e) { 
    err.value = `❌ ${e.message}` 
  } finally { 
    loading.value = false 
  }
}
</script>

<style scoped>
.wrap { max-width: 1000px; margin: 0 auto; padding: 2rem 1rem; }
.page-title { text-align: center; margin-bottom: 2rem; }
.page-title h1 { font-size: 2rem; margin-bottom: 0.5rem; }

.glass {
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid rgba(255,255,255,0.05);
  backdrop-filter: blur(12px);
  border-radius: 16px;
}
.card { padding: 1.5rem; margin-bottom: 1.5rem; }
.card-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
.card-header h2 { font-size: 1.2rem; }

/* Upload */
.upload-box {
  border: 2px dashed rgba(255,255,255,0.1); border-radius: 12px;
  padding: 2rem; text-align: center; cursor: pointer; transition: all 0.2s;
}
.upload-box:hover, .upload-box.dragging { border-color: #6366f1; background: rgba(99,102,241,0.05); }
.upload-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }

/* Jobs */
.jobs-list { display: flex; flex-direction: column; gap: 1rem; }
.job-item { background: rgba(0,0,0,0.2); padding: 1rem; border-radius: 12px; border: 1px solid rgba(255,255,255,0.02); }
.job-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.job-header h3 { font-size: 1rem; color: #818cf8; }
.btn-remove { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: none; padding: 0.2rem 0.5rem; border-radius: 6px; cursor: pointer; }

.input-group { margin-bottom: 0.8rem; }
.input-group label { display: block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.3rem; }
.input-group input, .input-group textarea {
  width: 100%; padding: 0.6rem; border-radius: 8px;
  background: rgba(15,23,42,0.6); border: 1px solid rgba(255,255,255,0.1); color: white;
}

.btn-outline { background: transparent; border: 1px dashed #6366f1; color: #818cf8; padding: 0.6rem 1rem; border-radius: 8px; cursor: pointer; }
.btn-primary { background: #4f46e5; color: white; border: none; padding: 0.8rem 2rem; border-radius: 12px; font-weight: bold; font-size: 1.1rem; cursor: pointer; width: 100%; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.submit-wrap { margin: 2rem 0; text-align: center; }

/* Kết quả */
.results-grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.result-card { padding: 1.5rem; border-top: 4px solid #6366f1; }
.match-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.match-header h3 { font-size: 1.1rem; }

.score-circle {
  width: 50px; height: 50px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: bold; font-size: 1.2rem;
  background: conic-gradient(var(--c) var(--p), rgba(255,255,255,0.1) 0);
}
.score-circle span { background: #1e293b; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.score-circle.excellent { --c: #10b981; color: #10b981; }
.score-circle.good { --c: #eab308; color: #eab308; }
.score-circle.poor { --c: #ef4444; color: #ef4444; }

.reason { color: #cbd5e1; font-size: 0.95rem; line-height: 1.5; margin-bottom: 1rem; }
.kw-group { margin-bottom: 0.5rem; }
.badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin: 0.2rem; }
.kw-found { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.kw-miss { background: rgba(239, 68, 68, 0.15); color: #f87171; }
</style>
