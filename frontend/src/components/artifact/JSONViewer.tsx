import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"

interface JSONViewerProps {
  value: Record<string, unknown>
}

export function JSONViewer({ value }: JSONViewerProps) {
  return (
    <CodeMirror
      value={JSON.stringify(value, null, 2)}
      extensions={[json()]}
      readOnly
      height="auto"
      maxHeight="31.25rem"
      theme="light"
      className="border rounded-md overflow-hidden"
    />
  )
}
