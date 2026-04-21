import Markdown from "react-markdown"
import type { PluggableList } from "unified"

interface MarkdownViewerProps {
  content: string
  remarkPlugins?: PluggableList
  className?: string
}

export function MarkdownViewer({ content, remarkPlugins, className }: MarkdownViewerProps) {
  return (
    <article className={className ?? "prose prose-sm max-w-none dark:prose-invert"}>
      <Markdown remarkPlugins={remarkPlugins}>{content}</Markdown>
    </article>
  )
}
