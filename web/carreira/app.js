const API = '/api/career';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { session: null, data: null, sources: [], view: 'overview', loading: false, runTimer: null, codexTimer: null };
const titles = { overview: 'Visão geral', jobs: 'Radar de vagas', applications: 'Candidaturas', interviews: 'Entrevistas', profile: 'Perfil profissional', answers: 'Banco de respostas', connections: 'Conexões e busca' };
const statusLabels = {
  discovered: 'Encontrada', found: 'Encontrada', analyzing: 'Em análise', matched: 'Compatível', eligible: 'Elegível',
  prepared: 'Preparada', ready: 'Pronta para envio', pending: 'Pendente', pending_info: 'Informação pendente',
  pending_eligibility: 'Elegibilidade pendente', blocked: 'Com pendência', queued: 'Na fila', sending: 'Envio em andamento',
  sent: 'Enviada', submitted: 'Enviada', received: 'Recebimento confirmado', acknowledged: 'Recebimento confirmado',
  awaiting_response: 'Aguardando retorno', response_received: 'Resposta recebida', replied: 'Resposta recebida',
  test_pending: 'Teste pendente', assessment: 'Avaliação', interview: 'Entrevista', interview_scheduled: 'Entrevista agendada',
  offer: 'Proposta recebida', rejected: 'Encerrada pela empresa', closed: 'Encerrada', withdrawn: 'Retirada',
  failed: 'Falha no envio', send_uncertain: 'Envio em verificação', sent_record_pending: 'Enviada · registro pendente',
  draft: 'Em preparação', interview_pending: 'Entrevista a confirmar', existing_contact: 'Contato já registrado', interested: 'Interesse recebido',
};
const eventLabels = {
  job_discovered: 'Oportunidade encontrada', job_found: 'Oportunidade encontrada', job_added: 'Vaga adicionada ao radar',
  match_evaluated: 'Compatibilidade analisada', job_matched: 'Compatibilidade analisada', application_created: 'Candidatura registrada',
  application_prepared: 'Apresentação preparada', prepared: 'Apresentação preparada', application_sent: 'Candidatura enviada', sent: 'Candidatura enviada',
  email_sent: 'E-mail enviado', email_received: 'Retorno recebido', mail_received: 'Retorno recebido', reply_received: 'Resposta recebida',
  receipt_confirmed: 'Recebimento confirmado', interview_created: 'Entrevista registrada na agenda', interview_scheduled: 'Entrevista agendada',
  interview_detected: 'Convite para entrevista identificado', profile_updated: 'Perfil atualizado', profile_imported: 'Perfil importado do portfólio',
  source_added: 'Fonte de vagas conectada', run_started: 'Rodada do agente iniciada', run_completed: 'Rodada do agente concluída',
  run_failed: 'Rodada com pendência', application_blocked: 'Candidatura com pendência', send_failed: 'Falha no envio',
  send_uncertain: 'Envio aguardando verificação', follow_up_sent: 'Acompanhamento enviado', github_synced: 'Projetos do GitHub sincronizados',
};
const closedStatuses = new Set(['rejected', 'closed', 'withdrawn', 'cancelled', 'accepted']);
const pendingStatuses = new Set(['pending', 'pending_info', 'pending_eligibility', 'blocked', 'test_pending', 'failed', 'send_uncertain', 'interview_pending']);

function node(tag, attributes = {}, children = []) {
  const result = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === undefined || value === null) continue;
    if (key === 'class') result.className = value;
    else if (key === 'text') result.textContent = String(value);
    else result.setAttribute(key, String(value));
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child === null || child === undefined) continue;
    result.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return result;
}

function text(selector, value) { const target = $(selector); if (target) target.textContent = String(value ?? ''); }
function list(value) { return Array.isArray(value) ? value : []; }
function split(value) { return String(value ?? '').split(/[,;\n]/).map(item => item.trim()).filter(Boolean); }
function normal(value) { return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
function statusLabel(value) { return statusLabels[value] || String(value || 'Registrada').replaceAll('_', ' '); }
function safeUrl(value) {
  if (!value) return null;
  try { const url = new URL(String(value), location.origin); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
function externalLink(label, url, className = 'subtle-link') {
  const href = safeUrl(url);
  return href ? node('a', { href, class: className, target: '_blank', rel: 'noopener noreferrer' }, label) : null;
}
function button(label, action, className = 'button secondary') {
  const result = node('button', { type: 'button', class: className }, label);
  result.addEventListener('click', action);
  return result;
}
function badge(label, kind = 'neutral') { return node('span', { class: `badge ${kind}` }, label); }
function applicationBadge(status) {
  const kind = closedStatuses.has(status) ? 'closed' : pendingStatuses.has(status) ? 'warning' : ['sent', 'submitted', 'interview', 'interview_scheduled', 'offer', 'received', 'acknowledged'].includes(status) ? 'good' : 'neutral';
  return badge(statusLabel(status), kind);
}
function formatDate(value, options = {}) {
  if (!value) return 'Data não informada';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Data não informada';
  try { return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', ...options }).format(date); }
  catch { return date.toLocaleDateString('pt-BR'); }
}
function empty(title, description, action, compact = false, symbol = '✳') {
  const box = node('div', { class: `empty-state${compact ? ' compact' : ''}` }, [node('span', { 'aria-hidden': 'true' }, symbol), node('h3', {}, title), node('p', {}, description)]);
  if (action) box.append(button(action.label, action.run, 'button secondary'));
  return box;
}
function toast(message, error = false) {
  const target = $('#toast');
  target.textContent = message;
  target.classList.toggle('error', error);
  target.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { target.hidden = true; }, error ? 9000 : 5500);
}
function errorMessage(error) { return error?.message || 'Não foi possível concluir. Atualize as informações e tente novamente.'; }
function setGlobalError(message) { const box = $('#global-error'); box.textContent = message || ''; box.hidden = !message; }

async function api(path, { method = 'GET', body, timeout = 45000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    if (state.session?.csrf_token) headers['X-CSRF-Token'] = state.session.csrf_token;
  }
  try {
    const response = await fetch(`${API}${path}`, { method, credentials: 'same-origin', headers, signal: controller.signal, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    let data = null;
    if (response.status !== 204 && response.headers.get('content-type')?.includes('json')) data = await response.json();
    if (!response.ok) {
      if (response.status === 401) { state.session = { authenticated: false, google_configured: true }; showLogin('Sua sessão terminou. Entre novamente para acessar seus dados.'); }
      const detail = typeof data?.detail === 'string' ? data.detail : typeof data?.error === 'string' ? data.error : `A solicitação não foi concluída (${response.status}).`;
      const error = new Error(detail); error.status = response.status; throw error;
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('A resposta está demorando. Atualize o painel para conferir o resultado antes de repetir a ação.');
    throw error;
  } finally { clearTimeout(timer); }
}

function showLogin(message = '') {
  $('#boot').hidden = true;
  $('#workspace').hidden = true;
  $('#login').hidden = false;
  const configured = state.session?.google_configured !== false;
  const link = $('#google-login');
  link.setAttribute('aria-disabled', String(!configured));
  if (!configured) link.removeAttribute('href');
  else link.href = `${API}/auth/google/start?connect=0`;
  const notice = message || (!configured ? 'O login Google ainda precisa ser configurado no serviço do gestor. O acesso será liberado quando a conexão estiver pronta.' : '');
  text('#login-message', notice);
  $('#login-message').hidden = !notice;
  $('#retry-login').hidden = !message;
}

async function boot() {
  $('#boot').hidden = false;
  $('#login').hidden = true;
  try {
    state.session = await api('/session');
    if (!state.session?.authenticated) { showLogin(); return; }
    $('#boot').hidden = true;
    $('#login').hidden = true;
    $('#workspace').hidden = false;
    const user = state.session.user || {};
    text('#user-name', user.name || user.email?.split('@')[0] || 'Meu perfil');
    text('#user-email', user.email || '');
    text('#user-initials', (user.name || 'Karen Angelis').split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase());
    await refresh();
    const initialView = location.hash.replace('#', '');
    switchView(titles[initialView] ? initialView : 'overview', false);
  } catch {
    state.session = { authenticated: false, google_configured: false };
    showLogin('O serviço do gestor ainda não respondeu. Tente novamente quando o serviço estiver disponível.');
  }
}

async function refresh({ quiet = false } = {}) {
  if (state.loading) return;
  state.loading = true;
  $('#refresh').disabled = true;
  try {
    const data = await api('/dashboard');
    state.data = data || {};
    if (data?.csrf_token) state.session.csrf_token = data.csrf_token;
    try {
      const sources = await api('/sources');
      state.sources = Array.isArray(sources) ? sources : list(sources?.sources || sources?.items);
    } catch { state.sources = list(data?.sources); }
    renderAll();
    setGlobalError('');
    text('#updated-at', `Atualizado às ${new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(new Date())}`);
  } catch (error) {
    if (!quiet) setGlobalError(errorMessage(error));
    throw error;
  } finally { state.loading = false; $('#refresh').disabled = false; }
}

function switchView(view, moveFocus = true) {
  if (!titles[view]) return;
  state.view = view;
  $$('.view').forEach(section => { section.hidden = section.id !== `view-${view}`; });
  $$('.nav-item').forEach(item => {
    const selected = item.dataset.view === view;
    item.classList.toggle('active', selected);
    if (selected) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
  });
  text('#view-name', titles[view]);
  document.title = `${titles[view]} · Gestor de Carreira`;
  history.replaceState(null, '', `#${view}`);
  if (moveFocus) { $('#main').focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }); }
}

function googleCapabilities() {
  const google = state.data?.connections?.google || {};
  const scopes = Array.isArray(google.scopes) ? google.scopes.join(' ') : String(google.scopes || '');
  const gmail = google.gmail_connected === true || google.gmail === true || (google.connected === true && scopes.includes('gmail.readonly') && scopes.includes('gmail.send'));
  const calendar = google.calendar_connected === true || google.calendar === true || (google.connected === true && scopes.includes('calendar.events'));
  return { google, gmail, calendar };
}
function connectionDefinitions() {
  const { google, gmail, calendar } = googleCapabilities();
  const codex = state.data?.connections?.codex || {};
  return [
    { id: 'gmail', icon: 'M', title: 'Gmail', connected: gmail, description: gmail ? (google.email || 'Envios e respostas conectados') : 'Envios e respostas aguardam conexão', copy: 'Envie candidaturas pelo seu e-mail e acompanhe as respostas dos processos.', button: gmail ? 'Sincronizar respostas' : 'Conectar Gmail e Agenda', action: gmail ? syncMail : connectGoogle },
    { id: 'calendar', icon: '▦', title: 'Google Agenda', connected: calendar, description: calendar ? 'Agenda autorizada' : 'Permissão de agenda pendente', copy: 'Guarde as entrevistas com data, horário e contexto na sua agenda pessoal.', button: calendar ? 'Ver minhas entrevistas' : 'Conectar Gmail e Agenda', action: calendar ? () => switchView('interviews') : connectGoogle },
    { id: 'codex', icon: '✳', title: 'Codex', connected: codex.connected === true, description: codex.connected ? (codex.account?.email || codex.email || 'Conta conectada') : codex.pairing_required ? 'Configuração inicial pendente' : codex.available === false ? 'Serviço aguardando configuração' : 'Sua conta ainda não está conectada', copy: codex.reason || 'Use seu perfil e suas evidências para analisar vagas e preparar respostas contextualizadas.', button: codex.connected ? 'Verificar conexão' : codex.pairing_required ? 'Configurar conexão' : 'Conectar minha conta', action: codex.connected ? checkCodex : loginCodex },
  ];
}

function renderConnections() {
  const definitions = connectionDefinitions();
  const overview = $('#overview-connections'); overview.replaceChildren();
  const cards = $('#connection-cards'); cards.replaceChildren();
  for (const definition of definitions) {
    overview.append(node('div', { class: 'connection-row' }, [node('span', { class: 'connection-icon', 'aria-hidden': 'true' }, definition.icon), node('div', {}, [node('strong', {}, definition.title), node('p', {}, definition.description)]), badge(definition.connected ? 'Conectado' : 'Pendente', definition.connected ? 'good' : 'warning')]));
    const card = node('article', { class: 'connection-card' }, [node('span', { class: 'connection-icon', 'aria-hidden': 'true' }, definition.icon), node('h3', {}, definition.title), node('p', {}, definition.copy), badge(definition.connected ? 'Conexão ativa' : definition.description, definition.connected ? 'good' : 'warning')]);
    card.append(button(definition.button, () => withButton(card.querySelector('button'), definition.action), 'button secondary'));
    cards.append(card);
  }
  const ready = definitions.every(item => item.connected);
  const hasProfile = Boolean(state.data?.profile?.resume_text || list(state.data?.profile?.skills).length);
  $('#setup-banner').hidden = ready && hasProfile;
  const missing = [!hasProfile && 'perfil profissional', ...definitions.filter(item => !item.connected).map(item => item.title)].filter(Boolean);
  text('#setup-description', missing.length ? `Falta completar: ${missing.join(', ')}.` : 'Suas conexões estão prontas. Revise as preferências para orientar a busca.');
  const worker = state.data?.worker || {};
  const indicator = $('#agent-indicator');
  indicator.classList.toggle('ready', Boolean(worker.enabled));
  indicator.replaceChildren(node('span', { class: 'status-dot' }), document.createTextNode(worker.running ? 'Rodada em andamento' : worker.enabled ? 'Agente habilitado' : 'Agente aguardando configuração'));
  text('#last-run', worker.last_run ? `Última rodada: ${formatDate(typeof worker.last_run === 'string' ? worker.last_run : worker.last_run.finished_at || worker.last_run.started_at)}` : 'Nenhuma rodada registrada');
  const calendarNote = $('#calendar-note');
  calendarNote.hidden = googleCapabilities().calendar;
  calendarNote.textContent = 'Conecte o Google Agenda em Conexões e busca para registrar entrevistas na sua agenda.';
}

function renderAll() {
  const data = state.data || {};
  const jobs = list(data.jobs), applications = list(data.applications), answers = list(data.answers);
  text('#stat-jobs', jobs.length); text('#stat-applications', applications.length); text('#stat-answers', answers.length);
  text('#stat-interviews', interviewItems().filter(item => new Date(item.start?.dateTime || item.start).getTime() >= Date.now()).length); text('#nav-jobs', jobs.length); text('#nav-applications', applications.length);
  renderConnections(); renderNextActions(); renderEvents(); renderJobs(); renderApplications(); renderAnswers(); renderInterviews(); renderSources();
  if (document.activeElement?.closest('#profile-form') === null) populateProfile();
}

function applicationJob(application) { return list(state.data?.jobs).find(job => job.id === application.job_id) || application.job_snapshot || {}; }
function applicationTitle(application) { return application.title || application.job_title || applicationJob(application).title || 'Candidatura'; }
function applicationCompany(application) { return application.company || applicationJob(application).company || 'Empresa'; }

function renderNextActions() {
  const target = $('#next-actions'); target.replaceChildren();
  const actions = list(state.data?.applications).filter(item => item.next_action || pendingStatuses.has(item.status)).slice(0, 4);
  if (!actions.length) {
    target.append(empty('Seu próximo passo aparece aqui', 'Conecte as fontes e comece a busca. Cada processo terá seu acompanhamento.', { label: 'Explorar meu radar →', run: () => switchView('jobs') }, true, '↗'));
    return;
  }
  for (const application of actions) {
    target.append(node('div', { class: 'action-row' }, [node('span', { class: 'action-marker', 'aria-hidden': 'true' }, '→'), node('div', {}, [node('strong', {}, `${applicationCompany(application)} · ${applicationTitle(application)}`), node('p', {}, application.next_action || statusLabel(application.status))]), button('↗', () => showApplication(application.id), 'subtle-link')]));
  }
}

function eventDetail(event) {
  const detail = event.detail;
  if (typeof detail === 'string') return detail;
  if (!detail || typeof detail !== 'object') return '';
  const parts = [detail.company, detail.title, detail.message || detail.summary || detail.next_action || detail.reason];
  return parts.filter(item => typeof item === 'string' && item.trim()).join(' · ') || (detail.status ? statusLabel(detail.status) : '');
}
function timeline(events, compact = false) {
  const target = node('ol', { class: 'timeline' });
  for (const event of events) {
    const date = event.created_at || event.at;
    const time = node('time', { datetime: date || '' }, formatDate(date));
    const title = eventLabels[event.kind] || String(event.kind || 'Movimento registrado').replaceAll('_', ' ');
    const item = node('li', {}, [node('div', { class: 'timeline-top' }, [node('strong', {}, title), time])]);
    const detail = eventDetail(event);
    if (detail) item.append(node('p', {}, detail));
    target.append(item);
  }
  if (!events.length) return empty('Nenhum movimento registrado', compact ? 'O histórico começa quando o gestor registra uma ação.' : 'As próximas ações confirmadas deste processo aparecerão aqui.', null, true, '↗');
  return target;
}
function renderEvents() {
  const events = list(state.data?.events).slice().sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).slice(0, 6);
  $('#recent-events').replaceChildren(timeline(events, true));
}

function renderJobs() {
  const query = normal($('#job-search').value), filter = $('#job-filter').value;
  const jobs = list(state.data?.jobs).filter(job => {
    const match = job.match || {};
    return (!query || normal(`${job.company} ${job.title} ${job.description} ${job.location}`).includes(query)) && (filter === 'all' || (filter === 'eligible' ? match.eligible === true : match.eligible !== true));
  }).sort((a, b) => Number(b.match?.score || 0) - Number(a.match?.score || 0));
  text('#job-count', `${jobs.length} ${jobs.length === 1 ? 'oportunidade' : 'oportunidades'}`);
  const target = $('#jobs-list'); target.replaceChildren();
  if (!jobs.length) {
    target.append(empty(query || filter !== 'all' ? 'Nenhuma vaga com este filtro' : 'Novas possibilidades começam aqui', query || filter !== 'all' ? 'Altere a busca para explorar outras oportunidades.' : 'Conecte os quadros de vagas das empresas ou adicione uma oportunidade que você encontrou.', { label: 'Conectar uma fonte →', run: () => switchView('connections') }, false, '⌕'));
    return;
  }
  for (const job of jobs) {
    const match = job.match || {};
    const hasScore = Number.isFinite(Number(match.score)) && match.score !== null && match.score !== undefined;
    const card = node('article', { class: 'job-card' });
    card.append(node('div', { class: 'job-top' }, [node('span', { class: 'company-label' }, job.company || 'Empresa'), node('span', { class: 'match-score', title: 'Índice de aderência aos requisitos. Não é chance de contratação.' }, [node('strong', {}, hasScore ? Math.round(Number(match.score)) : '—'), hasScore ? '/ 100' : 'A analisar'])]));
    card.append(node('h3', {}, job.title || 'Oportunidade'), node('p', { class: 'job-location' }, job.location || 'Localização a esclarecer'));
    card.append(badge(match.eligible ? 'Elegível para candidatura' : hasScore ? 'Condições a esclarecer' : 'Aguardando análise', match.eligible ? 'good' : 'warning'));
    const tags = node('div', { class: 'tag-list' });
    list(match.matched_skills).slice(0, 6).forEach(skill => tags.append(node('span', { class: 'skill-tag' }, skill)));
    list(match.missing_skills).slice(0, 3).forEach(skill => tags.append(node('span', { class: 'skill-tag missing', title: 'Requisito sem evidência no perfil' }, skill)));
    if (tags.childNodes.length) card.append(tags);
    const blockers = list(match.blockers).filter(item => typeof item === 'string');
    card.append(node('p', { class: 'job-note' }, blockers.length ? blockers.join(' · ') : hasScore ? 'Confira o anúncio e os materiais selecionados para esta oportunidade.' : 'O agente precisa analisar os requisitos e as condições desta vaga.'));
    const existing = list(state.data?.applications).find(application => application.job_id === job.id);
    const action = existing ? button('Ver candidatura →', () => showApplication(existing.id), 'button secondary') : button('Preparar candidatura →', event => prepareJob(job.id, event), 'button secondary');
    card.append(node('div', { class: 'job-card-footer' }, [externalLink('Anúncio original ↗', job.url || job.apply_url), action]));
    target.append(card);
  }
}

async function prepareJob(jobId, event) {
  const control = event?.currentTarget;
  await withButton(control, async () => {
    let application = await api('/applications', { method: 'POST', body: { job_id: jobId } });
    application = application?.application || application;
    try {
      if (application?.id) await api(`/applications/${encodeURIComponent(application.id)}/prepare`, { method: 'POST' });
    } catch (error) {
      await refresh();
      if (application?.id) showApplication(application.id);
      throw error;
    }
    await refresh();
    toast('Candidatura registrada. Confira os materiais e eventuais pendências.');
    if (application?.id) showApplication(application.id);
  });
}

function renderApplications() {
  const query = normal($('#application-search').value), filter = $('#application-filter').value;
  const applications = list(state.data?.applications).filter(application => {
    const matchesQuery = !query || normal(`${applicationCompany(application)} ${applicationTitle(application)} ${application.next_action || ''}`).includes(query);
    return matchesQuery && (filter === 'all' || (filter === 'closed' ? closedStatuses.has(application.status) : filter === 'pending' ? pendingStatuses.has(application.status) : !closedStatuses.has(application.status)));
  }).sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')));
  text('#application-count', `${applications.length} ${applications.length === 1 ? 'candidatura' : 'candidaturas'}`);
  const target = $('#applications-list'); target.replaceChildren();
  if (!applications.length) {
    target.append(empty(query || filter !== 'all' ? 'Nenhuma candidatura com este filtro' : 'Cada oportunidade terá uma história', query || filter !== 'all' ? 'Tente outro filtro para encontrar o processo.' : 'Ao preparar uma candidatura, os materiais, envios e próximos passos ficam reunidos aqui.', { label: 'Explorar vagas →', run: () => switchView('jobs') }, false, '▤'));
    return;
  }
  for (const application of applications) {
    const row = button('', () => showApplication(application.id), 'application-row');
    row.append(node('div', {}, [node('span', { class: 'company-label' }, applicationCompany(application)), node('h3', {}, applicationTitle(application)), node('p', {}, application.next_action || `Registrada em ${formatDate(application.created_at)}`)]), applicationBadge(application.status), node('span', { class: 'row-arrow', 'aria-hidden': 'true' }, '↗'));
    target.append(row);
  }
}

function showApplication(id) {
  const application = list(state.data?.applications).find(item => item.id === id);
  if (!application) { toast('A candidatura não está no painel atual. Atualize as informações.', true); return; }
  const job = applicationJob(application);
  text('#application-dialog-company', applicationCompany(application));
  text('#application-dialog-title', applicationTitle(application));
  const detail = $('#application-detail'); detail.replaceChildren();
  detail.append(node('div', { class: 'detail-meta' }, [applicationBadge(application.status), node('span', {}, `Registro: ${formatDate(application.created_at)}`), externalLink('Vaga original ↗', job.url)]));
  if (application.next_action) detail.append(node('div', { class: 'notice' }, application.next_action));
  const subject = application.email_subject || application.subject;
  const body = application.email_body || application.cover_letter || application.message;
  const material = node('section', { class: 'detail-section' }, node('h3', {}, application.status === 'sent' || application.message_id ? 'Material registrado no envio' : 'Apresentação preparada'));
  if (subject || body) material.append(node('div', { class: 'message-preview' }, [subject ? node('strong', {}, subject) : null, body || 'Texto ainda não registrado.']));
  else material.append(node('p', {}, 'A apresentação ainda não foi preparada para esta oportunidade.'));
  if (application.contact_email) material.append(node('p', {}, `Canal: ${application.contact_email}`));
  if (application.message_id || application.gmail_message_id) material.append(node('p', {}, `Comprovante do e-mail: ${application.message_id || application.gmail_message_id}`));
  if (['created', 'pending', 'prepared', 'pending_info', 'blocked'].includes(application.status) || !body) material.append(button('Atualizar preparação →', event => withButton(event.currentTarget, async () => { await api(`/applications/${encodeURIComponent(id)}/prepare`, { method: 'POST' }); await refresh(); showApplication(id); toast('Preparação atualizada.'); }), 'button secondary'));
  detail.append(material);
  const events = list(state.data?.events).filter(event => event.application_id === id).sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
  detail.append(node('section', { class: 'detail-section' }, [node('h3', {}, 'Linha do tempo'), timeline(events)]));
  openDialog('application-dialog');
}

function populateProfile() {
  const profile = state.data?.profile || {}, facts = profile.facts || {}, preferences = profile.preferences || {};
  const form = $('#profile-form');
  const values = { name: facts.name || profile.name || '', email: facts.email || '', location: facts.location || '', residence_country: facts.residence_country || '', languages: Array.isArray(facts.languages) ? facts.languages.join(', ') : facts.languages || '', resume_text: profile.resume_text || '', skills: list(profile.skills).join(', '), roles: list(preferences.roles).join(', '), countries: list(preferences.countries).join(', '), compensation: facts.compensation || '', availability: facts.availability || '', min_score: preferences.min_score ?? 80 };
  for (const [name, value] of Object.entries(values)) form.elements.namedItem(name).value = value;
  form.elements.remote_only.checked = preferences.remote_only !== false;
  form.elements.auto_apply.checked = preferences.auto_apply === true;
  text('#profile-revision', profile.revision ? `Versão ${profile.revision}` : 'Seu perfil inicial');
  if (document.activeElement?.id !== 'github-username') $('#github-username').value = facts.github_username || profile.github_username || 'KarenAngelis';
}

async function saveProfile(event) {
  event.preventDefault();
  const form = event.currentTarget, fields = new FormData(form), profile = state.data?.profile || {};
  const facts = { ...(profile.facts || {}), name: String(fields.get('name') || '').trim(), email: String(fields.get('email') || '').trim(), location: String(fields.get('location') || '').trim(), residence_country: String(fields.get('residence_country') || '').trim(), languages: String(fields.get('languages') || '').trim(), compensation: String(fields.get('compensation') || '').trim(), availability: String(fields.get('availability') || '').trim() };
  const body = { facts, resume_text: String(fields.get('resume_text') || ''), skills: split(fields.get('skills')), preferences: { roles: split(fields.get('roles')), countries: split(fields.get('countries')), remote_only: fields.has('remote_only'), min_score: Number(fields.get('min_score') || 0), auto_apply: fields.has('auto_apply') } };
  await withButton(form.querySelector('[type=submit]'), async () => {
    await api('/profile', { method: 'PUT', body });
    text('#profile-save-status', 'Perfil salvo. As próximas candidaturas usarão esta versão.');
    await refresh(); toast('Seu perfil foi salvo.');
  });
}

function renderAnswers() {
  const query = normal($('#answer-search').value);
  const answers = list(state.data?.answers).filter(answer => !query || normal(`${answer.intent} ${answer.text} ${answer.source}`).includes(query));
  const target = $('#answers-list'); target.replaceChildren();
  text('#answer-count', `${answers.length} ${answers.length === 1 ? 'resposta' : 'respostas'}`);
  if (!answers.length) { target.append(empty(query ? 'Nenhuma resposta com este termo' : 'Suas respostas ganham memória', query ? 'Busque por outro assunto ou palavra.' : 'Guarde respostas confirmadas sobre experiências, disponibilidade e condições de trabalho.', { label: 'Guardar minha primeira resposta →', run: () => openDialog('answer-dialog') }, false, '≋')); return; }
  for (const answer of answers) {
    const card = node('article', { class: 'answer-card' }, [node('p', { class: 'eyebrow' }, 'RESPOSTA CONFIRMADA'), node('h3', {}, answer.intent || 'Resposta'), node('p', { class: 'answer-text' }, answer.text || '')]);
    const footer = node('div', { class: 'answer-footer' }, [node('div', {}, [node('p', {}, `Fonte: ${answer.source || 'Não registrada'}`), node('time', { datetime: answer.updated_at || answer.created_at || '' }, formatDate(answer.updated_at || answer.created_at))]), button('Excluir', event => deleteAnswer(answer, event.currentTarget), 'text-button')]);
    card.append(footer); target.append(card);
  }
}

async function deleteAnswer(answer, control) {
  if (!window.confirm(`Excluir a resposta sobre “${answer.intent || 'este assunto'}”? O histórico das candidaturas anteriores será preservado.`)) return;
  await withButton(control, async () => { await api(`/answers/${encodeURIComponent(answer.id)}`, { method: 'DELETE' }); await refresh(); toast('Resposta excluída do banco.'); });
}

function renderSources() {
  const target = $('#sources-list'); target.replaceChildren();
  if (!state.sources.length) { target.append(empty('Escolha suas primeiras empresas', 'Adicione um quadro de vagas Greenhouse ou Lever para iniciar o radar com fontes diretas.', { label: 'Adicionar fonte →', run: () => openDialog('source-dialog') }, true, '⌕')); return; }
  for (const source of state.sources) {
    target.append(node('div', { class: 'source-row' }, [node('span', { 'aria-hidden': 'true' }, source.kind === 'lever' ? 'L' : 'G'), node('div', {}, [node('strong', {}, source.identifier || source.name || 'Fonte'), node('p', {}, `${source.kind === 'lever' ? 'Lever' : 'Greenhouse'}${source.last_sync ? ` · ${formatDate(source.last_sync)}` : ' · Aguardando primeira consulta'}`)]), badge(source.error ? 'Com pendência' : source.enabled === false ? 'Desabilitada' : 'Cadastrada', source.error ? 'warning' : 'neutral')]));
  }
}

function interviewItems() {
  const data = state.data || {};
  if (Array.isArray(data.interviews)) return data.interviews;
  return list(data.events).filter(event => ['interview_created', 'interview_scheduled'].includes(event.kind) && event.detail?.start).map(event => ({ ...event.detail, application_id: event.application_id, id: event.id }));
}
function renderInterviews() {
  const target = $('#interviews-list'); target.replaceChildren();
  const items = interviewItems().slice().sort((a, b) => String(a.start?.dateTime || a.start || '').localeCompare(String(b.start?.dateTime || b.start || '')));
  if (!items.length) { target.append(empty('Espaço reservado para novas conversas', 'Entrevistas com horário confirmado aparecerão aqui, ligadas à candidatura e à sua agenda.', { label: 'Ver candidaturas →', run: () => switchView('applications') }, false, '▦')); return; }
  for (const item of items) {
    const start = item.start?.dateTime || item.start, end = item.end?.dateTime || item.end, timeZone = item.time_zone || item.timeZone || item.start?.timeZone || 'America/Sao_Paulo';
    const date = new Date(start);
    const valid = !Number.isNaN(date.getTime());
    const application = list(state.data?.applications).find(application => application.id === item.application_id);
    const card = node('article', { class: 'interview-card' });
    let day = '—', month = '';
    if (valid) { try { day = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', timeZone }).format(date); month = new Intl.DateTimeFormat('pt-BR', { month: 'short', timeZone }).format(date).replace('.', ''); } catch { day = '—'; } }
    card.append(node('div', { class: 'date-block', 'aria-hidden': 'true' }, [node('strong', {}, day), node('span', {}, month)]));
    card.append(node('div', { class: 'interview-info' }, [node('h3', {}, item.title || item.summary || (application ? `Entrevista · ${applicationCompany(application)}` : 'Entrevista')), node('p', {}, `${formatDate(start, { timeZone })}${end ? ` até ${formatDate(end, { hour: '2-digit', minute: '2-digit', day: undefined, month: undefined, timeZone })}` : ''}`), node('p', {}, `Fuso: ${timeZone}`)]));
    const links = node('div', { class: 'interview-links' });
    const meeting = externalLink('Entrar na reunião ↗', item.meeting_url || item.hangoutLink); if (meeting) links.append(meeting);
    const calendar = externalLink('Ver na agenda ↗', item.htmlLink || item.calendar_url); if (calendar) links.append(calendar);
    if (application) links.append(button('Ver candidatura →', () => showApplication(application.id), 'subtle-link'));
    card.append(links); target.append(card);
  }
}

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (!dialog) return;
  const error = $('.form-error', dialog); if (error) { error.hidden = true; error.textContent = ''; }
  if (id === 'interview-dialog') {
    const select = $('#interview-application'); select.replaceChildren(node('option', { value: '' }, 'Selecione a candidatura'));
    list(state.data?.applications).forEach(application => select.append(node('option', { value: application.id }, `${applicationCompany(application)} · ${applicationTitle(application)}`)));
  }
  if (!dialog.open) dialog.showModal();
}

async function withButton(control, action) {
  if (control?.disabled) return;
  const label = control?.textContent;
  if (control) { control.disabled = true; control.textContent = 'Aguarde…'; }
  try { return await action(); }
  catch (error) { toast(errorMessage(error), true); }
  finally { if (control?.isConnected) { control.disabled = false; control.textContent = label; } }
}

function connectGoogle() {
  if (state.session?.google_configured === false || state.data?.connections?.google?.configured === false) { toast('A conexão Google precisa ser configurada no serviço do gestor antes de autorizar a conta.', true); return; }
  location.assign(`${API}/auth/google/start?connect=1`);
}

async function loginCodex() {
  const codex = state.data?.connections?.codex || {};
  if (codex.pairing_required) {
    text('#codex-setup-reason', codex.reason || 'O serviço do gestor precisa de uma configuração inicial para usar sua conta Codex neste servidor.');
    const documentation = safeUrl(codex.documentation_url);
    if (documentation && ['developers.openai.com', 'learn.chatgpt.com'].includes(new URL(documentation).hostname)) $('#codex-setup-documentation').href = documentation;
    openDialog('codex-setup-dialog');
    return;
  }
  const result = await api('/codex/login', { method: 'POST' });
  const url = safeUrl(result?.verification_url || result?.verificationUrl);
  if (!url || !['auth.openai.com', 'chatgpt.com', 'openai.com'].includes(new URL(url).hostname) || !(result.user_code || result.userCode)) throw new Error('O serviço não retornou uma página oficial de autenticação válida.');
  text('#codex-code', result.user_code || result.userCode);
  $('#codex-verification').href = url;
  text('#codex-login-status', 'Conclua a autenticação na página oficial e depois verifique a conexão.');
  openDialog('codex-dialog');
  clearTimeout(state.codexTimer);
  let attempts = 0;
  const check = async () => {
    if (!$('#codex-dialog').open || attempts++ >= 24) return;
    try {
      await refresh({ quiet: true });
      if (state.data?.connections?.codex?.connected) { text('#codex-login-status', 'Sua conta está conectada. Você já pode fechar esta janela.'); toast('Codex conectado ao seu gestor.'); return; }
    } catch { /* The dialog retains a manual check action. */ }
    state.codexTimer = setTimeout(check, 5000);
  };
  state.codexTimer = setTimeout(check, 5000);
}

async function checkCodex() {
  await refresh();
  const connected = state.data?.connections?.codex?.connected === true;
  text('#codex-login-status', connected ? 'Sua conta está conectada. Você já pode fechar esta janela.' : 'A conexão ainda não foi confirmada. Conclua o login oficial e verifique novamente.');
  text('#codex-setup-reason', connected ? 'Sua conta está conectada ao serviço do gestor. Você já pode fechar esta janela.' : state.data?.connections?.codex?.reason || 'A configuração inicial ainda não foi confirmada.');
  toast(connected ? 'Conexão com Codex confirmada.' : 'A conexão ainda está pendente.', !connected);
}

async function syncMail() {
  const result = await api('/sync-mail', { method: 'POST' });
  await refresh();
  toast(typeof result?.message === 'string' ? result.message : 'Sincronização de mensagens concluída. Confira os movimentos nas candidaturas.');
}

async function runAgent() {
  const control = $('#run-agent');
  await withButton(control, async () => {
    const previous = JSON.stringify(state.data?.worker?.last_run || null);
    const result = await api('/run', { method: 'POST' });
    toast(result?.status === 'completed' ? 'Rodada concluída. As informações do painel foram atualizadas.' : 'Rodada solicitada. Acompanhe os movimentos no painel.');
    await refresh();
    clearTimeout(state.runTimer);
    let attempts = 0;
    const poll = async () => {
      if (attempts++ >= 12 || !state.session?.authenticated) return;
      try {
        await refresh({ quiet: true });
        if (JSON.stringify(state.data?.worker?.last_run || null) !== previous && state.data?.worker?.running !== true) return;
      } catch { return; }
      state.runTimer = setTimeout(poll, 5000);
    };
    if (result?.status !== 'completed') state.runTimer = setTimeout(poll, 5000);
  });
}

async function submitDialog(event, path, transform = value => value) {
  event.preventDefault();
  const form = event.currentTarget, submit = form.querySelector('[type=submit]'), error = $('.form-error', form);
  const label = submit.textContent;
  submit.disabled = true; submit.textContent = 'Aguarde…'; error.hidden = true;
  try {
    const body = transform(Object.fromEntries(new FormData(form).entries()));
    await api(path, { method: 'POST', body });
    form.closest('dialog').close(); form.reset();
    if (form.id === 'interview-form') form.elements.time_zone.value = 'America/Sao_Paulo';
    await refresh();
    toast(form.id === 'interview-form' ? 'Entrevista registrada na sua agenda.' : 'Registro salvo no seu gestor.');
  } catch (failure) { error.textContent = errorMessage(failure); error.hidden = false; error.focus?.(); }
  finally { submit.disabled = false; submit.textContent = label; }
}

$$('[data-view]').forEach(control => control.addEventListener('click', () => switchView(control.dataset.view)));
$$('[data-go]').forEach(control => control.addEventListener('click', () => switchView(control.dataset.go)));
$$('[data-open]').forEach(control => control.addEventListener('click', () => openDialog(control.dataset.open)));
$$('[data-close]').forEach(control => control.addEventListener('click', () => control.closest('dialog').close()));
$$('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
$('#job-search').addEventListener('input', renderJobs); $('#job-filter').addEventListener('change', renderJobs);
$('#application-search').addEventListener('input', renderApplications); $('#application-filter').addEventListener('change', renderApplications);
$('#answer-search').addEventListener('input', renderAnswers);
$('#refresh').addEventListener('click', () => refresh().catch(() => {}));
$('#retry-login').addEventListener('click', boot);
$('#google-login').addEventListener('click', event => { if (event.currentTarget.getAttribute('aria-disabled') === 'true') event.preventDefault(); });
$('#logout').addEventListener('click', event => withButton(event.currentTarget, async () => { await api('/logout', { method: 'POST' }); clearTimeout(state.runTimer); clearTimeout(state.codexTimer); state.data = null; state.session = { authenticated: false, google_configured: true }; $$('dialog[open]').forEach(dialog => dialog.close()); showLogin(); }));
$('#run-agent').addEventListener('click', runAgent);
$('#profile-form').addEventListener('submit', saveProfile);
$('#import-profile').addEventListener('click', event => withButton(event.currentTarget, async () => { await api('/profile/import-site', { method: 'POST' }); await refresh(); populateProfile(); toast('Informações públicas do portfólio importadas para seu perfil.'); }));
$('#job-form').addEventListener('submit', event => submitDialog(event, '/jobs', data => ({ ...data, apply_email: data.apply_email || null })));
$('#answer-form').addEventListener('submit', event => submitDialog(event, '/answers'));
$('#source-form').addEventListener('submit', event => submitDialog(event, '/sources'));
$('#github-form').addEventListener('submit', event => {
  event.preventDefault();
  const form = event.currentTarget;
  withButton(form.querySelector('[type=submit]'), async () => { await api('/profile/sync-github', { method: 'POST', body: { username: String(new FormData(form).get('username') || '').trim() } }); await refresh(); toast('Projetos públicos do GitHub sincronizados.'); });
});
$('#interview-form').addEventListener('submit', event => submitDialog(event, '/interviews', data => {
  if (!data.application_id) throw new Error('Selecione a candidatura desta entrevista.');
  if (data.end <= data.start) throw new Error('O fim da entrevista deve ser posterior ao início.');
  try { new Intl.DateTimeFormat('pt-BR', { timeZone: data.time_zone }); } catch { throw new Error('Informe um fuso válido, como America/Sao_Paulo.'); }
  return { ...data, start: `${data.start}:00`, end: `${data.end}:00`, meeting_url: data.meeting_url || '' };
}));
$('#copy-code').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#codex-code').textContent); toast('Código copiado.'); } catch { toast('Selecione o código e copie para usar na autenticação oficial.'); } });
$('#check-codex').addEventListener('click', event => withButton(event.currentTarget, checkCodex));
$('#check-codex-setup').addEventListener('click', event => withButton(event.currentTarget, checkCodex));
window.addEventListener('pagehide', () => { clearTimeout(state.runTimer); clearTimeout(state.codexTimer); });

boot();
