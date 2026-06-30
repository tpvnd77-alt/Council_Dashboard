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
  res.setHeader('Access-Control-Allow-Credentials', true);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version');

  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  try {
    if (pool) {
      // 1. Cloud PostgreSQL Mode
      // Get speakers and total speech counts
      const speakerQuery = `
        SELECT speaker_name, SUM(speech_count) as total_speeches
        FROM (
          SELECT DISTINCT meeting_id, speaker_name, speech_count 
          FROM speeches
        ) t
        GROUP BY speaker_name
        ORDER BY total_speeches DESC;
      `;
      const speakerResult = await pool.query(speakerQuery);
      
      // Get speaker-level keywords
      const keywordQuery = `
        SELECT speaker_name, word, SUM(count) as total_count
        FROM keywords
        WHERE speaker_name IS NOT NULL
        GROUP BY speaker_name, word
        ORDER BY speaker_name, total_count DESC;
      `;
      const keywordResult = await pool.query(keywordQuery);
      
      // Map keywords to speakers
      const keywordsMap = {};
      for (const row of keywordResult.rows) {
        const name = row.speaker_name;
        if (!keywordsMap[name]) {
          keywordsMap[name] = [];
        }
        if (keywordsMap[name].length < 10) { // Limit to top 10 keywords
          keywordsMap[name].push({
            word: row.word,
            count: parseInt(row.total_count) || 0
          });
        }
      }

      const speakers = speakerResult.rows.map(row => ({
        name: row.speaker_name,
        speech_count: parseInt(row.total_speeches) || 0,
        keywords: keywordsMap[row.speaker_name] || []
      }));

      res.status(200).json({ success: true, speakers: speakers });
    } else {
      // 2. Local Fallback Mode
      const localPath = path.join('C:', 'Users', 'hp', '.gemini', 'antigravity', 'scratch', 'council_dashboard', 'data', 'meetings.json');
      if (!fs.existsSync(localPath)) {
        res.status(404).json({ success: false, message: 'Local meetings.json file not found' });
        return;
      }

      const raw = fs.readFileSync(localPath, 'utf8');
      const data = JSON.parse(raw);

      const speakersMap = {};
      for (const m of data.meetings) {
        for (const spk of m.speakers) {
          const name = spk.name;
          if (!speakersMap[name]) {
            speakersMap[name] = {
              name: name,
              speech_count: 0,
              keywords_counts: {}
            };
          }
          speakersMap[name].speech_count += spk.speech_count;
          
          for (const kw of spk.keywords || []) {
            speakersMap[name].keywords_counts[kw.word] = (speakersMap[name].keywords_counts[kw.word] || 0) + kw.count;
          }
        }
      }

      const speakers = Object.values(speakersMap).map(spk => {
        const kws = Object.entries(spk.keywords_counts)
          .map(([word, count]) => ({ word, count }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 10);
        return {
          name: spk.name,
          speech_count: spk.speech_count,
          keywords: kws
        };
      }).sort((a, b) => b.speech_count - a.speech_count);

      res.status(200).json({ success: true, speakers: speakers });
    }
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
};
