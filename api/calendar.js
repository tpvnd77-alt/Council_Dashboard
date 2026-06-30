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
      const query = `
        SELECT date, filename as title, meeting_type
        FROM meetings
        ORDER BY date ASC;
      `;
      const { rows } = await pool.query(query);
      res.status(200).json({ success: true, events: rows });
    } else {
      // 2. Local Fallback Mode
      const localPath = path.join('C:', 'Users', 'hp', '.gemini', 'antigravity', 'scratch', 'council_dashboard', 'data', 'meetings.json');
      if (!fs.existsSync(localPath)) {
        res.status(404).json({ success: false, message: 'Local meetings.json file not found' });
        return;
      }

      const raw = fs.readFileSync(localPath, 'utf8');
      const data = JSON.parse(raw);

      const events = data.meetings.map(m => ({
        date: m.date,
        title: m.filename,
        meeting_type: m.meeting_type
      }));

      res.status(200).json({ success: true, events: events });
    }
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
};
