/**
 * 제22대 국회 과학기술정보방송통신위원회 회의록 대시보드
 * app.js - 메인 애플리케이션 로직 (개선 v3)
 */

'use strict';

// ============================================================
// 전역 상태
// ============================================================
const STATE = {
  db: null,               // meetings.json 원본 데이터
  filtered: [],           // 필터링 및 정렬이 적용된 회의록 목록
  displayed: 0,           // 현재 렌더링된 카드 개수
  PAGE_SIZE: 24,          // 더보기 시 추가할 카드 개수
  currentTab: 'summary',
  viewMode: 'grid',       // 'grid' 또는 'list'
  sortMode: 'date-desc',  // 정렬 종류
  startDate: '',          // 날짜 필터 시작일
  endDate: '',            // 날짜 필터 종료일
  compareMode: false,     // 키워드 비교 모드 활성화 여부
  compareKeywords: [],    // 비교용 선택 키워드 (최대 2개)
  calendarInstance: null,
  speakerChartInstance: null,
  speakersBarChartInstance: null,
  trendChartInstance: null,
  selectedKeyword: null,
  selectedSpeakerMeetingId: null,
  isDark: true,
  selectedSpeakers: [],   // 모달 내 다중 선택된 발언자 목록
  lastOpenMeeting: null,  // 최근 열어본 회의록 (모달 복원용)
};

// 회의 유형별 HSL 컬러 매핑 (차트/배지 연동)
const TYPE_COLORS = {
  '전체회의':       '#6366f1',
  '국정감사':       '#f59e0b',
  '정보통신방송소위': '#10b981',
  '과학기술원자력소위': '#06b6d4',
  '예산결산소위':    '#ec4899',
  '안건조정위원회':  '#8b5cf6',
  '청원심사소위':   '#eab308',
  '기타':           '#64748b',
};

const TREND_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4'];

// ============================================================
// 애플리케이션 초기화
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initTabNav();
  initMobileTabNav();
  loadData();

  // URL Hash 변경 감지 핸들러 등록
  window.addEventListener('hashchange', handleRouting);
});

function initTheme() {
  const btn = document.getElementById('theme-toggle');
  const sun = document.getElementById('icon-sun');
  const moon = document.getElementById('icon-moon');
  const saved = localStorage.getItem('theme');
  
  if (saved === 'light') {
    document.body.classList.add('light-mode');
    STATE.isDark = false;
    sun.style.display = 'none';
    moon.style.display = '';
  }
  
  btn.addEventListener('click', () => {
    STATE.isDark = !STATE.isDark;
    document.body.classList.toggle('light-mode', !STATE.isDark);
    sun.style.display = STATE.isDark ? '' : 'none';
    moon.style.display = STATE.isDark ? 'none' : '';
    localStorage.setItem('theme', STATE.isDark ? 'dark' : 'light');
    
    // 차트 색상 보정을 위해 재렌더링
    if (STATE.trendChartInstance) renderTrendChart();
    if (STATE.speakersBarChartInstance) renderSpeakersOverview();
  });
}

function initTabNav() {
  document.querySelectorAll('.tab-nav .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
      updateHash();
    });
  });
}

function initMobileTabNav() {
  document.querySelectorAll('.mobile-tab-bar .mobile-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
      updateHash();
    });
  });
}

function switchTab(tab) {
  STATE.currentTab = tab;
  
  // PC 탭 네비게이션 동기화
  document.querySelectorAll('.tab-nav .tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  
  // 모바일 탭바 동기화
  document.querySelectorAll('.mobile-tab-bar .mobile-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });

  // 콘텐츠 섹션 활성화
  document.querySelectorAll('.tab-content').forEach(s => {
    s.classList.toggle('active', s.id === `tab-content-${tab}`);
    s.classList.toggle('hidden', s.id !== `tab-content-${tab}`);
  });

  // 탭 전환 시 차트 및 캘린더 지연 로드
  if (tab === 'calendar') {
    setTimeout(() => renderCalendar(), 50);
  } else if (tab === 'keywords') {
    setTimeout(() => {
      renderKeywordCloud();
      if (!STATE.trendChartInstance) renderTrendChart();
    }, 50);
  } else if (tab === 'speakers') {
    setTimeout(() => {
      if (!STATE.speakersBarChartInstance) renderSpeakersOverview();
    }, 50);
  }
}

// ============================================================
// 데이터 연동 및 로드
// ============================================================
async function loadData() {
  const loadSub = document.getElementById('loading-sub');
  try {
    loadSub.textContent = '서버에서 data/meetings.json 로드 중...';
    // 브라우저 디스크 캐시 방지를 위해 캐시 버스팅(Cache Busting) 쿼리 적용
    const resp = await fetch('data/meetings.json?v=' + Date.now());
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    
    STATE.db = await resp.json();
    
    // 일반명사(국민, 근거, 지원 등) 강제 필터링
    const filterNouns = new Set(['국민', '근거', '지원']);
    if (STATE.db) {
      if (STATE.db.global_keywords) {
        STATE.db.global_keywords = STATE.db.global_keywords.filter(k => !filterNouns.has(k.word));
      }
      if (STATE.db.meetings) {
        STATE.db.meetings.forEach(m => {
          if (m.keywords) {
            m.keywords = m.keywords.filter(k => !filterNouns.has(k.word));
          }
        });
      }
    }
    
    document.getElementById('loading-screen').classList.add('hidden');
    
    // 앱 초기 가동
    initApp();
    
    // 로드 후 URL 라우팅 적용
    handleRouting();
  } catch (err) {
    console.warn("로컬 fetch 실패. file:// 프로토콜 테스트용 더미 모드를 검토합니다.", err);
    tryDummyLoad(err);
  }
}

// 개발 및 오프라인 환경을 위한 우아한 대체(Fallback) 처리
function tryDummyLoad(originalErr) {
  const loadSub = document.getElementById('loading-sub');
  loadSub.textContent = "서버 데이터를 불러오지 못해 로컬 로드 테스트를 시도합니다...";
  
  // 3초 후에도 실패 시 에러 스크린 노출
  setTimeout(() => {
    if (STATE.db) return;
    document.getElementById('loading-screen').classList.add('hidden');
    const errScreen = document.getElementById('error-screen');
    errScreen.classList.remove('hidden');
    document.getElementById('error-msg').textContent = `데이터를 로드하지 못했습니다: ${originalErr.message}`;
  }, 1500);
}

function initApp() {
  const { meetings, global_keywords, total_count, generated_at } = STATE.db;

  // 1. 헤더 업데이트 시간 가공 표시
  if (generated_at) {
    const dateObj = new Date(generated_at);
    if (!isNaN(dateObj)) {
      const pad = (n) => String(n).padStart(2, '0');
      const formattedDate = `${dateObj.getFullYear()}.${pad(dateObj.getMonth()+1)}.${pad(dateObj.getDate())} ${pad(dateObj.getHours())}:${pad(dateObj.getMinutes())}`;
      document.getElementById('header-update-time').textContent = `업데이트: ${formattedDate}`;
    }
  }

  // 2. 발언자 정보 및 고유 통계 계산
  const allSpeakers = new Set();
  meetings.forEach(m => {
    (m.speakers || []).forEach(s => {
      // 발언자 정규화 병합 처리
      const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
      allSpeakers.add(cleanName);
    });
  });

  document.querySelector('#stat-total .stat-num').textContent = total_count;
  document.querySelector('#stat-speakers .stat-num').textContent = allSpeakers.size;
  document.querySelector('#stat-keywords .stat-num').textContent = (global_keywords?.length || 0);

  // 3. 총괄 상황판 통계값 계산 및 동적 주입
  const counts = {
    total: meetings.length,
    plenary: 0,
    audit: 0,
    it: 0,
    st: 0,
    budget: 0,
    agenda: 0,
    etc: 0
  };

  meetings.forEach(m => {
    const t = m.meeting_type;
    if (t === '전체회의') counts.plenary++;
    else if (t === '국정감사') counts.audit++;
    else if (t === '정보통신방송소위') counts.it++;
    else if (t === '과학기술원자력소위') counts.st++;
    else if (t === '예산결산소위') counts.budget++;
    else if (t === '안건조정위원회') counts.agenda++;
    else counts.etc++;
  });

  document.getElementById('ov-val-total').textContent = counts.total;
  document.getElementById('ov-val-plenary').textContent = counts.plenary;
  document.getElementById('ov-val-audit').textContent = counts.audit;
  document.getElementById('ov-val-it-sub').textContent = counts.it;
  document.getElementById('ov-val-st-sub').textContent = counts.st;
  document.getElementById('ov-val-budget-sub').textContent = counts.budget;
  document.getElementById('ov-val-agenda-sub').textContent = counts.agenda;
  document.getElementById('ov-val-etc-sub').textContent = counts.etc;

  // 4. 총괄 상황판 클릭 필터 연동 기능 바인딩
  const filterTypeSelect = document.getElementById('filter-type');
  const overviewCards = {
    'ov-card-total': '',
    'ov-card-plenary': '전체회의',
    'ov-card-audit': '국정감사',
    'ov-card-it-sub': '정보통신방송소위',
    'ov-card-st-sub': '과학기술원자력소위',
    'ov-card-budget-sub': '예산결산소위',
    'ov-card-agenda-sub': '안건조정위원회',
    'ov-card-etc-sub': 'etc'
  };

  const syncOverviewSelection = (selectedType) => {
    Object.keys(overviewCards).forEach(id => {
      const card = document.getElementById(id);
      if (!card) return;
      const type = overviewCards[id];
      if (selectedType === type || (type === 'etc' && (selectedType === '청원심사소위' || selectedType === '기타'))) {
        card.classList.add('active-all');
      } else {
        card.classList.remove('active-all');
      }
    });
  };

  Object.keys(overviewCards).forEach(id => {
    const card = document.getElementById(id);
    if (!card) return;
    card.addEventListener('click', () => {
      const type = overviewCards[id];
      if (type === 'etc') {
        filterTypeSelect.value = '청원심사소위';
      } else {
        filterTypeSelect.value = type;
      }
      filterTypeSelect.dispatchEvent(new Event('change'));
      syncOverviewSelection(type);
    });
  });

  filterTypeSelect.addEventListener('change', () => {
    syncOverviewSelection(filterTypeSelect.value);
  });

  // 5. 필터 제어 초기화
  initFilters();
  initSpeakerTab();
  initKeywordTab();
  
  // 요약 탭 정렬/필터 리스너들
  applyFilters();
}

// ============================================================
// 라우팅 (URL Hash 파싱 및 동기화)
// ============================================================
function handleRouting() {
  const hash = window.location.hash;
  if (!hash) {
    switchTab('summary');
    return;
  }

  const parts = hash.split('?');
  const path = parts[0].substring(2); // '#/summary' -> 'summary'
  const params = new URLSearchParams(parts[1] || '');

  switchTab(path);

  if (path === 'summary') {
    const q = params.get('q') || '';
    const year = params.get('year') || '';
    const type = params.get('type') || '';
    const session = params.get('session') || '';
    const sort = params.get('sort') || 'date-desc';
    const view = params.get('view') || 'grid';
    const start = params.get('start') || '';
    const end = params.get('end') || '';

    document.getElementById('summary-search').value = q;
    document.getElementById('filter-year').value = year;
    document.getElementById('filter-type').value = type;
    document.getElementById('filter-session').value = session;
    document.getElementById('sort-select').value = sort;
    document.getElementById('filter-start-date').value = start;
    document.getElementById('filter-end-date').value = end;
    
    STATE.viewMode = view;
    document.getElementById('view-grid-btn').classList.toggle('active', view === 'grid');
    document.getElementById('view-list-btn').classList.toggle('active', view === 'list');

    applyFilters(false); // 무한 루프 방지를 위해 hash 업데이트는 스킵
  } else if (path === 'keywords') {
    const k1 = params.get('k1') || '';
    const k2 = params.get('k2') || '';
    
    if (k1 && k2) {
      STATE.compareMode = true;
      document.getElementById('kw-compare-btn').classList.add('active');
      document.getElementById('kw-compare-btn').textContent = '키워드 다중 비교 모드 끄기';
      document.getElementById('kw-compare-bar').classList.remove('hidden');
      STATE.compareKeywords = [k1, k2];
      renderCompareTags();
      searchKeywordCompare();
    } else if (k1) {
      STATE.compareMode = false;
      document.getElementById('kw-compare-btn').classList.remove('active');
      document.getElementById('kw-compare-btn').textContent = '키워드 다중 비교 모드 켜기';
      document.getElementById('kw-compare-bar').classList.add('hidden');
      searchKeyword(k1, false);
    }
  } else if (path === 'speakers') {
    const name = params.get('name') || '';
    if (name) {
      setTimeout(() => {
        // 발언자를 바로 검색해주는 UI 보조 지원
        const sel = document.getElementById('speaker-meeting-select');
        // 첫 번째 만나는 해당 발언자 포함 회의 선택
        const meetings = STATE.db.meetings;
        const matchedIdx = meetings.findIndex(m => (m.speakers || []).some(s => s.name.includes(name)));
        if (matchedIdx !== -1) {
          sel.value = matchedIdx;
          sel.dispatchEvent(new Event('change'));
          // 리스트에서 발언자 찾아 클릭 유도
          setTimeout(() => {
            document.querySelectorAll('#speaker-list .speaker-item').forEach(el => {
              if (el.querySelector('.speaker-name').textContent.includes(name)) {
                el.click();
              }
            });
          }, 200);
        }
      }, 300);
    }
  }
}

function updateHash() {
  let hashStr = `#/${STATE.currentTab}`;

  if (STATE.currentTab === 'summary') {
    const q = document.getElementById('summary-search').value.trim();
    const year = document.getElementById('filter-year').value;
    const type = document.getElementById('filter-type').value;
    const session = document.getElementById('filter-session').value;
    const sort = document.getElementById('sort-select').value;
    const start = document.getElementById('filter-start-date').value;
    const end = document.getElementById('filter-end-date').value;

    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (year) params.set('year', year);
    if (type) params.set('type', type);
    if (session) params.set('session', session);
    if (sort !== 'date-desc') params.set('sort', sort);
    if (STATE.viewMode !== 'grid') params.set('view', STATE.viewMode);
    if (start) params.set('start', start);
    if (end) params.set('end', end);

    const queryStr = params.toString();
    if (queryStr) hashStr += `?${queryStr}`;
  } else if (STATE.currentTab === 'keywords') {
    if (STATE.compareKeywords.length > 0) {
      const params = new URLSearchParams();
      params.set('k1', STATE.compareKeywords[0]);
      if (STATE.compareKeywords[1]) params.set('k2', STATE.compareKeywords[1]);
      hashStr += `?${params.toString()}`;
    } else if (STATE.selectedKeyword) {
      hashStr += `?k1=${encodeURIComponent(STATE.selectedKeyword)}`;
    }
  }

  // Hash가 변경되면 handleRouting이 트리거됨
  window.location.hash = hashStr;
}

// ============================================================
// 1단계: 회의록 요약 & 다중 필터 & 정렬
// ============================================================
function initFilters() {
  const meetings = STATE.db.meetings;

  // 1. 연도 셀렉트 옵션 추가
  const years = [...new Set(meetings.map(m => m.year).filter(Boolean))].sort((a,b)=>a-b);
  const yearSel = document.getElementById('filter-year');
  years.forEach(y => {
    const opt = document.createElement('option');
    opt.value = y;
    opt.textContent = `${y}년`;
    yearSel.appendChild(opt);
  });

  // 2. 회기 셀렉트 옵션 추가
  const sessions = [...new Set(meetings.map(m => m.session_num).filter(Boolean))].sort((a,b)=>a-b);
  const sessionSel = document.getElementById('filter-session');
  sessions.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = `제${s}회`;
    sessionSel.appendChild(opt);
  });

  // 3. 검색 입력창 및 셀렉트 이벤트 핸들러 바인딩
  document.getElementById('summary-search').addEventListener('input', debounce(() => {
    applyFilters();
  }, 300));
  
  document.getElementById('summary-search-clear').addEventListener('click', () => {
    document.getElementById('summary-search').value = '';
    applyFilters();
  });

  yearSel.addEventListener('change', () => applyFilters());
  document.getElementById('filter-type').addEventListener('change', () => applyFilters());
  sessionSel.addEventListener('change', () => applyFilters());
  document.getElementById('sort-select').addEventListener('change', () => applyFilters());
  
  // 날짜 범위 필터 바인딩
  document.getElementById('filter-start-date').addEventListener('change', () => applyFilters());
  document.getElementById('filter-end-date').addEventListener('change', () => applyFilters());

  // 4. 리스트/그리드 토글 뷰 제어 바인딩
  const gridBtn = document.getElementById('view-grid-btn');
  const listBtn = document.getElementById('view-list-btn');

  gridBtn.addEventListener('click', () => {
    if (STATE.viewMode === 'grid') return;
    STATE.viewMode = 'grid';
    gridBtn.classList.add('active');
    listBtn.classList.remove('active');
    document.getElementById('meeting-cards').classList.remove('list-view');
    applyFilters();
  });

  listBtn.addEventListener('click', () => {
    if (STATE.viewMode === 'list') return;
    STATE.viewMode = 'list';
    listBtn.classList.add('active');
    gridBtn.classList.remove('active');
    document.getElementById('meeting-cards').classList.add('list-view');
    applyFilters();
  });

  document.getElementById('load-more-btn').addEventListener('click', loadMoreCards);
}

function applyFilters(shouldUpdateHash = true) {
  const query = document.getElementById('summary-search').value.trim().toLowerCase();
  const year = document.getElementById('filter-year').value;
  const type = document.getElementById('filter-type').value;
  const session = document.getElementById('filter-session').value;
  const sort = document.getElementById('sort-select').value;
  const startDate = document.getElementById('filter-start-date').value;
  const endDate = document.getElementById('filter-end-date').value;

  STATE.sortMode = sort;
  STATE.startDate = startDate;
  STATE.endDate = endDate;

  // 필터링 적용
  let result = STATE.db.meetings.filter(m => {
    if (year && String(m.year) !== year) return false;
    if (type && m.meeting_type !== type) return false;
    if (session && String(m.session_num) !== session) return false;
    
    // 날짜 범위 필터 체크
    if (startDate && m.date && m.date < startDate) return false;
    if (endDate && m.date && m.date > endDate) return false;

    if (query) {
      const haystack = [
        m.filename || '',
        m.summary || '',
        m.meeting_type || '',
        (m.keywords || []).map(k => k.word).join(' '),
        (m.agendas || []).join(' '),
        (m.speakers || []).map(s => s.name).join(' '),
      ].join(' ').toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });

  // 정렬 적용
  if (sort === 'date-desc') {
    result.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  } else if (sort === 'date-asc') {
    result.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  } else if (sort === 'speakers-desc') {
    result.sort((a, b) => (b.speakers?.length || 0) - (a.speakers?.length || 0));
  } else if (sort === 'length-desc') {
    result.sort((a, b) => (b.text_length || 0) - (a.text_length || 0));
  }

  STATE.filtered = result;
  STATE.displayed = 0;
  
  const cardsContainer = document.getElementById('meeting-cards');
  cardsContainer.innerHTML = '';

  renderSummaryCards();

  if (shouldUpdateHash) {
    updateHash();
  }
}

function renderSummaryCards() {
  const grid = document.getElementById('meeting-cards');
  const slice = STATE.filtered.slice(STATE.displayed, STATE.displayed + STATE.PAGE_SIZE);
  const query = document.getElementById('summary-search').value.trim();

  if (STATE.displayed === 0 && slice.length === 0) {
    grid.innerHTML = `<div class="no-results" style="grid-column: 1 / -1">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <p>조건에 맞는 회의록이 없습니다. 필터를 변경해보세요.</p>
    </div>`;
  }

  slice.forEach((m, i) => {
    const card = createMeetingCard(m, STATE.displayed + i, query);
    grid.appendChild(card);
  });

  STATE.displayed += slice.length;

  const remaining = STATE.filtered.length - STATE.displayed;
  const loadBtn = document.getElementById('load-more-btn');
  if (remaining > 0) {
    loadBtn.classList.remove('hidden');
    document.getElementById('load-more-count').textContent = `(${remaining}개 더)`;
  } else {
    loadBtn.classList.add('hidden');
  }

  document.getElementById('summary-result-count').textContent = `총 ${STATE.filtered.length}건 검색됨`;
}

function loadMoreCards() {
  renderSummaryCards();
}

/**
 * 회의록 카드를 생성하고 반환
 */
function createMeetingCard(m, index, query) {
  const card = document.createElement('div');
  card.className = 'meeting-card';
  card.style.animationDelay = `${(index % STATE.PAGE_SIZE) * 20}ms`;

  const type = m.meeting_type || '기타';
  const color = TYPE_COLORS[type] || TYPE_COLORS['기타'];
  card.style.setProperty('--card-accent', `linear-gradient(90deg, ${color}, ${color}88)`);

  const dateStr = m.date ? m.date.replace(/-/g, '.') : '날짜 미상';
  const keywords = (m.keywords || []).slice(0, 5).map(k => k.word);
  const speakerNames = (m.speakers || []).slice(0, 4).map(s => s.name);
  
  // 1. 회의 제목 정규화 및 보기 좋게 리뉴얼
  let cleanTitle = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '회의록';
  cleanTitle = cleanTitle.replace(/^제22대국회\s+과학기술정보방송통신위원회\s+회의록\s+/, '');
  cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');
  
  const titleRegex = /제(\d+)회\((.+?)\)\s+제(\d+)차\s+(.+)/;
  const titleMatch = cleanTitle.match(titleRegex);
  let displayTitle = cleanTitle;
  if (titleMatch) {
    displayTitle = `[제${titleMatch[1]}회 ${titleMatch[2]}] 제${titleMatch[3]}차 ${titleMatch[4]}`;
  }

  // 2. 검색어 하이라이트 함수 적용
  const highlight = (txt) => {
    if (!query || !txt) return escHtml(txt);
    const escapedQuery = query.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'gi');
    return escHtml(txt).replace(regex, '<mark class="search-highlight">$1</mark>');
  };

  // 3. 안건 미리보기 또는 요약 분기 출력 (사용자 피드백 반영 원복)
  let bodyContentHTML = '';
  if (m.agendas && m.agendas.length > 0) {
    bodyContentHTML = `
      <div class="card-agendas">
        ${m.agendas.slice(0, 2).map((a, i) => `
          <div class="card-agenda-item">
            <span class="card-agenda-num">${i + 1}</span>
            <span class="card-agenda-text">${highlight(a.title)}</span>
          </div>
        `).join('')}
      </div>
    `;
  } else {
    // 안건이 없는 회의록의 경우 상황 보고서 1. 총 평 하위의 ㅇ 대항목 요약문 발췌
    let displaySummary = '회의록 주요 요약 내용이 존재하지 않습니다.';
    if (m.summary) {
      const summaryMatch = m.summary.match(/ㅇ\s*([^\n]+)/);
      if (summaryMatch) {
        displaySummary = summaryMatch[1].replace(/\*\*/g, '').trim();
      } else {
        displaySummary = m.summary.replace(/\*\*/g, '').replace(/\n/g, ' ').trim();
      }
    }
    const cutSummary = displaySummary.length > 105 ? displaySummary.substring(0, 105) + '...' : displaySummary;
    bodyContentHTML = `<div class="card-summary">${highlight(cutSummary)}</div>`;
  }

  let badgeText = type;
  if (type === '정보통신방송소위') badgeText = '정보통신방송소위 법안심사';
  else if (type === '과학기술원자력소위') badgeText = '과학기술원자력소위 법안심사';

  card.innerHTML = `
    <div class="card-top">
      <span class="card-badge badge-${type}">${badgeText}</span>
      <span class="card-date">${dateStr}</span>
    </div>
    <div class="card-title">${highlight(displayTitle)}</div>
    ${bodyContentHTML}
    <div class="card-tags">
      ${keywords.map(k => `<span class="card-tag" data-kw="${escHtml(k)}">#${highlight(k)}</span>`).join('')}
    </div>
    <div class="card-footer">
      <span class="card-speakers">
        👤 ${speakerNames.length > 0 ? speakerNames.join(', ') + (m.speakers?.length > 4 ? ` 외 ${m.speakers.length - 4}명` : '') : '발언 의원 정보 없음'}
      </span>
      <span class="card-more">상세보고서 →</span>
    </div>
  `;

  // 태그 클릭 시 키워드 탭 검색 연동
  card.addEventListener('click', (e) => {
    const tag = e.target.closest('.card-tag');
    if (tag) {
      const kw = tag.dataset.kw;
      STATE.selectedKeyword = kw;
      switchTab('keywords');
      searchKeyword(kw);
      return;
    }
    openModal(m);
  });

  return card;
}

// ============================================================
// 2단계: 모달 레이아웃 & 상세 정보 (프로그레스바 적용)
// ============================================================
function openModal(m) {
  try {
    STATE.lastOpenMeeting = m; // 모달 복원을 위해 저장
    STATE.selectedSpeakers = []; // 초기화
    const overlay = document.getElementById('modal-overlay');
  const type = m.meeting_type || '기타';
  const color = TYPE_COLORS[type] || TYPE_COLORS['기타'];
  const dateStr = m.date ? m.date.replace(/-/g, '.') : '날짜 미상';

  let cleanTitle = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '회의록';
  cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

  // 1. 모달 머리글 매핑 & 유형 텍스트 분기
  let badgeText = type;
  if (type === '정보통신방송소위') badgeText = '정보통신방송소위 법안심사';
  else if (type === '과학기술원자력소위') badgeText = '과학기술원자력소위 법안심사';
  
  document.getElementById('modal-badge').innerHTML = `<span class="card-badge badge-${type}" style="border-color:${color}44">${badgeText}</span>`;
  document.getElementById('modal-title').textContent = cleanTitle;
  document.getElementById('modal-meta').innerHTML = `
    <span>🏛️ 제${m.session_num || '?'}회 (${m.session_type || '임시회'})</span>
    <span>📅 회의 일자: ${dateStr}</span>
    <span>📑 제${m.order_num || '?'}차 회의</span>
    <span>📏 회의록 분량: ${(m.text_length || 0).toLocaleString()}자</span>
  `;

  // 2. 사이드바 - 상정 안건 탭
  const agendasContainer = document.getElementById('modal-agendas');
  agendasContainer.innerHTML = (m.agendas && m.agendas.length > 0)
    ? m.agendas.map((a, i) => `
        <div class="modal-agenda-item" data-agenda-idx="${i}">
          <span class="modal-agenda-num">${i + 1}</span>
          <span style="flex:1; font-weight: 500;">${escHtml(a.title || a)}</span>
        </div>`).join('')
    : '<div style="color:var(--text-tertiary);font-size:12px;padding:8px;text-align:center;">본 의사일정 정보가 없습니다.</div>';

  // 3. 사이드바 - 발언 의원 탭
  const totalSpeechCount = (m.speakers || []).reduce((acc, curr) => acc + (curr.speech_count || 0), 0) || 1;
  const spks = (m.speakers || []).slice(0, 20);
  
  const getSpeakerRole = (name) => {
    if (name === '최민희') return { label: '위원장', color: 'rgba(99,102,241,0.15)', text: '#a5b4fc', border: 'rgba(99,102,241,0.3)', class: 'role-member' };
    if (name === '김현' || name === '최형두') return { label: '간사', color: 'rgba(16,185,129,0.15)', text: '#6ee7b7', border: 'rgba(16,185,129,0.3)', class: 'role-member' };
    if (['유상임', '배경훈', '김종철', '이진숙', '박민', '김태규', '구혁채', '류제명', '이복우'].includes(name)) {
      const isOfficer = name === '이복우' ? '수석전문위원' : '정부위원';
      return { label: isOfficer, color: 'rgba(245,158,11,0.15)', text: '#fcd34d', border: 'rgba(245,158,11,0.3)', class: 'role-officer' };
    }
    return { label: '위원', color: 'rgba(255,255,255,0.05)', text: '#94a3b8', border: 'rgba(255,255,255,0.1)', class: 'role-member' };
  };

  const speakersContainer = document.getElementById('modal-speakers');
  speakersContainer.innerHTML = spks.length
    ? spks.map(s => {
        const ratio = Math.round((s.speech_count / totalSpeechCount) * 100);
        const role = getSpeakerRole(s.name);
        return `
        <div class="modal-speaker-item" data-speaker-name="${escHtml(s.name)}" style="cursor:pointer; padding:6px 8px; border-radius:6px; transition:all 0.15s; margin-bottom:4px;">
          <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
            <input type="checkbox" class="speaker-checkbox" data-speaker-name="${escHtml(s.name)}" style="cursor:pointer; width:13px; height:13px; margin:0;" onclick="event.stopPropagation();">
            <div class="modal-speaker-avatar" style="width:24px; height:24px; font-size:10px;">${s.name.charAt(0)}</div>
            <div style="flex:1; display:flex; align-items:center; gap:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
              <span class="modal-speaker-name" style="font-weight:600;">${escHtml(s.name)}</span>
              <span class="timeline-role-badge ${role.class}" style="font-size:9px; padding:1px 5px; border-radius:100px; background:${role.color}; color:${role.text}; border:1px solid ${role.border}; font-weight:600; line-height:1;">${role.label}</span>
            </div>
            <span class="modal-speaker-cnt" style="font-size:11px; color:var(--text-tertiary);">${s.speech_count}회</span>
          </div>
          <div class="speaker-bar" style="height:3px; background:rgba(255,255,255,0.05); border-radius:10px; overflow:hidden; margin-left:21px;">
            <div class="speaker-bar-fill" style="width:${ratio}%; height:100%; background:linear-gradient(90deg, #6366f1, #8b5cf6);"></div>
          </div>
        </div>`;
      }).join('')
    : '<div style="color:var(--text-tertiary);font-size:12px;padding:8px;text-align:center;">발언자 정보가 없습니다.</div>';

  // 4. 사이드바 - 키워드 탭 (신설)
  const keywordsContainer = document.getElementById('modal-sidebar-keywords');
  const kws = m.keywords || [];
  keywordsContainer.innerHTML = kws.length
    ? kws.slice(0, 24).map(k => `
        <span class="keyword-tag-pill" data-keyword-name="${escHtml(k.word)}">
          #${escHtml(k.word)} (${k.count})
        </span>`).join('')
    : '<div style="color:var(--text-tertiary);font-size:12px;padding:8px;text-align:center;">키워드가 없습니다.</div>';

  // 5. 우측 본문 뷰어 - 기본 상황 보고서 및 키워드 마크업 준비
  const processBoldText = (txt) => {
    return txt.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  };

  const lines = (m.summary || '요약 정보 없음').split('\n');
  const summaryHTML = lines.map((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) return '';

    let className = 'summary-line';
    if (trimmed.startsWith('1. ') || trimmed.startsWith('2. ')) {
      return `<h3 class="viewer-report-title" style="font-size:15px; font-weight:700; color:var(--accent-3); margin: 20px 0 10px 0; border-bottom:1px dashed rgba(255,255,255,0.15); padding-bottom:4px;" data-line-idx="${idx}">${escHtml(trimmed)}</h3>`;
    } else if (trimmed.startsWith('ㅇ')) {
      className += ' summary-bullet-main';
      return `<div class="${className}" style="margin-left:4px; font-weight:500; font-size:13.5px; color:var(--text-primary); margin-bottom:8px; line-height:1.75;" data-line-idx="${idx}">${processBoldText(escHtml(trimmed))}</div>`;
    } else if (trimmed.startsWith('-')) {
      className += ' summary-bullet-sub';
      return `<div class="${className}" style="margin-left:14px; font-size:13px; color:var(--text-secondary); margin-bottom:6px; line-height:1.75;" data-line-idx="${idx}">${processBoldText(escHtml(trimmed))}</div>`;
    } else if (trimmed.startsWith('※')) {
      className += ' summary-bullet-ref';
      return `<div class="${className}" style="margin-left:14px; font-size:12.5px; color:var(--accent-amber); opacity:0.9; margin-bottom:6px; line-height:1.75;" data-line-idx="${idx}">${processBoldText(escHtml(trimmed))}</div>`;
    } else if (trimmed.startsWith('▲')) {
      className += ' summary-issue-title';
      return `<h4 class="${className}" style="font-size:13.5px; font-weight:600; color:var(--accent-cyan); margin: 18px 0 8px 10px;" data-line-idx="${idx}">${escHtml(trimmed)}</h4>`;
    }

    return `<div class="${className}" style="margin-bottom:6px; line-height:1.75;" data-line-idx="${idx}">${processBoldText(escHtml(trimmed))}</div>`;
  }).join('');

  const originalViewerHTML = `
    <!-- 본문 영역 서브 섹션들 -->
    <section class="viewer-section">
      <div class="viewer-section-header">
        <span class="viewer-icon">📝</span>
        <span class="viewer-title">국회 정책 대응 상황 보고서 (Status Report)</span>
      </div>
      <div class="modal-summary" id="modal-summary">${summaryHTML}</div>
    </section>
    
    <section class="viewer-section">
      <div class="viewer-section-header">
        <span class="viewer-icon">🔑</span>
        <span class="viewer-title">회의 핵심 법안 및 정책 키워드</span>
      </div>
      <div id="modal-keywords" class="modal-keywords-wrap">
        <div class="modal-keywords-wrap">
          ${kws.slice(0, 12).map(k => `<span class="modal-kw-tag" style="cursor:pointer" onclick="closeModal(); switchTab('keywords'); searchKeyword('${escHtml(k.word)}');">#${escHtml(k.word)} <sup>${k.count}</sup></span>`).join('')}
        </div>
      </div>
    </section>
  `;

  // 우측 컨테이너 기본 로드 및 퀵 헤더 초기화
  const viewerContainer = document.getElementById('dynamic-viewer-container');
  const backBtn = document.getElementById('btn-back-to-status');
  viewerContainer.innerHTML = originalViewerHTML;
  backBtn.classList.add('hidden');

  // 상황 보고서 전체보기 퀵 버튼 바인딩
  backBtn.onclick = () => {
    viewerContainer.innerHTML = originalViewerHTML;
    backBtn.classList.add('hidden');
    // 하이라이팅 초기화
    document.querySelectorAll('.modal-speaker-item, .keyword-tag-pill, .modal-agenda-item').forEach(el => el.classList.remove('active-highlight', 'active'));
  };

  // 6. 사이드바 탭 컨트롤 활성화 및 기본값 초기화
  const sidebarTabBtns = document.querySelectorAll('.sidebar-tab-btn');
  const sidebarPanels = document.querySelectorAll('.sidebar-panel');
  
  sidebarTabBtns.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.sidebarTab === 'agendas');
  });
  sidebarPanels.forEach(panel => {
    panel.classList.toggle('active', panel.id === 'sidebar-panel-agendas');
  });

  sidebarTabBtns.forEach(btn => {
    btn.onclick = () => {
      sidebarTabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const targetTab = btn.dataset.sidebarTab;
      sidebarPanels.forEach(panel => {
        panel.classList.toggle('active', panel.id === `sidebar-panel-${targetTab}`);
      });
    };
  });

  // 7. 인터랙티브 연동 - 안건 클릭 -> 입법 카드 렌더링 전환!
  const agendaItems = agendasContainer.querySelectorAll('.modal-agenda-item');
  agendaItems.forEach(item => {
    item.onclick = () => {
      agendaItems.forEach(a => a.classList.remove('active-highlight'));
      item.classList.add('active-highlight');
      
      const idx = parseInt(item.dataset.agendaIdx);
      let agendaData = m.agendas[idx];
      
      if (!agendaData) return;
      
      // 문자열 타입일 때 호환성 래핑 가드 작동
      if (typeof agendaData === 'string') {
        agendaData = {
          title: agendaData,
          proposer: "의원 발의",
          proposal_date: m.date ? m.date.replace(/-/g, '.') : "국회 계류 중",
          summary: "상세 법안 내용 및 심사 진행 경과는 국회의안정보시스템을 참조해 주세요.",
          link: "https://likms.assembly.go.kr/bill/main.do"
        };
      }
      
      backBtn.classList.remove('hidden');
      
      const isDirectLink = agendaData.link && agendaData.link.includes('billId=');
      
      viewerContainer.innerHTML = `
        <div class="bill-detail-card">
          <div class="bill-card-header">
            <h3 class="bill-card-title">📜 ${escHtml(agendaData.title)}</h3>
            <div class="bill-meta-row">
              <span class="bill-meta-badge proposer-badge">👤 제안자: ${escHtml(agendaData.proposer)}</span>
              <span class="bill-meta-badge date-badge">📅 제안일자: ${escHtml(agendaData.proposal_date)}</span>
            </div>
          </div>
          <div class="bill-card-body">
            <div class="bill-body-title">💡 제안이유 및 주요내용</div>
            <div class="bill-body-summary" style="margin-bottom:12px;">${escHtml(agendaData.summary)}</div>
            ${isDirectLink ? `
              <div style="font-size:11.5px; color:var(--text-tertiary); background:rgba(255,255,255,0.03); border:1px dashed var(--border-color); padding:10px 14px; border-radius:6px; margin-bottom:12px; line-height:1.6;">
                💡 <strong>[안내]</strong> 국회의안정보시스템 상세 페이지로 직접 연동됩니다. 심사 경과 및 제안의안 원문 문서를 바로 확인해 보세요.
              </div>
              <a href="${agendaData.link}" target="_blank" class="btn-likms-link">
                <span>국회의안정보시스템 상세 열기 🔗</span>
              </a>
            ` : `
              <div style="font-size:11.5px; color:var(--text-tertiary); background:rgba(255,255,255,0.03); border:1px dashed var(--border-color); padding:10px 14px; border-radius:6px; margin-bottom:12px; line-height:1.6;">
                💡 <strong>[안내]</strong> 국회 시스템 보안 정책으로 인한 404 에러를 방지하고자 공식 검색 허브로 연결됩니다. 국회의안정보시스템 열기 후 검색창에 의안명인 <strong>"${escHtml(agendaData.title.replace(/^\d+[\.\s]*/, '').split('(')[0].trim())}"</strong>을(를) 복사하여 검색하시면 심사 경과 및 상세 문서를 확인하실 수 있습니다.
              </div>
              <a href="https://likms.assembly.go.kr/bill/main.do" target="_blank" class="btn-likms-link">
                <span>국회의안정보시스템 검색 허브 바로가기 🔗</span>
              </a>
            `}
          </div>
        </div>
      `;
      viewerContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
  });

  // 8. 발언자 다중 선택 및 대화형 타임라인 렌더링 헬퍼 함수들 (openModal 내부 클로저로 정의)
  const getAllChronologicalTurns = () => {
    const allLines = [];
    (m.speakers || []).forEach(spk => {
      if (spk.lines) {
        spk.lines.forEach(line => {
          allLines.push({
            speaker: spk.name,
            text: line.text,
            page: line.page,
            idx: line.idx || 0
          });
        });
      }
    });
    
    allLines.sort((a, b) => {
      if (a.page !== b.page) return a.page - b.page;
      return a.idx - b.idx;
    });
    
    const turns = [];
    let current = null;
    
    allLines.forEach(line => {
      let cleaned = line.text.replace(/\d+\s+제\d+회\s*-\s*[가-힣\s\(\)]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)/g, '');
      cleaned = cleaned.replace(/^\d+\s+제\d+회-.*?$/gm, '').trim();
      if (!cleaned) return;
      
      if (!current) {
        current = {
          speaker: line.speaker,
          page: line.page,
          idx: line.idx
        };
      } else {
        if (current.speaker === line.speaker && current.page === line.page && (line.idx - current.idx <= 15)) {
          // 병합
        } else {
          turns.push(current);
          current = {
            speaker: line.speaker,
            page: line.page,
            idx: line.idx
          };
        }
      }
    });
    if (current) {
      turns.push(current);
    }
    
    return turns;
  };

  const getInteractorsForSpeaker = (targetName) => {
    const turns = getAllChronologicalTurns();
    const interactors = new Set();
    
    for (let i = 0; i < turns.length; i++) {
      if (turns[i].speaker === targetName) {
        for (let j = Math.max(0, i - 2); j <= Math.min(turns.length - 1, i + 2); j++) {
          if (turns[j].speaker !== targetName) {
            interactors.add(turns[j].speaker);
          }
        }
      }
    }
    
    return Array.from(interactors);
  };

  const updateSpeakerSidebar = () => {
    const selected = STATE.selectedSpeakers;
    const items = speakersContainer.querySelectorAll('.modal-speaker-item');
    
    if (selected.length === 0) {
      items.forEach(item => {
        item.classList.remove('disabled');
        item.style.opacity = '1';
        item.style.pointerEvents = 'auto';
        const checkbox = item.querySelector('.speaker-checkbox');
        if (checkbox) checkbox.checked = false;
      });
    } else {
      const firstSpeaker = selected[0];
      const interactors = getInteractorsForSpeaker(firstSpeaker);
      
      items.forEach(item => {
        const name = item.dataset.speakerName;
        const checkbox = item.querySelector('.speaker-checkbox');
        
        if (selected.includes(name)) {
          item.classList.remove('disabled');
          item.style.opacity = '1';
          item.style.pointerEvents = 'auto';
          if (checkbox) checkbox.checked = true;
        } else if (interactors.includes(name)) {
          item.classList.remove('disabled');
          item.style.opacity = '1';
          item.style.pointerEvents = 'auto';
          if (checkbox) checkbox.checked = false;
        } else {
          item.classList.add('disabled');
          item.style.opacity = '0.35';
          item.style.pointerEvents = 'none';
          if (checkbox) checkbox.checked = false;
        }
      });
    }
  };

  const renderSingleSpeakerTimeline = (spkName) => {
    const matchedSpk = m.speakers.find(s => s.name === spkName);
    if (!matchedSpk || !matchedSpk.lines || matchedSpk.lines.length === 0) {
      backBtn.onclick();
      const allLines = document.getElementById('modal-summary').querySelectorAll('div, h3, h4');
      allLines.forEach(el => el.classList.remove('speaker-qa-highlight'));
      let firstEl = null;
      allLines.forEach(el => {
        if (el.textContent.includes(spkName)) {
          el.classList.add('speaker-qa-highlight');
          if (!firstEl) firstEl = el;
        }
      });
      if (firstEl) firstEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    
    backBtn.classList.remove('hidden');
    const role = getSpeakerRole(spkName);
    
    viewerContainer.innerHTML = `
      <div class="viewer-section" style="border-left: 4px solid var(--accent-1);">
        <div class="viewer-section-header" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="viewer-icon">👤</span>
            <span class="viewer-title" style="font-size: 15px;">${escHtml(spkName)} 의원 실제 발언 원문 타임라인 (안건별 분류)</span>
            <span class="timeline-role-badge ${role.class}" style="font-size:10px; margin-left:8px;">${role.label}</span>
          </div>
          <button id="btn-modal-speaker-download" class="kw-compare-btn" style="font-size:11px; padding:4px 10px; background:rgba(99,102,241,0.2); border:1px solid rgba(99,102,241,0.4); border-radius:4px; color:#a5b4fc; cursor:pointer;">📄 본 회의 발언 다운로드 (.txt)</button>
        </div>
        <div id="modal-speaker-timeline-grouped" style="display:flex; flex-direction:column; gap:16px;">
          ${(() => {
            const agendas = m.agendas || [];
            const groupedLines = {};
            
            const mergedSpeakerLines = getSpeakerMergedTurns(matchedSpk.lines, spkName);
            
            mergedSpeakerLines.forEach(seg => {
              let matchedIdx = -1;
              let maxMatches = 0;
              
              agendas.forEach((agenda, idx) => {
                const title = typeof agenda === 'string' ? agenda : agenda.title;
                const keywords = getAgendaKeywords(title);
                const matches = keywords.filter(kw => seg.text.toLowerCase().includes(kw.toLowerCase())).length;
                if (matches > maxMatches) {
                  maxMatches = matches;
                  matchedIdx = idx;
                }
              });
              
              const groupKey = matchedIdx !== -1 ? matchedIdx : 'etc';
              if (!groupedLines[groupKey]) {
                groupedLines[groupKey] = [];
              }
              groupedLines[groupKey].push(seg);
            });

            let groupedHTML = '';
            
            agendas.forEach((agenda, idx) => {
              const linesInGroup = groupedLines[idx];
              if (!linesInGroup || linesInGroup.length === 0) return;
              
              const agendaTitle = typeof agenda === 'string' ? agenda : agenda.title;
              
              groupedHTML += `
                <div class="agenda-timeline-group" style="border: 1px solid rgba(255,255,255,0.04); border-radius: 8px; background: rgba(255,255,255,0.01); padding: 12px 14px 4px 14px;">
                  <div class="agenda-group-header" style="display:flex; align-items:center; gap:8px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px; margin-bottom:12px;">
                    <span style="font-size:14px; font-weight:700; color:var(--accent-cyan);">📋 안건: ${escHtml(agendaTitle)}</span>
                    <span class="card-badge" style="font-size:9.5px; margin-left:auto; background:rgba(99,102,241,0.15); color:#a5b4fc; border:1px solid rgba(99,102,241,0.25); border-radius: 100px; padding: 2px 8px; line-height:1;">${linesInGroup.length}건 발언</span>
                  </div>
                  <div class="timeline-wrap">
                    ${linesInGroup.map(seg => `
                      <div class="timeline-node" data-filename="${escHtml(m.filename)}" data-page="${seg.page}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(spkName)}" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)" style="cursor:pointer; margin-bottom:12px; display:flex; flex-direction:column; gap:4px;">
                        <div class="timeline-sender-row" style="display:flex; justify-content:space-between; align-items:center;">
                          <span style="font-weight:700; color:#22d3ee; font-size:11.5px; margin-left:auto;">📄 PDF ${seg.page}페이지 🔗</span>
                        </div>
                        <div class="timeline-bubble" style="font-size:13.5px; line-height:1.65; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05); padding:8px 12px; border-radius:6px; color:var(--text-primary); font-weight:500;">${escHtml(formatSpeechText(seg.text))}</div>
                      </div>
                    `).join('')}
                  </div>
                </div>
              `;
            });
            
            const etcLines = groupedLines['etc'];
            if (etcLines && etcLines.length > 0) {
              groupedHTML += `
                <div class="agenda-timeline-group" style="border: 1px solid rgba(99, 102, 241, 0.22); border-radius: 8px; background: rgba(99, 102, 241, 0.02); padding: 12px 14px 4px 14px;">
                  <div class="agenda-group-header" style="display:flex; align-items:center; gap:8px; border-bottom:1px solid rgba(99, 102, 241, 0.15); padding-bottom:8px; margin-bottom:12px;">
                    <span style="font-size:14px; font-weight:700; color:#a5b4fc;">💬 기타 의사일정 및 자유 토의/질의</span>
                    <span class="card-badge" style="font-size:9.5px; margin-left:auto; background:rgba(99,102,241,0.15); color:#a5b4fc; border:1px solid rgba(99,102,241,0.3); border-radius: 100px; padding: 2px 8px; line-height:1;">${etcLines.length}건 발언</span>
                  </div>
                  <div class="timeline-wrap">
                    ${etcLines.map(seg => `
                      <div class="timeline-node" data-filename="${escHtml(m.filename)}" data-page="${seg.page}" data-text="${escHtml(seg.text)}" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)" style="cursor:pointer; margin-bottom:12px; display:flex; flex-direction:column; gap:4px;">
                        <div class="timeline-sender-row" style="display:flex; justify-content:space-between; align-items:center;">
                          <span style="font-weight:700; color:#22d3ee; font-size:11.5px; margin-left:auto;">📄 PDF ${seg.page}페이지 🔗</span>
                        </div>
                        <div class="timeline-bubble" style="font-size:13.5px; line-height:1.65; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05); padding:8px 12px; border-radius:6px; color:var(--text-primary); font-weight:500;">${escHtml(formatSpeechText(seg.text))}</div>
                      </div>
                    `).join('')}
                  </div>
                </div>
              `;
            }
            
            return groupedHTML;
          })()}
        </div>
      </div>
    `;

    viewerContainer.querySelectorAll('.timeline-node').forEach(node => {
      node.onclick = (e) => {
        e.stopPropagation();
        openPdfWithHighlight(node.dataset.filename, parseInt(node.dataset.page), node.dataset.text, node.dataset.speaker);
      };
    });

    document.getElementById('btn-modal-speaker-download').onclick = () => {
      let txtContent = `[${spkName} 의원 국회 발언 기록 - ${m.date} ${cleanTitle}]\n`;
      txtContent += `==================================================\n\n`;
      matchedSpk.lines.forEach((line, idx) => {
        txtContent += `[발언 #${idx + 1}] (PDF ${line.page}p) ${line.text.trim()}\n\n`;
      });

      const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `${spkName}_발언기록_${m.date}.txt`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    };

    viewerContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const renderMultiSpeakerTimeline = (selectedNames) => {
    document.getElementById('btn-back-to-status').classList.remove('hidden');
    
    const allSelectedLines = [];
    selectedNames.forEach(name => {
      const spk = m.speakers.find(s => s.name === name);
      if (spk && spk.lines) {
        spk.lines.forEach(line => {
          allSelectedLines.push({
            speaker: name,
            text: line.text,
            page: line.page,
            idx: line.idx || 0
          });
        });
      }
    });
    
    allSelectedLines.sort((a, b) => {
      if (a.page !== b.page) return a.page - b.page;
      return a.idx - b.idx;
    });
    
    const conversationTurns = [];
    let currentTurn = null;
    
    allSelectedLines.forEach(line => {
      let cleaned = line.text.replace(/\d+\s+제\d+회\s*-\s*[가-힣\s\(\)]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)/g, '');
      cleaned = cleaned.replace(/^\d+\s+제\d+회-.*?$/gm, '').trim();
      if (!cleaned) return;
      
      if (cleaned.startsWith('◯') || cleaned.startsWith('○')) {
        cleaned = cleaned.substring(1).trim();
        cleaned = cleaned.replace(/^([가-힣]{2,25}?(?:위원장|소위원장|위원|의원|간사|차관|장관|사장|대행|후보자|전문위원|수석전문위원|참고인|증인)?)\s+/, '');
      }
      
      if (!currentTurn) {
        currentTurn = {
          speaker: line.speaker,
          text: cleaned,
          page: line.page,
          indices: [line.idx]
        };
      } else {
        const lastIdx = currentTurn.indices[currentTurn.indices.length - 1];
        if (currentTurn.speaker === line.speaker && currentTurn.page === line.page && (line.idx - lastIdx <= 15)) {
          currentTurn.text += " " + cleaned;
          currentTurn.indices.push(line.idx);
        } else {
          conversationTurns.push(currentTurn);
          currentTurn = {
            speaker: line.speaker,
            text: cleaned,
            page: line.page,
            indices: [line.idx]
          };
        }
      }
    });
    
    if (currentTurn) {
      conversationTurns.push(currentTurn);
    }
    
    const titleStr = selectedNames.join(' ↔ ');
    
    let timelineHTML = `
      <div class="viewer-section" style="border-left: 4px solid var(--accent-indigo);">
        <div class="viewer-section-header" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 20px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="viewer-icon">💬</span>
            <span class="viewer-title" style="font-size: 15px; font-weight:700;">[대화 뷰 모드] ${escHtml(titleStr)} 대화록 (${conversationTurns.length}건)</span>
          </div>
        </div>
        <div class="chat-container" style="display:flex; flex-direction:column; gap:16px; background:rgba(255,255,255,0.01); border:1px solid rgba(255,255,255,0.04); border-radius:12px; padding:20px;">
    `;
    
    if (conversationTurns.length === 0) {
      timelineHTML += `<div style="color:var(--text-tertiary); font-size:13px; text-align:center; padding:20px;">선택된 발언자들 사이의 대화 데이터가 없습니다.</div>`;
    } else {
      const leftSpeaker = selectedNames[0];
      
      timelineHTML += conversationTurns.map(turn => {
        const isLeft = turn.speaker === leftSpeaker;
        const bubbleBg = isLeft ? 'rgba(99, 102, 241, 0.08)' : 'rgba(16, 185, 129, 0.08)';
        const bubbleBorder = isLeft ? 'rgba(99, 102, 241, 0.15)' : 'rgba(16, 185, 129, 0.15)';
        const nameColor = isLeft ? '#a5b4fc' : '#6ee7b7';
        const alignSide = isLeft ? 'flex-start' : 'flex-end';
        const borderRadius = isLeft ? '0 12px 12px 12px' : '12px 0 12px 12px';
        
        const role = getSpeakerRole(turn.speaker);
        
        return `
          <div class="timeline-node chat-bubble-wrap" data-filename="${escHtml(m.filename)}" data-page="${turn.page}" data-text="${escHtml(turn.text)}" data-speaker="${escHtml(turn.speaker)}" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)" style="cursor:pointer; display:flex; flex-direction:column; align-self:${alignSide}; width:80%; max-width:85%;">
            <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px; align-self:${alignSide}; flex-direction:${isLeft ? 'row' : 'row-reverse'};">
              <span style="font-weight:700; color:${nameColor}; font-size:12.5px;">${escHtml(turn.speaker)}</span>
              <span class="timeline-role-badge ${role.class}" style="font-size:9px; padding:1px 5px; border-radius:100px; background:${role.color}; color:${role.text}; border:1px solid ${role.border}; font-weight:600; line-height:1;">${role.label}</span>
              <span style="color:var(--text-tertiary); font-size:10.5px; margin-${isLeft ? 'left' : 'right'}:8px;">PDF ${turn.page}p 🔗</span>
            </div>
            <div class="timeline-bubble" style="font-size:13.5px; line-height:1.7; background:${bubbleBg}; border:1px solid ${bubbleBorder}; padding:10px 14px; border-radius:${borderRadius}; color:var(--text-primary); text-align:left; white-space:pre-wrap;">
              ${escHtml(formatSpeechText(turn.text))}
            </div>
          </div>
        `;
      }).join('');
    }
    
    timelineHTML += `
        </div>
      </div>
    `;
    
    viewerContainer.innerHTML = timelineHTML;
    
    viewerContainer.querySelectorAll('.timeline-node').forEach(node => {
      node.onclick = () => {
        openPdfWithHighlight(m.filename, parseInt(node.dataset.page), node.dataset.text, node.dataset.speaker);
      };
    });
  };

  const speakerItems = speakersContainer.querySelectorAll('.modal-speaker-item');
  speakerItems.forEach(item => {
    // 체크박스 변경 이벤트 바인딩
    const checkbox = item.querySelector('.speaker-checkbox');
    if (checkbox) {
      checkbox.onchange = (e) => {
        e.stopPropagation();
        item.click();
      };
    }

    item.onclick = (e) => {
      // 비활성화된 항목 클릭 차단
      if (item.classList.contains('disabled')) {
        return;
      }
      
      const spkName = item.dataset.speakerName;
      
      if (STATE.selectedSpeakers.includes(spkName)) {
        STATE.selectedSpeakers = STATE.selectedSpeakers.filter(name => name !== spkName);
      } else {
        STATE.selectedSpeakers.push(spkName);
      }
      
      updateSpeakerSidebar();
      
      // 타임라인 렌더링 분기
      if (STATE.selectedSpeakers.length === 0) {
        backBtn.classList.add('hidden');
        viewerContainer.innerHTML = originalViewerHTML;
        speakerItems.forEach(s => s.classList.remove('active-highlight'));
      } else if (STATE.selectedSpeakers.length === 1) {
        speakerItems.forEach(s => {
          const name = s.dataset.speakerName;
          s.classList.toggle('active-highlight', name === STATE.selectedSpeakers[0]);
        });
        renderSingleSpeakerTimeline(STATE.selectedSpeakers[0]);
      } else {
        speakerItems.forEach(s => {
          const name = s.dataset.speakerName;
          s.classList.toggle('active-highlight', STATE.selectedSpeakers.includes(name));
        });
        renderMultiSpeakerTimeline(STATE.selectedSpeakers);
      }
    };
  });

  const renderKeywordSearchResults = (query) => {
    backBtn.classList.remove('hidden');
    
    // 날짜 검색 입력 시 모달을 닫고 메인 키워드 탐색기 탭으로 점프 연동
    const dateQuery = query.replace(/\./g, '-').replace(/\s+/g, '');
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (dateRegex.test(dateQuery)) {
      closeModal();
      switchTab('keywords');
      searchKeyword(dateQuery);
      return;
    }

    const searchResults = [];
    const highlightKeyword = (txt, keywordsList) => {
      let highlighted = escHtml(txt);
      keywordsList.forEach(kw => {
        const regex = new RegExp(`(${kw})`, 'gi');
        highlighted = highlighted.replace(regex, '<mark class="search-highlight" style="background:#eab308; color:#000; font-weight:bold; border-radius:2px; padding:0 2px;">$1</mark>');
      });
      return highlighted;
    };
    
    let highlightKws = [];
    
    if (query.includes('&')) {
      // 의원 & 키워드 혼합 검색
      const parts = query.split('&').map(p => p.trim());
      const speakerName = parts[0];
      const keywordGroups = parts.slice(1).map(g => 
        g.split(',').map(k => {
          let clean = k.trim().toLowerCase();
          clean = clean.replace(/\s*(통과|합의|반대|규제|진흥|개정|제정|폐지|상정|의결|처리|논의|보고|제출|검토|법안|개정안|법|의안)\s*$/, '').trim();
          return clean;
        }).filter(Boolean)
      ).filter(arr => arr.length > 0);
      
      keywordGroups.forEach(g => highlightKws.push(...g));
      
      m.speakers.forEach(spk => {
        const cleanName = spk.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        if (cleanName.includes(speakerName) || speakerName.includes(cleanName)) {
          if (spk.lines && spk.lines.length > 0) {
            const mergedTurns = getSpeakerMergedTurns(spk.lines, spk.name);
            mergedTurns.forEach(turn => {
              const matchesAllGroups = keywordGroups.every(group => 
                group.some(kw => turn.text.toLowerCase().includes(kw))
              );
              if (matchesAllGroups) {
                searchResults.push({
                  name: turn.name,
                  text: turn.text,
                  page: turn.page,
                  lineIdx: turn.lineIdxs[0]
                });
              }
            });
          }
        }
      });
    } else {
      // 키워드 OR 콤마 나열 검색 또는 단일 검색
      const orKws = query.split(',').map(k => {
        let clean = k.trim().toLowerCase();
        clean = clean.replace(/\s*(통과|합의|반대|규제|진흥|개정|제정|폐지|상정|의결|처리|논의|보고|제출|검토|법안|개정안|법|의안)\s*$/, '').trim();
        return clean;
      }).filter(Boolean);
      highlightKws = orKws;
      
      m.speakers.forEach(spk => {
        if (!spk.lines) return;
        const mergedTurns = getSpeakerMergedTurns(spk.lines, spk.name);
        mergedTurns.forEach(turn => {
          const matchedKw = orKws.find(kw => turn.text.toLowerCase().includes(kw));
          if (matchedKw) {
            searchResults.push({
              name: turn.name,
              text: turn.text,
              page: turn.page,
              lineIdx: turn.lineIdxs[0]
            });
          }
        });
      });
      
      // 요약 보고서 발췌
      if (searchResults.length === 0) {
        lines.forEach((line, idx) => {
          const matchedKw = orKws.find(kw => line.toLowerCase().includes(kw));
          if (matchedKw && !line.startsWith('1. ') && !line.startsWith('2. ') && !line.startsWith('▲')) {
            searchResults.push({
              name: "요약 보고서 발췌",
              text: line.replace(/^[ㅇ\-\※]\s*/, ''),
              page: 1,
              lineIdx: idx
            });
          }
        });
      }
    }

    viewerContainer.innerHTML = `
      <div class="viewer-section" style="border-left: 4px solid var(--accent-amber);">
        <div class="viewer-section-header" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="viewer-icon">🏷️</span>
            <span class="viewer-title" style="font-size: 15px;">#${escHtml(query)} 관련 본문 대사 실시간 발췌 (${searchResults.length}건)</span>
          </div>
          <button id="btn-modal-kw-download" class="kw-compare-btn" style="font-size:11px; padding:4px 10px; background:rgba(245,158,11,0.2); border:1px solid rgba(245,158,11,0.4); border-radius:4px; color:#fcd34d; cursor:pointer;">📥 발췌 기록 다운로드 (.txt)</button>
        </div>
        <div class="timeline-wrap">
          ${searchResults.length > 0 
            ? (() => {
                const mergedResults = mergeConsecutiveTimelineItems(searchResults);
                return mergedResults.map(res => {
                  const role = getSpeakerRole(res.name);
                  return `
                  <div class="timeline-node" data-filename="${escHtml(m.filename)}" data-page="${res.page}" data-text="${escHtml(res.text)}" data-speaker="${escHtml(res.name)}" style="cursor:pointer;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                    <div class="timeline-sender-row" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                      <span class="timeline-sender" style="font-weight:700; color:var(--accent-cyan); font-size:12.5px;">👤 ${escHtml(res.name)}</span>
                      <span style="font-weight:700; color:#22d3ee; font-size:11.5px; margin-left:auto;">📄 PDF ${res.page}페이지 🔗</span>
                    </div>
                    <div class="timeline-bubble" style="font-size:13.5px; line-height:1.7; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">${highlightKeyword(formatSpeechText(res.text), highlightKws)}</div>
                  </div>`;
                }).join('');
              })()
            : `<div class="no-results">
                 <p>발췌된 발언이 없습니다. 다른 키워드를 입력 또는 선택해 주세요.</p>
               </div>`
          }
        </div>
      </div>
    `;

    // 발언 노드 클릭 시 PDF 페이지 새 창 열기 바인딩 (클립보드 복사 및 토스트 연계)
    viewerContainer.querySelectorAll('.timeline-node').forEach(node => {
      node.onclick = (e) => {
        e.stopPropagation();
        const filename = node.dataset.filename;
        const page = parseInt(node.dataset.page);
        const text = node.dataset.text;
        const speaker = node.dataset.speaker || '';
        openPdfWithHighlight(filename, page, text, speaker);
      };
    });

    // 본 회의 키워드 발췌 기록 다운로드 바인딩
    const downloadBtn = document.getElementById('btn-modal-kw-download');
    if (downloadBtn && searchResults.length > 0) {
      downloadBtn.onclick = () => {
        let txtContent = `[#${query} 키워드 본 회의 발췌 기록 - ${m.date} ${cleanTitle}]\n`;
        txtContent += `발생 건수: ${searchResults.length}건\n`;
        txtContent += `==================================================\n\n`;
        searchResults.forEach((res, idx) => {
          txtContent += `[#${idx + 1}] 발언자: ${res.name} (PDF ${res.page}p)\n`;
          txtContent += ` - 내용: ${res.text.trim()}\n\n`;
        });

        const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `${query}_본회의발췌_${m.date}.txt`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      };
    }

    viewerContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // 10. 인터랙티브 연동 - 키워드 태그 클릭 -> 키워드 본문 발췌 렌더링 전환!
  const sidebarTagPills = keywordsContainer.querySelectorAll('.keyword-tag-pill');
  sidebarTagPills.forEach(pill => {
    pill.onclick = () => {
      sidebarTagPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const keyword = pill.dataset.keywordName;
      renderKeywordSearchResults(keyword);
    };
  });

  // 11. 모달 키워드 실시간 검색창 바인딩
  const modalKwInput = document.getElementById('modal-kw-search-input');
  modalKwInput.value = ''; // 초기화
  modalKwInput.onkeydown = (e) => {
    if (e.key === 'Enter') {
      const val = modalKwInput.value.trim();
      if (val) {
        // 알약 active 표시 모두 초기화
        sidebarTagPills.forEach(p => p.classList.remove('active'));
        renderKeywordSearchResults(val);
      }
    }
  };

    overlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  } catch (err) {
    alert("openModal 에러 감지!\n메시지: " + err.message + "\n스택: " + err.stack);
    console.error("openModal 런타임 오류 발생:", err);
    let errDiv = document.getElementById('debug-error-panel');
    if (!errDiv) {
      errDiv = document.createElement('div');
      errDiv.id = 'debug-error-panel';
      errDiv.style = 'position:fixed; top:20px; left:50%; transform:translateX(-50%); width:90%; max-width:600px; background:#ef4444; color:#fff; padding:18px; border-radius:8px; z-index:99999; box-shadow:0 10px 25px rgba(0,0,0,0.5); font-family:monospace; font-size:12px; line-height:1.5; white-space:pre-wrap;';
      document.body.appendChild(errDiv);
    }
    errDiv.innerHTML = `
      <div style="font-weight:bold; font-size:14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
        ⚠️ 대시보드 런타임 에러 감지 (openModal)
        <span style="cursor:pointer; font-size:18px;" onclick="this.parentElement.remove()">×</span>
      </div>
      <div><strong>에러명:</strong> \${err.name}: \${err.message}</div>
      <div style="margin-top:8px; background:rgba(0,0,0,0.2); padding:10px; border-radius:4px; max-height:200px; overflow-y:auto; font-size:11px;">\${err.stack}</div>
      <div style="margin-top:8px; text-align:right; font-size:10px; opacity:0.8;">※ 이 메시지를 복사해서 개발자에게 알려주세요.</div>
    `;
  }
}

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('modal-overlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  document.body.style.overflow = '';
}

// ============================================================
// 3단계: 발언자 분석 & 전체 발언자 요약 차트
// ============================================================
function initSpeakerTab() {
  const meetings = STATE.db.meetings;
  const sel = document.getElementById('speaker-meeting-select');

  // 통합 검색창 바인딩
  const speakerSearch = document.getElementById('speaker-integrated-search');
  speakerSearch.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = speakerSearch.value.trim();
      searchSpeakerTab(val);
    }
  });

  speakerSearch.addEventListener('input', () => {
    if (speakerSearch.value.trim() === '') {
      searchSpeakerTab('');
    }
  });

  // 회의 목록 정합성을 유지하여 셀렉트 박스 구축
  sel.innerHTML = '<option value="">— 분석할 회의록 선택 —</option>';
  const meetingOptions = meetings
    .map((m, i) => ({ meeting: m, originalIndex: i }))
    .filter(item => item.meeting.speakers?.length);

  // 날짜 최신순 정렬 (내림차순)
  meetingOptions.sort((a, b) => {
    const dateA = a.meeting.date || '';
    const dateB = b.meeting.date || '';
    return dateB.localeCompare(dateA);
  });

  meetingOptions.forEach(item => {
    const m = item.meeting;
    const opt = document.createElement('option');
    opt.value = item.originalIndex;
    let label = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
    label = label.replace(/^제22대국회\s+/, '');
    opt.textContent = `[${m.date || '?'}] ${label.substring(0, 42)}...`;
    sel.appendChild(opt);
  });

  sel.addEventListener('change', () => {
    const idx = sel.value;
    if (idx === '') {
      document.getElementById('speaker-list').innerHTML = '<div style="color:var(--text-tertiary); padding:16px; font-size:13px;">회의를 선택하면 상세 발언 의원 목록이 표시됩니다.</div>';
      renderSpeakersOverview(null); // 전체 통계 차트로 복원
      return;
    }
    const selectedMeeting = meetings[parseInt(idx)];
    renderSpeakersForMeeting(selectedMeeting);
    renderSpeakersOverview(selectedMeeting); // 선택된 회의록의 발언 통계 차트로 갱신
  });
}

function renderSpeakersForMeeting(meeting) {
  const speakers = meeting.speakers || [];
  const listEl = document.getElementById('speaker-list');
  
  const totalSpeeches = speakers.reduce((acc, c) => acc + c.speech_count, 0) || 1;

  listEl.innerHTML = speakers.map((s, i) => {
    const ratio = Math.round((s.speech_count / totalSpeeches) * 100);
    return `
      <div class="speaker-item" data-idx="${i}" id="spk-item-${i}">
        <div class="speaker-avatar">${s.name.charAt(0)}</div>
        <div class="speaker-info">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="speaker-name">${escHtml(s.name)}</span>
            <span style="font-size:11px; color:var(--text-accent); font-weight:500;">${ratio}%</span>
          </div>
          <div class="speaker-bar-wrap">
            <div class="speaker-bar">
              <div class="speaker-bar-fill" style="width: ${ratio}%"></div>
            </div>
          </div>
          <div class="speaker-count" style="font-size:10px;">누적 발언: ${s.speech_count}회</div>
        </div>
      </div>
    `;
  }).join('');

  listEl.querySelectorAll('.speaker-item').forEach(el => {
    el.addEventListener('click', () => {
      listEl.querySelectorAll('.speaker-item').forEach(e => e.classList.remove('active'));
      el.classList.add('active');
      renderSpeakerDetail(speakers[parseInt(el.dataset.idx)]);
    });
  });

  if (speakers.length > 0) {
    listEl.querySelector('.speaker-item')?.click();
  }
}

function renderSpeakerDetail(speaker) {
  const kws = (speaker.keywords || []).slice(0, 10);
  const labels = kws.map(k => k.word);
  const data = kws.map(k => k.count);

  const ctx = document.getElementById('speaker-keyword-chart').getContext('2d');
  if (STATE.speakerChartInstance) STATE.speakerChartInstance.destroy();

  const isLight = document.body.classList.contains('light-mode');
  const textColor = isLight ? '#0f172a' : '#f1f5f9';

  STATE.speakerChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '주요 발언 횟수',
        data,
        backgroundColor: labels.map((_, i) => `hsla(${230 + i * 14}, 75%, 62%, 0.75)`),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { 
          grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)' }, 
          ticks: { color: textColor } 
        },
        y: { 
          grid: { display: false }, 
          ticks: { color: textColor, font: { weight: '600' } } 
        },
      }
    }
  });

  // 하단 태그 클라우드
  const cloud = document.getElementById('speaker-tag-cloud');
  cloud.innerHTML = (speaker.keywords || []).map(k => `
    <span class="tag-cloud-item" style="font-size: ${Math.min(15, 11 + k.count * 0.4)}px" onclick="switchTab('keywords'); searchKeyword('${escHtml(k.word)}');">
      ${escHtml(k.word)}
    </span>
  `).join('');
}

/**
 * 과방위 전체 회의록 기준 누적 최다 발언 국회의원 분석 (선택된 회의록이 있으면 해당 회의록 분석)
 */
function renderSpeakersOverview(selectedMeeting = null) {
  const speakerMap = {};
  const headerEl = document.getElementById('speakers-overview-header');
  
  if (selectedMeeting) {
    // 특정 회의록이 선택되었을 때
    (selectedMeeting.speakers || []).forEach(s => {
      const name = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
      speakerMap[name] = (speakerMap[name] || 0) + s.speech_count;
    });
    
    if (headerEl) {
      let label = selectedMeeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
      label = label.replace(/^제22대국회\s+/, '');
      headerEl.textContent = `[${selectedMeeting.date || '?'}] ${label.substring(0, 32)}... 발언 빈도 TOP 20`;
    }
  } else {
    // 전체 누적 발언자 분석
    STATE.db.meetings.forEach(m => {
      (m.speakers || []).forEach(s => {
        // 국회 직책 접두사 정규화
        const name = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        speakerMap[name] = (speakerMap[name] || 0) + s.speech_count;
      });
    });
    
    if (headerEl) {
      headerEl.textContent = "과방위 전체 발언 빈도 TOP 20";
    }
  }

  const sorted = Object.entries(speakerMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20);

  const ctx = document.getElementById('speakers-bar-chart').getContext('2d');
  if (STATE.speakersBarChartInstance) STATE.speakersBarChartInstance.destroy();

  const isLight = document.body.classList.contains('light-mode');
  const textColor = isLight ? '#0f172a' : '#f1f5f9';

  STATE.speakersBarChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: sorted.map(([n]) => n),
      datasets: [{
        label: '발언 수',
        data: sorted.map(([, c]) => c),
        backgroundColor: 'rgba(99,102,241,0.7)',
        hoverBackgroundColor: 'rgba(139,92,246,0.88)',
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { 
          grid: { display: false }, 
          ticks: { color: textColor, font: { size: 11, weight: '600' } } 
        },
        y: { 
          grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)' }, 
          ticks: { color: textColor } 
        },
      }
    }
  });
}

// ============================================================
// 발언자 분석 탭 내 통합 검색 및 연동 결과 리스트
// ============================================================
function searchSpeakerTab(query) {
  const searchResultsEl = document.getElementById('speaker-search-results');
  const overviewHeaderEl = document.getElementById('speakers-overview-header');
  const overviewChartWrapEl = document.getElementById('speakers-overview-chart-wrap');

  if (!query) {
    // 검색어가 비어있을 때: 차트 복원
    searchResultsEl.style.display = 'none';
    searchResultsEl.innerHTML = '';
    if (overviewHeaderEl) overviewHeaderEl.style.display = '';
    if (overviewChartWrapEl) overviewChartWrapEl.style.display = '';
    return;
  }

  // 검색어가 있을 때: 차트 숨기기 및 결과 표시
  if (overviewHeaderEl) overviewHeaderEl.style.display = 'none';
  if (overviewChartWrapEl) overviewChartWrapEl.style.display = 'none';
  searchResultsEl.style.display = 'block';

  const keyword = query.trim();

  // 2-1. 날짜 검색
  const dateQuery = keyword.replace(/\./g, '-').replace(/\s+/g, '');
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;

  if (dateRegex.test(dateQuery)) {
    const matchedMeetings = STATE.db.meetings.filter(m => m.date === dateQuery);
    if (matchedMeetings.length === 0) {
      searchResultsEl.innerHTML = `
        <div class="no-results" style="padding:20px;">
          <p>📅 '${dateQuery}' 일자의 회의록을 찾을 수 없습니다.</p>
        </div>`;
      return;
    }

    searchResultsEl.innerHTML = `
      <div style="font-size:15px; font-weight:700; color:var(--accent-cyan); margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:8px;">
        📅 ${dateQuery} 회의록 검색 결과 (총 ${matchedMeetings.length}건)
      </div>
      ${matchedMeetings.map(m => {
        let cleanTitle = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
        cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

        const agendaCount = m.agendas?.length || 0;
        const agendaListHTML = m.agendas?.length 
          ? `<div class="speech-result-agendas" style="margin-top:8px; font-size:13px; color:var(--text-secondary);">
               <strong style="color:var(--accent-cyan); font-size:13.5px;">📋 상정 안건 (총 ${agendaCount}건):</strong>
               ${m.agendas.map((a, i) => `<div style="margin-left:8px; margin-top:3px; color:var(--text-primary); font-weight:500;">${i+1}. ${escHtml(a.title)}</div>`).join('')}
             </div>`
          : '<div style="margin-top:8px; font-size:12px; opacity:0.7;">의사 안건 정보 없음</div>';

        return `
          <div class="kw-result-item-full" data-idx="${STATE.db.meetings.indexOf(m)}" style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:8px; padding:16px; margin-bottom:12px; cursor:pointer; transition:all 0.2s;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:6px;">
              <span class="kw-result-title" style="font-weight:700; font-size:15px; color:var(--accent-cyan);">${escHtml(cleanTitle)}</span>
              <span class="card-badge badge-${m.meeting_type}" style="margin-left:auto;">${escHtml(m.meeting_type)}</span>
            </div>
            ${agendaListHTML}
            <div style="margin-top:12px; text-align:right; font-size:11.5px; color:var(--accent-cyan); font-weight:600;">상세 회의록 분석 모달 열기 ➔</div>
          </div>
        `;
      }).join('')}
    `;

    searchResultsEl.querySelectorAll('.kw-result-item-full').forEach(el => {
      el.onclick = () => openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
    });
    return;
  }

  // 2-2. 혼합 검색 (&)
  if (keyword.includes('&')) {
    const parts = keyword.split('&').map(p => p.trim());
    const speakerName = parts[0];
    const keywordGroups = parts.slice(1).map(g => 
      g.split(',').map(k => {
        let clean = k.trim().toLowerCase();
        clean = clean.replace(/\s*(통과|합의|반대|규제|진흥|개정|제정|폐지|상정|의결|처리|논의|보고|제출|검토|법안|개정안|법|의안)\s*$/, '').trim();
        return clean;
      }).filter(Boolean)
    ).filter(arr => arr.length > 0);

    const speechMatches = [];
    STATE.db.meetings.forEach(m => {
      (m.speakers || []).forEach(s => {
        const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        if (cleanName.includes(speakerName) || speakerName.includes(cleanName)) {
          if (s.lines && s.lines.length > 0) {
            const mergedTurns = getSpeakerMergedTurns(s.lines, s.name);
            mergedTurns.forEach(turn => {
              const matchesAllGroups = keywordGroups.every(group => 
                group.some(kw => turn.text.toLowerCase().includes(kw))
              );
              if (matchesAllGroups) {
                speechMatches.push({
                  meeting: m,
                  speaker: turn.name,
                  text: turn.text,
                  page: turn.page,
                  line: { text: turn.text, page: turn.page },
                  lineIdx: turn.lineIdxs[0]
                });
              }
            });
          }
        }
      });
    });

    const displayKeywordStr = keywordGroups.map(g => g.join(', ')).join(' & ');

    if (speechMatches.length === 0) {
      searchResultsEl.innerHTML = `<div class="no-results" style="padding:20px"><p>'${speakerName}' 의원의 '${displayKeywordStr}' 관련 발언 기록을 찾을 수 없습니다.</p></div>`;
      return;
    }

    const groups = [];
    speechMatches.forEach(match => {
      let group = groups.find(g => g.meeting === match.meeting);
      if (!group) {
        group = { meeting: match.meeting, items: [] };
        groups.push(group);
      }
      group.items.push(match);
    });

    searchResultsEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:8px;">
        <span style="font-size:15px; font-weight:700; color:var(--accent-cyan);">🔍 "${speakerName}"의 "${displayKeywordStr}" 관련 정밀 검색 (${speechMatches.length}건)</span>
        <button id="btn-download-speech-report-speaker" class="kw-compare-btn" style="font-size:12px; padding:6px 12px; background:rgba(99,102,241,0.2); border:1px solid rgba(99,102,241,0.4); border-radius:6px; color:#a5b4fc; font-weight:600; cursor:pointer;">📄 발언 기록 보고서 다운로드 (.txt)</button>
      </div>
      <div class="speech-timeline-list">
        ${groups.map(group => {
          let cleanTitle = group.meeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
          cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

          return `
            <div class="meeting-group-card" style="background:rgba(255,255,255,0.035); border:1px solid var(--border-color); border-radius:12px; padding:18px; margin-bottom:16px;">
              <div class="meeting-group-header" data-idx="${STATE.db.meetings.indexOf(group.meeting)}" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px; margin-bottom:12px; cursor:pointer;" title="클릭 시 회의록 상세 분석 모달 열기">
                <span style="font-weight:700; font-size:16.5px; color:var(--accent-cyan);">${escHtml(cleanTitle)}</span>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:13px; color:#cbd5e1; font-weight:600;">📅 ${group.meeting.date}</span>
                  <span class="card-badge badge-${group.meeting.meeting_type}" style="font-size:10px;">${escHtml(group.meeting.meeting_type)}</span>
                </div>
              </div>
              <div style="display:flex; flex-direction:column; gap:12px;">
                ${(() => {
                  const mergedItems = mergeConsecutiveTimelineItems(group.items);
                  return mergedItems.map(seg => {
                    let highlightedLine = escHtml(formatSpeechText(seg.text));
                    keywordGroups.forEach(grp => {
                      grp.forEach(kw => {
                        const regex = new RegExp(`(${kw})`, 'gi');
                        highlightedLine = highlightedLine.replace(regex, '<mark class="search-highlight" style="background:#eab308; color:#000; font-weight:bold; border-radius:2px; padding:0 2px;">$1</mark>');
                      });
                    });
                    return `
                      <div class="speech-timeline-node accent-indigo" data-page="${seg.page}" data-filename="${escHtml(group.meeting.filename)}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(seg.speaker)}" style="cursor:pointer;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary); margin-bottom:4px;">
                          <span style="font-weight:700; color:var(--accent-cyan); font-size:13.5px;">👤 ${escHtml(seg.speaker)}</span>
                          <span style="font-weight:700; color:#22d3ee; font-size:12.5px;">📄 PDF ${seg.page}페이지 🔗</span>
                        </div>
                        <div class="timeline-bubble" style="font-size:14.5px; line-height:1.75; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">${highlightedLine}</div>
                      </div>
                    `;
                  }).join('');
                })()}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    document.getElementById('btn-download-speech-report-speaker').onclick = () => {
      let txtContent = `[${speakerName} 의원 '${displayKeywordStr}' 관련 국회 발언 전체 보고서]\n`;
      txtContent += `발생 건수: ${speechMatches.length}건\n`;
      txtContent += `보고서 작성 기준: 제22대 국회 과학기술정보방송통신위원회 회의록\n`;
      txtContent += `==================================================\n\n`;
      speechMatches.forEach((match, idx) => {
        txtContent += `[#${idx + 1}] 날짜: ${match.meeting.date} | 회의명: ${match.meeting.filename.replace(/\.pdf$/i, '')} | PDF: ${match.line.page}p\n`;
        txtContent += ` - 발언자: ${match.speaker}\n`;
        txtContent += ` - 발언 원문: ${match.line.text.trim()}\n\n`;
      });
      const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `${speakerName}_발언보고서_${displayKeywordStr.replace(/\s*&\s*/g, '_')}.txt`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    };

    searchResultsEl.querySelectorAll('.speech-timeline-node').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        const page = parseInt(el.dataset.page);
        const filename = el.dataset.filename;
        const text = el.dataset.text || '';
        const speaker = el.dataset.speaker || '';
        openPdfWithHighlight(filename, page, text, speaker);
      };
    });

    searchResultsEl.querySelectorAll('.meeting-group-header').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
      };
    });
    return;
  }

  // 2-3. 의원 이름 검색
  const nameRegex = /^[가-힣]{2,4}$/;
  let isRealSpeaker = false;
  if (nameRegex.test(keyword)) {
    isRealSpeaker = STATE.db.meetings.some(m => 
      (m.speakers || []).some(s => {
        const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        return cleanName === keyword;
      })
    );
  }

  if (nameRegex.test(keyword) && isRealSpeaker) {
    const speechMatches = [];
    STATE.db.meetings.forEach(m => {
      (m.speakers || []).forEach(s => {
        const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        if (cleanName === keyword) {
          if (s.lines && s.lines.length > 0) {
            const mergedTurns = getSpeakerMergedTurns(s.lines, s.name);
            mergedTurns.forEach(turn => {
              speechMatches.push({
                meeting: m,
                speaker: turn.name,
                text: turn.text,
                page: turn.page,
                line: { text: turn.text, page: turn.page },
                lineIdx: turn.lineIdxs[0]
              });
            });
          }
        }
      });
    });

    if (speechMatches.length === 0) {
      searchResultsEl.innerHTML = `<div class="no-results" style="padding:20px"><p>'${keyword}' 의원의 발언 기록이 없습니다.</p></div>`;
      return;
    }

    const displayMatches = speechMatches.slice(0, 30);
    const groups = [];
    displayMatches.forEach(match => {
      let group = groups.find(g => g.meeting === match.meeting);
      if (!group) {
        group = { meeting: match.meeting, items: [] };
        groups.push(group);
      }
      group.items.push(match);
    });

    searchResultsEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:8px;">
        <span style="font-size:15px; font-weight:700; color:var(--accent-cyan);">👤 "${keyword}" 의원 발언 내역 검색 (총 ${speechMatches.length}건)</span>
        <button id="btn-download-speaker-all-speaker" class="kw-compare-btn" style="font-size:12px; padding:6px 12px; background:rgba(16,185,129,0.2); border:1px solid rgba(16,185,129,0.4); border-radius:6px; color:#6ee7b7; font-weight:600; cursor:pointer;">📥 전체 발언 원문 파일 정리 (.txt)</button>
      </div>
      <div class="speech-timeline-list">
        ${groups.map(group => {
          let cleanTitle = group.meeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
          cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

          return `
            <div class="meeting-group-card" style="background:rgba(255,255,255,0.035); border:1px solid var(--border-color); border-radius:12px; padding:18px; margin-bottom:16px;">
              <div class="meeting-group-header" data-idx="${STATE.db.meetings.indexOf(group.meeting)}" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px; margin-bottom:12px; cursor:pointer;" title="클릭 시 회의록 상세 분석 모달 열기">
                <span style="font-weight:700; font-size:16px; color:var(--accent-cyan);">${escHtml(cleanTitle)}</span>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:13px; color:#cbd5e1; font-weight:600;">📅 ${group.meeting.date}</span>
                  <span class="card-badge badge-${group.meeting.meeting_type}" style="font-size:10px;">${escHtml(group.meeting.meeting_type)}</span>
                </div>
              </div>
              <div style="display:flex; flex-direction:column; gap:12px;">
                ${(() => {
                  const mergedItems = mergeConsecutiveTimelineItems(group.items);
                  return mergedItems.map(seg => {
                    return `
                      <div class="speech-timeline-node" data-page="${seg.page}" data-filename="${escHtml(group.meeting.filename)}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(seg.speaker)}" style="background:rgba(255,255,255,0.02); border-left: 3px solid var(--accent-cyan); border-radius:0 8px 8px 0; padding:12px 16px; cursor:pointer; transition:all 0.2s;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary); margin-bottom:4px;">
                          <span style="font-weight:700; color:var(--accent-cyan); font-size:13.5px;">👤 ${escHtml(seg.speaker)}</span>
                          <span style="font-weight:700; color:#22d3ee; font-size:12.5px;">📄 PDF ${seg.page}페이지 🔗</span>
                        </div>
                        <div class="timeline-bubble" style="font-size:14.5px; line-height:1.75; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">
                          ${escHtml(formatSpeechText(seg.text))}
                        </div>
                      </div>
                    `;
                  }).join('');
                })()}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    document.getElementById('btn-download-speaker-all-speaker').onclick = () => {
      let txtContent = `👤 [${keyword} 의원 국회 전체 발언 원문 리포트]\n`;
      txtContent += `총 발언 수: ${speechMatches.length}건\n`;
      txtContent += `==================================================\n\n`;
      speechMatches.forEach((match, idx) => {
        txtContent += `■ [${match.meeting.date}] ${match.meeting.filename.replace(/\.pdf$/i, '')} | PDF: ${match.line.page}p\n`;
        txtContent += ` - ${match.line.text.trim()}\n\n`;
      });
      const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `${keyword}_전체발언_리포트.txt`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    };

    searchResultsEl.querySelectorAll('.speech-timeline-node').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        const page = parseInt(el.dataset.page);
        const filename = el.dataset.filename;
        const text = el.dataset.text || '';
        const speaker = el.dataset.speaker || '';
        openPdfWithHighlight(filename, page, text, speaker);
      };
    });

    searchResultsEl.querySelectorAll('.meeting-group-header').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
      };
    });
    return;
  }

  // 2-4. 일반 키워드 OR 검색
  const orKws = keyword.split(',').map(k => {
    let clean = k.trim().toLowerCase();
    clean = clean.replace(/\s*(통과|합의|반대|규제|진흥|개정|제정|폐지|상정|의결|처리|논의|보고|제출|검토|법안|개정안|법|의안)\s*$/, '').trim();
    return clean;
  }).filter(Boolean);

  const matchedSpeeches = [];
  STATE.db.meetings.forEach(m => {
    (m.speakers || []).forEach(s => {
      if (s.lines && s.lines.length > 0) {
        const mergedTurns = getSpeakerMergedTurns(s.lines, s.name);
        mergedTurns.forEach(turn => {
          const matchedKw = orKws.find(kw => turn.text.toLowerCase().includes(kw));
          if (matchedKw) {
            matchedSpeeches.push({
              meeting: m,
              speaker: turn.name,
              text: turn.text,
              page: turn.page,
              line: { text: turn.text, page: turn.page },
              lineIdx: turn.lineIdxs[0],
              matchedKw: matchedKw
            });
          }
        });
      }
    });
  });

  if (matchedSpeeches.length === 0) {
    searchResultsEl.innerHTML = `<div class="no-results" style="padding:20px"><p>'${orKws.join(', ')}' 관련 발언 기록이 없습니다.</p></div>`;
    return;
  }

  const displayMatches = matchedSpeeches.slice(0, 30);
  const groups = [];
  displayMatches.forEach(match => {
    let group = groups.find(g => g.meeting === match.meeting);
    if (!group) {
      group = { meeting: match.meeting, items: [] };
      groups.push(group);
    }
    group.items.push(match);
  });

  searchResultsEl.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:8px;">
      <span style="font-size:15px; font-weight:700; color:var(--accent-amber);">🔍 "${orKws.join(', ')}" 관련 발언 실시간 검색 (${matchedSpeeches.length}건)</span>
      <button id="btn-download-kws-all-speaker" class="kw-compare-btn" style="font-size:12px; padding:6px 12px; background:rgba(245,158,11,0.2); border:1px solid rgba(245,158,11,0.4); border-radius:6px; color:#fcd34d; font-weight:600; cursor:pointer;">📥 전체 발언 원문 파일 다운로드 (.txt)</button>
    </div>
    <div class="speech-timeline-list">
      ${groups.map(group => {
        let cleanTitle = group.meeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
        cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

        return `
          <div class="meeting-group-card" style="background:rgba(255,255,255,0.035); border:1px solid var(--border-color); border-radius:12px; padding:18px; margin-bottom:16px;">
            <div class="meeting-group-header" data-idx="${STATE.db.meetings.indexOf(group.meeting)}" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px; margin-bottom:12px; cursor:pointer;" title="클릭 시 회의록 상세 분석 모달 열기">
              <span style="font-weight:700; font-size:16px; color:var(--accent-amber);">${escHtml(cleanTitle)}</span>
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:13px; color:#cbd5e1; font-weight:600;">📅 ${group.meeting.date}</span>
                <span class="card-badge badge-${group.meeting.meeting_type}" style="font-size:10px;">${escHtml(group.meeting.meeting_type)}</span>
              </div>
            </div>
            <div style="display:flex; flex-direction:column; gap:12px;">
              ${(() => {
                const mergedItems = mergeConsecutiveTimelineItems(group.items);
                return mergedItems.map(seg => {
                  let highlightedLine = escHtml(formatSpeechText(seg.text));
                  orKws.forEach(kw => {
                    const regex = new RegExp(`(${kw})`, 'gi');
                    highlightedLine = highlightedLine.replace(regex, '<mark class="search-highlight" style="background:#eab308; color:#000; font-weight:bold; border-radius:2px; padding:0 2px;">$1</mark>');
                  });
                  return `
                    <div class="speech-timeline-node" data-page="${seg.page}" data-filename="${escHtml(group.meeting.filename)}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(seg.speaker)}" style="background:rgba(255,255,255,0.02); border-left: 3px solid var(--accent-amber); border-radius:0 8px 8px 0; padding:12px 16px; cursor:pointer; transition:all 0.2s;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                      <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-accent); font-size:13.5px;">👤 ${escHtml(seg.speaker)}</span>
                        <span style="font-weight:700; color:#22d3ee; font-size:12.5px;">📄 PDF ${seg.page}페이지 🔗</span>
                      </div>
                      <div class="timeline-bubble" style="font-size:14.5px; line-height:1.75; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">${highlightedLine}</div>
                    </div>
                  `;
                }).join('');
              })()}
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;

  document.getElementById('btn-download-kws-all-speaker').onclick = () => {
    let txtContent = `🔍 ['${orKws.join(', ')}' 국회 발언 히스토리 전체 원문]\n`;
    txtContent += `총 발언 수: ${matchedSpeeches.length}건\n`;
    txtContent += `==================================================\n\n`;
    matchedSpeeches.forEach((match, idx) => {
      txtContent += `■ [${match.meeting.date}] ${match.meeting.filename.replace(/\.pdf$/i, '')} | PDF: ${match.line.page}p\n`;
      txtContent += ` - [${match.speaker}] ${match.line.text.trim()}\n\n`;
    });
    const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `키워드검색_${orKws.join('_')}.txt`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  searchResultsEl.querySelectorAll('.speech-timeline-node').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      const page = parseInt(el.dataset.page);
      const filename = el.dataset.filename;
      const text = el.dataset.text || '';
      const speaker = el.dataset.speaker || '';
      openPdfWithHighlight(filename, page, text, speaker);
    };
  });

  searchResultsEl.querySelectorAll('.meeting-group-header').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
    };
  });
}

// ============================================================
// 4단계: 키워드 탐색기 & 자동완성 & 다중 비교
// ============================================================
function initKeywordTab() {
  // 1. 키워드 실시간 자동완성 리스너 바인딩
  const input = document.getElementById('kw-search-input');
  const list = document.getElementById('kw-autocomplete-list');

  input.addEventListener('input', () => {
    const val = input.value.trim().toLowerCase();
    if (!val) {
      list.classList.add('hidden');
      return;
    }

    const matched = (STATE.db.global_keywords || [])
      .filter(k => k.word.toLowerCase().includes(val))
      .slice(0, 7);

    if (matched.length === 0) {
      list.classList.add('hidden');
      return;
    }

    list.innerHTML = matched.map(k => `
      <div class="kw-autocomplete-item" data-word="${escHtml(k.word)}">
        <span style="font-weight:600;">${escHtml(k.word)}</span>
        <span class="kw-autocomplete-count">${k.count}회 등장</span>
      </div>
    `).join('');

    list.classList.remove('hidden');
  });

  list.addEventListener('click', (e) => {
    const item = e.target.closest('.kw-autocomplete-item');
    if (item) {
      const word = item.dataset.word;
      input.value = word;
      list.classList.add('hidden');
      searchKeyword(word);
    }
  });

  // 드롭다운 바깥 클릭 시 닫기
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.kw-search-box')) {
      list.classList.add('hidden');
    }
  });

  // 2. 검색 트리거
  document.getElementById('kw-search-btn').addEventListener('click', () => {
    searchKeyword(input.value.trim());
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      searchKeyword(input.value.trim());
      list.classList.add('hidden');
    }
  });

  // 3. 다중 비교 모드 토글 버튼 바인딩
  const compBtn = document.getElementById('kw-compare-btn');
  compBtn.addEventListener('click', () => {
    STATE.compareMode = !STATE.compareMode;
    compBtn.classList.toggle('active', STATE.compareMode);
    
    if (STATE.compareMode) {
      compBtn.textContent = '키워드 다중 비교 모드 끄기';
      document.getElementById('kw-compare-bar').classList.remove('hidden');
      if (STATE.selectedKeyword && STATE.compareKeywords.length === 0) {
        STATE.compareKeywords.push(STATE.selectedKeyword);
        renderCompareTags();
      }
    } else {
      compBtn.textContent = '키워드 다중 비교 모드 켜기';
      document.getElementById('kw-compare-bar').classList.add('hidden');
      STATE.compareKeywords = [];
      renderCompareTags();
      if (STATE.selectedKeyword) {
        searchKeyword(STATE.selectedKeyword);
      }
    }
    updateHash();
  });

  // 초기화 버튼
  document.getElementById('compare-reset-btn').addEventListener('click', () => {
    STATE.compareKeywords = [];
    renderCompareTags();
    document.getElementById('kw-results-list').innerHTML = '<div class="no-results" style="padding:20px"><p>비교할 키워드를 좌측 구름이나 하단 인기 태그에서 2개 선택하세요.</p></div>';
    document.getElementById('kw-results-title').textContent = '키워드를 선택하세요';
    updateHash();
  });

  // 4. 컴팩트 클라우드 확대 모달 바인딩
  const expandBtn = document.getElementById('btn-expand-cloud');
  const overlay = document.getElementById('cloud-expand-overlay');
  const closeBtn = document.getElementById('cloud-modal-close');

  if (expandBtn && overlay && closeBtn) {
    expandBtn.addEventListener('click', () => {
      overlay.classList.remove('hidden');
      renderFullKeywordCloud();
    });

    closeBtn.addEventListener('click', () => {
      overlay.classList.add('hidden');
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.add('hidden');
      }
    });
  }
}

function renderCompareTags() {
  const container = document.getElementById('compare-tags-container');
  container.innerHTML = STATE.compareKeywords.map((kw, i) => `
    <span class="kw-compare-tag">
      <span>${escHtml(kw)}</span>
      <span class="kw-compare-remove" data-idx="${i}">×</span>
    </span>
  `).join('');

  // 삭제 버튼 리스너 바인딩
  container.querySelectorAll('.kw-compare-remove').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const idx = parseInt(el.dataset.idx);
      STATE.compareKeywords.splice(idx, 1);
      renderCompareTags();
      if (STATE.compareKeywords.length > 0) {
        searchKeywordCompare();
      } else {
        document.getElementById('kw-results-list').innerHTML = '<div class="no-results" style="padding:20px"><p>비교할 키워드를 선택하세요.</p></div>';
      }
      updateHash();
    });
  });
}

function renderKeywordCloud() {
  const cloud = document.getElementById('keyword-cloud');
  // 글로벌 키워드 중 상위 15개만 컴팩트하게 노출
  const keywords = (STATE.db.global_keywords || []).slice(0, 15);
  if (!keywords.length) return;

  const maxCount = keywords[0].count;
  const minCount = keywords[keywords.length - 1].count;
  const range = maxCount - minCount || 1;

  const palette = [
    { bg: 'rgba(99,102,241,0.12)', color: '#a5b4fc', border: 'rgba(99,102,241,0.25)' },
    { bg: 'rgba(16,185,129,0.12)', color: '#6ee7b7', border: 'rgba(16,185,129,0.25)' },
    { bg: 'rgba(245,158,11,0.12)', color: '#fcd34d', border: 'rgba(245,158,11,0.25)' },
    { bg: 'rgba(236,72,153,0.12)', color: '#f9a8d4', border: 'rgba(236,72,153,0.25)' },
    { bg: 'rgba(6,182,212,0.12)', color: '#67e8f9', border: 'rgba(6,182,212,0.25)' },
  ];

  cloud.innerHTML = keywords.map((kw, i) => {
    const ratio = (kw.count - minCount) / range;
    const fontSize = 11 + ratio * 8; // 컴팩트 뷰에 맞춤 (11px ~ 19px)
    const p = palette[i % palette.length];
    
    const isSelected = STATE.compareMode 
      ? STATE.compareKeywords.includes(kw.word)
      : STATE.selectedKeyword === kw.word;

    return `<span class="kw-cloud-item ${isSelected ? 'selected' : ''}" 
      data-kw="${escHtml(kw.word)}"
      style="font-size:${fontSize.toFixed(1)}px;background:${p.bg};color:${p.color};border:1px solid ${p.border}"
    >${escHtml(kw.word)}</span>`;
  }).join('');

  bindCloudItemsClick(cloud, false);
}

function renderFullKeywordCloud() {
  const cloud = document.getElementById('keyword-cloud-full');
  if (!cloud) return;
  // 상위 80개 전체 노출
  const keywords = (STATE.db.global_keywords || []).slice(0, 80);
  if (!keywords.length) return;

  const maxCount = keywords[0].count;
  const minCount = keywords[keywords.length - 1].count;
  const range = maxCount - minCount || 1;

  const palette = [
    { bg: 'rgba(99,102,241,0.12)', color: '#a5b4fc', border: 'rgba(99,102,241,0.25)' },
    { bg: 'rgba(16,185,129,0.12)', color: '#6ee7b7', border: 'rgba(16,185,129,0.25)' },
    { bg: 'rgba(245,158,11,0.12)', color: '#fcd34d', border: 'rgba(245,158,11,0.25)' },
    { bg: 'rgba(236,72,153,0.12)', color: '#f9a8d4', border: 'rgba(236,72,153,0.25)' },
    { bg: 'rgba(6,182,212,0.12)', color: '#67e8f9', border: 'rgba(6,182,212,0.25)' },
  ];

  cloud.innerHTML = keywords.map((kw, i) => {
    const ratio = (kw.count - minCount) / range;
    const fontSize = 12 + ratio * 20; // 풀 뷰에서는 크기를 시원하게 벌려줌 (12px ~ 32px)
    const p = palette[i % palette.length];
    
    const isSelected = STATE.compareMode 
      ? STATE.compareKeywords.includes(kw.word)
      : STATE.selectedKeyword === kw.word;

    return `<span class="kw-cloud-item ${isSelected ? 'selected' : ''}" 
      data-kw="${escHtml(kw.word)}"
      style="font-size:${fontSize.toFixed(1)}px;background:${p.bg};color:${p.color};border:1px solid ${p.border};margin:4px"
    >${escHtml(kw.word)}</span>`;
  }).join('');

  bindCloudItemsClick(cloud, true);
}

function bindCloudItemsClick(container, isModal = false) {
  container.querySelectorAll('.kw-cloud-item').forEach(el => {
    el.addEventListener('click', () => {
      const kw = el.dataset.kw;
      
      if (STATE.compareMode) {
        if (STATE.compareKeywords.includes(kw)) {
          STATE.compareKeywords = STATE.compareKeywords.filter(k => k !== kw);
        } else {
          if (STATE.compareKeywords.length >= 2) {
            STATE.compareKeywords.shift();
          }
          STATE.compareKeywords.push(kw);
        }
        renderCompareTags();
        searchKeywordCompare();
      } else {
        STATE.selectedKeyword = kw;
        searchKeyword(kw);
      }
      
      if (isModal) {
        const overlay = document.getElementById('cloud-expand-overlay');
        if (overlay) overlay.classList.add('hidden');
      }

      syncCloudSelection();
      updateHash();
    });
  });
}

function syncCloudSelection() {
  const syncContainer = (container) => {
    if (!container) return;
    container.querySelectorAll('.kw-cloud-item').forEach(e => {
      const isSel = STATE.compareMode 
        ? STATE.compareKeywords.includes(e.dataset.kw)
        : STATE.selectedKeyword === e.dataset.kw;
      e.classList.toggle('selected', isSel);
    });
  };
  syncContainer(document.getElementById('keyword-cloud'));
  syncContainer(document.getElementById('keyword-cloud-full'));
}

function renderPopularKeywordTags() {
  const tags = (STATE.db.global_keywords || []).slice(0, 16);
  const container = document.getElementById('kw-popular-tags');
  container.innerHTML = tags.map(k =>
    `<span class="kw-pop-tag" data-kw="${escHtml(k.word)}">#${escHtml(k.word)}</span>`
  ).join('');

  container.querySelectorAll('.kw-pop-tag').forEach(el => {
    el.addEventListener('click', () => {
      const kw = el.dataset.kw;
      if (STATE.compareMode) {
        if (!STATE.compareKeywords.includes(kw)) {
          if (STATE.compareKeywords.length >= 2) STATE.compareKeywords.shift();
          STATE.compareKeywords.push(kw);
          renderCompareTags();
          searchKeywordCompare();
        }
      } else {
        searchKeyword(kw);
      }
      updateHash();
    });
  });
}

/**
 * 단일 키워드 검색 및 관련 회의록 리스팅
 */
function searchKeyword(keyword, shouldUpdate = true) {
  if (!keyword) return;
  
  keyword = keyword.trim();
  STATE.selectedKeyword = keyword;
  document.getElementById('kw-search-input').value = keyword;

  const listEl = document.getElementById('kw-results-list');
  const titleEl = document.getElementById('kw-results-title');
  const backBtn = document.getElementById('btn-back-to-modal');

  // 모달 복원 버튼 제어
  if (backBtn) {
    if (STATE.lastOpenMeeting) {
      let cleanMeetingName = STATE.lastOpenMeeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '이전 회의록';
      cleanMeetingName = cleanMeetingName.replace(/^제22대국회\s+/, '');
      backBtn.textContent = `↩️ ${cleanMeetingName} 뷰어로 돌아가기`;
      backBtn.style.display = 'inline-block';
      backBtn.onclick = () => {
        switchTab('summary');
        openModal(STATE.lastOpenMeeting);
      };
    } else {
      backBtn.style.display = 'none';
    }
  }

  // 1. [날짜 검색] YYYY-MM-DD 또는 YYYY.MM.DD 또는 YYYYMMDD
  const dateQuery = keyword.replace(/\./g, '-').replace(/\s+/g, '');
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;

  if (dateRegex.test(dateQuery)) {
    const matchedMeetings = STATE.db.meetings.filter(m => m.date === dateQuery);
    if (matchedMeetings.length === 0) {
      // 날짜가 없을 때 최근 5개 날짜 제안
      const recentDates = [...new Set(STATE.db.meetings.map(m => m.date).filter(Boolean))]
        .sort((a, b) => b.localeCompare(a))
        .slice(0, 5);

      listEl.innerHTML = `
        <div class="no-results" style="padding:20px;">
          <p>📅 '${dateQuery}' 일자의 회의록을 찾을 수 없습니다.</p>
          <p style="font-size:12px; margin-top:8px; opacity:0.8;">최근 회의 일자 제안: ${recentDates.map(d => `<a href="javascript:void(0)" class="recent-date-link" style="color:var(--accent-cyan); text-decoration:underline; font-weight:bold; margin-right:8px;">${d}</a>`).join('')}</p>
        </div>`;

      listEl.querySelectorAll('.recent-date-link').forEach(el => {
        el.onclick = () => searchKeyword(el.textContent);
      });
      titleEl.textContent = `날짜 검색 결과 없음`;
      return;
    }

    titleEl.textContent = `📅 ${dateQuery} 회의록 검색 (총 ${matchedMeetings.length}건)`;
    listEl.innerHTML = matchedMeetings.map(m => {
      let cleanTitle = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
      cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

      // 안건 리스트 요약
      const agendaCount = m.agendas?.length || 0;
      const agendaListHTML = m.agendas?.length 
        ? `<div class="speech-result-agendas" style="margin-top:8px; font-size:13px; color:var(--text-secondary);">
             <strong style="color:var(--accent-cyan); font-size:13.5px;">📋 상정 안건 (총 ${agendaCount}건):</strong>
             ${m.agendas.map((a, i) => `<div style="margin-left:8px; margin-top:3px; color:var(--text-primary); font-weight:500;">${i+1}. ${escHtml(a.title)}</div>`).join('')}
           </div>`
        : '<div style="margin-top:8px; font-size:12px; opacity:0.7;">의사 안건 정보 없음</div>';

      // 주요 키워드
      const keywordsHTML = m.keywords?.length
        ? `<div class="speech-result-kws" style="margin-top:8px; font-size:12px; display:flex; flex-wrap:wrap; gap:6px;">
             <strong style="color:var(--accent-amber); margin-right:4px;">🔑 주요 키워드:</strong>
             ${m.keywords.slice(0, 5).map(k => `<span class="card-tag" style="padding:1px 6px; font-size:11px;">#${escHtml(k.word)}(${k.count})</span>`).join('')}
           </div>`
        : '';

      // 회의 주요 요약 내용
      let summaryHTML = '';
      if (m.summary) {
        const bulletPoints = m.summary.split('\n')
          .filter(line => line.trim().startsWith('ㅇ') || line.trim().startsWith('-') || line.trim().startsWith('※'))
          .slice(0, 3)
          .map(line => `<div style="margin-top:4px; line-height:1.5; color:var(--text-primary); font-weight:500;">${escHtml(line.trim())}</div>`)
          .join('');
        summaryHTML = bulletPoints 
          ? `<div class="speech-result-summary" style="margin-top:10px; padding-top:8px; border-top:1px dashed rgba(255,255,255,0.1); font-size:13px;">
               <strong style="color:var(--accent-3); font-size:13.5px;">💡 회의 내용 주요 요약:</strong>
               <div style="margin-left:6px; margin-top:4px; color:var(--text-secondary);">${bulletPoints}</div>
             </div>`
          : '';
      }

      return `
        <div class="kw-result-item-full" data-idx="${STATE.db.meetings.indexOf(m)}" style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:8px; padding:16px; margin-bottom:12px; cursor:pointer; transition:all 0.2s;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:6px;">
            <span class="kw-result-title" style="font-weight:700; font-size:15px; color:var(--accent-cyan);">${escHtml(cleanTitle)}</span>
            <span class="card-badge badge-${m.meeting_type}" style="margin-left:auto;">${escHtml(m.meeting_type)}</span>
          </div>
          ${agendaListHTML}
          ${keywordsHTML}
          ${summaryHTML}
          <div style="margin-top:12px; text-align:right; font-size:11.5px; color:var(--accent-cyan); font-weight:600;">상세 회의록 분석 모달 열기 ➔</div>
        </div>
      `;
    }).join('');

    listEl.querySelectorAll('.kw-result-item-full').forEach(el => {
      el.onclick = () => openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
    });

    if (shouldUpdate) updateHash();
    return;
  }

  // 2. [이름 & AND/OR 혼합 검색] : '&'가 포함된 경우
  if (keyword.includes('&')) {
    const parts = keyword.split('&').map(p => p.trim());
    const speakerName = parts[0];
    const keywordGroups = parts.slice(1).map(g => 
      g.split(',').map(k => {
        let clean = k.trim().toLowerCase();
        clean = clean.replace(/\s*(통과|합의|반대|규제|진흥|개정|제정|폐지|상정|의결|처리|논의|보고|제출|검토|법안|개정안|법|의안)\s*$/, '').trim();
        return clean;
      }).filter(Boolean)
    ).filter(arr => arr.length > 0);

    const speechMatches = [];

    STATE.db.meetings.forEach(m => {
      (m.speakers || []).forEach(s => {
        const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        if (cleanName.includes(speakerName) || speakerName.includes(cleanName)) {
          if (s.lines && s.lines.length > 0) {
            const mergedTurns = getSpeakerMergedTurns(s.lines, s.name);
            mergedTurns.forEach(turn => {
              const matchesAllGroups = keywordGroups.every(group => 
                group.some(kw => turn.text.toLowerCase().includes(kw))
              );

              if (matchesAllGroups) {
                speechMatches.push({
                  meeting: m,
                  speaker: turn.name,
                  text: turn.text,
                  page: turn.page,
                  line: { text: turn.text, page: turn.page },
                  lineIdx: turn.lineIdxs[0]
                });
              }
            });
          }
        }
      });
    });

    const displayKeywordStr = keywordGroups.map(g => g.join(', ')).join(' & ');
    titleEl.textContent = `🔍 "${speakerName}"의 "${displayKeywordStr}" 관련 정밀 검색 (${speechMatches.length}건)`;

    if (speechMatches.length === 0) {
      listEl.innerHTML = `<div class="no-results" style="padding:20px"><p>'${speakerName}' 의원의 '${displayKeywordStr}' 관련 발언 기록을 찾을 수 없습니다.</p></div>`;
      return;
    }

    // 회의록별 그룹화
    const groups = [];
    speechMatches.forEach(match => {
      let group = groups.find(g => g.meeting === match.meeting);
      if (!group) {
        group = { meeting: match.meeting, items: [] };
        groups.push(group);
      }
      group.items.push(match);
    });

    listEl.innerHTML = `
      <div style="margin-bottom:12px; text-align:right;">
        <button id="btn-download-speech-report" class="kw-compare-btn" style="font-size:12px; padding:6px 12px; background:rgba(99,102,241,0.2); border:1px solid rgba(99,102,241,0.4); border-radius:6px; color:#a5b4fc; font-weight:600; cursor:pointer;">📄 발언 기록 보고서 다운로드 (.txt)</button>
      </div>
      <div class="speech-timeline-list">
        ${groups.map(group => {
          let cleanTitle = group.meeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
          cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

          return `
            <div class="meeting-group-card" style="background:rgba(255,255,255,0.035); border:1px solid var(--border-color); border-radius:12px; padding:18px; margin-bottom:16px;">
              <div class="meeting-group-header" data-idx="${STATE.db.meetings.indexOf(group.meeting)}" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px; margin-bottom:12px; cursor:pointer;" title="클릭 시 회의록 상세 분석 모달 열기">
                <span style="font-weight:700; font-size:16.5px; color:var(--accent-cyan);">${escHtml(cleanTitle)}</span>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:13px; color:#cbd5e1; font-weight:600;">📅 ${group.meeting.date}</span>
                  <span class="card-badge badge-${group.meeting.meeting_type}" style="font-size:10px;">${escHtml(group.meeting.meeting_type)}</span>
                </div>
              </div>
              <div style="display:flex; flex-direction:column; gap:12px;">
                ${(() => {
                  const mergedItems = mergeConsecutiveTimelineItems(group.items);
                  return mergedItems.map(seg => {
                    let highlightedLine = escHtml(formatSpeechText(seg.text));
                    keywordGroups.forEach(grp => {
                      grp.forEach(kw => {
                        const regex = new RegExp(`(${kw})`, 'gi');
                        highlightedLine = highlightedLine.replace(regex, '<mark class="search-highlight" style="background:#eab308; color:#000; font-weight:bold; border-radius:2px; padding:0 2px;">$1</mark>');
                      });
                    });

                    return `
                      <div class="speech-timeline-node accent-indigo" data-page="${seg.page}" data-filename="${escHtml(group.meeting.filename)}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(seg.speaker)}" style="cursor:pointer;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary); margin-bottom:4px;">
                          <span style="font-weight:700; color:var(--accent-cyan); font-size:13.5px;">👤 ${escHtml(seg.speaker)}</span>
                          <span style="font-weight:700; color:#22d3ee; font-size:12.5px;">📄 PDF ${seg.page}페이지 🔗</span>
                        </div>
                        <div class="timeline-bubble" style="font-size:14.5px; line-height:1.75; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">${highlightedLine}</div>
                      </div>
                    `;
                  }).join('');
                })()}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    document.getElementById('btn-download-speech-report').onclick = () => {
      let txtContent = `[${speakerName} 의원 '${displayKeywordStr}' 관련 국회 발언 전체 보고서]\n`;
      txtContent += `발생 건수: ${speechMatches.length}건\n`;
      txtContent += `보고서 작성 기준: 제22대 국회 과학기술정보방송통신위원회 회의록\n`;
      txtContent += `==================================================\n\n`;

      speechMatches.forEach((match, idx) => {
        txtContent += `[#${idx + 1}] 날짜: ${match.meeting.date} | 회의명: ${match.meeting.filename.replace(/\.pdf$/i, '')} | PDF: ${match.line.page}p\n`;
        txtContent += ` - 발언자: ${match.speaker}\n`;
        txtContent += ` - 발언 원문: ${match.line.text.trim()}\n\n`;
      });

      const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `${speakerName}_발언보고서_${displayKeywordStr.replace(/\s*&\s*/g, '_')}.txt`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    };

    // 발언 노드 클릭 시 PDF 페이지 새 창 열기 바인딩
    listEl.querySelectorAll('.speech-timeline-node').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        const page = parseInt(el.dataset.page);
        const filename = el.dataset.filename;
        const text = el.dataset.text || '';
        const speaker = el.dataset.speaker || '';
        openPdfWithHighlight(filename, page, text, speaker);
      };
    });

    // 회의록 헤더 클릭 시 상세 분석 모달 열기 바인딩
    listEl.querySelectorAll('.meeting-group-header').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
      };
    });

    if (shouldUpdate) updateHash();
    return;
  }

  // 3. [의원 이름 검색] : 2-4자 한글 이름이고 데이터베이스에 실제로 해당 이름을 가진 발언자가 존재할 때만 진입
  const nameRegex = /^[가-힣]{2,4}$/;
  let isRealSpeaker = false;
  if (nameRegex.test(keyword)) {
    isRealSpeaker = STATE.db.meetings.some(m => 
      (m.speakers || []).some(s => {
        const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        return cleanName === keyword;
      })
    );
  }

  if (nameRegex.test(keyword) && isRealSpeaker) {
    const speechMatches = [];
    STATE.db.meetings.forEach(m => {
      (m.speakers || []).forEach(s => {
        const cleanName = s.name.replace(/^(위원장|소위원장|의원|간사)\s+/, '').trim();
        if (cleanName === keyword) {
          if (s.lines && s.lines.length > 0) {
            const mergedTurns = getSpeakerMergedTurns(s.lines, s.name);
            mergedTurns.forEach(turn => {
              speechMatches.push({
                meeting: m,
                speaker: turn.name,
                text: turn.text,
                page: turn.page,
                line: { text: turn.text, page: turn.page },
                lineIdx: turn.lineIdxs[0]
              });
            });
          }
        }
      });
    });

    titleEl.textContent = `👤 "${keyword}" 의원 발언 내역 검색 (총 ${speechMatches.length}건)`;

    if (speechMatches.length === 0) {
      listEl.innerHTML = `<div class="no-results" style="padding:20px"><p>'${keyword}' 의원의 발언 기록이 없습니다.</p></div>`;
      return;
    }

    const displayMatches = speechMatches.slice(0, 30); // 최근 30건 노출로 확대

    // 회의록별 그룹화
    const groups = [];
    displayMatches.forEach(match => {
      let group = groups.find(g => g.meeting === match.meeting);
      if (!group) {
        group = { meeting: match.meeting, items: [] };
        groups.push(group);
      }
      group.items.push(match);
    });

    listEl.innerHTML = `
      <div style="margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:13px; color:#cbd5e1; font-weight:500;">최근 발언 30건이 회의록별로 묶여서 나열됩니다. 발언 클릭 시 회의록 PDF의 해당 페이지가 열립니다.</span>
        <button id="btn-download-speaker-all" class="kw-compare-btn" style="font-size:12px; padding:6px 12px; background:rgba(16,185,129,0.2); border:1px solid rgba(16,185,129,0.4); border-radius:6px; color:#6ee7b7; font-weight:600; cursor:pointer;">📥 전체 발언 원문 파일 정리 (.txt)</button>
      </div>
      <div class="speech-timeline-list">
        ${groups.map(group => {
          let cleanTitle = group.meeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
          cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

          return `
            <div class="meeting-group-card" style="background:rgba(255,255,255,0.035); border:1px solid var(--border-color); border-radius:12px; padding:18px; margin-bottom:16px;">
              <div class="meeting-group-header" data-idx="${STATE.db.meetings.indexOf(group.meeting)}" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px; margin-bottom:12px; cursor:pointer;" title="클릭 시 회의록 상세 분석 모달 열기">
                <span style="font-weight:700; font-size:16px; color:var(--accent-cyan);">${escHtml(cleanTitle)}</span>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:13px; color:#cbd5e1; font-weight:600;">📅 ${group.meeting.date}</span>
                  <span class="card-badge badge-${group.meeting.meeting_type}" style="font-size:10px;">${escHtml(group.meeting.meeting_type)}</span>
                </div>
              </div>
              <div style="display:flex; flex-direction:column; gap:12px;">
                ${(() => {
                  const mergedItems = mergeConsecutiveTimelineItems(group.items);
                  return mergedItems.map(seg => {
                    return `
                      <div class="speech-timeline-node" data-page="${seg.page}" data-filename="${escHtml(group.meeting.filename)}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(seg.speaker)}" style="background:rgba(255,255,255,0.02); border-left: 3px solid var(--accent-cyan); border-radius:0 8px 8px 0; padding:12px 16px; cursor:pointer; transition:all 0.2s;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary); margin-bottom:4px;">
                          <span style="font-weight:700; color:var(--accent-cyan); font-size:13.5px;">👤 ${escHtml(seg.speaker)}</span>
                          <span style="font-weight:700; color:#22d3ee; font-size:12.5px;">📄 PDF ${seg.page}페이지 🔗</span>
                        </div>
                        <div class="timeline-bubble" style="font-size:14.5px; line-height:1.75; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">
                          ${escHtml(formatSpeechText(seg.text))}
                        </div>
                      </div>
                    `;
                  }).join('');
                })()}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    document.getElementById('btn-download-speaker-all').onclick = () => {
      let txtContent = `👤 [${keyword} 의원 국회 전체 발언 원문 리포트]\n`;
      txtContent += `총 발언 수: ${speechMatches.length}건\n`;
      txtContent += `==================================================\n\n`;

      speechMatches.forEach((match, idx) => {
        txtContent += `■ [${match.meeting.date}] ${match.meeting.filename.replace(/\.pdf$/i, '')} | PDF: ${match.line.page}p\n`;
        txtContent += ` - ${match.line.text.trim()}\n\n`;
      });

      const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `${keyword}_전체발언_리포트.txt`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    };

    listEl.querySelectorAll('.speech-timeline-node').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        const page = parseInt(el.dataset.page);
        const filename = el.dataset.filename;
        const text = el.dataset.text || '';
        const speaker = el.dataset.speaker || '';
        openPdfWithHighlight(filename, page, text, speaker);
      };
    });

    listEl.querySelectorAll('.meeting-group-header').forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
      };
    });

    if (shouldUpdate) updateHash();
    return;
  }

  // 4. [키워드 OR 검색 / 일반 키워드 검색] : 쉼표가 있거나 일반 텍스트
  const orKws = keyword.split(',').map(k => {
    let clean = k.trim().toLowerCase();
    clean = clean.replace(/\s*(통과|합의|반대|규제|진흥|개정|제정|폐지|상정|의결|처리|논의|보고|제출|검토|법안|개정안|법|의안)\s*$/, '').trim();
    return clean;
  }).filter(Boolean);
  const matchedSpeeches = [];

  STATE.db.meetings.forEach(m => {
    (m.speakers || []).forEach(s => {
      if (s.lines && s.lines.length > 0) {
        const mergedTurns = getSpeakerMergedTurns(s.lines, s.name);
        mergedTurns.forEach(turn => {
          const matchedKw = orKws.find(kw => turn.text.toLowerCase().includes(kw));
          if (matchedKw) {
            matchedSpeeches.push({
              meeting: m,
              speaker: turn.name,
              text: turn.text,
              page: turn.page,
              line: { text: turn.text, page: turn.page },
              lineIdx: turn.lineIdxs[0],
              matchedKw: matchedKw
            });
          }
        });
      }
    });
  });

  titleEl.textContent = `🔍 "${orKws.join(', ')}" 관련 발언 실시간 검색 (${matchedSpeeches.length}건)`;

  if (matchedSpeeches.length === 0) {
    listEl.innerHTML = `<div class="no-results" style="padding:20px"><p>'${orKws.join(', ')}' 관련 발언 기록이 없습니다.</p></div>`;
    return;
  }

  const displayMatches = matchedSpeeches.slice(0, 30); // 최근 30건 노출로 확대

  // 회의록별 그룹화
  const groups = [];
  displayMatches.forEach(match => {
    let group = groups.find(g => g.meeting === match.meeting);
    if (!group) {
      group = { meeting: match.meeting, items: [] };
      groups.push(group);
    }
    group.items.push(match);
  });

  listEl.innerHTML = `
    <div style="margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
      <span style="font-size:13px; color:#cbd5e1; font-weight:500;">최근 발언 30건이 회의록별로 묶여서 정렬됩니다.</span>
      <button id="btn-download-kws-all" class="kw-compare-btn" style="font-size:12px; padding:6px 12px; background:rgba(245,158,11,0.2); border:1px solid rgba(245,158,11,0.4); border-radius:6px; color:#fcd34d; font-weight:600; cursor:pointer;">📥 전체 발언 원문 파일 다운로드 (.txt)</button>
    </div>
    <div class="speech-timeline-list">
      ${groups.map(group => {
        let cleanTitle = group.meeting.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
        cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');

        return `
          <div class="meeting-group-card" style="background:rgba(255,255,255,0.035); border:1px solid var(--border-color); border-radius:12px; padding:18px; margin-bottom:16px;">
            <div class="meeting-group-header" data-idx="${STATE.db.meetings.indexOf(group.meeting)}" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px; margin-bottom:12px; cursor:pointer;" title="클릭 시 회의록 상세 분석 모달 열기">
              <span style="font-weight:700; font-size:16px; color:var(--accent-amber);">${escHtml(cleanTitle)}</span>
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:13px; color:#cbd5e1; font-weight:600;">📅 ${group.meeting.date}</span>
                <span class="card-badge badge-${group.meeting.meeting_type}" style="font-size:10px;">${escHtml(group.meeting.meeting_type)}</span>
              </div>
            </div>
            <div style="display:flex; flex-direction:column; gap:12px;">
              ${(() => {
                const mergedItems = mergeConsecutiveTimelineItems(group.items);
                return mergedItems.map(seg => {
                  let highlightedLine = escHtml(formatSpeechText(seg.text));
                  orKws.forEach(kw => {
                    const regex = new RegExp(`(${kw})`, 'gi');
                    highlightedLine = highlightedLine.replace(regex, '<mark class="search-highlight" style="background:#eab308; color:#000; font-weight:bold; border-radius:2px; padding:0 2px;">$1</mark>');
                  });

                  return `
                    <div class="speech-timeline-node" data-page="${seg.page}" data-filename="${escHtml(group.meeting.filename)}" data-text="${escHtml(seg.text)}" data-speaker="${escHtml(seg.speaker)}" style="background:rgba(255,255,255,0.02); border-left: 3px solid var(--accent-amber); border-radius:0 8px 8px 0; padding:12px 16px; cursor:pointer; transition:all 0.2s;" title="클릭 시 회의록 PDF의 해당 페이지 열기 (노란색 형광펜 강조)">
                      <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary); margin-bottom:4px;">
                        <span style="font-weight:700; color:var(--text-accent); font-size:13.5px;">👤 ${escHtml(seg.speaker)}</span>
                        <span style="font-weight:700; color:#22d3ee; font-size:12.5px;">📄 PDF ${seg.page}페이지 🔗</span>
                      </div>
                      <div class="timeline-bubble" style="font-size:14.5px; line-height:1.75; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:10px 14px; border-radius:6px; color:var(--text-primary); font-weight:500;">${highlightedLine}</div>
                    </div>
                  `;
                }).join('');
              })()}
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;

  document.getElementById('btn-download-kws-all').onclick = () => {
    let txtContent = `🔍 ['${orKws.join(', ')}' 국회 발언 히스토리 전체 원문]\n`;
    txtContent += `총 발언 수: ${matchedSpeeches.length}건\n`;
    txtContent += `==================================================\n\n`;

    matchedSpeeches.forEach((match, idx) => {
      txtContent += `■ [${match.meeting.date}] ${match.meeting.filename.replace(/\.pdf$/i, '')} | PDF: ${match.line.page}p\n`;
      txtContent += ` - [${match.speaker}] ${match.line.text.trim()}\n\n`;
    });

    const blob = new Blob([txtContent], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `키워드검색_${orKws.join('_')}.txt`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  listEl.querySelectorAll('.speech-timeline-node').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      const page = parseInt(el.dataset.page);
      const filename = el.dataset.filename;
      const text = el.dataset.text || '';
      const speaker = el.dataset.speaker || '';
      openPdfWithHighlight(filename, page, text, speaker);
    };
  });

  listEl.querySelectorAll('.meeting-group-header').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      openModal(STATE.db.meetings[parseInt(el.dataset.idx)]);
    };
  });

  // 트렌드 차트 업데이트
  updateTrendForKeyword(orKws[0]);

  if (shouldUpdate) {
    updateHash();
  }
}

/**
 * 2개 키워드 비교 검색 (두 단어가 교집합으로 모두 등장하는 회의록 필터링)
 */
function searchKeywordCompare() {
  if (STATE.compareKeywords.length === 0) {
    document.getElementById('kw-results-list').innerHTML = '<div class="no-results" style="padding:20px"><p>좌측 단어를 클릭하여 비교를 시작하세요.</p></div>';
    return;
  }

  const kws = STATE.compareKeywords;
  
  // 교집합 등장 회의록 추출
  const results = STATE.db.meetings
    .map(m => {
      const matched1 = (m.keywords || []).find(k => k.word === kws[0]);
      const matched2 = kws[1] ? (m.keywords || []).find(k => k.word === kws[1]) : { count: 1 }; // 1개일때는 통과
      
      return { 
        m, 
        cnt1: matched1 ? matched1.count : 0, 
        cnt2: matched2 ? matched2.count : 0 
      };
    })
    .filter(x => x.cnt1 > 0 && x.cnt2 > 0)
    .sort((a, b) => (b.cnt1 + b.cnt2) - (a.cnt1 + a.cnt2));

  let compareLabel = `[비교] "${kws[0]}"`;
  if (kws[1]) compareLabel += ` ∩ "${kws[1]}"`;
  
  document.getElementById('kw-results-title').textContent = `${compareLabel} — 공통 출현 ${results.length}건`;

  const listEl = document.getElementById('kw-results-list');
  if (results.length === 0) {
    listEl.innerHTML = '<div class="no-results" style="padding:20px"><p>두 키워드가 공통으로 출현한 회의록이 존재하지 않습니다.</p></div>';
    return;
  }

  listEl.innerHTML = results.map(({ m, cnt1, cnt2 }) => {
    const dateStr = m.date ? m.date.replace(/-/g, '.') : '?';
    let cleanTitle = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
    cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');
    
    const countBadge2 = kws[1] ? `<span class="kw-result-count-badge" style="background:rgba(16,185,129,0.15); color:#6ee7b7; border-color:rgba(16,185,129,0.3); margin-left:4px;">${cnt2}회</span>` : '';
    
    return `
      <div class="kw-result-item" data-idx="${STATE.db.meetings.indexOf(m)}">
        <span class="kw-result-date">${dateStr}</span>
        <span class="kw-result-title">${escHtml(cleanTitle)}</span>
        <div style="display:flex; align-items:center;">
          <span class="kw-result-count-badge">${cnt1}회</span>
          ${countBadge2}
        </div>
      </div>
    `;
  }).join('');

  listEl.querySelectorAll('.kw-result-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx);
      openModal(STATE.db.meetings[idx]);
    });
  });

  // 트렌드 다중 라인 업데이트
  buildTrendChart(kws);
}

// ============================================================
// 5단계: 키워드 트렌드 차트 (Chart.js)
// ============================================================
function renderTrendChart() {
  const top5 = (STATE.db.global_keywords || []).slice(0, 5).map(k => k.word);
  buildTrendChart(top5);
}

function updateTrendForKeyword(keyword) {
  const top5 = [keyword, ...(STATE.db.global_keywords || []).slice(0, 4).map(k => k.word).filter(k => k !== keyword)];
  document.getElementById('trend-keyword-label').textContent = top5.slice(0, 5).join(', ');
  buildTrendChart(top5.slice(0, 5));
}

function buildTrendChart(keywords) {
  // 월별 집계
  const monthMap = {};
  STATE.db.meetings.forEach(m => {
    if (!m.date) return;
    const month = m.date.substring(0, 7); // 'YYYY-MM'
    if (!monthMap[month]) monthMap[month] = {};
    
    (m.keywords || []).forEach(kw => {
      if (keywords.includes(kw.word)) {
        monthMap[month][kw.word] = (monthMap[month][kw.word] || 0) + kw.count;
      }
    });
  });

  const months = Object.keys(monthMap).sort();
  const datasets = keywords.map((kw, i) => ({
    label: kw,
    data: months.map(mo => monthMap[mo]?.[kw] || 0),
    borderColor: TREND_COLORS[i % TREND_COLORS.length],
    backgroundColor: `${TREND_COLORS[i % TREND_COLORS.length]}18`,
    tension: 0.38,
    fill: true,
    pointRadius: 4,
    pointHoverRadius: 6,
  }));

  // 범례 구성
  const legend = document.getElementById('trend-legend');
  legend.innerHTML = keywords.map((kw, i) => `
    <div class="trend-legend-item" style="cursor:pointer" onclick="searchKeyword('${escHtml(kw)}')">
      <span class="trend-legend-dot" style="background:${TREND_COLORS[i % TREND_COLORS.length]}"></span>
      <span style="font-weight:600;">${escHtml(kw)}</span>
    </div>
  `).join('');

  const ctx = document.getElementById('trend-chart').getContext('2d');
  if (STATE.trendChartInstance) STATE.trendChartInstance.destroy();

  const isLight = document.body.classList.contains('light-mode');
  const textColor = isLight ? '#475569' : '#94a3b8';

  STATE.trendChartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels: months, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          padding: 10,
          backgroundColor: isLight ? 'rgba(255,255,255,0.95)' : 'rgba(15,23,42,0.95)',
          titleColor: isLight ? '#0f172a' : '#f1f5f9',
          bodyColor: isLight ? '#334155' : '#cbd5e1',
          borderColor: 'rgba(99,102,241,0.2)',
          borderWidth: 1,
          callbacks: {
            title: (items) => `${items[0].label} 월 집계 현황`,
          }
        }
      },
      scales: {
        x: { 
          grid: { color: isLight ? 'rgba(0,0,0,0.03)' : 'rgba(255,255,255,0.03)' }, 
          ticks: { color: textColor, maxRotation: 45 } 
        },
        y: { 
          grid: { color: isLight ? 'rgba(0,0,0,0.03)' : 'rgba(255,255,255,0.03)' }, 
          ticks: { color: textColor } 
        },
      }
    }
  });
}

// ============================================================
// 6단계: FullCalendar 달력 뷰 연동
// ============================================================
function renderCalendar() {
  const el = document.getElementById('fullcalendar');
  const events = buildCalendarEvents();

  if (STATE.calendarInstance) {
    STATE.calendarInstance.destroy();
  }

  STATE.calendarInstance = new FullCalendar.Calendar(el, {
    initialView: 'dayGridMonth',
    locale: 'ko',
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,listMonth',
    },
    buttonText: { today: '오늘', month: '월간 달력', list: '회의 목록' },
    events,
    eventClick: ({ event }) => {
      const m = event.extendedProps.meeting;
      if (m) openModal(m);
    },
    dateClick: ({ dateStr }) => {
      const dayMeetings = STATE.db.meetings.filter(m => m.date === dateStr);
      if (dayMeetings.length > 0) {
        renderCalendarSidebar(dateStr, dayMeetings);
      }
    },
    eventContent: ({ event }) => ({
      html: `<div class="fc-event-custom" style="background:${event.backgroundColor}; padding: 2px 6px; border-radius: 4px; font-weight:600; font-size:11px;">${event.title}</div>`
    }),
  });

  STATE.calendarInstance.render();
}

function buildCalendarEvents() {
  return STATE.db.meetings
    .filter(m => m.date)
    .map(m => {
      const type = m.meeting_type || '기타';
      const color = TYPE_COLORS[type] || TYPE_COLORS['기타'];
      let title = `[${type}]`;
      if (m.order_num) title += ` ${m.order_num}차`;
      return {
        title,
        start: m.date,
        backgroundColor: color,
        borderColor: 'transparent',
        textColor: '#fff',
        extendedProps: { meeting: m }
      };
    });
}

function renderCalendarSidebar(dateStr, meetings) {
  const sidebar = document.getElementById('calendar-sidebar');
  sidebar.innerHTML = `
    <div style="font-size:14px; font-weight:700; color:var(--text-primary); margin-bottom:14px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
      📅 ${dateStr.replace(/-/g, '.')} 회의 현황 (${meetings.length}건)
    </div>
    ${meetings.map(m => {
      const type = m.meeting_type || '기타';
      const color = TYPE_COLORS[type] || '#64748b';
      
      let cleanTitle = m.filename?.replace(/\.PDF?$/i, '').replace(/\s*\(1\)\s*$/, '') || '';
      cleanTitle = cleanTitle.replace(/^제22대국회\s+/, '');
      
      const agendaText = (m.agendas || []).slice(0, 2).join(' / ') || m.summary?.substring(0, 70) || '의사 안건 정보 없음';
      return `
        <div class="sidebar-meeting-item" data-idx="${STATE.db.meetings.indexOf(m)}">
          <div class="sidebar-meeting-type" style="color:${color}; font-weight:700;">${type}</div>
          <div class="sidebar-meeting-title" style="font-size:13px; font-weight:600; margin: 4px 0;">${escHtml(cleanTitle)}</div>
          <div class="sidebar-meeting-agendas" style="font-size:11.5px; opacity:0.8;">${escHtml(agendaText)}</div>
        </div>`;
    }).join('')}
  `;

  sidebar.querySelectorAll('.sidebar-meeting-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx);
      openModal(STATE.db.meetings[idx]);
    });
  });
}

// ============================================================
// 보조 유틸리티 함수
// ============================================================
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(new RegExp('"', 'g'), '&quot;');
}

function formatSpeechText(txt) {
  if (!txt) return '';
  txt = txt.trim();
  if (txt.startsWith('ㅇ')) return txt;

  // 물음표(?) 및 마침표(.) 뒤에 공백이 있는 부분을 기준으로 문장 나누기
  const sentences = txt.split(/(?<=\?|\.)\s+/);
  if (sentences.length <= 1) return 'ㅇ ' + txt;

  const blocks = [];
  let currentBlock = '';
  
  const conjunctions = ["그리고", "그래서", "하지만", "또한", "그러나", "즉", "따라서", "이에", "왜냐하면", "어쨌든", "결국은", "다만"];
  const tailPatterns = ["그렇지요", "맞습니까", "어떻게 보십니까", "그렇지 않습니까", "그렇죠", "어떠십니까", "맞나요", "그렇습니까", "맞고요"];

  sentences.forEach((sent) => {
    const trimmed = sent.trim();
    if (!trimmed) return;
    
    if (!currentBlock) {
      currentBlock = trimmed;
    } else {
      // 꼬리 질문 검사 (15자 이하이고 물음표로 끝나거나 꼬리 질문 단어가 포함된 경우)
      const isTail = (trimmed.length <= 15 && trimmed.endsWith('?')) || 
                     tailPatterns.some(p => trimmed.includes(p));
      
      // 접속사 검사
      const isConjunction = conjunctions.some(c => trimmed.startsWith(c));
      
      // 이전 블록이 ?로 끝났는지 여부
      const lastCharQ = currentBlock.endsWith('?');
      
      // 평서문 누적 방지: 이전 블록의 길이가 120자 이상이면 평서문 기준 끊어줌
      const isTooLong = currentBlock.length >= 120;
      
      // 이전 블록이 마침표로 끝나고, 현재 문장이 새로운 핵심 의사 표현으로 시작하는지 검사
      const isNewTopic = trimmed.startsWith("질문은") || trimmed.startsWith("질의는") || trimmed.startsWith("저는");

      if (isTail || isConjunction || (!lastCharQ && !isTooLong && !isNewTopic)) {
        currentBlock += ' ' + trimmed;
      } else {
        blocks.push(currentBlock);
        currentBlock = trimmed;
      }
    }
  });
  
  if (currentBlock) {
    blocks.push(currentBlock);
  }
  
  return blocks.map(b => 'ㅇ ' + b).join('\n');
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/**
 * 안건 제목에서 불필요한 조사 및 형식 어미를 제거하고 실질 검색어 리스트를 추출
 */
function getAgendaKeywords(title) {
  if (!title) return [];
  const cleanTitle = title.replace(/\(.*?\)/g, '')
    .replace(/(일부개정법률안|법률안|공동의안|일부개정안|법안|제정안|안건|의안|조항|관련|규정|조치|제안)/g, ' ')
    .trim();
  const words = cleanTitle.split(/[^가-힣a-zA-Z0-9]/).map(w => w.trim()).filter(w => w.length >= 2);
  const stopWords = ['대해', '대한', '등에', '관한', '및', '또는', '하고', '하는', '위한'];
  return words.filter(w => !stopWords.includes(w));
}

/**
 * 지능형 연속 대사 세그먼트 병합 (Segment Merge) 헬퍼 함수
 */
function mergeConsecutiveTimelineItems(items) {
  if (!items || items.length === 0) return [];
  const merged = [];
  let current = null;
  
  items.forEach(item => {
    const speakerName = item.speaker || item.name;
    const itemPage = item.page || (item.line ? item.line.page : 1);
    const itemText = item.text || (item.line ? item.line.text : '');
    
    if (!current) {
      current = {
        meeting: item.meeting,
        speaker: speakerName,
        name: speakerName,
        page: itemPage,
        text: itemText,
        lineIdxs: [item.lineIdx]
      };
    } else {
      const lastIdx = current.lineIdxs[current.lineIdxs.length - 1];
      
      const sameSpeaker = current.speaker === speakerName;
      const sameMeeting = current.meeting === item.meeting;
      const samePage = current.page === itemPage;
      const consecutiveIdx = item.lineIdx === lastIdx + 1;
      
      if (sameSpeaker && sameMeeting && samePage && consecutiveIdx) {
        current.text += " " + itemText;
        current.lineIdxs.push(item.lineIdx);
      } else {
        merged.push(current);
        current = {
          meeting: item.meeting,
          speaker: speakerName,
          name: speakerName,
          page: itemPage,
          text: itemText,
          lineIdxs: [item.lineIdx]
        };
      }
    }
  });
  if (current) {
    merged.push(current);
  }
  return merged;
}

/**
 * 사용자 피드백 2차 반영: 상단 고정 네온 글로우 안내 바 (Sticky Alert Bar)
 * PDF 새 창 이동 시 대시보드로 돌아왔을 때 사용자가 확인할 때까지 최상단에 계속 노출됩니다.
 */
function showStickyAlert(message) {
  let alertEl = document.getElementById('dashboard-sticky-alert');
  if (!alertEl) {
    alertEl = document.createElement('div');
    alertEl.id = 'dashboard-sticky-alert';
    alertEl.style = `
      position: fixed;
      top: 24px;
      left: 50%;
      transform: translateX(-50%) translateY(-150px);
      background: rgba(15, 23, 42, 0.93);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1.5px solid rgba(99, 102, 241, 0.5);
      box-shadow: 0 12px 40px rgba(99, 102, 241, 0.35), inset 0 1px 1px rgba(255, 255, 255, 0.1);
      color: #f8fafc;
      padding: 16px 28px;
      border-radius: 16px;
      z-index: 100000;
      font-size: 14px;
      transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      opacity: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      max-width: 90%;
      width: 620px;
      line-height: 1.6;
    `;
    document.body.appendChild(alertEl);
  }
  
  alertEl.innerHTML = `
    <div style="flex: 1; text-align: left; font-family: system-ui, -apple-system, sans-serif;">
      ${message}
    </div>
    <button onclick="document.getElementById('dashboard-sticky-alert').style.transform='translateX(-50%) translateY(-150px)'; document.getElementById('dashboard-sticky-alert').style.opacity='0';" style="background: linear-gradient(135deg, #6366f1, #4f46e5); color: #ffffff; border: none; padding: 8px 18px; border-radius: 8px; font-weight: 700; font-size: 12.5px; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 12px rgba(99,102,241,0.3); flex-shrink: 0;" onmouseover="this.style.filter='brightness(1.15)';" onmouseout="this.style.filter='none';">
      확인
    </button>
  `;
  
  // Show alert
  setTimeout(() => {
    alertEl.style.transform = 'translateX(-50%) translateY(0)';
    alertEl.style.opacity = '1';
  }, 50);
}

/**
 * 사용자 피드백 반영: 클립보드 자동 복사 및 글래스모피즘 가이드 토스트(Toast) 플로팅 모듈
 */
function showToast(message) {
  let toast = document.getElementById('dashboard-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'dashboard-toast';
    toast.style = `
      position: fixed;
      bottom: 80px;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: rgba(15, 23, 42, 0.88);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(99, 102, 241, 0.4);
      color: #f1f5f9;
      padding: 14px 28px;
      border-radius: 12px;
      font-size: 13.5px;
      font-weight: 500;
      line-height: 1.5;
      text-align: center;
      z-index: 999999;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.6), 0 0 20px rgba(99, 102, 241, 0.25);
      transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.4s ease;
      opacity: 0;
      pointer-events: none;
    `;
    document.body.appendChild(toast);
  }
  
  toast.innerHTML = message;
  // 진입 애니메이션 기동
  setTimeout(() => {
    toast.style.transform = 'translateX(-50%) translateY(0)';
    toast.style.opacity = '1';
  }, 50);
  
  if (window.toastTimeout) clearTimeout(window.toastTimeout);
  
  window.toastTimeout = setTimeout(() => {
    toast.style.transform = 'translateX(-50%) translateY(100px)';
    toast.style.opacity = '0';
  }, 5000);
}

/**
 * 텍스트에서 노란색 형광펜 매칭률 100%를 보장하는 최적의 단어(공백 없는 가장 긴 핵심 단어) 추출
 */
function getBestSearchWord(text) {
  if (!text) return '';
  const words = text.replace(/[^가-힣a-zA-Z0-9]/g, ' ')
    .split(/\s+/)
    .map(w => w.trim())
    .filter(w => w.length >= 3);
    
  if (words.length === 0) {
    const shortWords = text.replace(/[^가-힣a-zA-Z0-9]/g, ' ')
      .split(/\s+/)
      .map(w => w.trim())
      .filter(w => w.length >= 2);
    if (shortWords.length === 0) return '';
    return shortWords[0];
  }
  
  // 가장 긴 단어를 정렬하여 선택
  words.sort((a, b) => b.length - a.length);
  return words[0];
}

/**
 * 지능형 PDF 퀵링크 페이지 점프 및 노란색 형광펜 매뉴얼 검색 동시 유도 팩
 */
function openPdfWithHighlight(filename, page, text, speaker) {
  // 클라우드(GitHub Pages) 환경인지 확인 (보안 정책 상 원본 PDF는 클라우드에 업로드되지 않음)
  const isCloud = window.location.hostname !== 'localhost' && 
                  window.location.hostname !== '127.0.0.1' && 
                  window.location.protocol !== 'file:';
                  
  if (isCloud) {
    showStickyAlert(`🔒 <strong>로컬 전용 기능 안내</strong><br/>
      보안 및 용량 제한으로 원본 PDF 파일은 클라우드(GitHub)에 업로드되지 않았습니다.<br/>
      PDF 원본 보기 및 해당 페이지 점프 기능은 <strong>로컬 대시보드(http://localhost:8765)</strong>에서 실행할 때만 지원됩니다.`);
    return;
  }

  const pdfUrl = `pdf/${encodeURIComponent(filename)}#page=${page}`;
  window.open(pdfUrl, '_blank');
  
  showStickyAlert(`🏛️ <strong>PDF ${page}페이지로 이동 중...</strong><br/>
    브라우저가 해당 페이지로 자동 이동을 수행했습니다.`);
}

/**
 * 발언자의 lines 배열을 인덱스 연속성 및 페이지 일치 여부에 맞춰 온전한 문맥의 덩어리(Speech Turns)로 사전 병합하고,
 * 대사 내부의 페이지 번호 노이즈 제거 및 타인 발언 섞임 분리(문답 형식 복원)를 동적으로 수행
 */
function getSpeakerMergedTurns(lines, speakerName = '') {
  if (!lines || lines.length === 0) return [];
  const merged = [];
  let current = null;
  
  // 1. 페이지 번호 및 속기록 머리글 노이즈 제거 정규식
  const sanitizeText = (txt) => {
    if (!txt) return '';
    // 예: "12 제433회-과학기술정보방송통신소위제3차(2026년3월24일)" 등의 페이지 러닝헤드 패턴 완벽 소거
    let cleaned = txt.replace(/\d+\s+제\d+회\s*-\s*[가-힣\s\(\)]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)/g, '');
    // 추가적인 페이지 번호 노이즈 방어
    cleaned = cleaned.replace(/^\d+\s+제\d+회-.*?$/gm, '');
    return cleaned.trim();
  };

  lines.forEach((line, idx) => {
    const cleanedText = sanitizeText(line.text);
    if (!cleanedText) return; // 노이즈만 있는 라인은 패스

    if (!current) {
      current = {
        speaker: speakerName,
        name: speakerName,
        text: cleanedText,
        page: line.page,
        lineIdxs: [idx]
      };
    } else {
      const lastIdx = current.lineIdxs[current.lineIdxs.length - 1];
      // 페이지가 같고 라인이 연속된 경우 하나의 턴으로 일단 통합
      if (idx === lastIdx + 1 && line.page === current.page) {
        current.text += " " + cleanedText;
        current.lineIdxs.push(idx);
      } else {
        merged.push(current);
        current = {
          speaker: speakerName,
          name: speakerName,
          text: cleanedText,
          page: line.page,
          lineIdxs: [idx]
        };
      }
    }
  });
  
  if (current) {
    merged.push(current);
  }

  // 2. 동적 문답 분할 복원 알고리즘 (◯/○ 기호 기준 타인 발언 격리 분할)
  const finalTurns = [];
  
  merged.forEach(turn => {
    const text = turn.text;
    // ◯ 이나 ○ 기호가 중간에 들어있다면 분할 시도
    if (/[◯○]/.test(text)) {
      const parts = text.split(/[◯○]/);
      parts.forEach((part, pIdx) => {
        const trimmedPart = part.trim();
        if (!trimmedPart) return;
        
        if (pIdx === 0) {
          // 첫 파트는 원래 발언자의 발언
          finalTurns.push({
            speaker: turn.speaker,
            name: turn.name,
            text: sanitizeText(trimmedPart),
            page: turn.page,
            lineIdxs: turn.lineIdxs
          });
        } else {
          // 이후 파트들은 타인의 발언 (예: "과학기술정보통신부제2차관 류제명 위원님, 저희는...")
          // 발언자 이름/직책과 대사를 분리
          const spkMatch = trimmedPart.match(/^([가-힣]{2,25}?(?:위원장|소위원장|위원|의원|간사|차관|장관|사장|대행|후보자|전문위원|수석전문위원|참고인|증인)?)(?:\s+(.*))?$/);
          
          if (spkMatch) {
            const newSpk = spkMatch[1].trim();
            const newText = spkMatch[2] ? spkMatch[2].trim() : '';
            if (newText) {
              finalTurns.push({
                speaker: newSpk,
                name: newSpk,
                text: sanitizeText(newText),
                page: turn.page,
                lineIdxs: turn.lineIdxs
              });
            } else {
              // 대사 분리가 실패하거나 없으면 통째로 타인 발언으로 넣음
              finalTurns.push({
                speaker: newSpk,
                name: newSpk,
                text: sanitizeText(trimmedPart),
                page: turn.page,
                lineIdxs: turn.lineIdxs
              });
            }
          } else {
            // 발언자 분리가 실패하면 그냥 원래 발언 턴으로 추가
            finalTurns.push({
              speaker: turn.speaker,
              name: turn.name,
              text: sanitizeText(trimmedPart),
              page: turn.page,
              lineIdxs: turn.lineIdxs
            });
          }
        }
      });
    } else {
      finalTurns.push(turn);
    }
  });

  return finalTurns;
}

