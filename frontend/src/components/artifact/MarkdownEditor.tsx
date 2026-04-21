import { useState } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { markdown } from "@codemirror/lang-markdown"
import Markdown from "react-markdown"
import { Button } from "@/components/ui/button"

interface MarkdownEditorProps {
  value: string
  onSave: (updated: string) => void
  onCancel: () => void
  isSaving?: boolean
}

export function MarkdownEditor({ value, onSave, onCancel, isSaving }: MarkdownEditorProps) {
  const [raw, setRaw] = useState(value)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-4 border rounded-md overflow-hidden">
        <CodeMirror
          value={raw}
          extensions={[markdown()]}
          onChange={setRaw}
          height="31.25rem"
          theme="light"
        />
        <article className="prose prose-sm max-w-none p-4 overflow-y-auto h-[31.25rem] border-l">
          <Markdown>{raw}</Markdown>
        </article>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={isSaving}>
          Отмена
        </Button>
        <Button size="sm" onClick={() => onSave(raw)} disabled={isSaving}>
          {isSaving ? "Сохраняем..." : "Сохранить"}
        </Button>
      </div>
    </div>
  )
}
