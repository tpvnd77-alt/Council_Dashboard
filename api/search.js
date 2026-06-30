const fs = require('fs');
const path = require('path');
const { Pool } = require('pg');

let pool = null;
if (process.env.SUPABASE_DB_URL) {
  pool = new Pool({
    connectionString: process.env.SUPABASE_DB_URL,
    ssl: { rejectUnauthorized: false }
  });
}

function matchKeyword(text, kw) {
  if (!text || !kw) return false;
  const cleanText = text.toLowerCase();
  const cleanKw = kw.toLowerCase();
  const isEnglishAcronym = /^[a-z0-9_-]+$/i.test(cleanKw);
  if (isEnglishAcronym) {
    const escaped = cleanKw.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
    const regex = new RegExp('\\b' + escaped + '\\b', 'i');
    return regex.test(cleanText);
  }
  return cleanText.includes(cleanKw);
}

function getSpeakerMergedTurns(lines, speakerName = '') {
  if (!lines || lines.length === 0) return [];
  const merged = [];
  let current = null;
  
  const sanitizeText = (txt) => {
    if (!txt) return '';
    let cleaned = txt.replace(/\d+\s+제\d+회\s*-\s*[가-힣\s\(\)]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)/g, '');
    cleaned = cleaned.replace(/^\d+\s+제\d+회-.*?$/gm, '');
    return cleaned.trim();
  };

  lines.forEach((line, idx) => {
    const cleanedText = sanitizeText(line.text || line.content);
    if (!cleanedText) return;

    const page = line.page || 1;

    if (!current) {
      current = {
        name: speakerName,
        text: cleanedText,
        page: page,
        lineIdxs: [idx]
      };
    } else {
      const lastIdx = current.lineIdxs[current.lineIdxs.length - 1];
      if (idx === lastIdx + 1 && page === current.page) {
        current.text += " " + cleanedText;
        current.lineIdxs.push(idx);
      } else {
        merged.push(current);
        current = {
          name: speakerName,
          text: cleanedText,
          page: page,
          lineIdxs: [idx]
        };
      }
    }
  });
  if (current) {
    merged.push(current);
  }
  return merged;
}

function mergeDatabaseRowsToTurns(rows) {
  // Group by meeting and speaker
  const groups = {};
  for (const r of rows) {
    const key = `${r.filename}||${r.speaker_name}`;
    if (!groups[key]) {
      groups[key] = {
        filename: r.filename,
        date: r.date,
        summary: r.summary,
        session_num: r.session_num,
        session_type: r.session_type,
        order_num: r.order_num,
        meeting_type: r.meeting_type,
        year: r.year,
        speaker_name: r.speaker_name,
        lines: []
      };
    }
    groups[key].lines.push({
      content: r.content,
      page: r.page
    });
  }

  // Merge each group's lines into turns
  const turnMatches = [];
  for (const key in groups) {
    const g = groups[key];
    const turns = getSpeakerMergedTurns(g.lines, g.speaker_name);
    for (const turn of turns) {
      turnMatches.push({
        filename: g.filename,
        date: g.date,
        summary: g.summary,
        session_num: g.session_num,
        session_type: g.session_type,
        order_num: g.order_num,
        meeting_type: g.meeting_type,
        year: g.year,
        speaker: turn.name,
        content: turn.text,
        page: turn.page
      });
    }
  }
  return turnMatches;
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Credentials', true);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version');

  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  const queryStr = req.query.q || '';
  const speakerParam = req.query.speaker || '';

  if (!queryStr.trim() && !speakerParam.trim()) {
    res.status(200).json({ success: true, matched_meetings: [] });
    return;
  }

  try {
    if (pool) {
      // ==========================================
      // 1. Cloud PostgreSQL Mode
      // ==========================================
      let matchedMeetings = [];

      if (speakerParam.trim()) {
        const sqlQuery = `
          SELECT m.filename, m.date, m.summary, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year,
                 s.speaker_name, s.content, s.page
          FROM speeches s
          JOIN meetings m ON s.meeting_id = m.meeting_id
          WHERE s.speaker_name ILIKE $1
          ORDER BY m.meeting_id ASC, s.speaker_name ASC, s.page ASC, s.speech_id ASC;
        `;
        const { rows } = await pool.query(sqlQuery, [`%${speakerParam.trim()}%`]);
        const allTurns = mergeDatabaseRowsToTurns(rows);
        
        // Group turns by meeting
        const meetingsMap = {};
        for (const turn of allTurns) {
          const key = turn.filename;
          if (!meetingsMap[key]) {
            meetingsMap[key] = {
              filename: turn.filename,
              date: turn.date,
              summary: turn.summary,
              session_num: turn.session_num,
              session_type: turn.session_type,
              order_num: turn.order_num,
              meeting_type: turn.meeting_type,
              year: turn.year,
              matched_speeches: []
            };
          }
          meetingsMap[key].matched_speeches.push({
            speaker: turn.speaker,
            content: turn.content,
            page: turn.page
          });
        }
        matchedMeetings = Object.values(meetingsMap);
      } else if (queryStr.includes('&')) {
        const parts = queryStr.split('&').map(p => p.trim());
        const speaker = parts[0];
        const keywordGroups = parts.slice(1);

        // Find speaker-page units containing any of the keywords
        const orKws = [];
        for (const group of keywordGroups) {
          const kws = group.split(',').map(k => k.trim()).filter(Boolean);
          orKws.push(...kws);
        }
        const likeClauses = orKws.map((_, i) => `s2.content ILIKE $${i + 2}`).join(' OR ');
        
        const sqlQuery = `
          SELECT m.filename, m.date, m.summary, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year,
                 s.speaker_name, s.content, s.page
          FROM speeches s
          JOIN meetings m ON s.meeting_id = m.meeting_id
          WHERE (s.meeting_id, s.speaker_name, s.page) IN (
            SELECT DISTINCT s2.meeting_id, s2.speaker_name, s2.page
            FROM speeches s2
            WHERE s2.speaker_name ILIKE $1 AND (${likeClauses})
          )
          ORDER BY m.meeting_id ASC, s.speaker_name ASC, s.page ASC, s.speech_id ASC;
        `;
        const params = [`%${speaker}%`, ...orKws.map(k => `%${k}%`)];
        const { rows } = await pool.query(sqlQuery, params);
        
        const allTurns = mergeDatabaseRowsToTurns(rows);
        
        // Filter turns in JS for strict AND conditions
        const filteredTurns = [];
        for (const turn of allTurns) {
          let matchAll = true;
          for (const group of keywordGroups) {
            const kws = group.split(',').map(k => k.trim()).filter(Boolean);
            if (!kws.some(kw => matchKeyword(turn.content, kw))) {
              matchAll = false;
              break;
            }
          }
          if (matchAll) {
            filteredTurns.push(turn);
          }
        }

        // Group by meeting
        const meetingsMap = {};
        for (const turn of filteredTurns) {
          const key = turn.filename;
          if (!meetingsMap[key]) {
            meetingsMap[key] = {
              filename: turn.filename,
              date: turn.date,
              summary: turn.summary,
              session_num: turn.session_num,
              session_type: turn.session_type,
              order_num: turn.order_num,
              meeting_type: turn.meeting_type,
              year: turn.year,
              matched_speeches: []
            };
          }
          meetingsMap[key].matched_speeches.push({
            speaker: turn.speaker,
            content: turn.content,
            page: turn.page
          });
        }
        matchedMeetings = Object.values(meetingsMap);
      } else {
        const orKws = queryStr.split(',').map(k => k.trim()).filter(Boolean);
        const likeClauses = orKws.map((_, i) => `s2.content ILIKE $${i + 1}`).join(' OR ');

        // Find speaker-page units containing any of the keywords
        const sqlQuery = `
          SELECT m.filename, m.date, m.summary, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year,
                 s.speaker_name, s.content, s.page
          FROM speeches s
          JOIN meetings m ON s.meeting_id = m.meeting_id
          WHERE (s.meeting_id, s.speaker_name, s.page) IN (
            SELECT DISTINCT s2.meeting_id, s2.speaker_name, s2.page
            FROM speeches s2
            WHERE ${likeClauses}
          )
          ORDER BY m.meeting_id ASC, s.speaker_name ASC, s.page ASC, s.speech_id ASC;
        `;
        const { rows } = await pool.query(sqlQuery, orKws.map(k => `%${k}%`));
        
        const allTurns = mergeDatabaseRowsToTurns(rows);

        // Filter exact word boundaries in JS
        const filteredTurns = [];
        for (const turn of allTurns) {
          if (orKws.some(kw => matchKeyword(turn.content, kw))) {
            filteredTurns.push(turn);
          }
        }

        // Group by meeting
        const meetingsMap = {};
        for (const turn of filteredTurns) {
          const key = turn.filename;
          if (!meetingsMap[key]) {
            meetingsMap[key] = {
              filename: turn.filename,
              date: turn.date,
              summary: turn.summary,
              session_num: turn.session_num,
              session_type: turn.session_type,
              order_num: turn.order_num,
              meeting_type: turn.meeting_type,
              year: turn.year,
              matched_speeches: []
            };
          }
          meetingsMap[key].matched_speeches.push({
            speaker: turn.speaker,
            content: turn.content,
            page: turn.page
          });
        }
        matchedMeetings = Object.values(meetingsMap);
      }

      res.status(200).json({ success: true, matched_meetings: matchedMeetings });
    } else {
      // ==========================================
      // 2. Local Fallback Mode
      // ==========================================
      const localPath = path.join('C:', 'Users', 'hp', '.gemini', 'antigravity', 'scratch', 'council_dashboard', 'data', 'meetings.json');
      if (!fs.existsSync(localPath)) {
        res.status(404).json({ success: false, message: 'Local meetings.json file not found' });
        return;
      }

      const raw = fs.readFileSync(localPath, 'utf8');
      const data = JSON.parse(raw);
      const matchedMeetings = [];

      if (speakerParam.trim()) {
        const cleanSpkParam = speakerParam.trim().toLowerCase();
        for (const m of data.meetings) {
          const matchedSpeeches = [];
          for (const spk of m.speakers) {
            if (spk.name.toLowerCase().includes(cleanSpkParam)) {
              const turns = getSpeakerMergedTurns(spk.lines, spk.name);
              for (const turn of turns) {
                matchedSpeeches.push({
                  speaker: turn.name,
                  content: turn.text,
                  page: turn.page
                });
              }
            }
          }
          if (matchedSpeeches.length > 0) {
            matchedMeetings.push({
              filename: m.filename,
              date: m.date,
              summary: m.summary,
              session_num: m.session_num,
              session_type: m.session_type,
              order_num: m.order_num,
              meeting_type: m.meeting_type,
              year: m.year,
              matched_speeches: matchedSpeeches
            });
          }
        }
      } else if (queryStr.includes('&')) {
        const parts = queryStr.split('&').map(p => p.trim());
        const speaker = parts[0];
        const keywordGroups = parts.slice(1);

        for (const m of data.meetings) {
          const matchedSpeeches = [];
          for (const spk of m.speakers) {
            if (spk.name.toLowerCase().includes(speaker.toLowerCase())) {
              const turns = getSpeakerMergedTurns(spk.lines, spk.name);
              for (const turn of turns) {
                let matchAll = true;
                for (const group of keywordGroups) {
                  const kws = group.split(',').map(k => k.trim()).filter(Boolean);
                  if (!kws.some(kw => matchKeyword(turn.text, kw))) {
                    matchAll = false;
                    break;
                  }
                }
                if (matchAll) {
                  matchedSpeeches.push({
                    speaker: turn.name,
                    content: turn.text,
                    page: turn.page
                  });
                }
              }
            }
          }

          if (matchedSpeeches.length > 0) {
            matchedMeetings.push({
              filename: m.filename,
              date: m.date,
              summary: m.summary,
              session_num: m.session_num,
              session_type: m.session_type,
              order_num: m.order_num,
              meeting_type: m.meeting_type,
              year: m.year,
              matched_speeches: matchedSpeeches
            });
          }
        }
      } else {
        const orKws = queryStr.split(',').map(k => k.trim()).filter(Boolean);

        for (const m of data.meetings) {
          const matchedSpeeches = [];
          for (const spk of m.speakers) {
            const turns = getSpeakerMergedTurns(spk.lines, spk.name);
            for (const turn of turns) {
              if (orKws.some(kw => matchKeyword(turn.text, kw))) {
                matchedSpeeches.push({
                  speaker: turn.name,
                  content: turn.text,
                  page: turn.page
                });
              }
            }
          }

          if (matchedSpeeches.length > 0) {
            matchedMeetings.push({
              filename: m.filename,
              date: m.date,
              summary: m.summary,
              session_num: m.session_num,
              session_type: m.session_type,
              order_num: m.order_num,
              meeting_type: m.meeting_type,
              year: m.year,
              matched_speeches: matchedSpeeches
            });
          }
        }
      }

      res.status(200).json({ success: true, matched_meetings: matchedMeetings });
    }
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
};
