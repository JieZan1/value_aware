import { useEffect, useMemo, useState } from 'react'
import products from './data/products.json'
import reviews from './data/reviews.json'
import tunnel from './data/tunnel.json'
import visual from './data/visual.json'
import ShoeImage from './components/ShoeImage.jsx'

// ?sim=1   virtual-shopper mode: hide wind-tunnel output (it would leak hints), show photo cues as text
// ?v=tunnel open pages in their "After wind tunnel" version (used to re-test the fixes)
const params = new URLSearchParams(window.location.search)
const SIM = params.has('sim')
const START_VERSION = params.get('v') === 'tunnel' ? 'tunnel' : 'original'

// What the photo shows, as labels: this is how virtual shoppers "see" the picture.
// reshot: the "After wind tunnel" page, once staff have shot the fixer's natural-light photos.
function PhotoCues({ id, reshot = false }) {
  const v = visual[id]
  if (!SIM || !v) return null
  const colour = reshot ? v.colour_natural_light : v.colour_as_seen
  return <div className="photo-cues">Photo shows{reshot ? ' (natural light)' : ''}: {[v.texture, v.shape, colour, v.style].join(' · ')}</div>
}

// Real photo (free-licence Unsplash) with the drawn illustration as a fallback if it can't load.
function Photo({ p, index = 0, w = 900, colour }) {
  const [failed, setFailed] = useState(false)
  const src = p.images && p.images[index]
  if (!src || failed) return <ShoeImage category={p.category} hex={(colour || p.colours[0]).hex} heelCm={p.details.heelCm} label={p.name} />
  return <img className="photo" src={`${src}?auto=format&fit=crop&w=${w}&h=${w}&q=75`} alt={`${p.name} ${p.type}`} loading="lazy" onError={() => setFailed(true)} />
}

// ---------- tiny hash router: #/   #/search?q=...   #/product/<id>
function useRoute() {
  const [hash, setHash] = useState(window.location.hash || '#/')
  useEffect(() => {
    const onChange = () => { setHash(window.location.hash || '#/'); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const m = hash.match(/^#\/product\/(.+)$/)
  if (m) return { page: 'product', id: m[1] }
  const s = hash.match(/^#\/search(?:\?q=(.*))?$/)
  if (s) return { page: 'search', q: decodeURIComponent(s[1] || '') }
  return { page: 'home' }
}

const money = (n) => `$${n.toFixed(2)}`
const goSearch = (q) => { window.location.hash = `#/search?q=${encodeURIComponent(q.trim())}` }
const FEATURED = ['rosewood', 'elliette', 'braxtonn', 'clementinne', 'lagoon']
const labelList = (p) => (p.labels ? [p.labels.material, p.labels.gender, p.labels.height, p.labels.season] : [])

// every word typed must appear somewhere in the product's text
function matches(p, q) {
  const text = [p.name, p.type, p.category, p.description, p.details.material, p.details.toe, p.details.closure,
    ...p.colours.map((c) => c.name), ...labelList(p), p.isNew ? 'new' : ''].join(' ').toLowerCase()
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => text.includes(w.replace(/s$/, '')))
}
const pct = (x) => `${Math.round(x * 100)}%`

export default function App() {
  const route = useRoute()
  const [cart, setCart] = useState([])
  const [cartOpen, setCartOpen] = useState(false)
  // "original" = page as first written; "tunnel" = page after the wind-tunnel fixes
  const [version, setVersion] = useState(START_VERSION)

  const addToCart = (item) => { setCart((c) => [...c, item]); setCartOpen(true) }
  const removeFromCart = (i) => setCart((c) => c.filter((_, k) => k !== i))

  return (
    <div className="app">
      <Header cartCount={cart.length} onCart={() => setCartOpen(true)} version={version} setVersion={setVersion} />
      <main>
        {route.page === 'home' && <Home />}
        {route.page === 'search' && <SearchPage q={route.q} />}
        {route.page === 'product' && <ProductPage id={route.id} version={version} onAdd={addToCart} />}
      </main>
      {!SIM && <footer className="footer">Prototype store for the BSRM × ALDO Retail Gen AI Hackathon 2026. Photos from Unsplash (free licence) show similar shoes; colours and descriptions are synthetic.</footer>}
      {cartOpen && <CartDrawer cart={cart} onClose={() => setCartOpen(false)} onRemove={removeFromCart} />}
    </div>
  )
}

function Header({ cartCount, onCart, version, setVersion }) {
  return (
    <header className="header">
      <a href="#/" className="logo">SOLE<span>·</span>STUDIO</a>
      <SearchBox />
      <div className="header-right">
        {!SIM && (
          <div className="toggle" title="Switch between the original product page and the page after the wind-tunnel fixes">
            <button className={version === 'original' ? 'on' : ''} onClick={() => setVersion('original')}>Original page</button>
            <button className={version === 'tunnel' ? 'on' : ''} onClick={() => setVersion('tunnel')}>After wind tunnel</button>
          </div>
        )}
        <button className="cart-btn" onClick={onCart}>Bag ({cartCount})</button>
      </div>
    </header>
  )
}

function SearchBox({ initial = '', big = false }) {
  const [q, setQ] = useState(initial)
  useEffect(() => setQ(initial), [initial])
  return (
    <form className={big ? 'search big' : 'search'} onSubmit={(e) => { e.preventDefault(); goSearch(q) }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search shoes, e.g. black boots, loafer, suede" aria-label="Search" />
      <button type="submit">Search</button>
    </form>
  )
}

function Home() {
  const featured = FEATURED.map((id) => products.find((p) => p.id === id)).filter(Boolean)
  const chips = ['Boots', 'Ankle boot', 'Loafer', 'Sandal', 'Heel', 'Black', 'Suede', 'New']
  return (
    <section className="container">
      <div className="hero">
        <h1>Autumn edit</h1>
        <p>Boots, shoes and sandals. Free returns in store.</p>
      </div>
      <h2 className="section-title">Featured</h2>
      <div className="grid five">
        {featured.map((p) => <ProductCard key={p.id} p={p} />)}
      </div>
      <div className="more">
        <h2>Looking for something else?</h2>
        <p>Search all {products.length} styles.</p>
        <SearchBox big />
        <div className="chips">
          {chips.map((c) => <button key={c} onClick={() => goSearch(c)}>{c}</button>)}
          <button onClick={() => goSearch('')}>See all</button>
        </div>
      </div>
    </section>
  )
}

function SearchPage({ q }) {
  const [cat, setCat] = useState('All')
  const cats = ['All', 'Boots', 'Shoes', 'Sandals']
  const list = useMemo(() => products.filter((p) => matches(p, q) && (cat === 'All' || p.category === cat)), [q, cat])
  return (
    <section className="container">
      <div className="hero">
        <h1>{q ? `Results for "${q}"` : 'All shoes'}</h1>
        <SearchBox initial={q} big />
      </div>
      <div className="tabs">
        {cats.map((c) => (
          <button key={c} className={c === cat ? 'tab on' : 'tab'} onClick={() => setCat(c)}>{c}</button>
        ))}
        <span className="count">{list.length} {list.length === 1 ? 'style' : 'styles'}</span>
      </div>
      {list.length === 0
        ? <p className="muted empty">No shoes match "{q}". Try "boots", "loafer" or "black". <a href="#/search?q=">See all shoes</a></p>
        : <div className="grid">{list.map((p) => <ProductCard key={p.id} p={p} />)}</div>}
    </section>
  )
}

function ProductCard({ p }) {
  return (
    <a className="card" href={`#/product/${p.id}`}>
      <div className="card-img">
        <Photo p={p} w={600} />
        {(p.isNew || visual[p.id]?.popularity) && <span className="badge">{p.isNew ? 'New' : visual[p.id].popularity}</span>}
      </div>
      <PhotoCues id={p.id} />
      <div className="card-body">
        <div className="card-name">{p.name}</div>
        <div className="card-type">{p.type}</div>
        <div className="card-labels">{labelList(p).join(' · ')}</div>
        <div className="card-row">
          <span className="price">{SIM ? '' : money(p.price)}</span>
          <span className="dots">{p.colours.map((c) => <i key={c.name} style={{ background: c.hex }} title={c.name} />)}</span>
        </div>
      </div>
    </a>
  )
}

function ProductPage({ id, version, onAdd }) {
  const p = products.find((x) => x.id === id)
  const [colour, setColour] = useState(p ? p.colours[0] : null)
  const [size, setSize] = useState(null)
  const [view, setView] = useState(0)
  const [msg, setMsg] = useState('')
  useEffect(() => { if (p) { setColour(p.colours[0]); setSize(null); setView(0); setMsg('') } }, [id])
  if (!p) return <section className="container"><p>Product not found. <a href="#/">Back to all shoes</a></p></section>

  const t = tunnel[p.id]
  const after = version === 'tunnel' && t
  const views = (p.images && p.images.length ? p.images : [null]).map((_, i) => i)

  const add = () => {
    if (!size) { setMsg('Please choose a size.'); return }
    onAdd({ id: p.id, name: p.name, price: p.price, colour: colour.name, size })
    setMsg('')
  }

  return (
    <section className="container product">
      <a href="#/" className="back" onClick={(e) => { if (window.history.length > 1) { e.preventDefault(); window.history.back() } }}>← Back</a>
      <div className="product-grid">
        <div className="gallery">
          <div className="main-img"><Photo p={p} index={view} w={1100} colour={colour} /></div>
          <PhotoCues id={p.id} reshot={!!(after && t.photoStatus)} />
          <div className="thumbs">
            {views.map((v) => (
              <button key={v} className={v === view ? 'thumb on' : 'thumb'} onClick={() => setView(v)}>
                <Photo p={p} index={v} w={200} colour={colour} />
              </button>
            ))}
            {after && t.photoStatus && !SIM && (
              <div className="thumb pending" title={t.photoStatus}>Natural-light photos coming</div>
            )}
          </div>
        </div>

        <div className="info">
          {(p.isNew || visual[p.id]?.popularity) && <span className="badge inline">{p.isNew ? 'New' : visual[p.id].popularity}</span>}
          <h1>{p.name}</h1>
          <div className="type">{p.type}</div>
          <div className="labels">{labelList(p).map((l) => <span key={l} className="label-chip">{l}</span>)}</div>
          {/* price is out of scope for the returns tunnel, so virtual shoppers don't see it */}
          {!SIM && <div className="price big">{money(p.price)}</div>}

          <div className="label">Colour: <b>{colour.name}</b></div>
          <div className="swatches">
            {p.colours.map((c) => (
              <button key={c.name} className={c.name === colour.name ? 'swatch on' : 'swatch'} style={{ background: c.hex }} onClick={() => setColour(c)} title={c.name} />
            ))}
          </div>
          {after && t.colourNote && <div className="note colour"><b>About this colour</b>{t.colourNote}</div>}

          <div className="label">Size</div>
          <div className="sizes">
            {p.sizes.map((s) => (
              <button key={s} className={s === size ? 'size on' : 'size'} onClick={() => setSize(s)}>{s}</button>
            ))}
          </div>
          {after && t.fitNote && <div className="note fit"><b>Fit</b>{t.fitNote}</div>}
          {after && t.comfortNote && <div className="note fit"><b>Comfort</b>{t.comfortNote}</div>}
          {after && t.materialNote && <div className="note colour"><b>Material</b>{t.materialNote}</div>}

          <button className="add" onClick={add}>Add to bag</button>
          {msg && <div className="msg">{msg}</div>}

          <div className="section">
            <h3>Description</h3>
            <p>{p.description}</p>
          </div>
          <div className="section">
            <h3>Details</h3>
            <ul className="details">
              <li><span>Material</span>{p.details.material}</li>
              <li><span>Toe</span>{p.details.toe}</li>
              <li><span>Heel height</span>{p.details.heelCm} cm</li>
              <li><span>Width</span>{after && t.feedFacts?.width === 'narrow' ? 'Narrow' : p.details.width}</li>
              <li><span>Closure</span>{p.details.closure}</li>
              {after && t.feedFacts?.calf_fit && <li><span>Calf</span>{t.feedFacts.calf_fit}</li>}
            </ul>
          </div>
        </div>
      </div>

      {!SIM && <Reviews id={p.id} />}
      {!SIM && t && <TunnelPanel t={t} version={version} />}
    </section>
  )
}

function Reviews({ id }) {
  const list = reviews[id] || []
  return (
    <div className="reviews">
      <h2>Wind-tunnel reviews <span className="sub">from simulated shoppers and AI assistants</span></h2>
      {list.length === 0 && <p className="muted">No simulated reviews yet for this style.</p>}
      <div className="review-grid">
        {list.map((r, i) => (
          <div key={i} className={`review ${r.kind}`}>
            <div className="review-top">
              <span className="persona">{r.kind === 'ai' ? '🤖 ' : ''}{r.persona}</span>
              {r.rating != null && <span className="stars">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>}
            </div>
            <p>"{r.text}"</p>
            <div className="review-meta">
              Size {r.size} · {r.likelyReturn ? <span className="risk">Likely return: {r.reason}</span> : <span className="ok">Likely to keep</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TunnelPanel({ t, version }) {
  const run = version === 'tunnel' ? t.after : t.before
  if (!run) return null // e.g. fixes written but not re-tested yet
  return (
    <div className="tunnel">
      <div>
        <div className="tunnel-label">Wind tunnel · {version === 'tunnel' ? 'after fixes' : 'original page'}</div>
        <div className="tunnel-nums">
          <div><b>{pct(run.rate)}</b> ± {pct(run.range)}<span>predicted returns, shoppers</span></div>
          {run.aiRate != null && <div><b>{pct(run.aiRate)}</b> ± {pct(run.aiRange)}<span>predicted returns, AI buyers</span></div>}
        </div>
      </div>
      {t.illustrative && <div className="tunnel-note">Illustrative numbers until the agents' runs are connected.</div>}
    </div>
  )
}

function CartDrawer({ cart, onClose, onRemove }) {
  const total = cart.reduce((s, x) => s + x.price, 0)
  const [done, setDone] = useState(false)
  return (
    <div className="drawer-wrap" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head"><h2>Your bag</h2><button onClick={onClose}>✕</button></div>
        {cart.length === 0 && <p className="muted">Your bag is empty.</p>}
        {cart.map((x, i) => (
          <div key={i} className="line">
            <div><b>{x.name}</b><div className="muted">{x.colour} · size {x.size}</div></div>
            <div className="line-right">{money(x.price)}<button onClick={() => onRemove(i)}>Remove</button></div>
          </div>
        ))}
        {cart.length > 0 && (
          <>
            <div className="total"><span>Total</span><b>{money(total)}</b></div>
            <button className="add" onClick={() => setDone(true)}>Checkout</button>
            {done && <p className="muted">Demo store: checkout is not connected.</p>}
          </>
        )}
      </aside>
    </div>
  )
}
