import { useMemo, type ReactNode } from "react"
import Markdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import rehypeSanitize, { defaultSchema } from "rehype-sanitize"
import type { ExternalDocEnrichment } from "@/types/api"

const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br",
    "ul", "ol", "li",
    "strong", "em", "code", "pre", "blockquote", "a",
    "table", "thead", "tbody", "tr", "th", "td",
  ],
  attributes: {
    ...defaultSchema.attributes,
    a: ["href", "title", "target", "rel"],
    th: ["rowSpan", "colSpan"],
    td: ["rowSpan", "colSpan"],
  },
}

const REHYPE_PLUGINS = [rehypeRaw, [rehypeSanitize, SANITIZE_SCHEMA]] as const

const TYPE_BADGE_COLORS: Record<string, string> = {
  STRING: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  NUMBER: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  INTEGER: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  LONG: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  DECIMAL: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  FLOAT: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  DOUBLE: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  BOOLEAN: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  OBJECT: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  ARRAY: "bg-violet-100 text-violet-800 dark:bg-violet-950/60 dark:text-violet-300",
  "ARRAY OF OBJECT": "bg-violet-100 text-violet-800 dark:bg-violet-950/60 dark:text-violet-300",
  TIMESTAMP: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300",
  DATE: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300",
  BYTES: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  UUID: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  NULL: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
}

function extractText(children: ReactNode): string | null {
  if (typeof children === "string") return children
  if (typeof children === "number") return String(children)
  if (Array.isArray(children)) {
    const parts: string[] = []
    for (const c of children) {
      if (typeof c === "string") parts.push(c)
      else if (typeof c === "number") parts.push(String(c))
      else return null
    }
    return parts.join("")
  }
  return null
}

function renderCellContent(children: ReactNode): ReactNode {
  const text = extractText(children)
  if (text === null) return children

  const trimmed = text.trim()
  if (!trimmed) return children

  const badgeClass = TYPE_BADGE_COLORS[trimmed.toUpperCase()]
  if (badgeClass) {
    return (
      <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold font-mono uppercase tracking-wide ${badgeClass}`}>
        {trimmed}
      </span>
    )
  }

  const commentIdx = text.search(/\/\/\s/)
  if (commentIdx > 0) {
    const code = text.slice(0, commentIdx).trimEnd()
    const comment = text.slice(commentIdx)
    const looksLikeCode = /[=._]/.test(code) && code.length < 120
    return (
      <>
        <span className={looksLikeCode ? "font-mono text-xs" : undefined}>{code}</span>
        {" "}
        <span className="text-muted-foreground italic">{comment}</span>
      </>
    )
  }

  if (/^[a-zA-Z_][\w.]*\s*=/.test(trimmed) || /^[a-z_][a-z0-9_.]{2,}$/i.test(trimmed)) {
    return <span className="font-mono text-xs">{text}</span>
  }

  return children
}

const MARKDOWN_COMPONENTS = {
  table: ({ children }: { children?: ReactNode }) => (
    <div className="my-4 overflow-x-auto rounded-lg border border-border/60">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => (
    <thead className="bg-muted/60">{children}</thead>
  ),
  tbody: ({ children }: { children?: ReactNode }) => (
    <tbody className="[&>tr:nth-child(even)]:bg-muted/20">{children}</tbody>
  ),
  tr: ({ children }: { children?: ReactNode }) => (
    <tr className="border-b border-border/40 last:border-b-0">{children}</tr>
  ),
  th: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <th
      {...props}
      className="border-r border-border/40 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide last:border-r-0 align-top"
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <td
      {...props}
      className="border-r border-border/40 px-3 py-2 align-top last:border-r-0 whitespace-pre-wrap break-words"
    >
      {renderCellContent(children)}
    </td>
  ),
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mt-6 mb-3 text-2xl font-bold">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mt-5 mb-2 text-xl font-semibold">{children}</h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mt-4 mb-2 text-lg font-semibold">{children}</h3>
  ),
  h4: ({ children }: { children?: ReactNode }) => (
    <h4 className="mt-3 mb-1 text-base font-semibold">{children}</h4>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="my-2 leading-relaxed">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => <li className="leading-relaxed">{children}</li>,
  code: ({ children }: { children?: ReactNode }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{children}</code>
  ),
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="my-3 overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">{children}</pre>
  ),
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-3 border-l-2 border-border/60 pl-4 text-muted-foreground">
      {children}
    </blockquote>
  ),
  a: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 hover:no-underline"
    >
      {children}
    </a>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => <em className="italic">{children}</em>,
}

export function ExternalDocView({ data }: { data: ExternalDocEnrichment }) {
  const content = useMemo(() => data.content_html?.trim() ?? "", [data.content_html])

  if (!content) {
    return (
      <div className="rounded-xl border border-dashed px-4 py-10 text-center">
        <p className="text-sm font-medium">Содержимое документа пусто</p>
        <p className="mt-2 text-xs text-muted-foreground">
          Обогащение прошло, но HTML-контент не извлёкся. Попробуйте загрузить PDF заново.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {data.description && (
        <p className="text-sm text-muted-foreground">{data.description}</p>
      )}
      <div className="rounded-xl border border-border/70 bg-background p-4">
        <Markdown rehypePlugins={REHYPE_PLUGINS as never} components={MARKDOWN_COMPONENTS as never}>
          {content}
        </Markdown>
      </div>
    </div>
  )
}
