import { useState, useCallback } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"
import { Button } from "@/components/ui/button"

interface JSONEditorProps {
  value: Record<string, unknown>
  onSave: (updated: Record<string, unknown>) => void
  onCancel: () => void
  isSaving?: boolean
}

export function JSONEditor({ value, onSave, onCancel, isSaving }: JSONEditorProps) {
  const [raw, setRaw] = useState(() => JSON.stringify(value, null, 2))
  const [parseError, setParseError] = useState<string | null>(null)

  const handleChange = useCallback((val: string) => {
    setRaw(val)
    try {
      JSON.parse(val)
      setParseError(null)
    } catch (e) {
      setParseError((e as Error).message)
    }
  }, [])

  const handleSave = () => {
    try {
      const parsed = JSON.parse(raw)
      setParseError(null)
      onSave(parsed)
    } catch (e) {
      setParseError((e as Error).message)
    }
  }

  return (
    <div className="space-y-2">
      <CodeMirror
        value={raw}
        extensions={[json()]}
        onChange={handleChange}
        height="500px"
        theme="light"
        className="border rounded-md overflow-hidden"
      />
      {parseError && (
        <p className="text-xs text-destructive">JSON error: {parseError}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={isSaving}>
          Cancel
        </Button>
        <Button size="sm" onClick={handleSave} disabled={!!parseError || isSaving}>
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </div>
    </div>
  )
}
