import Markdown from "react-markdown"

interface MarkdownViewerProps {
  content: string
}

export function MarkdownViewer({ content }: MarkdownViewerProps) {
  return (
    <article className="prose prose-sm max-w-none dark:prose-invert">
      <Markdown>{content}</Markdown>
    </article>
  )
}
