export type DiffLine =
  | { type: "same" | "add" | "del"; text: string }
  | { type: "skip"; count: number }

const MAX_LINES = 400

/** Line diff (LCS) with unchanged runs collapsed to `context` lines around each change. */
export function diffLines(before: string, after: string, context = 1): DiffLine[] {
  const a = before ? before.split("\n") : []
  const b = after ? after.split("\n") : []
  if (a.length > MAX_LINES || b.length > MAX_LINES) {
    return [...a.map((text) => ({ type: "del" as const, text })), ...b.map((text) => ({ type: "add" as const, text }))]
  }

  // lcs[i][j] = length of the longest common subsequence of a[i..] and b[j..]
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const full: { type: "same" | "add" | "del"; text: string }[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      full.push({ type: "same", text: a[i] })
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      full.push({ type: "del", text: a[i++] })
    } else {
      full.push({ type: "add", text: b[j++] })
    }
  }
  while (i < a.length) full.push({ type: "del", text: a[i++] })
  while (j < b.length) full.push({ type: "add", text: b[j++] })

  const keep = full.map((line) => line.type !== "same")
  full.forEach((line, index) => {
    if (line.type === "same") return
    for (let k = Math.max(0, index - context); k <= Math.min(full.length - 1, index + context); k++) keep[k] = true
  })

  const result: DiffLine[] = []
  let skipped = 0
  full.forEach((line, index) => {
    if (keep[index]) {
      if (skipped > 0) result.push({ type: "skip", count: skipped })
      skipped = 0
      result.push(line)
    } else {
      skipped++
    }
  })
  if (skipped > 0) result.push({ type: "skip", count: skipped })
  return result
}
