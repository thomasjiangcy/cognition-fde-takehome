import { useEffect, useState } from 'react'
import './App.css'

type ApiStatus = 'checking' | 'connected' | 'unavailable'

function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/health', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error('API health check failed')
        }
        return response.json() as Promise<{ status: string }>
      })
      .then(({ status }) => setApiStatus(status === 'ok' ? 'connected' : 'unavailable'))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setApiStatus('unavailable')
        }
      })

    return () => controller.abort()
  }, [])

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="Devin webhook dashboard home">
          <span className="brand-mark" aria-hidden="true">D</span>
          <span>Devin webhook dashboard</span>
        </a>
        <div className={`api-status api-status--${apiStatus}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          API {apiStatus}
        </div>
      </header>

      <main>
        <section className="hero">
          <p className="eyebrow">GitHub → Devin</p>
          <h1>Webhook activity,<br />at a glance.</h1>
          <p className="hero-copy">
            This dashboard will report on incoming GitHub events and the Devin
            sessions they start.
          </p>
        </section>

        <section className="dashboard-placeholder" aria-labelledby="dashboard-heading">
          <div>
            <p className="section-label">Dashboard</p>
            <h2 id="dashboard-heading">Analytics are coming next</h2>
          </div>
          <p>
            The React and Vite foundation is ready. Metrics and activity will
            appear here once the webhook flow is implemented.
          </p>
        </section>
      </main>
    </div>
  )
}

export default App
