// Parser for LLM-generated curl artifacts: turns the shell command into a
// structured request the UI can render swagger-style and replay on the stand.

export interface CurlParam {
  name: string
  value: string
}

export interface ParsedCurl {
  method: string
  url: string
  /** path + query string, relative to the artifact's host */
  path: string
  query: CurlParam[]
  headers: CurlParam[]
  body: string | null
}

/** Split a shell command into tokens, honoring quotes and line continuations. */
function tokenize(command: string): string[] | null {
  const tokens: string[] = []
  let current = ""
  let hasCurrent = false
  let i = 0
  const n = command.length

  while (i < n) {
    const ch = command[i]

    if (ch === "\\") {
      // Backslash-newline is a line continuation; otherwise it escapes the next char
      if (command[i + 1] === "\n" || command.slice(i + 1, i + 3) === "\r\n") {
        i += command[i + 1] === "\r" ? 3 : 2
        continue
      }
      if (i + 1 < n) {
        current += command[i + 1]
        hasCurrent = true
        i += 2
        continue
      }
      i += 1
      continue
    }

    if (ch === "'") {
      const end = command.indexOf("'", i + 1)
      if (end === -1) return null
      current += command.slice(i + 1, end)
      hasCurrent = true
      i = end + 1
      continue
    }

    if (ch === '"') {
      let j = i + 1
      while (j < n) {
        if (command[j] === "\\" && j + 1 < n) {
          current += command[j + 1]
          j += 2
          continue
        }
        if (command[j] === '"') break
        current += command[j]
        j += 1
      }
      if (j >= n) return null
      hasCurrent = true
      i = j + 1
      continue
    }

    if (/\s/.test(ch)) {
      if (hasCurrent) {
        tokens.push(current)
        current = ""
        hasCurrent = false
      }
      i += 1
      continue
    }

    current += ch
    hasCurrent = true
    i += 1
  }

  if (hasCurrent) tokens.push(current)
  return tokens
}

const DATA_FLAGS = new Set(["-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--json"])
// Flags that consume a value we don't render — skip them together with the value
const SKIP_WITH_VALUE = new Set([
  "-o", "--output", "-w", "--write-out", "-m", "--max-time", "--connect-timeout",
  "-u", "--user", "-F", "--form", "-c", "--cookie-jar", "--retry", "--cacert", "--capath",
])

export function parseCurl(command: string): ParsedCurl | null {
  const tokens = tokenize(command.trim())
  if (!tokens || tokens.length === 0 || !tokens[0].startsWith("curl")) return null

  let method: string | null = null
  let rawUrl: string | null = null
  let body: string | null = null
  const headers: CurlParam[] = []

  let i = 1
  while (i < tokens.length) {
    const token = tokens[i]

    if (token === "-X" || token === "--request") {
      method = (tokens[i + 1] ?? "").toUpperCase()
      i += 2
      continue
    }
    if (token === "-H" || token === "--header") {
      const raw = tokens[i + 1] ?? ""
      const sep = raw.indexOf(":")
      if (sep > 0) {
        headers.push({ name: raw.slice(0, sep).trim(), value: raw.slice(sep + 1).trim() })
      }
      i += 2
      continue
    }
    if (DATA_FLAGS.has(token)) {
      body = tokens[i + 1] ?? ""
      if (token === "--json") {
        headers.push({ name: "Content-Type", value: "application/json" })
      }
      i += 2
      continue
    }
    if (token === "-b" || token === "--cookie") {
      headers.push({ name: "Cookie", value: tokens[i + 1] ?? "" })
      i += 2
      continue
    }
    if (token === "-A" || token === "--user-agent") {
      headers.push({ name: "User-Agent", value: tokens[i + 1] ?? "" })
      i += 2
      continue
    }
    if (token === "--url") {
      rawUrl = tokens[i + 1] ?? null
      i += 2
      continue
    }
    if (SKIP_WITH_VALUE.has(token)) {
      i += 2
      continue
    }
    if (token.startsWith("-")) {
      // Boolean flag we don't care about (-s, -k, -v, --compressed, …)
      i += 1
      continue
    }
    if (rawUrl === null) rawUrl = token
    i += 1
  }

  if (!rawUrl) return null

  let url: URL
  try {
    url = new URL(rawUrl.includes("://") ? rawUrl : `http://${rawUrl}`)
  } catch {
    return null
  }

  const query: CurlParam[] = []
  url.searchParams.forEach((value, name) => query.push({ name, value }))

  return {
    method: method ?? (body !== null ? "POST" : "GET"),
    url: url.toString(),
    path: url.pathname + url.search,
    query,
    headers,
    body,
  }
}
