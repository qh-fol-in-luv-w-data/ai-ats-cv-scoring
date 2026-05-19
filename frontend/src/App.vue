<template>
  <div class="app">
    <!-- Header -->
    <header class="header">
      <div class="header-inner">
        <div class="logo-wrap">
          <div class="logo-icon">🧠</div>
          <div>
            <div class="logo-title">AI ATS</div>
            <div class="logo-sub">CT Group · NoAI-NoHire</div>
          </div>
        </div>
        
        <!-- Tabs -->
        <div class="tabs">
          <button :class="{ active: currentTab === 'report' }" @click="currentTab = 'report'">Đánh Giá</button>
          <button :class="{ active: currentTab === 'match' }" @click="currentTab = 'match'">Gợi ý công việc</button>
        </div>

        <div class="header-badges">
          <span class="hbadge">Powered by GPT-4o</span>
          <span class="hbadge accent">DAIT Division</span>
        </div>
      </div>
    </header>

    <main class="main">
      <CandidateReport v-if="currentTab === 'report'" />
      <JobMatcher v-if="currentTab === 'match'" />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import CandidateReport from './components/CandidateReport.vue'
import JobMatcher from './components/JobMatcher.vue'

const currentTab = ref('match')
</script>

<style scoped>
.app { min-height: 100vh; display: flex; flex-direction: column; }

/* ── Header ── */
.header {
  position: sticky; top: 0; z-index: 100;
  background: rgba(5, 8, 20, 0.85);
  backdrop-filter: blur(24px) saturate(1.8);
  border-bottom: 1px solid rgba(99,102,241,0.2);
  box-shadow: 0 1px 0 rgba(255,255,255,0.04), 0 4px 24px rgba(0,0,0,0.3);
}
.header-inner {
  max-width: 1200px; margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.85rem 2rem;
}
.logo-wrap { display: flex; align-items: center; gap: 0.85rem; }
.logo-icon {
  width: 42px; height: 42px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.3rem;
  box-shadow: 0 0 20px rgba(99,102,241,0.4);
  animation: pulse-glow 3s ease-in-out infinite;
}
.logo-title { font-size: 1.15rem; font-weight: 800; color: #e2e8f0; letter-spacing: -0.02em; }
.logo-sub   { font-size: 0.72rem; color: #64748b; margin-top: 1px; }

.tabs {
  display: flex; gap: 0.5rem; background: rgba(15,23,42,0.6); padding: 0.3rem; border-radius: 12px;
}
.tabs button {
  background: transparent; border: none; color: #94a3b8; padding: 0.5rem 1rem; border-radius: 8px;
  font-weight: 600; cursor: pointer; transition: 0.2s;
}
.tabs button:hover { color: white; }
.tabs button.active { background: #4f46e5; color: white; box-shadow: 0 2px 10px rgba(79,70,229,0.3); }

.header-badges { display: flex; gap: 0.6rem; }
.hbadge {
  padding: 0.28rem 0.75rem;
  border-radius: 20px;
  font-size: 0.73rem; font-weight: 600;
  background: rgba(99,102,241,0.1);
  border: 1px solid rgba(99,102,241,0.3);
  color: #818cf8;
}
.hbadge.accent {
  background: rgba(168,85,247,0.1);
  border-color: rgba(168,85,247,0.3);
  color: #c084fc;
}

.main { flex: 1; }

@media (max-width: 600px) {
  .header-inner { padding: 0.7rem 1rem; }
  .header-badges { display: none; }
}
</style>
