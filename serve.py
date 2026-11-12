"""Start one web worker using the configured bind address and port."""
import os
import uvicorn

if __name__ == '__main__':
    uvicorn.run('app:app', host=os.getenv('PANEL_BIND', '127.0.0.1'), port=int(os.getenv('PANEL_PORT', '8080')),
                workers=1, proxy_headers=False, access_log=False)
