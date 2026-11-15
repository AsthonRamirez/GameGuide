<script setup>
import { computed, onMounted, ref } from 'vue'

const api = ''
const health = ref({ status: 'connecting', gemini_configured: false, supabase_configured: false })
const dashboard = ref({ configured: false, total: 0, categories: {}, feedback: {} })
const edition = ref('No especificada')
const gameVersion = ref('')
const question = ref('')
const busy = ref(false)
const error = ref('')
const pendingInteraction = ref(null)
const feedback = ref('')
const feedbackComment = ref('')
const feedbackStatus = ref('')
const sessionId = ref(null)
const messages = ref([
  { role: 'assistant', content: '¡Hola! Soy GameGuide AI. Pregúntame sobre Minecraft Vanilla, criaturas, objetos, crafteos, dimensiones y mecánicas. También puedo ayudarte a encontrar mods, modpacks y shaders en Modrinth.' }
])
const history = computed(() => messages.value.filter(m => ['user','assistant'].includes(m.role)).map(m => ({role:m.role, content:m.content})))
const categories = computed(() => Object.entries(dashboard.value.categories || {}).sort((a,b)=>b[1]-a[1]))
const maxCategory = computed(() => Math.max(1, ...categories.value.map(x=>x[1])))

async function loadData() {
  try {
    const [h, d] = await Promise.all([fetch(`${api}/api/health`), fetch(`${api}/api/dashboard`)])
    if (h.ok) health.value = await h.json()
    if (d.ok) dashboard.value = await d.json()
  } catch { health.value.status = 'offline' }
}
async function sendMessage() {
  const text = question.value.trim()
  if (!text || busy.value) return
  messages.value.push({ role:'user', content:text })
  question.value = ''
  busy.value = true
  error.value = ''
  feedbackStatus.value = ''
  pendingInteraction.value = null
  try {
    const response = await fetch(`${api}/api/chat`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text, edition:edition.value, game_version:gameVersion.value, history:history.value.slice(0,-1), session_id:sessionId.value})
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'No fue posible consultar el asistente.')
    sessionId.value = data.session_id
    messages.value.push({ role:'assistant', content:data.answer, sources:data.sources || [], meta:`${data.model_used} · ${(data.response_ms/1000).toFixed(2)} s` })
    pendingInteraction.value = data.interaction_id
    await loadData()
  } catch (e) {
    error.value = e.message
    messages.value.push({role:'assistant', content:`No pude completar la consulta. ${e.message}`})
  } finally { busy.value = false }
}
async function sendFeedback() {
  if (!pendingInteraction.value || !feedback.value) return
  try {
    const response = await fetch(`${api}/api/feedback`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({interaction_id:String(pendingInteraction.value), rating:feedback.value, comment:feedbackComment.value})
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'No se pudo guardar.')
    feedbackStatus.value = data.status
    pendingInteraction.value = null
    feedback.value = ''
    feedbackComment.value = ''
    await loadData()
  } catch (e) { feedbackStatus.value = e.message }
}
function clearChat() {
  messages.value = [{role:'assistant', content:'Conversación nueva. ¿Qué quieres descubrir sobre Minecraft?'}]
  pendingInteraction.value = null
  feedbackStatus.value = ''
}
onMounted(loadData)
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div class="eyebrow">TU GUÍA INTELIGENTE DE MINECRAFT</div>
      <div class="hero-content">
        <div>
          <h1>Explora, construye<br>y resuelve tus dudas.</h1>
          <p>Información de Minecraft Vanilla, criaturas, objetos, crafteos y mecánicas. Encuentra también mods, modpacks y shaders de Modrinth.</p>
          <div class="chips"><span>🧱 Minecraft Vanilla</span><span>🧩 Mods en Modrinth</span><span>🔎 Respuestas con fuentes</span></div>
        </div>
        <div class="pickaxe" aria-hidden="true">⛏</div>
      </div>
    </header>

    <div class="status-row">
      <span class="status-dot" :class="{online:health.status==='ok'}"></span>
      <span>API {{ health.status==='ok' ? 'conectada' : 'sin conexión' }}</span>
      <span class="status-separator">·</span>
      <span>Gemini {{ health.gemini_configured ? 'configurado' : 'pendiente de configurar' }}</span>
      <span class="status-separator">·</span>
      <span>Supabase {{ health.supabase_configured ? 'conectado' : 'pendiente de configurar' }}</span>
      <button class="refresh" @click="loadData">Actualizar</button>
    </div>

    <section class="dashboard">
      <div class="section-heading"><div><h2>Resumen de actividad</h2><p>Indicadores reales de Supabase · últimos 30 días</p></div><span class="section-tag">ANALYTICS</span></div>
      <div class="kpi-grid">
        <article class="kpi"><span>Consultas</span><strong>{{ dashboard.total ?? 0 }}</strong><small>Últimos 30 días</small></article>
        <article class="kpi"><span>Resolución validada</span><strong>{{ dashboard.resolution == null ? '—' : dashboard.resolution.toFixed(1)+'%' }}</strong><small>“Sí me ayudó” / consultas</small></article>
        <article class="kpi"><span>Satisfacción positiva</span><strong>{{ dashboard.satisfaction == null ? '—' : dashboard.satisfaction.toFixed(1)+'%' }}</strong><small>Calificaciones positivas</small></article>
        <article class="kpi"><span>Tiempo promedio</span><strong>{{ dashboard.avg_seconds == null ? '—' : dashboard.avg_seconds.toFixed(2)+' s' }}</strong><small>Tiempo de respuesta</small></article>
        <article class="kpi"><span>Con evidencia</span><strong>{{ dashboard.evidence_pct == null ? '—' : dashboard.evidence_pct.toFixed(1)+'%' }}</strong><small>Respuestas con fuentes</small></article>
        <article class="kpi"><span>Reutilización</span><strong>{{ dashboard.reuse_pct == null ? '—' : dashboard.reuse_pct.toFixed(1)+'%' }}</strong><small>Conocimiento en caché</small></article>
      </div>
      <div class="analytics-grid">
        <article class="panel">
          <h3>Consultas por categoría</h3>
          <div v-if="categories.length" class="bars">
            <div v-for="[name,value] in categories" :key="name" class="bar-row">
              <span>{{ name }}</span><div class="bar-track"><i :style="{width:(value/maxCategory*100)+'%'}"></i></div><b>{{ value }}</b>
            </div>
          </div>
          <p v-else class="empty">Aún no hay interacciones registradas.</p>
        </article>
        <article class="panel scenario">
          <h3>Escenario académico de referencia</h3>
          <p>Datos simulados del ejercicio; no se mezclan con registros reales.</p>
          <div class="scenario-stats"><div><small>Adopción</small><b>72%</b><span>1,800 / 2,500</span></div><div><small>Consultas por usuario</small><b>3.33</b><span>6,000 / 1,800</span></div><div><small>Tasa de resolución</small><b>85%</b><span>5,100 / 6,000</span></div><div><small>Precision RAG</small><b>80%</b><span>16 / 20</span></div><div><small>Recall RAG</small><b>64%</b><span>16 / 25</span></div></div>
        </article>
      </div>
    </section>

    <section class="chat-layout">
      <div class="chat-main panel">
        <div class="chat-title"><div><span class="live-dot"></span><div><h2>Chat de GameGuide AI</h2><p>Pregunta y recibe respuestas fundamentadas en fuentes.</p></div></div><button class="ghost-btn" @click="clearChat">Nueva conversación ↻</button></div>
        <div class="settings">
          <label>Edición <select v-model="edition"><option>No especificada</option><option>Java Edition</option><option>Bedrock Edition</option></select></label>
          <label>Versión (opcional)<input v-model="gameVersion" placeholder="Ej. 1.21.11 o 26.1"></label>
        </div>
        <div class="messages" aria-live="polite">
          <div v-for="(message,index) in messages" :key="index" class="message" :class="message.role">
            <div class="avatar">{{ message.role==='assistant' ? '⛏' : 'TÚ' }}</div>
            <div class="bubble">
              <div class="message-text">{{ message.content }}</div>
              <div v-if="message.sources?.length" class="sources"><strong>Fuentes consultadas</strong><a v-for="(source,i) in message.sources" :key="i" :href="source.url" target="_blank" rel="noreferrer">[{{ i+1 }}] {{ source.title }} ↗</a></div>
              <small v-if="message.meta" class="meta">{{ message.meta }}</small>
            </div>
          </div>
          <div v-if="busy" class="typing"><span></span><span></span><span></span> Buscando conocimiento…</div>
        </div>
        <form class="composer" @submit.prevent="sendMessage">
          <textarea v-model="question" rows="2" placeholder="Ej. ¿Cómo consigo una Elytra en supervivencia?" @keydown.enter.exact.prevent="sendMessage"></textarea>
          <button class="send-btn" :disabled="busy || !question.trim()">{{ busy ? 'Consultando…' : '⛏ Enviar pregunta' }}</button>
        </form>
        <p v-if="error" class="error">{{ error }}</p>
        <div v-if="pendingInteraction" class="feedback-box">
          <strong>¿Podrías contestar si esta información fue útil?</strong>
          <div class="rating-options">
            <label><input type="radio" v-model="feedback" value="si_me_ayudo"> Sí me ayudó</label>
            <label><input type="radio" v-model="feedback" value="no_entrego_justo"> No era justo lo que pedía</label>
            <label><input type="radio" v-model="feedback" value="nada_que_ver"> Nada que ver</label>
          </div>
          <textarea v-model="feedbackComment" rows="2" placeholder="Comentario opcional"></textarea>
          <button class="secondary-btn" :disabled="!feedback" @click="sendFeedback">Guardar calificación</button>
        </div>
        <p v-if="feedbackStatus" class="feedback-status">{{ feedbackStatus }}</p>
      </div>
      <aside class="side-panel">
        <div class="side-card"><span class="side-icon">📚</span><h3>Conocimiento con fuentes</h3><p>Prioriza información oficial, distingue la wiki comunitaria y separa contenido Vanilla de mods.</p></div>
        <div class="side-card"><span class="side-icon">🧭</span><h3>Respuestas contextualizadas</h3><p>Indica tu edición y versión para mejorar la precisión de las recomendaciones.</p></div>
        <div class="side-card"><span class="side-icon">🛠️</span><h3>¿Buscas un mod?</h3><p>Consulta compatibilidad, cargadores y versiones disponibles en Modrinth.</p></div>
      </aside>
    </section>
    <footer>GAMEGUIDE AI · PROTOTIPO ACADÉMICO · MINECRAFT.NET / MINECRAFT HELP / MINECRAFT WIKI / MODRINTH</footer>
  </main>
</template>
