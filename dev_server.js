const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = 3000;

const server = http.createServer((req, res) => {
  const parsedUrl = url.parse(req.url, true);
  let pathname = parsedUrl.pathname;

  // Handle root and clean URLs mapping
  if (pathname === '/') {
    pathname = '/index.html';
  }

  // Route API requests to serverless function modules
  if (pathname.startsWith('/api/')) {
    const apiName = pathname.substring(5); // e.g. "meetings" or "search"
    const apiPath = path.join(__dirname, 'api', `${apiName}.js`);
    if (fs.existsSync(apiPath)) {
      try {
        // Clear require cache for live development editing
        delete require.cache[require.resolve(apiPath)];
        const handler = require(apiPath);
        
        // Mock req and res objects for Vercel
        const mockReq = {
          method: req.method,
          headers: req.headers,
          query: parsedUrl.query,
          url: req.url
        };
        const mockRes = {
          statusCode: 200,
          headers: {},
          setHeader(name, value) {
            this.headers[name.toLowerCase()] = value;
          },
          status(code) {
            this.statusCode = code;
            return this;
          },
          json(data) {
            this.setHeader('Content-Type', 'application/json; charset=utf-8');
            this.end(JSON.stringify(data));
          },
          end(data) {
            res.writeHead(this.statusCode, this.headers);
            res.end(data);
          }
        };
        handler(mockReq, mockRes);
      } catch (err) {
        res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end(`API Error: ${err.message}\n${err.stack}`);
      }
    } else {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('API EndPoint Not Found');
    }
  } else {
    // Serve static files
    const filePath = path.join(__dirname, pathname);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      let contentType = 'text/html; charset=utf-8';
      if (filePath.endsWith('.js')) contentType = 'application/javascript; charset=utf-8';
      else if (filePath.endsWith('.css')) contentType = 'text/css; charset=utf-8';
      else if (filePath.endsWith('.json')) contentType = 'application/json; charset=utf-8';

      res.writeHead(200, { 'Content-Type': contentType });
      fs.createReadStream(filePath).pipe(res);
    } else {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Static File Not Found');
    }
  }
});

server.listen(PORT, () => {
  console.log(`\n🚀 [System C Dev Server] Running at http://localhost:${PORT}`);
  console.log(`Checking local JSON fallback at: C:\\Users\\hp\\.gemini\\antigravity\\scratch\\council_dashboard\\data\\meetings.json`);
});
