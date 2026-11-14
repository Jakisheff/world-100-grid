// One-call protocol compliance smoke: the exact recorded failing condition
// (round-one market, menu=[pass]) replayed against a candidate endpoint.
import { readFileSync } from 'node:fs'
const [url, model] = process.argv.slice(2)
const { model_menu: menu, messages } = JSON.parse(readFileSync('/tmp/smoke-messages.json', 'utf8'))
const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ model, messages, temperature: 0, max_tokens: 256, chat_template_kwargs: { enable_thinking: false } }) })
const body = await response.json()
const content = body.choices?.[0]?.message?.content
let action = null
try { action = JSON.parse(content) } catch {}
const exact = JSON.stringify(action) === JSON.stringify(menu[0])
console.log(JSON.stringify({ model, http: response.status, content: String(content).slice(0, 120),
  exact_menu_object: exact, verdict: exact ? 'PASS' : 'FAIL' }))
