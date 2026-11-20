import { useEffect, useMemo, useState } from 'react'
import { Activity, BadgeCheck, Bitcoin, Boxes, ChartNoAxesCombined, ChevronRight, CircleHelp, Compass, LayoutDashboard, LockKeyhole, LogOut, Menu, MessageSquareText, Package, Radio, RefreshCw, Search, Shield, ShoppingBasket, Store, Wallet, X, Zap } from 'lucide-react'
import { approveNegotiation, checkInvoice, createInvoice, createMerchant, createProduct, getHealth, getNostrStatus, getNostrMerchants, getMyMerchant, getProducts, getUnsignedNostrListing, publishNostrListing, getMarketplace, getMerchants, getSecurityChecks, getSessions, getSessionMessages, getTransactions, runAgents, getMe, login, logout, register, simulateInvoicePayment, submitMerchantSettlement, getMerchantSettlement, getLightningStatus, connectAlbyWallets, getWalletBalance, getWalletTransactions, payInvoice } from './api'
import './App.css'

const nav = [
  ['Overview', LayoutDashboard], ['Marketplace', ShoppingBasket], ['Agent Arena', Activity], ['Negotiation', MessageSquareText],
  ['Lightning Wallet', Wallet], ['Merchant Portal', Store], ['Transactions', ChartNoAxesCombined], ['Security Center', Shield],
]
const agents = [
  ['Buyer Agent', 'Turns a request into a clear product, quantity, budget and location.', 'shopping'],
  ['Merchant Discovery', 'Finds available listings and ranks them by fit and total cost.', 'compass'],
  ['Merchant Agent', 'Builds offers from the merchant’s saved inventory and prices.', 'store'],
  ['Negotiation Agent', 'Compares offers, tracks counters and keeps the total within budget.', 'message'],
  ['Risk Guardian', 'Runs deterministic transaction checks before customer approval.', 'shield'],
]
const money = (n) => `${Number(n || 0).toLocaleString()} sats`

function App() {
  const [auth, setAuth] = useState(() => {
    try { return JSON.parse(localStorage.getItem('satoshi_user') || 'null') } catch { return null }
  })
  const [page, setPage] = useState('Overview')
  const [mobileNav, setMobileNav] = useState(false)
  const [health, setHealth] = useState(null)
  const [nostrStatus, setNostrStatus] = useState(null)
  const [nostrListings, setNostrListings] = useState([])
  const [nostrRelays, setNostrRelays] = useState([])
  const [market, setMarket] = useState([])
  const [merchants, setMerchants] = useState([])
  const [transactions, setTransactions] = useState([])
  const [sessions, setSessions] = useState([])
  const [checks, setChecks] = useState([])
  const [timelineMessages, setTimelineMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All categories')
  const [query, setQuery] = useState('I need 10 kg of rice in Dakar for a maximum total of 250,000 sats.')
  const [workflow, setWorkflow] = useState(null)
  const [invoice, setInvoice] = useState(null)
  const [walletStatus, setWalletStatus] = useState(null)
  const [walletError, setWalletError] = useState('')
  const [walletConnectForm, setWalletConnectForm] = useState({ buyer_url: '', merchant_url: '' })
  const [walletBalance, setWalletBalance] = useState(null)
  const [walletTransactions, setWalletTransactions] = useState([])
  const [appMode, setAppMode] = useState('demo')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [merchantForm, setMerchantForm] = useState({ name: '', location: 'Dakar, Senegal', description: '' })
  const [productForm, setProductForm] = useState({ merchant_id: '', name: '', category: 'Groceries', price_sats: '', quantity_available: '', description: '' })

  useEffect(() => {
    getHealth().then(({ data }) => { setHealth(data); setAppMode(data.payment_mode || 'demo') }).catch(() => {})
  }, [])

  const refreshWallet = async () => {
    if (appMode !== 'alby_sandbox' || auth?.role !== 'CUSTOMER') return
    const results = await Promise.allSettled([getLightningStatus(), getWalletBalance(), getWalletTransactions()])
    if (results[0].status === 'fulfilled') { setWalletStatus(results[0].value.data); setWalletError('') }
    else {
      const detail = results[0].reason?.response?.data?.detail
      setWalletStatus(null)
      setWalletError(typeof detail?.message === 'string' ? detail.message : typeof detail === 'string' ? detail : 'Could not verify both Alby faucet wallets.')
    }
    if (results[1].status === 'fulfilled') setWalletBalance(results[1].value.data)
    if (results[2].status === 'fulfilled') setWalletTransactions(results[2].value.data)
  }
  const connectWallets = async (event) => {
    event.preventDefault(); setBusy(true); setWalletError('')
    try {
      const { data } = await connectAlbyWallets(walletConnectForm)
      setWalletConnectForm({ buyer_url: '', merchant_url: '' })
      setWalletStatus(data)
      if (data.connected) setNotice('Both Alby Faucet wallets are connected.')
      else { setWalletError(data.connection_error || 'Wallet URLs saved, but the relay check did not complete. Try Refresh wallet.'); setNotice('Wallet URLs saved in this app session.') }
    } catch (error) {
      const detail = error.response?.data?.detail
      setWalletError(typeof detail === 'string' ? detail : detail?.message || 'Could not save these faucet wallet URLs.')
    } finally { setBusy(false) }
  }
  useEffect(() => { refreshWallet() }, [page, appMode, auth?.role])

  const refresh = async () => {
    setLoading(true)
    const settled = await Promise.allSettled([getHealth(), getMarketplace(), getMerchants(), getTransactions(), getSessions(), getSecurityChecks(), getNostrStatus()])
    if (settled[0].status === 'fulfilled') { setHealth(settled[0].value.data); setAppMode(settled[0].value.data.payment_mode || 'demo') }
    if (settled[1].status === 'fulfilled') setMarket(settled[1].value.data)
    if (settled[2].status === 'fulfilled') setMerchants(settled[2].value.data)
    if (settled[3].status === 'fulfilled') setTransactions(settled[3].value.data)
    if (settled[4].status === 'fulfilled') {
      const rows = settled[4].value.data
      setSessions(rows)
      if (rows[0]) {
        try { setTimelineMessages((await getSessionMessages(rows[0].session_id)).data) } catch { setTimelineMessages([]) }
      } else setTimelineMessages([])
    }
    if (settled[5].status === 'fulfilled') setChecks(settled[5].value.data)
    if (settled[6].status === 'fulfilled') setNostrStatus(settled[6].value.data)
    if (settled.every((x) => x.status === 'rejected')) setNotice('Could not connect to the backend. Start the API at localhost:8000 and refresh.')
    setLoading(false)
  }
  useEffect(() => {
    if (!auth) return
    let active = true
    getMe().then(({ data }) => { if (active) { setAuth(data); localStorage.setItem('satoshi_user', JSON.stringify(data)); refresh() } }).catch(() => {
      localStorage.removeItem('satoshi_access_token'); localStorage.removeItem('satoshi_user'); setAuth(null)
    })
    return () => { active = false }
  }, [auth?.id])

  const acceptAuth = (data) => {
    localStorage.setItem('satoshi_access_token', data.access_token)
    localStorage.setItem('satoshi_user', JSON.stringify(data.user))
    setAuth(data.user)
    setPage('Overview')
  }
  const signOut = async () => {
    try { await logout() } catch { /* token may have expired; local logout still applies */ }
    localStorage.removeItem('satoshi_access_token'); localStorage.removeItem('satoshi_user'); setAuth(null)
  }

  const filtered = useMemo(() => market.filter((p) => {
    const match = `${p.product_name} ${p.merchant_name} ${p.merchant_location}`.toLowerCase().includes(search.toLowerCase())
    return match && (category === 'All categories' || p.category?.toLowerCase() === category.toLowerCase())
  }), [market, search, category])
  const categories = useMemo(() => ['All categories', ...new Set(market.map((x) => x.category).filter(Boolean))], [market])
  const totalVolume = transactions.filter((x) => x.status === 'COMPLETED').reduce((n, x) => n + x.amount_sats, 0)
  const latestSession = sessions[0]
  const latestMessages = workflow && latestSession && workflow.session_id === latestSession.session_id ? workflow.messages : timelineMessages

  const runWorkflow = async (event) => {
    event.preventDefault(); setBusy(true); setNotice('')
    try {
      const result = (await runAgents(query, 'Dakar, Senegal')).data
      setWorkflow(result); setInvoice(null); setPage('Negotiation')
      setNotice(result.negotiation?.best_merchant ? 'Offers are ready for your review.' : 'No matching in-stock offers were found.')
      await refresh()
    } catch (e) { setNotice(e.response?.data?.detail?.error || e.response?.data?.detail || 'The agent workflow could not complete.') }
    finally { setBusy(false) }
  }
  const approve = async () => {
    const id = workflow?.negotiation?.negotiation_id
    if (!id) return
    setBusy(true)
    try {
      if (!workflow.negotiation?.approved_by_customer) await approveNegotiation(id)
      setWorkflow((current) => current ? { ...current, negotiation: { ...current.negotiation, approved_by_customer: true } } : current)
      const result = (await createInvoice({ negotiation_id: id, amount_sats: workflow.negotiation.agreed_price_sats, description: `Order with ${workflow.negotiation.best_merchant.merchant_name}` })).data
      setInvoice(result); setNotice(result.payment_mode === 'demo' ? 'Approval recorded. Demo invoice created; it cannot receive real Bitcoin.' : `${result.payment_mode.toUpperCase()} invoice created and checked against its Lightning network.`)
      await refresh()
    } catch (e) { const detail = e.response?.data?.detail; setNotice(typeof detail === 'string' ? detail : detail?.message || e.message || 'Approval or invoice creation failed validation.') }
    finally { setBusy(false) }
  }
  const pollInvoice = async () => {
    if (!invoice?.invoice_id) return
    try { setInvoice((await checkInvoice(invoice.invoice_id)).data); await refreshWallet(); await refresh() } catch { setNotice('Could not refresh invoice status.') }
  }
  const approveAndPayInvoice = async () => {
    if (!invoice?.invoice_id || invoice.payment_mode !== 'alby_sandbox' || invoice.payment_attempted) return
    setBusy(true)
    try {
      const result = (await payInvoice(invoice.invoice_id)).data
      setInvoice(result)
      setNotice(result.status === 'PAID' && result.merchant_verification === 'verified' ? 'TEST PAYMENT — VERIFIED' : 'Payment was sent. The merchant wallet is checking receipt; refresh to confirm.')
      await refreshWallet(); await refresh()
    } catch (error) {
      if (error.response?.data?.detail?.retry_allowed === false) setInvoice((current) => ({ ...current, status: 'PAYMENT_UNKNOWN', payment_attempted: true }))
      setNotice(typeof error.response?.data?.detail?.message === 'string' ? error.response.data.detail.message : 'Payment could not be confirmed. Refresh invoice status before taking another action.')
      await refreshWallet()
    } finally { setBusy(false) }
  }
  const simulateDemoPayment = async () => {
    if (!invoice?.invoice_id || appMode !== 'demo') return
    try { const result = (await simulateInvoicePayment(invoice.invoice_id)).data; setInvoice((current) => ({ ...current, status: result.status })); setNotice('Demo payment simulated locally. No Bitcoin or Lightning network was used.'); await refresh() }
    catch { setNotice('This demo invoice can no longer be simulated.') }
  }
  const discoverNostr = async () => {
    setBusy(true)
    try { const result = (await getNostrMerchants()).data; setNostrListings(result.events || []); setNostrRelays(result.relays || []); setNotice(result.count ? `Verified ${result.count} signed Nostr listing(s).` : 'No valid SatoshiBazaar events found on the configured relays.') }
    catch { setNotice('Relay discovery failed. Local marketplace listings remain available.') }
    finally { setBusy(false) }
  }
  const addMerchant = async (event) => {
    event.preventDefault(); setBusy(true)
    try { const m = (await createMerchant({ ...merchantForm, is_demo: appMode === 'demo' })).data; setMerchantForm({ name: '', location: 'Dakar, Senegal', description: '' }); await refresh(); setProductForm((x) => ({ ...x, merchant_id: String(m.id) })); setNotice(`${appMode.toUpperCase()} merchant profile saved.`) }
    catch { setNotice('Merchant profile could not be saved.') } finally { setBusy(false) }
  }
  const addProduct = async (event) => {
    event.preventDefault(); setBusy(true)
    try { await createProduct({ ...productForm, merchant_id: Number(productForm.merchant_id), price_sats: Number(productForm.price_sats), quantity_available: Number(productForm.quantity_available), is_demo: appMode === 'demo' }); setProductForm((x) => ({ ...x, name: '', price_sats: '', quantity_available: '', description: '' })); await refresh(); setNotice(`${appMode.toUpperCase()} product added to the marketplace.`) }
    catch { setNotice('Product could not be saved. Select a merchant and enter valid values.') } finally { setBusy(false) }
  }

  const statCards = [
    ['Merchants', merchants.length, Store, '+ local sellers'], ['Available products', market.length, Boxes, 'Across active listings'],
    ['Agent sessions', sessions.length, Activity, 'Persisted workflows'], ['Completed transactions', transactions.filter((x) => x.status === 'COMPLETED').length, BadgeCheck, 'Provider verified'],
  ]
  if (!auth) return <AuthScreen onAuthenticated={acceptAuth} paymentMode={appMode}/>
  return <div className="app-shell">
    {mobileNav && <button aria-label="Close navigation" className="mobile-scrim" onClick={() => setMobileNav(false)} />}
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Bitcoin size={21}/></div><div><strong>Satoshi<span>Bazaar</span></strong><small>LOCAL COMMERCE NETWORK</small></div><button className="icon-button mobile-close" onClick={() => setMobileNav(false)} aria-label="Close"><X size={18}/></button></div>
      <div className="nav-label">WORKSPACE</div><nav>{nav.filter(([label]) => auth.role === 'MERCHANT' ? ['Overview', 'Marketplace', 'Merchant Portal', 'Transactions', 'Security Center'].includes(label) : true).map(([label, Icon]) => <button key={label} className={`nav-item ${page === label ? 'active' : ''}`} onClick={() => { setPage(label); setMobileNav(false) }}><Icon size={18}/><span>{label}</span>{label === 'Negotiation' && workflow && <i className="nav-live"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="network-card"><div className="network-head"><span className={`live-dot ${health ? '' : 'offline'}`}/><span>{health ? 'API connected' : 'Connecting'}</span><span className="demo-tag">{appMode.toUpperCase()}</span></div><p>{appMode === 'demo' ? 'Payments are simulated locally; no Bitcoin is transferred.' : health?.payment_provider_configured ? `${appMode.toUpperCase()} Lightning network is configured.` : `${appMode.toUpperCase()} payment provider is not configured.`}</p></div><div className="user-chip"><div className="avatar">SB</div><div><strong>Local workspace</strong><small>Dakar, Senegal</small></div><ChevronRight size={16}/></div></div>
    </aside>
    <main className="main-area"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={19}/></button><div className="crumb">Workspace <ChevronRight size={14}/> <strong>{page}</strong></div></div><div className="top-actions"><span className="mode-control"><span>PAYMENT MODE</span><b>{appMode.toUpperCase()}</b><small>{health?.payment_network || 'initializing'}</small></span><button className="icon-button refresh" onClick={refresh} aria-label="Refresh data" title="Refresh data"><RefreshCw size={17}/></button><span className="signed-user">{auth.username}</span><button className="icon-button" onClick={signOut} aria-label="Log out" title="Log out"><LogOut size={16}/></button></div></header>
      <div className="page-wrap"><div className="page-heading"><div><p className="eyebrow">{auth.role} · DAKAR, SENEGAL</p><h1>{page === 'Overview' ? `Welcome, ${auth.username}` : page}</h1><p className="subtitle">{page === 'Overview' ? 'Your local marketplace at a glance.' : descriptions[page]}</p></div>{page === 'Marketplace' && auth.role === 'CUSTOMER' && <button className="button primary" onClick={() => setPage('Negotiation')}><Zap size={16}/> Find with AI</button>}</div>
        {notice && <div className="notice"><CircleHelp size={16}/><span>{typeof notice === 'string' ? notice : JSON.stringify(notice)}</span><button onClick={() => setNotice('')} aria-label="Dismiss"><X size={15}/></button></div>}
        {loading && <div className="loading-line"><span/> Syncing marketplace data…</div>}
        {page === 'Overview' && <><section className="stats-grid">{statCards.map(([name, value, Icon, hint]) => <article className="stat-card" key={name}><div className="stat-top"><span>{name}</span><span className="stat-icon"><Icon size={17}/></span></div><strong>{loading ? '—' : value}</strong><small>{hint}</small></article>)}</section><section className="overview-grid"><article className="panel welcome-panel"><div className="welcome-copy"><span className="pill orange-pill"><Zap size={13}/> LOCAL, OPEN, HUMAN-CONTROLLED</span><h2>Commerce that works<br/>for your community.</h2><p>Find fair offers from local merchants, compare prices, and stay in control of every payment.</p><button className="button light-button" onClick={() => setPage('Marketplace')}>Explore marketplace <ChevronRight size={16}/></button></div><div className="welcome-art"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="art-bitcoin"><Bitcoin size={42}/></div><div className="float-card float-one"><span>Best local offer</span><b>24,000 <small>sats</small></b></div><div className="float-card float-two"><BadgeCheck size={14}/> Customer approved</div></div></article><article className="panel system-panel"><div className="section-title"><div><h3>Network status</h3><p>Connected services</p></div><span className="soft-badge">API</span></div><ServiceRow icon={Zap} name="Lightning payments" status={health?.payment_mode === 'demo' ? 'Simulated locally' : health?.payment_provider_configured ? `${appMode.toUpperCase()} provider configured` : 'Needs configuration'} good={health?.payment_mode === 'demo' || Boolean(health?.payment_provider_configured)}/><ServiceRow icon={Radio} name="Nostr relay" status={nostrStatus?.connectivity === 'connected' ? 'Relay connected' : nostrStatus?.connectivity === 'unavailable' ? 'Relay unavailable' : nostrStatus?.connectivity === 'not_configured' ? 'Local only' : 'Checking relays'} good={nostrStatus?.connectivity === 'connected'}/><ServiceRow icon={Activity} name="Agent orchestrator" status={health ? 'Operational' : 'Offline'} good={Boolean(health)}/><div className="safe-note"><Shield size={16}/><span>Every payment requires your explicit approval.</span></div></article></section><section className="panel table-panel"><div className="section-title"><div><h3>Recent transactions</h3><p>Latest payment activity from your workspace</p></div><button className="text-link" onClick={() => setPage('Transactions')}>View all <ChevronRight size={15}/></button></div><TransactionsTable rows={transactions.slice(0, 5)}/></section><section className="panel activity-panel"><div className="section-title"><div><h3>Agent activity</h3><p>Recent persisted workflow sessions</p></div><button className="text-link" onClick={() => setPage('Agent Arena')}>Open arena <ChevronRight size={15}/></button></div>{sessions.slice(0, 3).length ? sessions.slice(0, 3).map((s) => <div className="activity-row" key={s.session_id}><span className="activity-icon"><Activity size={16}/></span><div><b>Agent workflow {s.status}</b><small>{formatDate(s.created_at)}</small></div><span className="mono">{s.session_id.slice(0, 8)}</span></div>) : <Empty text="Agent activity will appear here when a workflow runs."/>}</section></>}
        {page === 'Marketplace' && <><div className="filterbar"><label className="searchbox"><Search size={17}/><input placeholder="Search products, merchants or location" value={search} onChange={(e) => setSearch(e.target.value)}/></label><select value={category} onChange={(e) => setCategory(e.target.value)}>{categories.map((c) => <option key={c}>{c}</option>)}</select><span className="result-count">{filtered.length} local listings</span><button className="button outline-button" onClick={discoverNostr} disabled={busy}><Radio size={14}/> Discover Nostr</button></div><div className="product-grid">{filtered.map((item) => <article className="product-card" key={item.product_id}><div className="product-visual"><span className="category-tag">{item.category}</span><div className="product-emoji">{productEmoji(item.product_name)}</div><span className="source-tag">{item.is_demo ? 'DEMO LISTING' : item.listing_source === 'nostr_relay' ? 'NOSTR RELAY' : 'LOCAL LISTING'}</span></div><div className="product-body"><div className="product-title"><h3>{item.product_name}</h3><span className="stock">{item.quantity_available} available</span></div><p className="merchant-line"><Store size={14}/>{item.merchant_name}<span>·</span><Compass size={13}/>{item.merchant_location}</p><div className="product-footer"><div><strong>{money(item.price_sats)}</strong><small>per listed unit</small></div><button className="button outline-button" onClick={() => { setQuery(`I need ${item.product_name} from ${item.merchant_location} for a maximum total of ${item.price_sats} sats.`); setPage('Negotiation') }}>Request offer <ChevronRight size={15}/></button></div></div></article>)}</div>{!filtered.length && <Empty text="No listings match those filters."/>}{nostrListings.length > 0 && <section className="panel table-panel nostr-results"><div className="section-title"><div><h3>Verified Nostr relay listings</h3><p>Signature and event ID verified. External inventory is not locally reserved.</p></div><span className="soft-badge">{nostrListings.length} EVENTS</span></div><div className="nostr-list">{nostrListings.map((event) => { let listing = {}; try { listing = JSON.parse(event.content) } catch {} return <div className="activity-row" key={event.id}><span className="activity-icon"><Radio size={16}/></span><div><b>{listing.product} · {listing.merchant_name}</b><small>{listing.location} · {listing.quantity_available} listed · {event.pubkey.slice(0, 12)}…</small></div><strong className="amount-cell">{money(listing.price_sats)}</strong><span className="source-tag nostr-source">NOSTR</span></div> })}</div>{nostrRelays.map((relay) => <small className="relay-status" key={relay.relay}>{relay.relay}: {relay.connected ? `${relay.events} verified events` : relay.error}</small>)}</section>}</>}
        {page === 'Agent Arena' && <><section className="arena-intro"><div><span className="pill"><Activity size={13}/> ORCHESTRATED WORKFLOW</span><h2>Five specialists. One clear outcome.</h2><p>Each agent runs in sequence and records its messages in the backend session log.</p></div><button className="button primary" onClick={() => setPage('Negotiation')}><Zap size={16}/> Start a workflow</button></section><div className="agent-grid">{agents.map(([name, role], i) => <article className="panel agent-card" key={name}><div className="agent-card-top"><div className={`agent-icon agent-${i}`}><AgentIcon index={i}/></div><span className="soft-badge">{i === 4 ? 'GUARDRAIL' : 'READY'}</span></div><h3>{name}</h3><p>{role}</p><div className="agent-meta"><span><Activity size={14}/> {i === 0 ? sessions.length : sessions.length} tasks</span><span>Stage 0{i + 1}</span></div></article>)}</div><section className="panel timeline-panel"><div className="section-title"><div><h3>Latest persisted activity</h3><p>Messages generated by real backend workflow runs</p></div><button className="text-link" onClick={refresh}><RefreshCw size={14}/> Refresh</button></div>{latestSession ? <div className="session-detail"><div className="session-banner"><span className="live-dot"/><div><b>Session {latestSession.session_id.slice(0, 12)}</b><small>{latestSession.status} · {formatDate(latestSession.created_at)}</small></div><span className="soft-badge">{latestSession.status}</span></div>{latestMessages.length ? latestMessages.map((m) => <div className="message-row" key={m.message_id}><div className="message-node"/><div><b>{prettyAgent(m.sender_agent)} <span>→ {prettyAgent(m.recipient_agent)}</span></b><p>{m.message_type.replaceAll('_', ' ')}</p><small>{formatDate(m.created_at)}</small></div></div>) : <p className="muted">Run a workflow to inspect its saved message timeline.</p>}</div> : <Empty text="No agent sessions yet. Start a negotiation to populate the timeline."/>}</section></>}
        {page === 'Negotiation' && <div className="negotiation-layout"><section className="panel request-panel"><div className="section-title"><div><h3>Describe what you need</h3><p>The buyer agent extracts product, quantity, total budget and location.</p></div><span className="step-badge">01</span></div><form onSubmit={runWorkflow}><label className="field-label">Purchase request</label><textarea className="request-input" value={query} onChange={(e) => setQuery(e.target.value)} rows="4"/><div className="hint-row"><span><Shield size={14}/> Your budget is enforced by the backend</span><span>Demo agents · no API key required</span></div><button className="button primary wide-button" disabled={busy || !query.trim()}>{busy ? <><span className="button-spinner"/> Working through agents…</> : <><Zap size={16}/> Find and negotiate offers</>}</button></form>{workflow && <div className="parsed-box"><div className="parsed-title"><BadgeCheck size={15}/> Buyer request parsed <span>{workflow.buyer_result?.parsed_by || 'agent'}</span></div><div className="parsed-grid"><span>Product<b>{workflow.buyer_result?.product}</b></span><span>Quantity<b>{workflow.buyer_result?.quantity}</b></span><span>Budget<b>{money(workflow.buyer_result?.budget_sats)}</b></span><span>Location<b>{workflow.buyer_result?.location}</b></span></div></div>}</section><section className="panel offer-panel"><div className="section-title"><div><h3>Offers & recommendation</h3><p>Stored merchant prices, checked against available stock</p></div><span className="step-badge">02</span></div>{workflow?.offers?.length ? <><div className="offer-list">{workflow.offers.map((o) => { const chosen = workflow.negotiation?.best_merchant?.merchant_id === o.merchant_id; return <div className={`offer-row ${chosen ? 'best-offer' : ''}`} key={`${o.merchant_id}-${o.product_id}`}><div className="merchant-avatar">{o.merchant_name?.slice(0, 1)}</div><div className="offer-merchant"><b>{o.merchant_name}{chosen && <span className="recommended">BEST FIT</span>}</b><small>{o.quantity_available} in stock · demo merchant</small></div><div className="offer-price"><b>{money(o.total_price_sats || o.asking_price_sats)}</b><small>{money(o.asking_price_sats)} per unit</small></div></div>})}</div><div className="recommendation"><div><span className="recommend-label"><BadgeCheck size={14}/> RECOMMENDED OFFER</span><h3>{workflow.negotiation?.best_merchant?.merchant_name || 'No offer'}</h3><p>{workflow.negotiation?.best_merchant?.product_name}</p></div><div className="recommend-price"><strong>{money(workflow.negotiation?.agreed_price_sats)}</strong><small>total · {workflow.negotiation?.within_budget ? `${money((workflow.buyer_result?.budget_sats || 0) - (workflow.negotiation?.agreed_price_sats || 0))} under budget` : 'over budget'}</small></div></div><div className="mode-note">Checkout mode: <b>{appMode.toUpperCase()} ? {health?.payment_network || 'network validating'}</b></div><div className="risk-summary"><Shield size={17}/><div><b>Risk Guardian {workflow.risk_assessment?.is_valid ? 'checks passed' : 'needs review'}</b><small>{workflow.risk_assessment?.checks?.length || 0} deterministic checks recorded · customer approval required</small></div><span className={`status-pill ${workflow.risk_assessment?.is_valid ? 'status-ok' : 'status-warn'}`}>{workflow.risk_assessment?.is_valid ? 'READY' : 'BLOCKED'}</span></div>{!workflow.negotiation?.approved_by_customer ? <button className="button primary wide-button" disabled={busy || !workflow.risk_assessment?.is_valid || !workflow.negotiation?.within_budget} onClick={approve}><LockKeyhole size={16}/> Review and approve offer</button> : !invoice && <button className="button primary wide-button" disabled={busy} onClick={approve}><RefreshCw size={16}/> Retry invoice creation</button>}<div className="rounds"><h4>Negotiation history</h4>{workflow.negotiation?.all_rounds?.map((merchantRound) => merchantRound.rounds?.map((round) => <div className="round-row" key={`${merchantRound.merchant_id}-${round.round}`}><span>Round {round.round}</span><p>{round.reasoning}</p><b>{money(round.merchant_offer)}</b></div>))}</div></> : <div className="offer-empty"><div className="offer-empty-icon"><Compass size={22}/></div><b>Offers will show up here</b><p>Start a workflow and the agents will search available marketplace inventory.</p><div className="mini-steps"><span>01 Buyer request</span><ChevronRight size={13}/><span>02 Discovery</span><ChevronRight size={13}/><span>03 Risk review</span></div></div>}</section>{invoice && <section className="panel invoice-panel"><div className="section-title"><div><h3>Invoice created</h3><p>{invoice.payment_mode === 'demo' ? 'SIMULATED DEMO INVOICE ? NON-PAYABLE' : `${invoice.payment_mode.toUpperCase()} BOLT11 INVOICE`}</p></div><span className="demo-tag">{invoice.payment_mode?.toUpperCase()}</span></div><div className="invoice-content"><div className="demo-qr">{invoice.qr_code_data ? <img className="invoice-qr" src={invoice.qr_code_data} alt="Lightning invoice QR code"/> : <div className="demo-stamp">DEMO</div>}<span>{invoice.payment_mode === 'demo' ? 'SIMULATED ? NO NETWORK PAYMENT' : `SCAN ${invoice.payment_mode.toUpperCase()} WALLET`}</span></div><div className="invoice-info"><span className="eyebrow">AMOUNT DUE</span><strong>{money(invoice.amount_sats)}</strong><div className="invoice-code">{invoice.bolt11}</div><span className="status-pill status-pending">{invoice.status}</span><button className="button outline-button" onClick={pollInvoice}><RefreshCw size={14}/> Refresh status</button>{invoice.payment_mode === 'demo' && invoice.status === 'PENDING' && <button className="button primary" onClick={simulateDemoPayment}>Simulate demo payment</button>}</div></div></section>}</div>}
        {page === 'Lightning Wallet' && <><section className="wallet-hero panel"><div className="wallet-orb"><Bitcoin size={32}/></div><div><span className="pill orange-pill">{appMode === 'alby_sandbox' ? 'ALBY SANDBOX' : health?.payment_provider_configured ? `${appMode.toUpperCase()} CONFIGURED` : `${appMode.toUpperCase()} NOT CONFIGURED`}</span><h2>Lightning wallet</h2><p>Invoice generation follows Risk Guardian approval. Every payment needs a separate buyer approval.</p></div><div className="wallet-balance"><small>{appMode === 'alby_sandbox' ? 'BUYER TEST BALANCE' : 'COMPLETED VOLUME'}</small><strong>{appMode === 'alby_sandbox' ? (walletBalance ? `${Number(walletBalance.balance_sats).toLocaleString()} sats` : '—') : money(totalVolume)}</strong><span>{walletTransactions.length || transactions.length} recorded transactions</span></div></section>{appMode === 'alby_sandbox' ? <><div className="info-banner"><LockKeyhole size={17}/><div><b>{walletStatus?.connected ? 'Wallet connection verified' : walletError ? 'Wallet connection failed' : 'Wallet connection needs configuration'}</b><p>Alby NWC Faucet Sandbox. Balances are simulated and have no real monetary value. No real Bitcoin is transferred.</p><small>Buyer: {walletStatus?.buyer_wallet?.alias || 'not connected'} · Merchant: {walletStatus?.merchant_wallet?.alias || 'not connected'}</small>{walletError && <small>{walletError}</small>}{health?.payment_mode_blockers?.length > 0 && <small>{health.payment_mode_blockers.join(' ')}</small>}</div><button className="button outline-button" onClick={refreshWallet}>Refresh wallet</button></div>{health?.wallet_configuration_available && <section className="panel form-panel wallet-connect-panel"><div className="section-title"><div><h3>Connect Alby Faucet wallets</h3><p>Paste two distinct wallet URLs from faucet.nwc.dev to use this app.</p></div><Wallet size={19}/></div><form className="stack-form" onSubmit={connectWallets}><Field label="Buyer wallet connection URL" type="password" autoComplete="off" required value={walletConnectForm.buyer_url} onChange={(buyer_url) => setWalletConnectForm({ ...walletConnectForm, buyer_url })} placeholder="nostr+walletconnect://?"/><Field label="Merchant wallet connection URL" type="password" autoComplete="off" required value={walletConnectForm.merchant_url} onChange={(merchant_url) => setWalletConnectForm({ ...walletConnectForm, merchant_url })} placeholder="nostr+walletconnect://?"/><button className="button primary" disabled={busy || !walletConnectForm.buyer_url || !walletConnectForm.merchant_url}>{busy ? 'Connecting?' : 'Connect wallets'}</button></form><small>URLs are held in backend memory and cleared when the backend restarts. They are not shown back or saved in browser storage. Faucet balances are simulated.</small></section>}{invoice?.payment_mode === 'alby_sandbox' && <section className="panel invoice-panel"><div className="section-title"><div><h3>Alby sandbox invoice</h3><p>MERCHANT INVOICE · {invoice.amount_msat?.toLocaleString()} MSAT</p></div><span className="demo-tag">{invoice.status}</span></div><div className="invoice-content"><div className="demo-qr">{invoice.qr_code_data ? <img className="invoice-qr" src={invoice.qr_code_data} alt="Lightning invoice QR code"/> : <div className="demo-stamp">ALBY</div>}<span>SCAN BOLT11 INVOICE</span></div><div className="invoice-info"><span className="eyebrow">AMOUNT DUE</span><strong>{money(invoice.amount_sats)}</strong><div className="invoice-code">{invoice.bolt11}</div><span className={`status-pill ${invoice.status === 'PAID' ? 'status-ok' : invoice.status === 'FAILED' || invoice.status === 'EXPIRED' ? 'status-warn' : 'status-pending'}`}>{invoice.status}{invoice.merchant_verification === 'verified' ? ' · MERCHANT VERIFIED' : ''}</span><button className="button outline-button" onClick={pollInvoice}><RefreshCw size={14}/> Check merchant status</button>{invoice.status === 'PENDING' && !invoice.payment_attempted && <button className="button primary" disabled={busy} onClick={approveAndPayInvoice}><LockKeyhole size={15}/> Approve & pay {money(invoice.amount_sats)}</button>}{invoice.payment_attempted && invoice.status !== 'PAID' && <small>Payment attempt recorded. Refresh status; do not retry.</small>}</div></div></section>}<section className="panel table-panel"><div className="section-title"><div><h3>Alby wallet activity</h3><p>Buyer wallet transaction history</p></div></div>{walletTransactions.length ? <div className="audit-list">{walletTransactions.map((row, index) => <div className="audit-row" key={`${row.payment_hash || 'tx'}-${index}`}><span className={`audit-dot ${row.status === 'PAID' ? 'pass' : ''}`}/><div><b>{row.type || 'Lightning'} · {money(Math.abs(row.amount_sats))}</b><small>{walletStatus?.buyer_wallet?.alias} · {formatDate(typeof row.created_at === 'number' ? row.created_at * 1000 : row.created_at)}</small></div><span className="status-pill">{row.status}</span></div>)}</div> : <Empty text="No Alby faucet wallet activity yet."/>}</section></> : <><div className="info-banner"><LockKeyhole size={17}/><div><b>Payments stay under your control</b><p>Demo invoices are non-payable references. Lightning status updates only after provider verification.</p>{health?.payment_mode_blockers?.length > 0 && <small>{health.payment_mode_blockers.join(" ")}</small>}</div></div><section className="panel table-panel"><div className="section-title"><div><h3>Invoice & transaction history</h3><p>Persisted transaction records</p></div></div><TransactionsTable rows={transactions}/></section></>}</>}
        {page === 'Merchant Portal' && <div className="merchant-layout"><section className="panel form-panel"><div className="section-title"><div><h3>Create merchant profile</h3><p>Profiles belong to your merchant account.</p></div><Store size={19}/></div><form onSubmit={addMerchant} className="stack-form"><Field label="Merchant name" required value={merchantForm.name} onChange={(name) => setMerchantForm({ ...merchantForm, name })} placeholder="e.g. Medina Fresh Market"/><Field label="Location" required value={merchantForm.location} onChange={(location) => setMerchantForm({ ...merchantForm, location })}/><label className="field-label">Description<textarea value={merchantForm.description} onChange={(e) => setMerchantForm({ ...merchantForm, description: e.target.value })} placeholder="Tell customers about your store" rows="3"/></label><button className="button primary" disabled={busy}>Save merchant profile</button></form><div className="merchant-list">{merchants.map((m) => <div className="merchant-list-row" key={m.id}><div className="merchant-avatar">{m.name?.slice(0,1)}</div><div><b>{m.name}</b><small>{m.location}</small></div><span className={m.is_demo ? 'demo-tag' : 'soft-badge'}>{m.is_demo ? 'DEMO' : 'LOCAL'}</span></div>)}</div></section><section className="panel form-panel"><div className="section-title"><div><h3>Add a product</h3><p>Price is stored per listing unit; inventory is checked by agents.</p></div><Package size={19}/></div><form onSubmit={addProduct} className="stack-form"><label className="field-label">Merchant<select required value={productForm.merchant_id} onChange={(e) => setProductForm({ ...productForm, merchant_id: e.target.value })}><option value="">Select merchant</option>{merchants.map((m) => <option value={m.id} key={m.id}>{m.name}</option>)}</select></label><Field label="Product name" required value={productForm.name} onChange={(name) => setProductForm({ ...productForm, name })} placeholder="Rice 1kg"/><div className="two-fields"><Field label="Price (sats, max 10,000)" type="number" min="1" max="10000" required value={productForm.price_sats} onChange={(price_sats) => setProductForm({ ...productForm, price_sats })}/><Field label="Stock" type="number" required value={productForm.quantity_available} onChange={(quantity_available) => setProductForm({ ...productForm, quantity_available })}/></div><Field label="Category" value={productForm.category} onChange={(category) => setProductForm({ ...productForm, category })}/><button className="button primary" disabled={busy || !merchants.length}>Add local listing</button></form></section></div>}
        {page === 'Transactions' && auth.role === 'MERCHANT' && <MerchantSettlementPanel rows={transactions} onRefresh={refresh} onNotice={setNotice}/>}
        {page === 'Transactions' && <section className="panel table-panel"><div className="section-title"><div><h3>Transaction history</h3><p>Completed provider verifications and demo records are labeled separately.</p></div><span className="soft-badge">{transactions.length} RECORDS</span></div><TransactionsTable rows={transactions} full/></section>}
        {page === 'Security Center' && <><section className="security-banner"><div className="security-emblem"><Shield size={27}/></div><div><span className="eyebrow">TRANSACTION SAFETY</span><h2>Human approval is always required.</h2><p>Risk rules run on the backend before an invoice can be created. AI agents cannot authorize or send payments.</p></div></section><div className="security-grid">{[['Customer approval', 'Required before invoice creation', LockKeyhole], ['Budget enforcement', 'Offer total must fit the requested budget', Wallet], ['Invoice matching', 'Invoice amount must match negotiated total', BadgeCheck], ['Duplicate prevention', 'Paid invoices block repeat processing', Shield], ['Transaction limit', 'Hard cap of 1,000,000 sats', Bitcoin], ['Provider verification', 'Real payment status comes from LNbits', Radio]].map(([a,b,Icon]) => <article className="panel security-rule" key={a}><div className="rule-icon"><Icon size={18}/></div><div><b>{a}</b><p>{b}</p></div><BadgeCheck className="rule-check" size={18}/></article>)}</div><section className="panel table-panel"><div className="section-title"><div><h3>Security audit history</h3><p>Persisted Risk Guardian validation results</p></div></div>{checks.length ? <div className="audit-list">{checks.map((check) => <div className="audit-row" key={check.id}><span className={`audit-dot ${check.result === 'PASS' ? 'pass' : 'fail'}`}/><div><b>{check.check_type.replaceAll('_', ' ')}</b><small>{check.details?.reason || check.result}</small></div><span className={`status-pill ${check.result === 'PASS' ? 'status-ok' : 'status-warn'}`}>{check.result}</span><time>{formatDate(check.created_at)}</time></div>)}</div> : <Empty text="Risk checks will be recorded when an offer is evaluated."/>}</section></>}
        {page === 'Merchant Portal' && auth.role === 'MERCHANT' && <MerchantNostrPanel onNotice={setNotice} onRefresh={refresh}/>}
        <footer className="footer"><span>© 2026 SatoshiBazaar</span><span><Shield size={13}/> Human-controlled payments ? {appMode.toUpperCase()} mode</span></footer>
      </div>
    </main>
  </div>
}

function AuthScreen({ onAuthenticated, paymentMode }) {
  const [mode, setMode] = useState('login')
  const [role, setRole] = useState('CUSTOMER')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event) => {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const response = mode === 'login'
        ? await login({ email, password })
        : await register({ email, username, password, role })
      onAuthenticated(response.data)
    } catch (e) {
      setError(authErrorMessage(e, mode))
    } finally { setBusy(false) }
  }
  return <main className="auth-shell"><section className="auth-story"><div className="brand auth-brand"><div className="brand-mark"><Bitcoin size={21}/></div><div><strong>Satoshi<span>Bazaar</span></strong><small>LOCAL COMMERCE NETWORK</small></div></div><div className="auth-story-copy"><span className="pill orange-pill"><Zap size={13}/> DAKAR, SENEGAL</span><h1>Local trade.<br/>On your terms.</h1><p>Discover nearby merchants, compare transparent offers, and stay in control at every step.</p><div className="auth-points"><span><BadgeCheck size={16}/> Merchant-backed listings</span><span><Shield size={16}/> Human-approved payments</span><span><Radio size={16}/> Open commerce foundations</span></div></div><div className="auth-story-foot">ACTIVE PAYMENT MODE: {paymentMode.toUpperCase()}</div></section><section className="auth-form-side"><form className="auth-form panel" onSubmit={submit}><span className="eyebrow">YOUR LOCAL MARKETPLACE · {paymentMode.toUpperCase()} MODE</span><h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2><p className="auth-subtitle">{mode === 'login' ? 'Sign in to continue to SatoshiBazaar.' : 'Join the local commerce network.'}</p>{error && <div className="notice auth-error" role="alert"><CircleHelp size={16}/><span>{error}</span></div>}{mode === 'register' && <><div className="role-switch" aria-label="Account type"><button type="button" className={role === 'CUSTOMER' ? 'selected' : ''} onClick={() => setRole('CUSTOMER')}>Customer</button><button type="button" className={role === 'MERCHANT' ? 'selected' : ''} onClick={() => setRole('MERCHANT')}>Merchant</button></div><label className="field-label">Username<input autoComplete="username" minLength="3" maxLength="40" required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your display name"/></label></>}<label className="field-label">Email address<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"/></label><label className="field-label">Password<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 10 : 1} maxLength="72" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder={mode === 'register' ? 'At least 10 characters' : 'Your password'}/></label>{mode === 'register' && <p className="password-hint">Use at least 10 characters. Passwords are hashed before storage.</p>}<button className="button primary wide-button" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <ChevronRight size={15}/></button><div className="auth-switch">{mode === 'login' ? 'New to SatoshiBazaar?' : 'Already have an account?'} <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></div><div className="auth-demo-note"><Shield size={14}/> {paymentMode === 'demo' ? 'Demo purchases are simulated and never transfer Bitcoin.' : `${paymentMode.toUpperCase()} payments require matching LNbits credentials and verified provider status.`}</div></form></section></main>
}

function MerchantNostrPanel({ onNotice, onRefresh }) {
  const [merchant, setMerchant] = useState(null)
  const [products, setProducts] = useState([])
  const [busyId, setBusyId] = useState(null)
  useEffect(() => {
    getMyMerchant().then(async ({ data }) => {
      setMerchant(data)
      if (data) setProducts((await getProducts(data.id)).data)
    }).catch(() => onNotice('Could not load this merchant profile.'))
  }, [])
  const publish = async (productId) => {
    setBusyId(productId)
    try {
      if (!window.nostr?.getPublicKey || !window.nostr?.signEvent) throw new Error('Install a NIP-07 signing extension such as Alby or nos2x.')
      const unsigned = (await getUnsignedNostrListing(productId)).data
      const pubkey = await window.nostr.getPublicKey()
      const signed = await window.nostr.signEvent({ ...unsigned, pubkey })
      const response = (await publishNostrListing(productId, signed)).data
      onNotice(response.published ? 'A configured Nostr relay acknowledged the listing.' : 'No relay acknowledged this listing.')
      const productsResponse = await getProducts(merchant.id)
      setProducts(productsResponse.data)
      onRefresh()
    } catch (error) {
      const detail = error.response?.data?.detail
      onNotice(typeof detail === 'string' ? detail : error.message || 'Nostr publication failed.')
    } finally { setBusyId(null) }
  }
  return <section className="panel table-panel nostr-publish-panel"><div className="section-title"><div><h3>Nostr product publishing</h3><p>Events are signed by your NIP-07 browser extension. The backend stores no private key.</p></div><Radio size={18}/></div>{!merchant ? <Empty text="Create your merchant profile before publishing Nostr listings."/> : products.length ? products.map((product) => <div className="activity-row" key={product.id}><span className="activity-icon"><Package size={15}/></span><div><b>{product.name}</b><small>{money(product.price_sats)} · {product.quantity_available} available</small></div>{product.nostr_event_id ? <span className="status-pill status-ok">RELAY LISTING</span> : <button className="button outline-button" disabled={busyId === product.id} onClick={() => publish(product.id)}>{busyId === product.id ? 'Signing…' : 'Sign & publish'}</button>}</div>) : <Empty text="Add a product to publish a listing."/>}</section>
}

function MerchantSettlementPanel({ rows, onRefresh, onNotice }) {
  const [invoices, setInvoices] = useState({})
  const [busyId, setBusyId] = useState(null)
  const relevant = rows.filter((row) => ['PAYMENT_CONFIRMED', 'SETTLEMENT_PENDING', 'SETTLEMENT_REVIEW_REQUIRED', 'SETTLEMENT_FAILED'].includes(row.status))
  const submit = async (event, row) => {
    event.preventDefault(); setBusyId(row.id)
    try {
      const result = (await submitMerchantSettlement(row.id, invoices[row.id] || '')).data
      onNotice(`Merchant payout ${result.status.toLowerCase()} on ${result.network}.`)
      await onRefresh()
    } catch (error) {
      onNotice(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Settlement request could not be completed.')
    } finally { setBusyId(null) }
  }
  const verify = async (row) => {
    setBusyId(row.id)
    try {
      const result = (await getMerchantSettlement(row.id)).data
      onNotice(`Merchant payout status: ${result.status} (${result.payment_mode}/${result.network}).`)
      await onRefresh()
    } catch { onNotice('Could not verify the merchant payout with its configured LNbits provider.') }
    finally { setBusyId(null) }
  }
  return <section className="panel table-panel"><div className="section-title"><div><h3>Merchant Lightning settlement</h3><p>Enter an invoice for the exact sale total. The backend checks its amount and network before paying.</p></div><span className="soft-badge">ADMIN KEY SERVER ONLY</span></div>{relevant.length ? relevant.map((row) => <form className="activity-row" key={row.id} onSubmit={(event) => submit(event, row)}><div className="activity-icon"><Zap size={16}/></div><div><b>{row.merchant_name} · {money(row.amount_sats)}</b><small>{row.status} · {String(row.mode).toUpperCase()} · {row.tx_ref}</small></div>{row.status === 'PAYMENT_CONFIRMED' ? <><input aria-label={`Merchant invoice for ${row.tx_ref}`} required minLength="30" maxLength="2000" placeholder="Merchant BOLT11 invoice" value={invoices[row.id] || ''} onChange={(event) => setInvoices((current) => ({ ...current, [row.id]: event.target.value }))}/><button className="button primary" disabled={busyId === row.id || row.mode === 'demo'}>Pay merchant</button></> : row.status === 'SETTLEMENT_PENDING' ? <button type="button" className="button outline-button" disabled={busyId === row.id} onClick={() => verify(row)}>Verify payout</button> : <span className="status-pill status-warn">REVIEW REQUIRED</span>}</form>) : <Empty text="Provider-verified buyer payments awaiting merchant payout will appear here."/>}</section>
}

const descriptions = { Marketplace: 'Browse local products and compare clear, merchant-backed prices.', 'Agent Arena': 'See the specialists and inspect activity from persisted sessions.', Negotiation: 'Request an offer and review every step before you approve.', 'Lightning Wallet': 'Review invoices, payment modes and transaction activity.', 'Merchant Portal': 'Manage a local demo profile and publish marketplace inventory.', Transactions: 'A clear record of marketplace payment activity.', 'Security Center': 'See how transaction checks protect customer approval and payment integrity.' }
function ServiceRow({ icon: Icon, name, status, good }) { return <div className="service-row"><span className="service-icon"><Icon size={16}/></span><span>{name}</span><small><i className={`service-dot ${good ? 'good' : ''}`}/>{status}</small></div> }
function TransactionsTable({ rows, full = false }) { return rows.length ? <div className="table-scroll"><table><thead><tr><th>REFERENCE</th><th>MERCHANT / PRODUCT</th><th>AMOUNT</th><th>MODE</th><th>STATUS</th><th>DATE</th></tr></thead><tbody>{rows.map((x) => <tr key={x.id || x.tx_ref}><td><span className="mono ref-code">{x.tx_ref}</span></td><td><b>{x.merchant_name}</b><small className="table-sub">{x.product_name}</small></td><td className="amount-cell">{money(x.amount_sats)}</td><td><span className="mode-tag">{String(x.mode || 'demo').toUpperCase()}</span></td><td><span className={`status-pill ${x.status === 'COMPLETED' ? 'status-ok' : 'status-pending'}`}>{x.status}</span></td><td>{formatDate(x.created_at)}</td></tr>)}</tbody></table></div> : <Empty text="No transaction records yet."/> }
function Empty({ text }) { return <div className="empty-state"><div className="empty-icon"><Boxes size={20}/></div><span>{text}</span></div> }
function Field({ label, value, onChange, type = 'text', ...props }) { return <label className="field-label">{label}<input type={type} value={value} onChange={(e) => onChange(e.target.value)} {...props}/></label> }
function AgentIcon({ index }) { const list = [ShoppingBasket, Compass, Store, MessageSquareText, Shield]; const Icon = list[index]; return <Icon size={18}/> }
function prettyAgent(s) { return (s || '').split('_').map((x) => x[0]?.toUpperCase() + x.slice(1)).join(' ') }
function authErrorMessage(error, mode) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((issue) => {
      const field = issue.loc?.at(-1)
      if (field === 'email') return 'Enter a valid email address.'
      if (field === 'username') return 'Username must be 3–40 characters.'
      if (field === 'password' && issue.type?.includes('too_short')) return 'Password must be at least 10 characters.'
      if (field === 'password' && issue.type?.includes('too_long')) return 'Password must be 72 characters or fewer.'
      if (field === 'password') return issue.msg || 'Check the password and try again.'
      return issue.msg || 'Check the form fields and try again.'
    }).join(' ')
  }
  const status = error.response?.status
  if (status === 401) return mode === 'login' ? 'Email or password is incorrect.' : 'Could not authenticate this account.'
  if (status === 409) return 'That email or username is already registered. Sign in or choose another.'
  if (status === 429) return 'Too many attempts. Wait a minute, then try again.'
  if (!error.response) return 'Could not reach the API. Make sure the backend is running, then reload this page.'
  return `The server could not complete the request (HTTP ${status || 'error'}). Please try again.`
}
function formatDate(value) { if (!value) return '—'; const d = new Date(value); return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
function productEmoji(name = '') { const n = name.toLowerCase(); if (n.includes('rice')) return '🌾'; if (n.includes('tomato')) return '🍅'; if (n.includes('sugar')) return '🍯'; if (n.includes('millet')) return '🌿'; return '🧺' }
export default App
