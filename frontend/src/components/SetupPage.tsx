import { useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { saveApiKey, startBackend } from "@/api/desktop"

interface Props {
  onReady: () => void
  initialError?: string | null
}

export function SetupPage({ onReady, initialError }: Props) {
  const [apiKey, setApiKey] = useState("")
  const [error, setError] = useState<string | null>(initialError ?? null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    const trimmed = apiKey.trim()
    if (!trimmed) {
      setError("Введите API-ключ")
      return
    }
    if (!trimmed.startsWith("sk-ant-")) {
      setError("Ключ должен начинаться с sk-ant-")
      return
    }

    setSaving(true)
    try {
      await saveApiKey(trimmed)
      await startBackend()
      onReady()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-8">
      <div className="w-full max-w-md space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Настройка Extract Agent</h1>
          <p className="text-sm text-muted-foreground">
            Введите Anthropic API-ключ. Он сохранится в системном Keychain и не покинет ваш компьютер.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="api-key" className="text-sm font-medium">
              ANTHROPIC_API_KEY
            </label>
            <Input
              id="api-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-ant-..."
              autoFocus
              autoComplete="off"
              spellCheck={false}
              disabled={saving}
            />
          </div>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Сохранение..." : "Сохранить и запустить"}
          </Button>
        </form>

        <p className="text-center text-xs text-muted-foreground">
          Получить ключ:{" "}
          <a
            href="https://console.anthropic.com/settings/keys"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-foreground"
          >
            console.anthropic.com/settings/keys
          </a>
        </p>
      </div>
    </div>
  )
}
