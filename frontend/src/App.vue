<script setup>
import { computed, onMounted, ref } from 'vue'
const api = ''
const view = ref('dashboard')
const health = ref({ status: 'connecting', gemini_configured: false, supabase_configured: false })
const dashboard = ref({ configured:false, total:0, categories:{}, feedback:{}, daily:[] })
const publicItems = ref([])
const publicLoading = ref(false)
const publicError = ref('')
const edition = ref('No especificada')
const gameVersion = ref('')
const question = ref('')
const busy = ref(false)
const error = ref('')
const sessionId = ref(null)
const messages = ref([
  { role:'assistant', content:'¡Hola! Soy GameGuide AI. Pregúntame sobre Minecraft Vanilla, criaturas, objetos, crafteos, dimensiones y mecánicas. También puedo ayudarte a encontrar mods, modpacks y shaders en Modrinth.' }
])
const history = computed(() => messages.value.filter(m => ['user','assistant'].includes(m.role)).map(m => ({role:m.role,content:m.content})))
const categories = computed(() => Object.entries(dashboard.value.categories || {}).sort((a,b)=>b[1]-a[1]))
const totalVotes = computed(() => (dashboard.value.feedback?.likes || 0) + (dashboard.value.feedback?.dislikes || 0))
const dailyLabels = computed(() => (dashboard.value.daily || []).map(x => x.date.slice(5)))
const dailyValues = computed(() => (dashboard.value.daily || []).map(x => x.count))
const trendPoints = computed(() => {
  const values = dailyValues.value
  if (!values.length) return ''
  const max = Math.max(1, ...values)
  return values.map((value,index) => {
    const x = values.length === 1 ? 360 : 28 + index * (664 / (values.length - 1))
    const y = 188 - (value / max) * 155
    return `${x},${y}`
  }).join(' ')
})
const trendArea = computed(() => trendPoints.value ? `28,188 ${trendPoints.value} 692,188` : '')
const donutStyle = computed(() => {
  const likes = dashboard.value.feedback?.likes || 0
  const dislikes = dashboard.value.feedback?.dislikes || 0
  const total = likes + dislikes
  const split = total ? likes / total * 100 : 50
  return { background: `conic-gradient(#12a88a 0 ${split}%, #f08b78 ${split}% 100%)` }
})

function voterId() {
  let id = localStorage.getItem('gameguide_voter_id')
  if (!id) { id = crypto.randomUUID(); localStorage.setItem('gameguide_voter_id', id) }
  return id
}
async function loadData() {
  try {
    const [h,d] = await Promise.all([fetch(`${api}/api/health`),fetch(`${api}/api/dashboard`)])
    if (h.ok) health.value = await h.json()
    if (d.ok) dashboard.value = await d.json()
  } catch { health.value.status = 'offline' }
}
async function loadPublic() {
  publicLoading.value = true
  publicError.value = ''
  try {
    const response = await fetch(`${api}/api/public/consultations?limit=50`)
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'No se pudieron cargar las consultas públicas.')
    publicItems.value = data.items || []
  } catch (e) { publicError.value = e.message }
  finally { publicLoading.value = false }
}
async function sendMessage() {
  const text = question.value.trim()
  if (!text || busy.value) return
  messages.value.push({role:'user',content:text})
  question.value = ''
  busy.value = true
  error.value = ''
  try {
    const response = await fetch(`${api}/api/chat`, {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text,edition:edition.value,game_version:gameVersion.value,history:history.value.slice(0,-1),session_id:sessionId.value})
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'No fue posible consultar el asistente.')
    sessionId.value = data.session_id
    messages.value.push({role:'assistant',content:data.answer,sources:data.sources || [],meta:`${data.model_used} · ${(data.response_ms/1000).toFixed(2)} s`})
    await loadData()
  } catch (e) {
    error.value = e.message
    messages.value.push({role:'assistant',content:`No pude completar la consulta. ${e.message}`})
  } finally { busy.value = false }
}
function clearChat() {
  messages.value = [{role:'assistant',content:'Conversación nueva. ¿Qué quieres descubrir sobre Minecraft?'}]
  sessionId.value = null
  error.value = ''
}
async function vote(item, voteValue) {
  try {
    const response = await fetch(`${api}/api/public/consultations/${item.id}/vote`, {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({voter_id:voterId(),vote:voteValue})
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'No se pudo guardar tu voto.')
    await loadPublic()
    await loadData()
  } catch (e) { publicError.value = e.message }
}
function setView(next) {
  view.value = next
  if (next === 'public') loadPublic()
}
onMounted(loadData)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">⛏</div><div><strong>GameGuide AI</strong><small>GAME INTELLIGENCE</small></div></div>
      <div class="nav-label">ESPACIO DE TRABAJO</div>
      <nav>
        <button :class="{active:view==='dashboard'}" @click="setView('dashboard')"><span>▦</span> Panel principal</button>
        <button :class="{active:view==='chat'}" @click="setView('chat')"><span>✧</span> Asistente IA</button>
        <button :class="{active:view==='public'}" @click="setView('public')"><span>▤</span> Consultas públicas</button>
      </nav>
      <div class="sidebar-bottom"><div class="sidebar-orb">✦</div><strong>Conocimiento de Minecraft</strong><p>Explora, aprende y comparte conocimiento con la comunidad.</p></div>
    </aside>

    <main class="main-area">
      <header class="topbar">
        <div><span class="breadcrumb">GAMEGUIDE AI</span><span class="crumb-sep">/</span><strong>{{ view==='dashboard'?'Panel principal':view==='chat'?'Asistente IA':'Consultas públicas' }}</strong></div>
        <div class="top-status"><i :class="{online:health.status==='ok'}"></i>{{ health.status==='ok'?'API conectada':'API sin conexión' }}<button class="icon-button" @click="loadData" title="Actualizar">↻</button></div>
      </header>

      <section v-if="view==='dashboard'" class="content-view">
        <div class="welcome-banner">
          <div><div class="eyebrow">CENTRO DE ANALÍTICA</div><h1>Resumen de actividad</h1><p>Monitorea el uso, la calidad y el rendimiento de GameGuide AI.</p></div>
          <div class="welcome-icon">✦</div>
        </div>
        <div class="section-head"><div><h2>Indicadores clave de rendimiento</h2><p>Datos reales registrados en Supabase · últimos 30 días</p></div><span class="live-label"><i></i> DATOS EN VIVO</span></div>
        <div class="kpi-grid">
          <article class="kpi-card"><div class="kpi-top"><span class="kpi-icon blue">▤</span><span class="kpi-caption">VOLUMEN</span></div><label>Consultas registradas</label><strong>{{ dashboard.total ?? 0 }}</strong><small>Primeras consultas guardadas</small></article>
          <article class="kpi-card"><div class="kpi-top"><span class="kpi-icon green">✓</span><span class="kpi-caption">RESOLUCIÓN</span></div><label>Resolución validada</label><strong>{{ dashboard.resolution==null?'—':dashboard.resolution.toFixed(1)+'%' }}</strong><small>Likes respecto a consultas</small></article>
          <article class="kpi-card"><div class="kpi-top"><span class="kpi-icon violet">♡</span><span class="kpi-caption">SATISFACCIÓN</span></div><label>Votos positivos</label><strong>{{ dashboard.satisfaction==null?'—':dashboard.satisfaction.toFixed(1)+'%' }}</strong><small>Likes sobre votos emitidos</small></article>
          <article class="kpi-card"><div class="kpi-top"><span class="kpi-icon amber">◷</span><span class="kpi-caption">VELOCIDAD</span></div><label>Tiempo promedio</label><strong>{{ dashboard.avg_seconds==null?'—':dashboard.avg_seconds.toFixed(2)+' s' }}</strong><small>Tiempo de generación</small></article>
          <article class="kpi-card"><div class="kpi-top"><span class="kpi-icon teal">⌁</span><span class="kpi-caption">EVIDENCIA</span></div><label>Respuestas con fuentes</label><strong>{{ dashboard.evidence_pct==null?'—':dashboard.evidence_pct.toFixed(1)+'%' }}</strong><small>Respuestas con referencias</small></article>
          <article class="kpi-card"><div class="kpi-top"><span class="kpi-icon orange">↻</span><span class="kpi-caption">REUTILIZACIÓN</span></div><label>Conocimiento reutilizado</label><strong>{{ dashboard.reuse_pct==null?'—':dashboard.reuse_pct.toFixed(1)+'%' }}</strong><small>Documentos recuperados de caché</small></article>
        </div>
        <div class="charts-grid">
          <article class="chart-card wide"><div class="chart-heading"><div><h3>Tendencia de consultas</h3><p>Actividad diaria durante los últimos 30 días</p></div><span class="chart-tag">VOLUMEN</span></div><div class="chart-area"><svg v-if="dailyValues.length" class="line-chart" viewBox="0 0 720 220" role="img" aria-label="Consultas por día"><line v-for="y in [35,85,135,188]" :key="y" x1="28" :y1="y" x2="692" :y2="y" stroke="#edf1f5" stroke-width="1"/><polygon :points="trendArea" fill="rgba(18,168,138,.10)"/><polyline :points="trendPoints" fill="none" stroke="#12a88a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle v-for="(value,index) in dailyValues" :key="index" :cx="dailyValues.length===1?360:28+index*(664/(dailyValues.length-1))" :cy="188-(value/Math.max(1,...dailyValues))*155" r="3" fill="#12a88a"/></svg><div v-else class="chart-empty">Aún no hay suficientes consultas para mostrar la tendencia.</div></div></article>
          <article class="chart-card"><div class="chart-heading"><div><h3>Consultas por categoría</h3><p>Distribución del conocimiento solicitado</p></div></div><div class="chart-area category-chart"><template v-if="categories.length"><div v-for="[name,value] in categories" :key="name" class="category-bar"><span>{{ name }}</span><div><i :style="{width:(value/Math.max(1,...categories.map(x=>x[1]))*100)+'%'}"></i></div><b>{{ value }}</b></div></template><div v-else class="chart-empty">Sin datos por categoría.</div></div></article>
          <article class="chart-card"><div class="chart-heading"><div><h3>Retroalimentación</h3><p>Valoración de la comunidad</p></div></div><div class="chart-area doughnut-area"><div v-if="totalVotes" class="donut" :style="donutStyle"><div><strong>{{ totalVotes }}</strong><small>votos</small></div></div><div v-else class="chart-empty">Aún no hay votos.</div></div><div class="vote-summary"><span>👍 {{ dashboard.feedback?.likes || 0 }} likes</span><span>👎 {{ dashboard.feedback?.dislikes || 0 }} dislikes</span></div></article>
        </div>
        <div class="footnote">Las métricas se calculan con consultas principales guardadas y votos públicos. Los mensajes de seguimiento no se contabilizan como consultas nuevas.</div>
      </section>

      <section v-else-if="view==='chat'" class="content-view">
        <div class="welcome-banner compact"><div><div class="eyebrow">ASISTENTE CONVERSACIONAL</div><h1>¿Qué quieres descubrir?</h1><p>Consulta Minecraft Vanilla, mecánicas, criaturas, objetos o encuentra contenido en Modrinth.</p></div><div class="welcome-icon">✧</div></div>
        <div class="chat-layout">
          <section class="chat-card">
            <div class="chat-header"><div><span class="assistant-avatar">⛏</span><div><h2>GameGuide AI</h2><p><i></i> Asistente disponible</p></div></div><button class="outline-btn" @click="clearChat">＋ Nueva conversación</button></div>
            <div class="chat-settings"><label>Edición<select v-model="edition"><option>No especificada</option><option>Java Edition</option><option>Bedrock Edition</option></select></label><label>Versión de Minecraft<input v-model="gameVersion" placeholder="Ej. 1.21.11"/></label></div>
            <div class="messages" aria-live="polite">
              <div v-for="(message,index) in messages" :key="index" class="message" :class="message.role">
                <div class="message-avatar">{{ message.role==='assistant'?'⛏':'TÚ' }}</div>
                <div class="message-body"><div class="bubble">{{ message.content }}</div><div v-if="message.sources?.length" class="sources"><strong>Fuentes consultadas</strong><a v-for="(source,i) in message.sources" :key="i" :href="source.url" target="_blank" rel="noreferrer">[{{ i+1 }}] {{ source.title }} ↗</a></div><small v-if="message.meta" class="message-meta">{{ message.meta }}</small></div>
              </div>
              <div v-if="busy" class="typing"><span></span><span></span><span></span> Recuperando conocimiento y generando respuesta…</div>
            </div>
            <form class="composer" @submit.prevent="sendMessage"><textarea v-model="question" rows="2" placeholder="Escribe tu pregunta sobre Minecraft…" @keydown.enter.exact.prevent="sendMessage"></textarea><button :disabled="busy||!question.trim()">{{ busy?'Consultando…':'Enviar pregunta →' }}</button></form>
            <p v-if="error" class="error-message">{{ error }}</p>
            <p class="privacy-note">Solo la primera pregunta y su primera respuesta se guardan en la biblioteca pública. Los mensajes de seguimiento permanecen dentro de la sesión.</p>
          </section>
          <aside class="chat-aside"><article><span>📚</span><h3>Respuestas fundamentadas</h3><p>Consulta información recuperada de fuentes y documentos relevantes.</p></article><article><span>🧭</span><h3>Contexto de juego</h3><p>Indica tu edición y versión para mejorar la precisión de las respuestas.</p></article><article><span>🌐</span><h3>Comunidad</h3><p>Las consultas principales se comparten para que otros jugadores puedan valorarlas.</p></article></aside>
        </div>
      </section>

      <section v-else class="content-view">
        <div class="welcome-banner compact"><div><div class="eyebrow">CONOCIMIENTO COMPARTIDO</div><h1>Biblioteca de la comunidad</h1><p>Explora preguntas y respuestas compartidas por otros jugadores. Tu voto ayuda a mejorar la calidad.</p></div><div class="welcome-icon">▤</div></div>
        <div class="public-toolbar"><div><h2>Consultas publicadas</h2><p>Se almacena únicamente la primera pregunta y respuesta de cada sesión.</p></div><button class="outline-btn" @click="loadPublic">↻ Actualizar</button></div>
        <div v-if="publicLoading" class="loading-state">Cargando consultas…</div>
        <div v-else-if="publicError" class="error-message">{{ publicError }}</div>
        <div v-else-if="!publicItems.length" class="empty-state"><span>📖</span><h3>Aún no hay consultas públicas</h3><p>Realiza una consulta en el asistente para iniciar la biblioteca.</p><button @click="setView('chat')">Ir al asistente</button></div>
        <div v-else class="public-list">
          <article v-for="item in publicItems" :key="item.id" class="public-card">
            <div class="public-card-top"><span class="category-pill">{{ item.category || 'General' }}</span><time>{{ new Date(item.created_at).toLocaleDateString('es-MX',{day:'numeric',month:'short',year:'numeric'}) }}</time></div>
            <h3>{{ item.question }}</h3>
            <div class="answer-preview">{{ item.answer }}</div>
            <div v-if="item.sources?.length" class="public-sources"><a v-for="(source,i) in item.sources" :key="i" :href="source.url" target="_blank" rel="noreferrer">{{ source.title || `Fuente ${i+1}` }} ↗</a></div>
            <div class="vote-actions"><span>¿Te fue útil esta respuesta?</span><div><button @click="vote(item,'like')">👍 Me gusta <b>{{ item.likes || 0 }}</b></button><button @click="vote(item,'dislike')">👎 No me gusta <b>{{ item.dislikes || 0 }}</b></button></div></div>
          </article>
        </div>
      </section>
      <footer class="app-footer">GAMEGUIDE AI <span>·</span> MINECRAFT KNOWLEDGE PLATFORM</footer>
    </main>
  </div>
</template>
