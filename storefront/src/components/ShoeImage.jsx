// Simple drawn shoe illustrations (no real product photos in the prototype).
// view: 'side' | 'angle' | 'sole'
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16)
  let r = (n >> 16) + amt, g = ((n >> 8) & 255) + amt, b = (n & 255) + amt
  r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); b = Math.max(0, Math.min(255, b))
  return `rgb(${r},${g},${b})`
}

function Boot({ c, heel }) {
  return (
    <g>
      <path d="M70 40 H130 V150 C130 160 140 168 160 172 L235 186 C250 189 255 200 250 210 H70 Z" fill={c} />
      <path d="M70 40 H130 V60 H70 Z" fill={shade(c, 25)} />
      <rect x="70" y="210" width="182" height="8" rx="3" fill={shade(c, -40)} />
      <rect x="70" y={210} width="34" height={heel} rx="2" fill={shade(c, -50)} />
      <path d="M118 70 V150" stroke={shade(c, 40)} strokeWidth="2" strokeDasharray="4 4" />
    </g>
  )
}

function LowShoe({ c, heel }) {
  return (
    <g>
      <path d="M60 150 C60 125 85 112 115 118 C150 125 185 150 225 165 C250 175 258 195 250 210 H60 Z" fill={c} />
      <path d="M95 120 C115 135 150 140 175 140" stroke={shade(c, 45)} strokeWidth="3" fill="none" />
      <rect x="60" y="210" width="192" height="8" rx="3" fill={shade(c, -40)} />
      {heel > 2 && <rect x="60" y="210" width="26" height={heel} rx="2" fill={shade(c, -50)} />}
    </g>
  )
}

function Sandal({ c, heel }) {
  return (
    <g>
      <path d="M55 205 C80 198 200 196 252 204 L252 214 H55 Z" fill={shade(c, -40)} />
      <path d="M85 205 C95 160 125 150 140 150" stroke={c} strokeWidth="12" fill="none" strokeLinecap="round" />
      <path d="M150 200 C165 165 205 160 225 175" stroke={c} strokeWidth="14" fill="none" strokeLinecap="round" />
      <path d="M180 202 C190 180 215 178 238 192" stroke={c} strokeWidth="10" fill="none" strokeLinecap="round" />
      {heel > 2 && <rect x="58" y="214" width="26" height={heel} rx="2" fill={shade(c, -50)} />}
    </g>
  )
}

export default function ShoeImage({ category, hex = '#1c1c1c', heelCm = 3, view = 'side', label }) {
  const heel = Math.max(4, Math.min(40, heelCm * 5))
  const Shape = category === 'Boots' ? Boot : category === 'Sandals' ? Sandal : LowShoe
  const transform =
    view === 'angle' ? 'translate(300 0) scale(-1 1)' :
    view === 'sole' ? 'translate(10 30) rotate(-8 150 150)' : ''
  return (
    <svg viewBox="0 0 300 280" className="shoe-svg" role="img" aria-label={label || `${category} illustration`}>
      <rect width="300" height="280" fill="#f3f1ee" />
      <ellipse cx="155" cy={222 + heel} rx="110" ry="8" fill="#000" opacity="0.06" />
      <g transform={transform}>
        <Shape c={hex} heel={heel} />
      </g>
    </svg>
  )
}
