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

module.exports = async (req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Credentials', true);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version');

  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  const filename = req.query.filename;

  try {
    if (filename) {
      // ==========================================
      // Mode A: Specific Meeting Detail Fetch
      // ==========================================
      if (pool) {
        // 1. Cloud PostgreSQL Mode
        const meetingQuery = `
          SELECT meeting_id, filename, date, session_num, session_type, order_num, meeting_type, year, text_length, summary
          FROM meetings
          WHERE filename = $1;
        `;
        const meetingRes = await pool.query(meetingQuery, [filename]);
        if (meetingRes.rows.length === 0) {
          res.status(404).json({ success: false, message: 'Meeting not found in PostgreSQL' });
          return;
        }
        const meetingRow = meetingRes.rows[0];
        const meetingId = meetingRow.meeting_id;

        // Fetch agendas
        const agendaQuery = `
          SELECT title, proposer, proposal_date, summary, link
          FROM agendas
          WHERE meeting_id = $1
          ORDER BY agenda_id ASC;
        `;
        const agendaRes = await pool.query(agendaQuery, [meetingId]);

        // Fetch speeches
        const speechQuery = `
          SELECT speaker_name, content, page, speech_count
          FROM speeches
          WHERE meeting_id = $1
          ORDER BY speech_id ASC;
        `;
        const speechRes = await pool.query(speechQuery, [meetingId]);

        // Fetch keywords
        const keywordQuery = `
          SELECT speaker_name, word, count
          FROM keywords
          WHERE meeting_id = $1
          ORDER BY count DESC;
        `;
        const keywordRes = await pool.query(keywordQuery, [meetingId]);

        // Group speeches and keywords to match the JSON speaker structure
        const speakersMap = {};
        for (const row of speechRes.rows) {
          const name = row.speaker_name;
          if (!speakersMap[name]) {
            speakersMap[name] = {
              name: name,
              speech_count: row.speech_count,
              lines: [],
              keywords: []
            };
          }
          speakersMap[name].lines.push({
            text: row.content,
            page: row.page
          });
        }

        const meetingKeywords = [];
        for (const row of keywordRes.rows) {
          if (row.speaker_name === null) {
            meetingKeywords.push({
              word: row.word,
              count: row.count
            });
          } else if (speakersMap[row.speaker_name]) {
            speakersMap[row.speaker_name].keywords.push({
              word: row.word,
              count: row.count
            });
          }
        }

        res.status(200).json({
          success: true,
          meeting: {
            filename: meetingRow.filename,
            date: meetingRow.date,
            session_num: meetingRow.session_num,
            session_type: meetingRow.session_type,
            order_num: meetingRow.order_num,
            meeting_type: meetingRow.meeting_type,
            year: meetingRow.year,
            text_length: meetingRow.text_length,
            summary: meetingRow.summary,
            agendas: agendaRes.rows,
            speakers: Object.values(speakersMap),
            keywords: meetingKeywords
          }
        });
      } else {
        // 2. Local Fallback Mode
        const localPath = path.join('C:', 'Users', 'hp', '.gemini', 'antigravity', 'scratch', 'council_dashboard', 'data', 'meetings.json');
        if (!fs.existsSync(localPath)) {
          res.status(404).json({ success: false, message: 'Local meetings.json file not found' });
          return;
        }
        const raw = fs.readFileSync(localPath, 'utf8');
        const data = JSON.parse(raw);
        const meeting = data.meetings.find(m => m.filename === filename);
        if (!meeting) {
          res.status(404).json({ success: false, message: 'Meeting not found in local JSON' });
          return;
        }
        res.status(200).json({ success: true, meeting: meeting });
      }
    } else {
      // ==========================================
      // Mode B: Meeting Metadata List Fetch
      // ==========================================
      const limit = parseInt(req.query.limit) || 1000;
      const offset = parseInt(req.query.offset) || 0;
      const sortBy = req.query.sortBy || 'date';
      const sortOrder = req.query.sortOrder || 'desc';

      if (pool) {
        // 1. Cloud PostgreSQL Mode
        let orderClause = 'm.date DESC';
        if (sortBy === 'session') {
          orderClause = `m.session_num ${sortOrder}, m.order_num ${sortOrder}`;
        } else if (sortBy === 'speakers') {
          // Sort by speaker count
          orderClause = `speaker_count ${sortOrder}`;
        } else {
          orderClause = `m.date ${sortOrder}`;
        }

        // We run a batched query to avoid N+1 queries.
        // A. Meetings basic query
        const meetingsQuery = `
          SELECT m.meeting_id, m.filename, m.date, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year, m.text_length, m.summary,
                 (SELECT COUNT(DISTINCT s.speaker_name) FROM speeches s WHERE s.meeting_id = m.meeting_id) as speaker_count,
                 (SELECT COUNT(*) FROM agendas a WHERE a.meeting_id = m.meeting_id) as agenda_count
          FROM meetings m
          ORDER BY ${orderClause}
          LIMIT $1 OFFSET $2;
        `;
        const meetingsRes = await pool.query(meetingsQuery, [limit, offset]);
        const meetingIds = meetingsRes.rows.map(r => r.meeting_id);

        let meetings = [];
        if (meetingIds.length > 0) {
          // B. Get Agendas for these meetings
          const agendasQuery = `
            SELECT meeting_id, title, proposer, proposal_date, summary, link
            FROM agendas
            WHERE meeting_id = ANY($1)
            ORDER BY agenda_id ASC;
          `;
          const agendasRes = await pool.query(agendasQuery, [meetingIds]);

          // C. Get Keywords for these meetings
          const keywordsQuery = `
            SELECT meeting_id, word, count
            FROM keywords
            WHERE meeting_id = ANY($1) AND speaker_name IS NULL
            ORDER BY count DESC;
          `;
          const keywordsRes = await pool.query(keywordsQuery, [meetingIds]);

          // D. Get Speakers and Counts for these meetings
          const speakersQuery = `
            SELECT DISTINCT ON (meeting_id, speaker_name) meeting_id, speaker_name, speech_count
            FROM speeches
            WHERE meeting_id = ANY($1)
            ORDER BY meeting_id, speaker_name, speech_count DESC;
          `;
          const speakersRes = await pool.query(speakersQuery, [meetingIds]);

          // Map for easy grouping
          const agendasMap = {};
          for (const row of agendasRes.rows) {
            if (!agendasMap[row.meeting_id]) agendasMap[row.meeting_id] = [];
            agendasMap[row.meeting_id].push({
              title: row.title,
              proposer: row.proposer,
              proposal_date: row.proposal_date,
              summary: row.summary,
              link: row.link
            });
          }

          const keywordsMap = {};
          for (const row of keywordsRes.rows) {
            if (!keywordsMap[row.meeting_id]) keywordsMap[row.meeting_id] = [];
            keywordsMap[row.meeting_id].push({
              word: row.word,
              count: row.count
            });
          }

          const speakersMap = {};
          for (const row of speakersRes.rows) {
            if (!speakersMap[row.meeting_id]) speakersMap[row.meeting_id] = [];
            speakersMap[row.meeting_id].push({
              name: row.speaker_name,
              speech_count: row.speech_count
            });
          }

          meetings = meetingsRes.rows.map(row => ({
            filename: row.filename,
            date: row.date,
            session_num: row.session_num,
            session_type: row.session_type,
            order_num: row.order_num,
            meeting_type: row.meeting_type,
            year: row.year,
            text_length: row.text_length,
            summary: row.summary,
            agenda_count: parseInt(row.agenda_count) || 0,
            speaker_count: parseInt(row.speaker_count) || 0,
            agendas: agendasMap[row.meeting_id] || [],
            keywords: keywordsMap[row.meeting_id] || [],
            speakers: speakersMap[row.meeting_id] || []
          }));
        }

        // Fetch global keywords from DB
        const globalKeywordsQuery = `
          SELECT word, SUM(count) as total_count
          FROM keywords
          WHERE speaker_name IS NULL
          GROUP BY word
          ORDER BY total_count DESC
          LIMIT 100;
        `;
        const globalKeywordsRes = await pool.query(globalKeywordsQuery);
        const globalKeywords = globalKeywordsRes.rows.map(row => ({
          word: row.word,
          count: parseInt(row.total_count) || 0
        }));

        res.status(200).json({
          success: true,
          total_count: meetings.length,
          generated_at: new Date().toISOString(),
          global_keywords: globalKeywords,
          meetings: meetings
        });
      } else {
        // 2. Local Fallback Mode (Read local meetings.json)
        const localPath = path.join('C:', 'Users', 'hp', '.gemini', 'antigravity', 'scratch', 'council_dashboard', 'data', 'meetings.json');
        if (!fs.existsSync(localPath)) {
          res.status(404).json({ success: false, message: 'Local meetings.json file not found' });
          return;
        }

        const raw = fs.readFileSync(localPath, 'utf8');
        const data = JSON.parse(raw);
        let meetings = data.meetings.map(m => ({
          filename: m.filename,
          date: m.date,
          session_num: m.session_num,
          session_type: m.session_type,
          order_num: m.order_num,
          meeting_type: m.meeting_type,
          year: m.year,
          text_length: m.text_length,
          summary: m.summary,
          speaker_count: m.speakers.length,
          agenda_count: m.agendas.length,
          agendas: m.agendas,
          keywords: m.keywords || [],
          speakers: m.speakers.map(s => ({
            name: s.name,
            speech_count: s.speech_count
          }))
        }));

        // Apply sorting in JS
        if (sortBy === 'session') {
          meetings.sort((a, b) => {
            const factor = sortOrder === 'desc' ? -1 : 1;
            if (a.session_num !== b.session_num) return (a.session_num - b.session_num) * factor;
            return (a.order_num - b.order_num) * factor;
          });
        } else if (sortBy === 'speakers') {
          meetings.sort((a, b) => {
            const factor = sortOrder === 'desc' ? -1 : 1;
            return (a.speaker_count - b.speaker_count) * factor;
          });
        } else {
          meetings.sort((a, b) => {
            const factor = sortOrder === 'desc' ? -1 : 1;
            return a.date.localeCompare(b.date) * factor;
          });
        }

        const sliced = meetings.slice(offset, offset + limit);

        res.status(200).json({
          success: true,
          total_count: data.total_count || meetings.length,
          generated_at: data.generated_at || new Date().toISOString(),
          global_keywords: data.global_keywords || [],
          meetings: sliced
        });
      }
    }
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
};
